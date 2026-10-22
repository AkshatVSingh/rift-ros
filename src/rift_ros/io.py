from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from rift_ros import __version__
from rift_ros.analysis import summarize
from rift_ros.models import Event, Incident
from rift_ros.privacy import sanitize_incident

_CORE_FILES = ("incident.json", "events.jsonl", "summary.json")
_MAX_ARCHIVE_MEMBER_BYTES = 2 * 1024 * 1024 * 1024
_MAX_ARCHIVE_TOTAL_BYTES = 4 * 1024 * 1024 * 1024


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def write_events(path: str | Path, events: list[Event]) -> Path:
    path = Path(path)
    content = "".join(json.dumps(event.to_dict(), sort_keys=True) + "\n" for event in events)
    return _atomic_write(path, content)


def read_events(path: str | Path) -> list[Event]:
    events: list[Event] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                events.append(Event.from_dict(json.loads(line)))
    return events


def _file_manifest(path: Path) -> dict[str, Any]:
    return {"sha256": _sha256(path), "bytes": path.stat().st_size}


def _safe_member_name(name: str) -> bool:
    return bool(name) and Path(name).name == name and name not in {".", ".."}


def write_incident(directory: str | Path, incident: Incident) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    events_path = write_events(directory / "events.jsonl", incident.events)
    incident_path = directory / "incident.json"
    _atomic_write(incident_path, json.dumps(incident.to_dict(), indent=2, sort_keys=True) + "\n")

    summary_path = directory / "summary.json"
    summary = summarize(incident.events)
    _atomic_write(summary_path, json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n")

    bundle = {
        "schema": "rift.bundle/v3",
        "rift_version": __version__,
        "incident_id": incident.incident_id,
        "incident_schema": "rift.incident/v2",
        "created_at": incident.created_at,
        "session_id": incident.metadata.get("session_id"),
        "identity": (incident.metadata.get("identity") if isinstance(incident.metadata.get("identity"), dict) else {}),
        "completed_at": time.time(),
        "event_count": len(incident.events),
        "fingerprint": summary.fingerprint,
        "sanitized": bool(incident.metadata.get("sanitized", False)),
        "files": {
            "incident.json": _file_manifest(incident_path),
            "events.jsonl": _file_manifest(events_path),
            "summary.json": _file_manifest(summary_path),
        },
        "attachments": {},
    }
    # bundle.json is intentionally written last. Its presence means the core
    # payload files were fsync'd and the bundle reached a complete state.
    _atomic_write(directory / "bundle.json", json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    return incident_path


def register_attachment(
    directory: str | Path,
    source: str | Path,
    *,
    name: str | None = None,
    role: str = "attachment",
    media_type: str | None = None,
) -> Path:
    """Add a verified top-level artifact to an existing incident bundle."""

    directory = Path(directory)
    source = Path(source)
    if not source.is_file():
        raise ValueError(f"attachment source is not a file: {source}")
    filename = name or source.name
    if not _safe_member_name(filename) or filename in {"bundle.json", *_CORE_FILES}:
        raise ValueError(f"unsafe or reserved attachment name: {filename!r}")
    bundle_path = directory / "bundle.json"
    if not bundle_path.exists():
        raise ValueError("bundle.json missing; write the incident before registering attachments")

    destination = directory / filename
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle.setdefault("files", {})[filename] = _file_manifest(destination)
    bundle.setdefault("attachments", {})[filename] = {
        "role": role,
        "media_type": media_type or mimetypes.guess_type(filename)[0] or "application/octet-stream",
    }
    bundle["completed_at"] = time.time()
    _atomic_write(bundle_path, json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    return destination


def _manifest_expected(entry: object) -> tuple[str | None, int | None]:
    # v1 stored files as filename -> sha256 string. v2+ stores digest + size.
    if isinstance(entry, str):
        return entry, None
    if isinstance(entry, dict):
        digest = entry.get("sha256")
        size = entry.get("bytes")
        return (str(digest) if digest is not None else None, int(size) if size is not None else None)
    return None, None


def _manifest_file_names(bundle: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for filename in bundle.get("files", {}):
        filename = str(filename)
        if not _safe_member_name(filename):
            raise ValueError(f"unsafe manifest filename: {filename!r}")
        names.append(filename)
    return names


def pack_bundle(path: str | Path, output: str | Path | None = None) -> Path:
    directory = Path(path)
    if directory.is_file():
        directory = directory.parent
    ok, problems = verify_bundle(directory)
    if not ok:
        raise ValueError("cannot pack invalid bundle: " + "; ".join(problems))
    bundle = json.loads((directory / "bundle.json").read_text(encoding="utf-8"))
    filenames = _manifest_file_names(bundle)
    output_path = Path(output) if output is not None else directory.with_suffix(".rift.zip")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            archive.write(directory / "bundle.json", arcname="bundle.json")
            for filename in filenames:
                archive.write(directory / filename, arcname=filename)
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return output_path


def _load_zip_manifest(archive: zipfile.ZipFile) -> tuple[dict[str, Any] | None, list[str]]:
    problems: list[str] = []
    infos = archive.infolist()
    names = [item.filename for item in infos]
    if len(names) != len(set(names)):
        problems.append("archive contains duplicate member names")
    total = 0
    for info in infos:
        if info.is_dir():
            problems.append(f"unexpected directory member: {info.filename}")
            continue
        if not _safe_member_name(info.filename):
            problems.append(f"unsafe archive member path: {info.filename}")
        if info.file_size > _MAX_ARCHIVE_MEMBER_BYTES:
            problems.append(f"{info.filename} exceeds safe uncompressed size limit")
        total += info.file_size
    if total > _MAX_ARCHIVE_TOTAL_BYTES:
        problems.append("archive exceeds safe total uncompressed size limit")
    if "bundle.json" not in names:
        problems.append("bundle.json missing")
        return None, problems
    try:
        bundle = json.loads(archive.read("bundle.json").decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, KeyError) as exc:
        problems.append(f"invalid bundle.json: {exc}")
        return None, problems
    try:
        expected_members = {"bundle.json", *_manifest_file_names(bundle)}
    except ValueError as exc:
        problems.append(str(exc))
        return bundle, problems
    unexpected = sorted(set(names) - expected_members)
    missing = sorted(expected_members - set(names))
    if unexpected:
        problems.append("unexpected archive members: " + ", ".join(unexpected))
    if missing:
        problems.append("missing archive members: " + ", ".join(missing))
    return bundle, problems


def _verify_zip(path: Path) -> tuple[bool, list[str]]:
    problems: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            bundle, initial = _load_zip_manifest(archive)
            problems.extend(initial)
            if bundle is None:
                return False, problems
            for filename, entry in bundle.get("files", {}).items():
                filename = str(filename)
                expected, expected_bytes = _manifest_expected(entry)
                if filename not in archive.namelist():
                    problems.append(f"{filename} missing")
                    continue
                data = archive.read(filename)
                if expected is None or _sha256_bytes(data) != expected:
                    problems.append(f"{filename} checksum mismatch")
                if expected_bytes is not None and len(data) != expected_bytes:
                    problems.append(f"{filename} size mismatch")
            try:
                incident = json.loads(archive.read("incident.json").decode("utf-8"))
                if bundle.get("incident_id") and incident.get("incident_id") != bundle.get("incident_id"):
                    problems.append("incident_id mismatch between manifest and incident.json")
            except (json.JSONDecodeError, UnicodeDecodeError, KeyError) as exc:
                problems.append(f"invalid incident.json: {exc}")
    except zipfile.BadZipFile as exc:
        return False, [f"invalid bundle archive: {exc}"]
    return not problems, problems


def verify_bundle(path: str | Path) -> tuple[bool, list[str]]:
    target = Path(path)
    if target.is_file() and zipfile.is_zipfile(target):
        return _verify_zip(target)
    directory = target.parent if target.is_file() else target
    bundle_path = directory / "bundle.json"
    if not bundle_path.exists():
        return False, ["bundle.json missing"]

    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return False, [f"invalid bundle.json: {exc}"]

    problems: list[str] = []
    schema = bundle.get("schema")
    if schema not in {"rift.bundle/v1", "rift.bundle/v2", "rift.bundle/v3"}:
        problems.append(f"unsupported bundle schema: {schema}")
    try:
        filenames = _manifest_file_names(bundle)
    except ValueError as exc:
        problems.append(str(exc))
        filenames = []
    for filename in filenames:
        entry = bundle.get("files", {}).get(filename)
        expected, expected_bytes = _manifest_expected(entry)
        file_path = directory / filename
        if not file_path.is_file():
            problems.append(f"{filename} missing")
            continue
        if expected is None or _sha256(file_path) != expected:
            problems.append(f"{filename} checksum mismatch")
        if expected_bytes is not None and file_path.stat().st_size != expected_bytes:
            problems.append(f"{filename} size mismatch")
    incident_path = directory / "incident.json"
    if incident_path.exists():
        try:
            incident = json.loads(incident_path.read_text(encoding="utf-8"))
            if bundle.get("incident_id") and incident.get("incident_id") != bundle.get("incident_id"):
                problems.append("incident_id mismatch between manifest and incident.json")
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            problems.append(f"invalid incident.json: {exc}")
    return not problems, problems


def read_bundle_manifest(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if target.is_file() and zipfile.is_zipfile(target):
        with zipfile.ZipFile(target) as archive:
            bundle, problems = _load_zip_manifest(archive)
            if bundle is None or problems:
                raise ValueError("invalid bundle: " + "; ".join(problems))
            return bundle
    directory = target.parent if target.is_file() else target
    return json.loads((directory / "bundle.json").read_text(encoding="utf-8"))


def inspect_bundle(path: str | Path) -> dict[str, Any]:
    ok, problems = verify_bundle(path)
    manifest: dict[str, Any] = {}
    try:
        manifest = read_bundle_manifest(path)
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    incident = None
    if ok:
        incident = read_incident(path)
    return {
        "integrity_ok": ok,
        "problems": problems,
        "manifest": manifest,
        "attachments": manifest.get("attachments", {}) if manifest else {},
        "summary": summarize(incident.events).to_dict() if incident else None,
    }


def read_incident(path: str | Path) -> Incident:
    path = Path(path)
    if path.is_file() and zipfile.is_zipfile(path):
        ok, problems = verify_bundle(path)
        if not ok:
            raise ValueError("invalid bundle: " + "; ".join(problems))
        with zipfile.ZipFile(path) as archive:
            return Incident.from_dict(json.loads(archive.read("incident.json").decode("utf-8")))
    if path.is_dir():
        path = path / "incident.json"
    return Incident.from_dict(json.loads(path.read_text(encoding="utf-8")))



def extract_attachment(
    path: str | Path,
    name: str,
    output: str | Path,
) -> Path:
    """Extract one manifest-declared attachment without unpacking the full bundle."""

    if not _safe_member_name(name):
        raise ValueError(f"unsafe attachment name: {name!r}")
    manifest = read_bundle_manifest(path)
    attachments = manifest.get("attachments", {})
    if name not in attachments:
        raise ValueError(f"attachment not found: {name}")
    ok, problems = verify_bundle(path)
    if not ok:
        raise ValueError("invalid bundle: " + "; ".join(problems))
    destination = Path(output)
    if destination.exists() and destination.is_dir():
        destination = destination / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    target = Path(path)
    if target.is_file() and zipfile.is_zipfile(target):
        with zipfile.ZipFile(target) as archive:
            data = archive.read(name)
        temporary = destination.with_name(f".{destination.name}.tmp")
        temporary.write_bytes(data)
        os.replace(temporary, destination)
        return destination
    directory = target.parent if target.is_file() else target
    shutil.copy2(directory / name, destination)
    return destination


def sanitize_bundle(path: str | Path, output: str | Path) -> Path:
    # Deliberately rebuild from the structured incident only. Binary/raw
    # attachments (including rosbag snapshots) are omitted by default because
    # RIFT cannot safely redact arbitrary message payloads.
    incident = sanitize_incident(read_incident(path))
    incident.metadata["attachments_omitted_by_sanitizer"] = True
    output_path = Path(output)
    if output_path.name.endswith(".rift.zip") or output_path.suffix == ".zip":
        with tempfile.TemporaryDirectory(prefix="rift-sanitize-") as temp:
            directory = Path(temp) / "bundle"
            write_incident(directory, incident)
            return pack_bundle(directory, output_path)
    write_incident(output_path, incident)
    return output_path

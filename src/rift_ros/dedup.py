from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from rift_ros.io import read_bundle_manifest


@dataclass(frozen=True, slots=True)
class DuplicateOccurrence:
    ts: float
    fingerprint: str
    canonical_path: str
    session_id: str | None
    robot_id: str | None
    site_id: str | None
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _same_scope(manifest: dict, robot_id: str | None, site_id: str | None) -> bool:
    identity = manifest.get("identity") if isinstance(manifest.get("identity"), dict) else {}
    other_robot = str(identity.get("robot_id")) if identity.get("robot_id") else None
    other_site = str(identity.get("site_id")) if identity.get("site_id") else None
    return other_robot == robot_id and other_site == site_id


def find_recent_duplicate(
    output_dir: str | Path,
    fingerprint: str,
    *,
    now: float,
    window_seconds: float,
    robot_id: str | None,
    site_id: str | None,
) -> Path | None:
    if window_seconds <= 0 or fingerprint == "healthy":
        return None
    root = Path(output_dir)
    if not root.exists():
        return None
    candidates = [item for item in root.iterdir() if (item.is_dir() and (item / "bundle.json").exists()) or (item.is_file() and item.name.endswith(".rift.zip"))]
    best: tuple[float, Path] | None = None
    for item in candidates:
        try:
            manifest = read_bundle_manifest(item)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if manifest.get("fingerprint") != fingerprint or not _same_scope(manifest, robot_id, site_id):
            continue
        completed = float(manifest.get("completed_at", manifest.get("created_at", 0.0)))
        age = now - completed
        if age < 0 or age > window_seconds:
            continue
        if best is None or completed > best[0]:
            best = (completed, item)
    return best[1] if best else None


def append_duplicate_occurrence(
    output_dir: str | Path,
    *,
    fingerprint: str,
    canonical_path: str | Path,
    session_id: str | None,
    robot_id: str | None,
    site_id: str | None,
    reason: str,
    ts: float | None = None,
) -> Path:
    path = Path(output_dir) / "_duplicates" / "occurrences.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = DuplicateOccurrence(float(ts if ts is not None else time.time()), fingerprint, str(canonical_path), session_id, robot_id, site_id, reason)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return path


def list_duplicate_occurrences(path: str | Path) -> list[DuplicateOccurrence]:
    path = Path(path)
    if path.is_dir():
        path = path / "_duplicates" / "occurrences.jsonl"
    if not path.exists():
        return []
    rows: list[DuplicateOccurrence] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        rows.append(DuplicateOccurrence(
            ts=float(data["ts"]), fingerprint=str(data["fingerprint"]), canonical_path=str(data["canonical_path"]),
            session_id=str(data["session_id"]) if data.get("session_id") else None,
            robot_id=str(data["robot_id"]) if data.get("robot_id") else None,
            site_id=str(data["site_id"]) if data.get("site_id") else None,
            reason=str(data.get("reason", "duplicate incident")),
        ))
    return sorted(rows, key=lambda row: row.ts, reverse=True)

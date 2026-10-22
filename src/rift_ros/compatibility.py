from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from rift_ros.io import read_bundle_manifest, verify_bundle

SUPPORTED_BUNDLE_SCHEMAS = ("rift.bundle/v1", "rift.bundle/v2", "rift.bundle/v3")
SUPPORTED_INCIDENT_SCHEMAS = ("rift.incident/v1", "rift.incident/v2")


@dataclass(frozen=True, slots=True)
class BundleCompatibility:
    readable: bool
    integrity_ok: bool
    bundle_schema: str | None
    incident_schema: str | None
    producer_version: str | None
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "readable": self.readable,
            "integrity_ok": self.integrity_ok,
            "bundle_schema": self.bundle_schema,
            "incident_schema": self.incident_schema,
            "producer_version": self.producer_version,
            "reasons": list(self.reasons),
        }


def inspect_compatibility(path: str | Path) -> BundleCompatibility:
    reasons: list[str] = []
    ok, problems = verify_bundle(path)
    manifest = None
    try:
        manifest = read_bundle_manifest(path)
    except (OSError, ValueError):
        reasons.extend(problems or ("bundle manifest is unreadable",))
        return BundleCompatibility(False, False, None, None, None, tuple(reasons))

    bundle_schema = str(manifest.get("schema")) if manifest.get("schema") is not None else None
    if bundle_schema not in SUPPORTED_BUNDLE_SCHEMAS:
        reasons.append(f"unsupported bundle schema: {bundle_schema}")

    incident_schema = None
    try:
        target = Path(path)
        if target.is_file() and zipfile.is_zipfile(target):
            with zipfile.ZipFile(target) as archive:
                raw_incident = json.loads(archive.read("incident.json").decode("utf-8"))
        else:
            directory = target.parent if target.is_file() else target
            raw_incident = json.loads((directory / "incident.json").read_text(encoding="utf-8"))
        incident_schema = str(raw_incident.get("schema", "rift.incident/v1"))
        if incident_schema not in SUPPORTED_INCIDENT_SCHEMAS:
            reasons.append(f"unsupported incident schema: {incident_schema}")
    except (OSError, ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError, zipfile.BadZipFile):
        reasons.append("incident payload is unreadable")

    if not ok:
        reasons.extend(item for item in problems if item not in reasons)
    readable = bundle_schema in SUPPORTED_BUNDLE_SCHEMAS and incident_schema in SUPPORTED_INCIDENT_SCHEMAS
    return BundleCompatibility(
        readable=readable,
        integrity_ok=ok,
        bundle_schema=bundle_schema,
        incident_schema=incident_schema,
        producer_version=(str(manifest.get("rift_version")) if manifest.get("rift_version") is not None else None),
        reasons=tuple(reasons),
    )

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from rift_ros.analysis import summarize
from rift_ros.io import read_bundle_manifest, read_incident, verify_bundle


@dataclass(frozen=True, slots=True)
class CatalogRow:
    path: str
    incident_id: str
    created_at: float
    reason: str
    session_id: str | None
    robot_id: str | None
    site_id: str | None
    failures: int
    warnings: int
    fingerprint: str
    has_rosbag: bool
    integrity_ok: bool

    def to_dict(self) -> dict:
        return asdict(self)


def discover_incidents(root: str | Path) -> list[Path]:
    root = Path(root)
    if root.is_file():
        return [root]
    if not root.exists():
        return []
    found: list[Path] = []
    if (root / "bundle.json").exists():
        found.append(root)
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "bundle.json").exists():
            found.append(child)
        elif child.is_file() and child.name.endswith(".rift.zip"):
            found.append(child)
    return found


def catalog(paths: Iterable[str | Path]) -> list[CatalogRow]:
    rows: list[CatalogRow] = []
    expanded: list[Path] = []
    for path in paths:
        expanded.extend(discover_incidents(path))
    for path in expanded:
        try:
            incident = read_incident(path)
            summary = summarize(incident.events)
            manifest = read_bundle_manifest(path)
            ok, _ = verify_bundle(path)
            attachments = manifest.get("attachments", {}) if isinstance(manifest, dict) else {}
            has_rosbag = any(
                isinstance(meta, dict) and meta.get("role") == "rosbag2-snapshot"
                for meta in attachments.values()
            )
            identity = incident.metadata.get("identity") if isinstance(incident.metadata.get("identity"), dict) else {}
            rows.append(
                CatalogRow(
                    path=str(path),
                    incident_id=incident.incident_id,
                    created_at=incident.created_at,
                    reason=incident.reason,
                    session_id=(str(incident.metadata.get("session_id")) if incident.metadata.get("session_id") else None),
                    robot_id=(str(identity.get("robot_id")) if identity.get("robot_id") else None),
                    site_id=(str(identity.get("site_id")) if identity.get("site_id") else None),
                    failures=summary.failures,
                    warnings=summary.warnings,
                    fingerprint=summary.fingerprint,
                    has_rosbag=has_rosbag,
                    integrity_ok=ok,
                )
            )
        except (OSError, ValueError, KeyError):
            continue
    return sorted(rows, key=lambda row: (row.created_at, row.incident_id))

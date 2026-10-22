from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class SessionRecord:
    session_id: str
    started_at: float
    stopped_at: float
    profile: str | None
    config_id: str | None
    robot_id: str | None
    site_id: str | None
    labels: dict[str, str]
    cycles: int
    incidents_captured: int
    deduplicated_incidents: int
    anomalous_cycles: int
    overrun_cycles: int
    probe_error_cycles: int
    marker_scenarios: dict[str, int]
    path: Path

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.stopped_at - self.started_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "duration_seconds": self.duration_seconds,
            "profile": self.profile,
            "config_id": self.config_id,
            "robot_id": self.robot_id,
            "site_id": self.site_id,
            "labels": dict(self.labels),
            "cycles": self.cycles,
            "incidents_captured": self.incidents_captured,
            "deduplicated_incidents": self.deduplicated_incidents,
            "anomalous_cycles": self.anomalous_cycles,
            "overrun_cycles": self.overrun_cycles,
            "probe_error_cycles": self.probe_error_cycles,
            "marker_scenarios": dict(self.marker_scenarios),
            "path": str(self.path),
        }


def _atomic_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def write_session_report(
    output_dir: str | Path,
    *,
    session_id: str,
    started_at: float,
    stopped_at: float,
    profile: str | None,
    config_id: str | None,
    robot_id: str | None = None,
    site_id: str | None = None,
    labels: dict[str, str] | None = None,
    incidents: Iterable[str | Path] = (),
    metrics: dict[str, Any],
    marker_scenarios: dict[str, int],
    armed_at: float | None,
    last_healthy_at: float | None,
    last_anomaly_at: float | None,
    stopped_reason: str,
    deduplicated_incidents: int = 0,
) -> Path:
    incident_paths = [str(Path(item)) for item in incidents]
    payload = {
        "schema": "rift.session/v3",
        "session_id": session_id,
        "started_at": float(started_at),
        "stopped_at": float(stopped_at),
        "duration_seconds": max(0.0, float(stopped_at) - float(started_at)),
        "profile": profile,
        "config_id": config_id,
        "identity": {"robot_id": robot_id, "site_id": site_id, "labels": dict(sorted((labels or {}).items()))},
        "stopped_reason": stopped_reason,
        "armed_at": armed_at,
        "last_healthy_at": last_healthy_at,
        "last_anomaly_at": last_anomaly_at,
        "incidents_captured": len(incident_paths),
        "deduplicated_incidents": int(deduplicated_incidents),
        "incidents": incident_paths,
        "metrics": metrics,
        "marker_scenarios": dict(sorted(marker_scenarios.items())),
    }
    path = Path(output_dir) / "_sessions" / f"{session_id}.json"
    return _atomic_json(path, payload)


def read_session_report(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") not in {"rift.session/v1", "rift.session/v2", "rift.session/v3"}:
        raise ValueError("unsupported or invalid RIFT session report")
    if not data.get("session_id"):
        raise ValueError("session report missing session_id")
    return data


def list_session_reports(path: str | Path) -> list[SessionRecord]:
    root = Path(path)
    if root.is_file():
        candidates = [root]
    else:
        session_dir = root / "_sessions" if (root / "_sessions").is_dir() else root
        candidates = sorted(session_dir.glob("*.json")) if session_dir.exists() else []
    rows: list[SessionRecord] = []
    for candidate in candidates:
        try:
            data = read_session_report(candidate)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
        scenarios = data.get("marker_scenarios") if isinstance(data.get("marker_scenarios"), dict) else {}
        identity = data.get("identity") if isinstance(data.get("identity"), dict) else {}
        rows.append(
            SessionRecord(
                session_id=str(data["session_id"]),
                started_at=float(data.get("started_at", 0.0)),
                stopped_at=float(data.get("stopped_at", data.get("started_at", 0.0))),
                profile=str(data["profile"]) if data.get("profile") is not None else None,
                config_id=str(data["config_id"]) if data.get("config_id") is not None else None,
                robot_id=str(identity["robot_id"]) if identity.get("robot_id") is not None else None,
                site_id=str(identity["site_id"]) if identity.get("site_id") is not None else None,
                labels={str(key): str(value) for key, value in (identity.get("labels") or {}).items()},
                cycles=int(metrics.get("cycles", 0)),
                incidents_captured=int(data.get("incidents_captured", 0)),
                deduplicated_incidents=int(data.get("deduplicated_incidents", 0)),
                anomalous_cycles=int(metrics.get("anomalous_cycles", 0)),
                overrun_cycles=int(metrics.get("overrun_cycles", 0)),
                probe_error_cycles=int(metrics.get("probe_error_cycles", 0)),
                marker_scenarios={str(key): int(value) for key, value in scenarios.items()},
                path=candidate,
            )
        )
    return sorted(rows, key=lambda item: (item.started_at, item.session_id), reverse=True)

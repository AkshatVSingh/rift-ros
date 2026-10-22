from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from rift_ros.io import read_incident
from rift_ros.status import atomic_json_write

VALID_REVIEW_STATUSES = ("open", "acknowledged", "resolved", "ignored")


@dataclass(frozen=True, slots=True)
class ReviewNote:
    ts: float
    text: str
    actor: str | None = None


@dataclass(slots=True)
class ReviewRecord:
    incident_id: str
    status: str = "open"
    owner: str | None = None
    updated_at: float = 0.0
    labels: dict[str, str] = field(default_factory=dict)
    notes: list[ReviewNote] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "status": self.status,
            "owner": self.owner,
            "updated_at": self.updated_at,
            "labels": dict(sorted(self.labels.items())),
            "notes": [asdict(note) for note in self.notes],
        }


def _empty_store() -> dict[str, Any]:
    return {"schema": "rift.reviews/v1", "updated_at": time.time(), "records": {}}


def load_review_store(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return _empty_store()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "rift.reviews/v1" or not isinstance(data.get("records"), dict):
        raise ValueError("unsupported or invalid RIFT review store")
    return data


def _record_from_data(incident_id: str, data: dict[str, Any]) -> ReviewRecord:
    return ReviewRecord(
        incident_id=incident_id,
        status=str(data.get("status", "open")),
        owner=str(data["owner"]) if data.get("owner") else None,
        updated_at=float(data.get("updated_at", 0.0)),
        labels={str(k): str(v) for k, v in (data.get("labels") or {}).items()},
        notes=[
            ReviewNote(float(item.get("ts", 0.0)), str(item.get("text", "")), str(item["actor"]) if item.get("actor") else None)
            for item in (data.get("notes") or []) if isinstance(item, dict)
        ],
    )


def list_reviews(path: str | Path) -> list[ReviewRecord]:
    store = load_review_store(path)
    rows = [_record_from_data(str(iid), data) for iid, data in store["records"].items() if isinstance(data, dict)]
    return sorted(rows, key=lambda row: (row.updated_at, row.incident_id), reverse=True)


def review_for(path: str | Path, incident_id: str) -> ReviewRecord | None:
    store = load_review_store(path)
    data = store["records"].get(incident_id)
    return _record_from_data(incident_id, data) if isinstance(data, dict) else None


def update_review(
    store_path: str | Path,
    incident: str | Path,
    *,
    status: str | None = None,
    owner: str | None = None,
    note: str | None = None,
    actor: str | None = None,
    labels: dict[str, str] | None = None,
) -> ReviewRecord:
    if status is not None and status not in VALID_REVIEW_STATUSES:
        raise ValueError(f"invalid review status {status!r}")
    incident_id = read_incident(incident).incident_id
    store = load_review_store(store_path)
    raw = store["records"].get(incident_id, {})
    record = _record_from_data(incident_id, raw if isinstance(raw, dict) else {})
    if status is not None:
        record.status = status
    if owner is not None:
        record.owner = owner or None
    if labels:
        record.labels.update({str(k): str(v) for k, v in labels.items()})
    if note:
        record.notes.append(ReviewNote(time.time(), note, actor))
    record.updated_at = time.time()
    store["records"][incident_id] = record.to_dict()
    store["updated_at"] = record.updated_at
    atomic_json_write(store_path, store)
    return record

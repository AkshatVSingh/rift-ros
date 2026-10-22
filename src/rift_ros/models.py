from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    INFO = "info"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class Event:
    ts: float
    kind: str
    source: str
    message: str
    severity: Severity = Severity.INFO
    value: float | str | bool | None = None
    unit: str | None = None
    tags: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        data["tags"] = list(self.tags)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        return cls(
            ts=float(data["ts"]),
            kind=str(data["kind"]),
            source=str(data["source"]),
            message=str(data["message"]),
            severity=Severity(data.get("severity", "info")),
            value=data.get("value"),
            unit=data.get("unit"),
            tags=tuple(data.get("tags", [])),
            evidence=dict(data.get("evidence", {})),
        )


@dataclass(slots=True)
class Incident:
    incident_id: str
    created_at: float
    reason: str
    events: list[Event]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rift.incident/v2",
            "incident_id": self.incident_id,
            "created_at": self.created_at,
            "reason": self.reason,
            "metadata": self.metadata,
            "events": [event.to_dict() for event in self.events],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Incident":
        # v1 and v2 incident files intentionally share the same required fields.
        return cls(
            incident_id=str(data["incident_id"]),
            created_at=float(data["created_at"]),
            reason=str(data["reason"]),
            events=[Event.from_dict(item) for item in data.get("events", [])],
            metadata=dict(data.get("metadata", {})),
        )

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from rift_ros.models import Event, Severity


@dataclass(frozen=True, slots=True)
class MarkerRecord:
    ts: float
    message: str
    severity: Severity = Severity.INFO
    tags: tuple[str, ...] = ()
    scenario: str | None = None
    session_id: str | None = None
    actor: str = "operator"

    def to_dict(self) -> dict:
        return {
            "schema": "rift.marker/v1",
            "ts": self.ts,
            "message": self.message,
            "severity": self.severity.value,
            "tags": list(self.tags),
            "scenario": self.scenario,
            "session_id": self.session_id,
            "actor": self.actor,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MarkerRecord":
        return cls(
            ts=float(data.get("ts", time.time())),
            message=str(data["message"]),
            severity=Severity(str(data.get("severity", "info"))),
            tags=tuple(str(item) for item in data.get("tags", [])),
            scenario=str(data["scenario"]) if data.get("scenario") is not None else None,
            session_id=str(data["session_id"]) if data.get("session_id") is not None else None,
            actor=str(data.get("actor", "operator")),
        )

    def to_event(self) -> Event:
        tags = tuple(dict.fromkeys(("operator", "marker", *self.tags)))
        evidence = {
            "scenario": self.scenario,
            "session_id": self.session_id,
            "actor": self.actor,
        }
        return Event(
            self.ts,
            "operator_marker",
            self.actor,
            self.message,
            self.severity,
            tags=tags,
            evidence={key: value for key, value in evidence.items() if value is not None},
        )


def append_marker(
    path: str | Path,
    message: str,
    *,
    severity: Severity = Severity.INFO,
    tags: Iterable[str] = (),
    scenario: str | None = None,
    session_id: str | None = None,
    actor: str = "operator",
    ts: float | None = None,
) -> MarkerRecord:
    if not message.strip():
        raise ValueError("marker message cannot be empty")
    record = MarkerRecord(
        ts=time.time() if ts is None else float(ts),
        message=message.strip(),
        severity=severity,
        tags=tuple(str(item).strip() for item in tags if str(item).strip()),
        scenario=scenario,
        session_id=session_id,
        actor=actor,
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    fd = os.open(target, flags, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    return record


class MarkerReader:
    """Incrementally read an append-only marker journal without replaying old markers."""

    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path is not None else None
        self.offset = 0
        self._identity: tuple[int, int] | None = None

    def read_new(self) -> list[MarkerRecord]:
        if self.path is None or not self.path.exists():
            return []
        stat = self.path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if self._identity is not None and identity != self._identity:
            self.offset = 0
        if stat.st_size < self.offset:
            self.offset = 0
        self._identity = identity

        records: list[MarkerRecord] = []
        with self.path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(self.offset)
            while True:
                line = handle.readline()
                if not line:
                    break
                self.offset = handle.tell()
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                    records.append(MarkerRecord.from_dict(payload))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    # A corrupt operator annotation must never crash the recorder.
                    continue
        return records

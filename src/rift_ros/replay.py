from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from rift_ros.io import read_incident
from rift_ros.models import Event, Severity


@dataclass(frozen=True, slots=True)
class ReplayFilter:
    anomalies_only: bool = False
    kinds: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    start_seconds: float | None = None
    end_seconds: float | None = None

    def matches(self, event: Event, origin: float) -> bool:
        if self.anomalies_only and event.severity == Severity.INFO:
            return False
        if self.kinds and event.kind not in self.kinds:
            return False
        if self.sources and event.source not in self.sources:
            return False
        relative = event.ts - origin
        if self.start_seconds is not None and relative < self.start_seconds:
            return False
        if self.end_seconds is not None and relative > self.end_seconds:
            return False
        return True


def filtered_events(path: str | Path, filters: ReplayFilter | None = None) -> list[Event]:
    incident = read_incident(path)
    events = sorted(incident.events, key=lambda item: item.ts)
    if not events:
        return []
    filters = filters or ReplayFilter()
    origin = events[0].ts
    return [event for event in events if filters.matches(event, origin)]


def replay_records(path: str | Path, filters: ReplayFilter | None = None) -> list[dict]:
    events = filtered_events(path, filters)
    if not events:
        return []
    origin = events[0].ts
    records: list[dict] = []
    for index, event in enumerate(events):
        item = event.to_dict()
        item["index"] = index
        item["relative_seconds"] = round(event.ts - origin, 6)
        records.append(item)
    return records


def write_replay_jsonl(path: str | Path, output: str | Path, filters: ReplayFilter | None = None) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    records = replay_records(path, filters)
    output.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in records), encoding="utf-8")
    return output


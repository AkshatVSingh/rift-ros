from __future__ import annotations

import csv
import json
from pathlib import Path

from rift_ros.io import read_incident


def export_timeline(path: str | Path, output: str | Path, fmt: str = "csv") -> Path:
    incident = read_incident(path)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    events = sorted(incident.events, key=lambda event: event.ts)
    start = events[0].ts if events else incident.created_at
    if fmt == "json":
        payload = [
            {
                "relative_seconds": round(event.ts - start, 6),
                **event.to_dict(),
            }
            for event in events
        ]
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return target
    if fmt != "csv":
        raise ValueError("format must be csv or json")
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["relative_seconds", "timestamp", "severity", "kind", "source", "message", "value", "unit", "tags", "evidence_json"])
        for event in events:
            writer.writerow([
                f"{event.ts - start:.6f}",
                f"{event.ts:.6f}",
                event.severity.value,
                event.kind,
                event.source,
                event.message,
                event.value,
                event.unit,
                ";".join(event.tags),
                json.dumps(event.evidence, sort_keys=True),
            ])
    return target

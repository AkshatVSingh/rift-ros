from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass

from rift_ros.models import Event, Severity


@dataclass(frozen=True, slots=True)
class Summary:
    total: int
    failures: int
    warnings: int
    first_ts: float | None
    last_ts: float | None
    by_kind: dict[str, int]
    failed_sources: tuple[str, ...]
    fingerprint: str
    first_anomaly: str | None

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "failures": self.failures,
            "warnings": self.warnings,
            "first_ts": self.first_ts,
            "last_ts": self.last_ts,
            "duration_seconds": (
                None if self.first_ts is None or self.last_ts is None else self.last_ts - self.first_ts
            ),
            "by_kind": self.by_kind,
            "failed_sources": list(self.failed_sources),
            "fingerprint": self.fingerprint,
            "first_anomaly": self.first_anomaly,
        }


def timeline(events: list[Event], only_anomalies: bool = False) -> list[Event]:
    ordered = sorted(events, key=lambda event: event.ts)
    if only_anomalies:
        ordered = [event for event in ordered if event.severity != Severity.INFO]
    return ordered


def fault_fingerprint(events: list[Event]) -> str:
    anomalies = timeline(events, only_anomalies=True)
    signature = "|".join(sorted({f"{event.kind}:{event.source}:{event.severity.value}" for event in anomalies}))
    if not signature:
        return "healthy"
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()[:12]


def summarize(events: list[Event]) -> Summary:
    ordered = timeline(events)
    kinds = Counter(event.kind for event in ordered)
    failures = [event for event in ordered if event.severity == Severity.FAIL]
    warnings = [event for event in ordered if event.severity == Severity.WARN]
    anomalies = failures + warnings
    first_anomaly_event = min(anomalies, key=lambda event: event.ts) if anomalies else None
    return Summary(
        total=len(ordered),
        failures=len(failures),
        warnings=len(warnings),
        first_ts=ordered[0].ts if ordered else None,
        last_ts=ordered[-1].ts if ordered else None,
        by_kind=dict(sorted(kinds.items())),
        failed_sources=tuple(sorted({event.source for event in failures})),
        fingerprint=fault_fingerprint(ordered),
        first_anomaly=(
            None
            if first_anomaly_event is None
            else f"{first_anomaly_event.kind}:{first_anomaly_event.source}"
        ),
    )


def render_summary(events: list[Event]) -> str:
    summary = summarize(events)
    lines = [
        "RIFT-ROS incident summary",
        "=" * 48,
        f"Events: {summary.total}",
        f"Failures: {summary.failures}",
        f"Warnings: {summary.warnings}",
        f"Fingerprint: {summary.fingerprint}",
    ]
    if summary.first_anomaly:
        lines.append(f"First anomaly: {summary.first_anomaly}")
    if summary.failed_sources:
        lines.append("Failed sources: " + ", ".join(summary.failed_sources))

    anomalies = timeline(events, True)
    if anomalies:
        lines.extend(["", "Anomaly timeline:"])
        start = timeline(events)[0].ts if events else anomalies[0].ts
        for event in anomalies:
            lines.append(
                f"  +{event.ts - start:7.3f}s  {event.severity.value.upper():4}  "
                f"{event.source}: {event.message}"
            )
    else:
        lines.extend(["", "No failures or warnings recorded."])
    return "\n".join(lines)

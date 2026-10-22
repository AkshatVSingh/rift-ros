from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass, field

from rift_ros.models import Event


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


@dataclass(slots=True)
class RecorderMetrics:
    max_samples: int = 120
    durations: deque[float] = field(default_factory=deque)
    cycles: int = 0
    overrun_cycles: int = 0
    probe_errors: int = 0
    probe_error_cycles: int = 0
    triggerable_anomalies: int = 0
    markers_ingested: int = 0
    anomalous_cycles: int = 0

    def observe(self, duration_seconds: float, events: list[Event], interval_seconds: float, triggerable_count: int) -> None:
        self.cycles += 1
        self.durations.append(float(duration_seconds))
        while len(self.durations) > self.max_samples:
            self.durations.popleft()
        if duration_seconds > interval_seconds:
            self.overrun_cycles += 1
        cycle_probe_errors = sum(event.kind == "probe_error" for event in events)
        self.probe_errors += cycle_probe_errors
        if cycle_probe_errors:
            self.probe_error_cycles += 1
        self.triggerable_anomalies += triggerable_count
        if triggerable_count > 0:
            self.anomalous_cycles += 1
        self.markers_ingested += sum(event.kind == "operator_marker" for event in events)

    def to_dict(self) -> dict:
        values = list(self.durations)
        return {
            "window_samples": len(values),
            "cycles": self.cycles,
            "cycle_seconds_mean": round(statistics.fmean(values), 6) if values else None,
            "cycle_seconds_p50": round(_percentile(values, 0.50), 6) if values else None,
            "cycle_seconds_p95": round(_percentile(values, 0.95), 6) if values else None,
            "cycle_seconds_max": round(max(values), 6) if values else None,
            "overrun_cycles": self.overrun_cycles,
            "overrun_rate": round(self.overrun_cycles / max(1, self.cycles), 6),
            "probe_errors": self.probe_errors,
            "probe_error_cycles": self.probe_error_cycles,
            "probe_error_cycle_rate": round(self.probe_error_cycles / max(1, self.cycles), 6),
            "triggerable_anomalies": self.triggerable_anomalies,
            "markers_ingested": self.markers_ingested,
            "anomalous_cycles": self.anomalous_cycles,
            "healthy_cycles": max(0, self.cycles - self.anomalous_cycles),
        }


def performance_budget(metrics: "RecorderMetrics", max_p95_seconds: float | None) -> dict:
    data = metrics.to_dict()
    p95 = data.get("cycle_seconds_p95")
    if max_p95_seconds is None:
        return {"configured": False, "max_p95_seconds": None, "observed_p95_seconds": p95, "within_budget": None}
    observed = float(p95 or 0.0)
    return {
        "configured": True,
        "max_p95_seconds": float(max_p95_seconds),
        "observed_p95_seconds": observed,
        "within_budget": observed <= float(max_p95_seconds),
    }

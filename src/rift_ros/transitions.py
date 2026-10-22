from __future__ import annotations

import time
from dataclasses import dataclass, field

from rift_ros.models import Event, Severity

_TRACKED_KINDS = {
    "node_presence",
    "topic_presence",
    "topic_publishers",
    "topic_subscribers",
    "topic_rate",
    "topic_jitter",
    "topic_delay",
    "qos_compatibility",
    "tf_presence",
    "lifecycle_state",
    "system_pressure",
}


@dataclass(slots=True)
class StateTracker:
    _previous: dict[tuple[str, str], Event] = field(default_factory=dict)

    def update(self, events: list[Event]) -> list[Event]:
        transitions: list[Event] = []
        for event in events:
            if event.kind not in _TRACKED_KINDS:
                continue
            key = (event.kind, event.source)
            previous = self._previous.get(key)
            self._previous[key] = event
            if previous is None or previous.severity == event.severity:
                continue
            recovered = event.severity == Severity.INFO
            transitions.append(
                Event(
                    time.time(),
                    "state_transition",
                    event.source,
                    (
                        f"recovered: {event.kind} {previous.severity.value} -> info"
                        if recovered
                        else f"degraded: {event.kind} {previous.severity.value} -> {event.severity.value}"
                    ),
                    event.severity,
                    tags=("transition", "recovery" if recovered else "degradation"),
                    evidence={
                        "kind": event.kind,
                        "from_severity": previous.severity.value,
                        "to_severity": event.severity.value,
                        "previous_message": previous.message,
                        "current_message": event.message,
                    },
                )
            )
        return transitions

from __future__ import annotations

from dataclasses import dataclass

from rift_ros.models import Event, Severity


@dataclass(slots=True)
class ClockGuard:
    threshold_seconds: float = 2.0
    _wall: float | None = None
    _mono: float | None = None

    def observe(self, wall: float, monotonic: float) -> Event | None:
        if self._wall is None or self._mono is None:
            self._wall = wall
            self._mono = monotonic
            return None
        wall_delta = wall - self._wall
        mono_delta = monotonic - self._mono
        drift = wall_delta - mono_delta
        self._wall = wall
        self._mono = monotonic
        if abs(drift) < self.threshold_seconds:
            return None
        return Event(
            wall,
            "clock_jump",
            "host-clock",
            f"wall/monotonic delta diverged by {drift:+.3f} s",
            Severity.WARN,
            drift,
            "s",
            tags=("rift", "clock", "timestamp"),
            evidence={
                "threshold_seconds": self.threshold_seconds,
                "wall_delta_seconds": wall_delta,
                "monotonic_delta_seconds": mono_delta,
            },
        )

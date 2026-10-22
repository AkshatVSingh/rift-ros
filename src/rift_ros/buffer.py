from __future__ import annotations

from collections import deque

from rift_ros.models import Event


class RollingEventBuffer:
    def __init__(self, window_seconds: float = 60.0) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.window_seconds = float(window_seconds)
        self._events: deque[Event] = deque()

    def append(self, event: Event) -> None:
        self._events.append(event)
        cutoff = event.ts - self.window_seconds
        while self._events and self._events[0].ts < cutoff:
            self._events.popleft()

    def snapshot(self) -> list[Event]:
        return list(self._events)

    def __len__(self) -> int:
        return len(self._events)

from __future__ import annotations

import re
from dataclasses import dataclass

from ros_doctor.shell import run


_RATE_RE = re.compile(r"average rate:\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class RateSample:
    topic: str
    hz: float | None
    evidence: str


def sample_rate(topic: str, seconds: float = 4.0) -> RateSample:
    # `ros2 topic hz` normally runs until interrupted. A short timeout gives us
    # enough output to parse an average without leaving a process running.
    result = run(["ros2", "topic", "hz", topic], timeout=seconds)
    combined = f"{result.stdout}\n{result.stderr}".strip()
    matches = _RATE_RE.findall(combined)
    hz = float(matches[-1]) if matches else None
    if hz is None:
        evidence = "no average rate observed in sample window"
    else:
        evidence = f"average rate {hz:.2f} Hz"
    return RateSample(topic, hz, evidence)

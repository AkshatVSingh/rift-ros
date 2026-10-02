from __future__ import annotations

from dataclasses import dataclass

from ros_doctor.shell import run


@dataclass(frozen=True, slots=True)
class TfCheck:
    parent: str
    child: str
    available: bool
    evidence: str


def check_transform(parent: str, child: str, timeout: float = 2.0) -> TfCheck:
    result = run(
        ["ros2", "run", "tf2_ros", "tf2_echo", parent, child],
        timeout=timeout,
    )
    combined = f"{result.stdout}\n{result.stderr}".strip()
    # A timestamp alone is not evidence that a transform was resolved.
    # tf2_echo may print status/timing information while it is still waiting.
    available = "Translation:" in combined and "Rotation:" in combined

    if available:
        evidence = "transform data received"
    elif result.returncode == 127:
        evidence = "ros2 or tf2_ros executable not available"
    elif result.timed_out:
        evidence = "no transform received before timeout"
    else:
        evidence = combined.splitlines()[-1] if combined else "transform unavailable"

    return TfCheck(parent, child, available, evidence)

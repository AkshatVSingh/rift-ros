from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import dataclass

from rift_ros.shell import run


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    name: str
    ok: bool
    message: str
    required: bool = True


def runtime_checks() -> list[DiagnosticCheck]:
    checks: list[DiagnosticCheck] = []
    py = sys.version_info
    checks.append(
        DiagnosticCheck(
            "python",
            py >= (3, 10),
            f"Python {platform.python_version()}",
        )
    )
    ros2 = shutil.which("ros2")
    checks.append(DiagnosticCheck("ros2-cli", bool(ros2), ros2 or "ros2 not found in PATH"))
    distro = os.environ.get("ROS_DISTRO")
    checks.append(
        DiagnosticCheck(
            "ros-environment",
            bool(distro),
            f"ROS_DISTRO={distro}" if distro else "ROS_DISTRO is not set",
        )
    )
    if ros2 and distro:
        result = run(["ros2", "pkg", "prefix", "tf2_ros"], timeout=3.0)
        checks.append(
            DiagnosticCheck(
                "tf2-ros",
                result.returncode == 0,
                result.stdout.strip() if result.returncode == 0 else (result.stderr.strip() or "tf2_ros unavailable"),
                required=False,
            )
        )
    return checks


def diagnostics_exit_code(checks: list[DiagnosticCheck]) -> int:
    return 0 if all(check.ok or not check.required for check in checks) else 1

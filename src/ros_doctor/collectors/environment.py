from __future__ import annotations

import os
import shutil
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EnvironmentSnapshot:
    ros_distro: str | None
    ros_version: str | None
    rmw_implementation: str | None
    ros_domain_id: str | None
    ros2_executable: str | None

    @property
    def ros_available(self) -> bool:
        return bool(self.ros2_executable and self.ros_distro)


def collect_environment() -> EnvironmentSnapshot:
    return EnvironmentSnapshot(
        ros_distro=os.environ.get("ROS_DISTRO"),
        ros_version=os.environ.get("ROS_VERSION"),
        rmw_implementation=os.environ.get("RMW_IMPLEMENTATION"),
        ros_domain_id=os.environ.get("ROS_DOMAIN_ID"),
        ros2_executable=shutil.which("ros2"),
    )

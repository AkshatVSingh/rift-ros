from __future__ import annotations

from dataclasses import dataclass

from rift_ros.collectors import LifecycleExpectation, TopicExpectation


@dataclass(frozen=True, slots=True)
class RuntimeProfile:
    name: str
    description: str
    nodes: tuple[str, ...] = ()
    topics: tuple[TopicExpectation, ...] = ()
    transforms: tuple[tuple[str, str], ...] = ()
    lifecycle: tuple[LifecycleExpectation, ...] = ()


def _ns_join(namespace: str, name: str) -> str:
    ns = namespace.strip()
    if not ns or ns == "/":
        return name if name.startswith("/") else f"/{name}"
    ns = "/" + ns.strip("/")
    return f"{ns}/{name.lstrip('/')}"


def _frame(namespace: str, name: str) -> str:
    ns = namespace.strip("/")
    return f"{ns}/{name}" if ns else name


def nav2_profile(namespace: str = "") -> RuntimeProfile:
    nodes = tuple(
        _ns_join(namespace, name)
        for name in ("controller_server", "planner_server", "bt_navigator")
    )
    lifecycle = tuple(LifecycleExpectation(node, "active") for node in nodes)
    return RuntimeProfile(
        name="nav2",
        description="Core Nav2 runtime, odometry, lidar, QoS and localization transforms",
        nodes=nodes,
        topics=(
            TopicExpectation(
                _ns_join(namespace, "odom"),
                min_hz=10.0,
                max_jitter_seconds=0.05,
                require_publishers=True,
                check_qos=True,
            ),
            TopicExpectation(
                _ns_join(namespace, "scan"),
                min_hz=5.0,
                max_jitter_seconds=0.10,
                require_publishers=True,
                check_qos=True,
            ),
        ),
        transforms=(
            (_frame(namespace, "map"), _frame(namespace, "odom")),
            (_frame(namespace, "odom"), _frame(namespace, "base_link")),
        ),
        lifecycle=lifecycle,
    )


def sensor_profile(namespace: str = "") -> RuntimeProfile:
    return RuntimeProfile(
        name="sensors",
        description="Common odometry, lidar and IMU streams with timing/QoS evidence",
        topics=(
            TopicExpectation(
                _ns_join(namespace, "odom"),
                min_hz=10.0,
                max_jitter_seconds=0.05,
                require_publishers=True,
                check_qos=True,
            ),
            TopicExpectation(
                _ns_join(namespace, "scan"),
                min_hz=5.0,
                max_jitter_seconds=0.10,
                require_publishers=True,
                check_qos=True,
            ),
            TopicExpectation(
                _ns_join(namespace, "imu/data"),
                min_hz=20.0,
                max_jitter_seconds=0.02,
                require_publishers=True,
                check_qos=True,
            ),
        ),
    )


_PROFILE_BUILDERS = {"nav2": nav2_profile, "sensors": sensor_profile}


def available_profiles() -> tuple[str, ...]:
    return tuple(sorted(_PROFILE_BUILDERS))


def get_profile(name: str, namespace: str = "") -> RuntimeProfile:
    try:
        return _PROFILE_BUILDERS[name](namespace)
    except KeyError as exc:
        raise ValueError(f"unknown profile {name!r}; choose from {', '.join(available_profiles())}") from exc

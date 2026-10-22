from __future__ import annotations

import time

from rift_ros.models import Event, Incident, Severity


def _incident(name: str, reason: str, events: list[Event]) -> Incident:
    return Incident(
        f"demo-{name}-001",
        max(event.ts for event in events),
        reason,
        events,
        {
            "source": "built-in synthetic demo",
            "scenario": name,
            "robot": "simulated-mobile-base",
            "ground_truth": name,
        },
    )


def nav2_failure_demo() -> Incident:
    base = time.time() - 12.0
    events = [
        Event(base + 0.0, "topic_rate", "/odom", "topic rate 49.8 Hz", value=49.8, unit="Hz"),
        Event(base + 0.1, "topic_rate", "/scan", "topic rate 15.0 Hz", value=15.0, unit="Hz"),
        Event(
            base + 3.5,
            "topic_rate",
            "/odom",
            "topic rate 11.2 Hz",
            Severity.FAIL,
            11.2,
            "Hz",
            tags=("odometry", "timing"),
            evidence={"minimum_hz": 30.0},
        ),
        Event(
            base + 3.9,
            "localization_health",
            "/amcl",
            "pose covariance increased",
            Severity.WARN,
            3.7,
            "x-baseline",
            tags=("localization",),
        ),
        Event(
            base + 4.4,
            "tf_presence",
            "map->odom",
            "transform unavailable",
            Severity.FAIL,
            False,
            tags=("tf", "localization"),
        ),
        Event(
            base + 5.7,
            "nav2_event",
            "/controller_server",
            "failed to make progress",
            Severity.FAIL,
            tags=("nav2", "controller"),
        ),
        Event(
            base + 6.2,
            "nav2_event",
            "/bt_navigator",
            "navigation goal aborted",
            Severity.FAIL,
            tags=("nav2",),
        ),
    ]
    return _incident("nav2-odom", "navigation aborted", events)


def lidar_dropout_demo() -> Incident:
    base = time.time() - 10.0
    events = [
        Event(base, "topic_rate", "/scan", "topic rate 15.1 Hz", value=15.1, unit="Hz"),
        Event(
            base + 2.0,
            "topic_rate",
            "/scan",
            "topic rate 1.2 Hz",
            Severity.FAIL,
            1.2,
            "Hz",
            tags=("lidar", "timing"),
        ),
        Event(
            base + 2.4,
            "topic_publishers",
            "/scan",
            "publisher count 0",
            Severity.FAIL,
            0,
            tags=("lidar", "connectivity"),
        ),
        Event(
            base + 3.1,
            "localization_health",
            "/amcl",
            "scan matching degraded",
            Severity.WARN,
            tags=("localization", "lidar"),
        ),
        Event(
            base + 4.0,
            "nav2_event",
            "/controller_server",
            "control aborted",
            Severity.FAIL,
            tags=("nav2",),
        ),
    ]
    return _incident("lidar-dropout", "lidar stream dropped during navigation", events)


def lifecycle_demo() -> Incident:
    base = time.time() - 8.0
    events = [
        Event(
            base,
            "lifecycle_state",
            "/controller_server",
            "lifecycle state active",
            value="active",
            tags=("nav2", "lifecycle"),
        ),
        Event(
            base + 2.0,
            "lifecycle_state",
            "/controller_server",
            "lifecycle state inactive",
            Severity.FAIL,
            "inactive",
            tags=("nav2", "lifecycle"),
            evidence={"expected_state": "active"},
        ),
        Event(
            base + 2.8,
            "nav2_event",
            "/bt_navigator",
            "navigation goal aborted",
            Severity.FAIL,
            tags=("nav2",),
        ),
    ]
    return _incident("lifecycle-drop", "Nav2 lifecycle server became inactive", events)


def tf_loss_demo() -> Incident:
    base = time.time() - 7.0
    events = [
        Event(base, "tf_presence", "map->odom", "transform available", value=True, tags=("tf",)),
        Event(
            base + 2.5,
            "tf_presence",
            "map->odom",
            "transform unavailable",
            Severity.FAIL,
            False,
            tags=("tf", "localization"),
        ),
        Event(
            base + 3.0,
            "nav2_event",
            "/controller_server",
            "transform timeout",
            Severity.FAIL,
            tags=("nav2", "tf"),
        ),
    ]
    return _incident("tf-loss", "localization transform lost", events)


def qos_mismatch_demo() -> Incident:
    base = time.time() - 6.0
    events = [
        Event(base, "topic_presence", "/scan", "topic present", value=True, tags=("topic",)),
        Event(
            base + 1.0,
            "qos_compatibility",
            "/scan",
            "subscriber 1 requests RELIABLE but no publisher offers RELIABLE",
            Severity.FAIL,
            False,
            tags=("topic", "qos", "connectivity", "lidar"),
        ),
        Event(
            base + 2.0,
            "localization_health",
            "/amcl",
            "laser updates unavailable",
            Severity.WARN,
            tags=("localization", "lidar"),
        ),
        Event(
            base + 3.2,
            "nav2_event",
            "/controller_server",
            "local costmap stale",
            Severity.FAIL,
            tags=("nav2", "lidar"),
        ),
    ]
    return _incident("qos-mismatch", "sensor topic exists but endpoints are QoS-incompatible", events)


def timestamp_delay_demo() -> Incident:
    base = time.time() - 7.0
    events = [
        Event(base, "topic_delay", "/imu/data", "average header delay 0.012 s", value=0.012, unit="s"),
        Event(
            base + 2.0,
            "topic_delay",
            "/imu/data",
            "average header delay 0.420 s",
            Severity.FAIL,
            0.420,
            "s",
            tags=("imu", "timing", "timestamp"),
        ),
        Event(
            base + 2.4,
            "topic_jitter",
            "/imu/data",
            "period stddev 0.08200 s",
            Severity.FAIL,
            0.082,
            "s",
            tags=("imu", "timing", "jitter"),
        ),
        Event(
            base + 3.1,
            "localization_health",
            "/localization",
            "state estimate timing degraded",
            Severity.WARN,
            tags=("localization", "timing"),
        ),
    ]
    return _incident("timestamp-delay", "sensor timestamps became delayed and unstable", events)


def resource_pressure_demo() -> Incident:
    base = time.time() - 9.0
    events = [
        Event(
            base + 1.0,
            "system_pressure",
            "host",
            "1m load exceeds CPU budget; available memory low",
            Severity.WARN,
            tags=("system", "timing"),
        ),
        Event(
            base + 2.0,
            "topic_jitter",
            "/odom",
            "period stddev 0.09500 s",
            Severity.FAIL,
            0.095,
            "s",
            tags=("odometry", "timing", "jitter"),
        ),
        Event(
            base + 3.0,
            "topic_delay",
            "/scan",
            "average header delay 0.350 s",
            Severity.FAIL,
            0.35,
            "s",
            tags=("lidar", "timing", "timestamp"),
        ),
        Event(
            base + 5.0,
            "nav2_event",
            "/controller_server",
            "control loop missed deadline",
            Severity.FAIL,
            tags=("nav2", "timing"),
        ),
    ]
    return _incident("resource-pressure", "host pressure preceded timing and navigation failures", events)


_SCENARIOS = {
    "nav2-odom": nav2_failure_demo,
    "lidar-dropout": lidar_dropout_demo,
    "lifecycle-drop": lifecycle_demo,
    "tf-loss": tf_loss_demo,
    "qos-mismatch": qos_mismatch_demo,
    "timestamp-delay": timestamp_delay_demo,
    "resource-pressure": resource_pressure_demo,
}


def scenarios() -> tuple[str, ...]:
    return tuple(sorted(_SCENARIOS))


def generate_demo(name: str) -> Incident:
    try:
        return _SCENARIOS[name]()
    except KeyError as exc:
        raise ValueError(f"unknown demo scenario {name!r}; choose from {', '.join(scenarios())}") from exc

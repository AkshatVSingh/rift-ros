from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rift_ros.collectors import LifecycleExpectation, TopicExpectation
from rift_ros.profiles import available_profiles, get_profile
from rift_ros.rosbag import BagSnapshotConfig
from rift_ros.migration import LATEST_CONFIG_SCHEMA, upgrade_config_dict


@dataclass(slots=True)
class FileConfig:
    profile: str | None = None
    namespace: str = ""
    robot_id: str | None = None
    site_id: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    window_seconds: float = 60.0
    interval_seconds: float = 5.0
    duration_seconds: float | None = 60.0
    post_trigger_seconds: float = 10.0
    consecutive_failures: int = 2
    cooldown_seconds: float = 30.0
    max_incidents: int = 10
    trigger_on_warning: bool = False
    trigger_min_events_per_cycle: int = 1
    trigger_operator_markers: bool = False
    trigger_exclude_kinds: list[str] = field(default_factory=lambda: ["probe_error", "recorder_overrun", "recorder_storage", "clock_jump", "rosbag_sidecar", "recorder_probe_health"])
    output_dir: str = "rift-incidents"
    sample_seconds: float = 1.2
    workers: int = 8
    status_file: str | None = "rift-status.json"
    lock_file: str | None = "rift-recorder.lock"
    marker_file: str | None = "rift-markers.jsonl"
    clock_jump_threshold_seconds: float = 2.0
    probe_degraded_after_cycles: int = 3
    dedup_window_seconds: float = 120.0
    startup_grace_seconds: float = 15.0
    arm_after_healthy_cycles: int = 0
    include_hostname: bool = False
    min_free_storage_mb: float = 128.0
    max_saved_incidents: int | None = 100
    max_storage_mb: float | None = 2048.0
    validation_max_probe_error_rate: float = 0.0
    validation_max_overrun_rate: float = 0.05
    validation_max_failed_cycle_rate: float = 0.0
    validation_max_p95_cycle_seconds: float | None = None
    expect_nodes: list[str] = field(default_factory=list)
    expect_topics: list[TopicExpectation] = field(default_factory=list)
    expect_tf: list[tuple[str, str]] = field(default_factory=list)
    expect_lifecycle: list[LifecycleExpectation] = field(default_factory=list)
    bag_snapshot: BagSnapshotConfig = field(default_factory=BagSnapshotConfig)


def _positive(value: Any, name: str, allow_none: bool = False) -> float | None:
    if value is None and allow_none:
        return None
    number = float(value)
    if number <= 0:
        raise ValueError(f"{name} must be positive")
    return number


def _nonnegative(value: Any, name: str) -> float:
    number = float(value)
    if number < 0:
        raise ValueError(f"{name} must be non-negative")
    return number


def _optional_positive(value: Any, name: str) -> float | None:
    if value is None:
        return None
    return _positive(value, name, allow_none=False)


def _topic_from_item(item: object) -> TopicExpectation:
    if isinstance(item, str):
        return TopicExpectation(item)
    if not isinstance(item, dict):
        raise ValueError(f"invalid topic expectation {item!r}")
    return TopicExpectation(
        topic=str(item["topic"]),
        min_hz=float(item["min_hz"]) if item.get("min_hz") is not None else None,
        max_hz=float(item["max_hz"]) if item.get("max_hz") is not None else None,
        max_jitter_seconds=(
            float(item["max_jitter_seconds"])
            if item.get("max_jitter_seconds") is not None
            else None
        ),
        max_delay_seconds=(
            float(item["max_delay_seconds"])
            if item.get("max_delay_seconds") is not None
            else None
        ),
        require_publishers=bool(item.get("require_publishers", False)),
        require_subscribers=bool(item.get("require_subscribers", False)),
        check_qos=bool(item.get("check_qos", False)),
    )


def load_config(path: str | Path) -> FileConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    data = upgrade_config_dict(raw)

    profile = data.get("profile")
    if profile is not None and profile not in available_profiles():
        raise ValueError(f"unknown profile {profile!r}; choose from {', '.join(available_profiles())}")

    identity = data.get("identity", {})
    if not isinstance(identity, dict):
        raise ValueError("identity must be an object")
    labels_raw = identity.get("labels", {}) or {}
    if not isinstance(labels_raw, dict):
        raise ValueError("identity.labels must be an object")
    if any(not str(key).strip() for key in labels_raw):
        raise ValueError("identity.labels keys must be non-empty")
    watch = data.get("watch", {})
    trigger = data.get("trigger", {})
    validation = data.get("validation", {})
    retention = data.get("retention", {})
    privacy = data.get("privacy", {})
    expectations = data.get("expectations", {})
    bag = data.get("rosbag_snapshot", {})

    topics = [_topic_from_item(item) for item in expectations.get("topics", [])]
    for topic in topics:
        for value, name in (
            (topic.min_hz, "min_hz"),
            (topic.max_hz, "max_hz"),
            (topic.max_jitter_seconds, "max_jitter_seconds"),
            (topic.max_delay_seconds, "max_delay_seconds"),
        ):
            if value is not None and value <= 0:
                raise ValueError(f"{topic.topic} {name} must be positive")
        if topic.min_hz is not None and topic.max_hz is not None and topic.min_hz > topic.max_hz:
            raise ValueError(f"{topic.topic} min_hz cannot exceed max_hz")

    transforms: list[tuple[str, str]] = []
    for item in expectations.get("transforms", []):
        if isinstance(item, str):
            if ":" not in item:
                raise ValueError(f"invalid transform {item!r}; use PARENT:CHILD")
            parent, child = item.split(":", 1)
            if not parent or not child:
                raise ValueError(f"invalid transform {item!r}; use PARENT:CHILD")
            transforms.append((parent, child))
        else:
            transforms.append((str(item[0]), str(item[1])))

    lifecycle: list[LifecycleExpectation] = []
    for item in expectations.get("lifecycle", []):
        if isinstance(item, str):
            lifecycle.append(LifecycleExpectation(item))
        else:
            lifecycle.append(LifecycleExpectation(str(item["node"]), str(item.get("state", "active"))))

    duration = _positive(watch.get("duration_seconds", 60.0), "duration_seconds", allow_none=True)
    post = _nonnegative(watch.get("post_trigger_seconds", 10.0), "post_trigger_seconds")
    cooldown = _nonnegative(watch.get("cooldown_seconds", 30.0), "cooldown_seconds")
    startup_grace = _nonnegative(watch.get("startup_grace_seconds", 15.0), "startup_grace_seconds")

    consecutive = int(watch.get("consecutive_failures", 2))
    max_incidents = int(watch.get("max_incidents", 10))
    workers = int(watch.get("workers", 8))
    arm_after_healthy = int(watch.get("arm_after_healthy_cycles", 0))
    probe_degraded_after = int(watch.get("probe_degraded_after_cycles", 3))
    dedup_window = _nonnegative(watch.get("dedup_window_seconds", 120.0), "dedup_window_seconds")
    if consecutive <= 0 or max_incidents <= 0 or workers <= 0 or probe_degraded_after <= 0:
        raise ValueError("consecutive_failures, max_incidents, workers and probe_degraded_after_cycles must be positive")
    if arm_after_healthy < 0:
        raise ValueError("arm_after_healthy_cycles must be non-negative")

    status_file = watch.get("status_file", "rift-status.json")
    lock_file = watch.get("lock_file", "rift-recorder.lock")
    marker_file = watch.get("marker_file", "rift-markers.jsonl")
    if status_file is not None:
        status_file = str(status_file)
    if lock_file is not None:
        lock_file = str(lock_file)
    if marker_file is not None:
        marker_file = str(marker_file)

    bag_snapshot = BagSnapshotConfig(
        enabled=bool(bag.get("enabled", False)),
        topics=[str(item) for item in bag.get("topics", [])],
        max_cache_mb=int(bag.get("max_cache_mb", 256)),
        storage_id=str(bag.get("storage_id", "mcap")),
        node_name=str(bag.get("node_name", "rift_rosbag2_recorder")),
        use_sim_time=bool(bag.get("use_sim_time", False)),
        startup_timeout_seconds=float(_positive(bag.get("startup_timeout_seconds", 8.0), "rosbag_snapshot.startup_timeout_seconds")),
        snapshot_timeout_seconds=float(_positive(bag.get("snapshot_timeout_seconds", 8.0), "rosbag_snapshot.snapshot_timeout_seconds")),
        settle_seconds=float(_nonnegative(bag.get("settle_seconds", 0.4), "rosbag_snapshot.settle_seconds")),
        keep_failed_session=bool(bag.get("keep_failed_session", False)),
    )
    bag_snapshot.validate()

    config = FileConfig(
        profile=profile,
        namespace=str(data.get("namespace", "")),
        robot_id=(str(identity.get("robot_id")) if identity.get("robot_id") not in {None, ""} else None),
        site_id=(str(identity.get("site_id")) if identity.get("site_id") not in {None, ""} else None),
        labels={str(key): str(value) for key, value in labels_raw.items()},
        window_seconds=float(_positive(watch.get("window_seconds", 60.0), "window_seconds")),
        interval_seconds=float(_positive(watch.get("interval_seconds", 5.0), "interval_seconds")),
        duration_seconds=duration,
        post_trigger_seconds=post,
        consecutive_failures=consecutive,
        cooldown_seconds=cooldown,
        max_incidents=max_incidents,
        trigger_on_warning=bool(watch.get("trigger_on_warning", False)),
        trigger_min_events_per_cycle=int(trigger.get("min_events_per_cycle", 1)),
        trigger_operator_markers=bool(trigger.get("operator_markers", False)),
        trigger_exclude_kinds=[str(item) for item in trigger.get("exclude_kinds", [])],
        output_dir=str(watch.get("output_dir", "rift-incidents")),
        sample_seconds=float(_positive(watch.get("sample_seconds", 1.2), "sample_seconds")),
        workers=workers,
        status_file=status_file,
        lock_file=lock_file,
        marker_file=marker_file,
        clock_jump_threshold_seconds=float(_positive(watch.get("clock_jump_threshold_seconds", 2.0), "clock_jump_threshold_seconds")),
        probe_degraded_after_cycles=probe_degraded_after,
        dedup_window_seconds=dedup_window,
        startup_grace_seconds=startup_grace,
        arm_after_healthy_cycles=arm_after_healthy,
        include_hostname=bool(privacy.get("include_hostname", False)),
        min_free_storage_mb=float(_positive(retention.get("min_free_storage_mb", 128), "min_free_storage_mb")),
        max_saved_incidents=(
            int(retention["max_saved_incidents"])
            if retention.get("max_saved_incidents") is not None
            else None
        ),
        max_storage_mb=_optional_positive(retention.get("max_storage_mb", 2048), "max_storage_mb"),
        validation_max_probe_error_rate=float(validation.get("max_probe_error_rate", 0.0)),
        validation_max_overrun_rate=float(validation.get("max_overrun_rate", 0.05)),
        validation_max_failed_cycle_rate=float(validation.get("max_failed_cycle_rate", 0.0)),
        validation_max_p95_cycle_seconds=_optional_positive(validation.get("max_p95_cycle_seconds"), "validation.max_p95_cycle_seconds"),
        expect_nodes=[str(item) for item in expectations.get("nodes", [])],
        expect_topics=topics,
        expect_tf=transforms,
        expect_lifecycle=lifecycle,
        bag_snapshot=bag_snapshot,
    )
    if config.max_saved_incidents is not None and config.max_saved_incidents <= 0:
        raise ValueError("max_saved_incidents must be positive")
    if config.trigger_min_events_per_cycle <= 0:
        raise ValueError("trigger.min_events_per_cycle must be positive")
    for name, value in (("max_probe_error_rate", config.validation_max_probe_error_rate), ("max_overrun_rate", config.validation_max_overrun_rate), ("max_failed_cycle_rate", config.validation_max_failed_cycle_rate)):
        if value < 0 or value > 1:
            raise ValueError(f"validation.{name} must be between 0 and 1")
    return config


def config_template(
    profile: str | None = "nav2",
    namespace: str = "",
    robot_id: str | None = None,
    site_id: str | None = None,
    labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    if profile is not None and profile not in available_profiles():
        raise ValueError(f"unknown profile {profile!r}")
    bag_topics: list[str] = ["/tf", "/tf_static", "/rosout"]
    if profile is not None:
        for item in get_profile(profile, namespace).topics:
            if item.topic not in bag_topics:
                bag_topics.append(item.topic)
    return {
        "schema": LATEST_CONFIG_SCHEMA,
        "profile": profile,
        "namespace": namespace,
        "identity": {"robot_id": robot_id, "site_id": site_id, "labels": dict(sorted((labels or {}).items()))},
        "watch": {
            "window_seconds": 60,
            "interval_seconds": 5,
            "duration_seconds": None,
            "post_trigger_seconds": 10,
            "startup_grace_seconds": 15,
            "arm_after_healthy_cycles": 0,
            "consecutive_failures": 2,
            "cooldown_seconds": 30,
            "max_incidents": 50,
            "trigger_on_warning": False,
            "output_dir": "rift-incidents",
            "sample_seconds": 1.2,
            "workers": 8,
            "status_file": "rift-status.json",
            "lock_file": "rift-recorder.lock",
            "marker_file": "rift-markers.jsonl",
            "clock_jump_threshold_seconds": 2.0,
            "probe_degraded_after_cycles": 3,
            "dedup_window_seconds": 120,
        },
        "trigger": {
            "min_events_per_cycle": 1,
            "operator_markers": False,
            "exclude_kinds": ["probe_error", "recorder_overrun", "recorder_storage", "clock_jump", "rosbag_sidecar", "recorder_probe_health"],
        },
        "validation": {
            "max_probe_error_rate": 0.0,
            "max_overrun_rate": 0.05,
            "max_failed_cycle_rate": 0.0,
            "max_p95_cycle_seconds": None,
        },
        "privacy": {"include_hostname": False},
        "rosbag_snapshot": {
            "enabled": False,
            "topics": bag_topics,
            "max_cache_mb": 256,
            "storage_id": "mcap",
            "node_name": "rift_rosbag2_recorder",
            "use_sim_time": False,
            "startup_timeout_seconds": 8,
            "snapshot_timeout_seconds": 8,
            "settle_seconds": 0.4,
            "keep_failed_session": False,
        },
        "retention": {
            "max_saved_incidents": 100,
            "max_storage_mb": 2048,
            "min_free_storage_mb": 128,
        },
        "expectations": {
            "nodes": [],
            "topics": [],
            "transforms": [],
            "lifecycle": [],
        },
    }


def write_config_template(
    path: str | Path,
    profile: str | None = "nav2",
    namespace: str = "",
    robot_id: str | None = None,
    site_id: str | None = None,
    labels: dict[str, str] | None = None,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config_template(profile, namespace, robot_id, site_id, labels), indent=2) + "\n", encoding="utf-8")
    return path


def config_to_dict(config: FileConfig) -> dict[str, Any]:
    return {
        "schema": LATEST_CONFIG_SCHEMA,
        "profile": config.profile,
        "namespace": config.namespace,
        "identity": {
            "robot_id": config.robot_id,
            "site_id": config.site_id,
            "labels": dict(sorted(config.labels.items())),
        },
        "watch": {
            "window_seconds": config.window_seconds,
            "interval_seconds": config.interval_seconds,
            "duration_seconds": config.duration_seconds,
            "post_trigger_seconds": config.post_trigger_seconds,
            "startup_grace_seconds": config.startup_grace_seconds,
            "arm_after_healthy_cycles": config.arm_after_healthy_cycles,
            "consecutive_failures": config.consecutive_failures,
            "cooldown_seconds": config.cooldown_seconds,
            "max_incidents": config.max_incidents,
            "trigger_on_warning": config.trigger_on_warning,
            "output_dir": config.output_dir,
            "sample_seconds": config.sample_seconds,
            "workers": config.workers,
            "status_file": config.status_file,
            "lock_file": config.lock_file,
            "marker_file": config.marker_file,
            "clock_jump_threshold_seconds": config.clock_jump_threshold_seconds,
            "probe_degraded_after_cycles": config.probe_degraded_after_cycles,
            "dedup_window_seconds": config.dedup_window_seconds,
        },
        "trigger": {
            "min_events_per_cycle": config.trigger_min_events_per_cycle,
            "operator_markers": config.trigger_operator_markers,
            "exclude_kinds": list(config.trigger_exclude_kinds),
        },
        "validation": {
            "max_probe_error_rate": config.validation_max_probe_error_rate,
            "max_overrun_rate": config.validation_max_overrun_rate,
            "max_failed_cycle_rate": config.validation_max_failed_cycle_rate,
            "max_p95_cycle_seconds": config.validation_max_p95_cycle_seconds,
        },
        "privacy": {"include_hostname": config.include_hostname},
        "rosbag_snapshot": {
            "enabled": config.bag_snapshot.enabled,
            "topics": list(config.bag_snapshot.topics),
            "max_cache_mb": config.bag_snapshot.max_cache_mb,
            "storage_id": config.bag_snapshot.storage_id,
            "node_name": config.bag_snapshot.node_name,
            "use_sim_time": config.bag_snapshot.use_sim_time,
            "startup_timeout_seconds": config.bag_snapshot.startup_timeout_seconds,
            "snapshot_timeout_seconds": config.bag_snapshot.snapshot_timeout_seconds,
            "settle_seconds": config.bag_snapshot.settle_seconds,
            "keep_failed_session": config.bag_snapshot.keep_failed_session,
        },
        "retention": {
            "max_saved_incidents": config.max_saved_incidents,
            "max_storage_mb": config.max_storage_mb,
            "min_free_storage_mb": config.min_free_storage_mb,
        },
        "expectations": {
            "nodes": list(config.expect_nodes),
            "topics": [
                {
                    "topic": item.topic,
                    "min_hz": item.min_hz,
                    "max_hz": item.max_hz,
                    "max_jitter_seconds": item.max_jitter_seconds,
                    "max_delay_seconds": item.max_delay_seconds,
                    "require_publishers": item.require_publishers,
                    "require_subscribers": item.require_subscribers,
                    "check_qos": item.check_qos,
                }
                for item in config.expect_topics
            ],
            "transforms": [f"{parent}:{child}" for parent, child in config.expect_tf],
            "lifecycle": [
                {"node": item.node, "state": item.expected_state}
                for item in config.expect_lifecycle
            ],
        },
    }


def config_digest(config: FileConfig) -> str:
    raw = json.dumps(config_to_dict(config), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def config_warnings(config: FileConfig) -> tuple[str, ...]:
    warnings: list[str] = []
    if config.sample_seconds >= config.interval_seconds:
        warnings.append("sample_seconds is >= interval_seconds; recorder overruns are likely")
    if not config.robot_id:
        warnings.append("identity.robot_id is not set; multi-robot incident attribution will be limited")
    if config.validation_max_p95_cycle_seconds is not None and config.validation_max_p95_cycle_seconds >= config.interval_seconds:
        warnings.append("validation.max_p95_cycle_seconds is >= interval_seconds; this budget will not catch recorder overruns early")
    if config.workers > 32:
        warnings.append("workers > 32 is rarely useful and may increase host pressure")
    if (
        not config.profile
        and not config.expect_nodes
        and not config.expect_topics
        and not config.expect_tf
        and not config.expect_lifecycle
    ):
        warnings.append("no profile or runtime expectations configured; incident triggering will be limited")
    if any(item.max_delay_seconds is not None for item in config.expect_topics):
        warnings.append("header-delay probes add overhead and require careful clock handling in simulation; enable them only when needed")
    if config.trigger_min_events_per_cycle > 3:
        warnings.append("trigger.min_events_per_cycle > 3 may suppress real failures with only one or two direct signals")
    if config.trigger_operator_markers:
        warnings.append("operator FAIL/WARN markers may contribute to automatic incident triggering")
    if config.marker_file is None:
        warnings.append("operator marker ingestion is disabled")
    if config.bag_snapshot.enabled and config.bag_snapshot.max_cache_mb < 64:
        warnings.append("rosbag snapshot cache below 64 MB may retain very little sensor history")
    if config.bag_snapshot.enabled:
        warnings.append(
            "rosbag2 snapshot caching is memory-bounded; Jazzy uses double buffering so peak cache "
            "memory can approach roughly 2x max_cache_mb"
        )
    if config.bag_snapshot.enabled and "/tf_static" not in config.bag_snapshot.topics:
        warnings.append("rosbag snapshot does not include /tf_static; replay context may be incomplete")
    if config.arm_after_healthy_cycles > 0 and config.duration_seconds is not None:
        minimum = config.startup_grace_seconds + config.arm_after_healthy_cycles * config.interval_seconds
        if config.duration_seconds <= minimum:
            warnings.append("duration may end before the recorder can arm")
    return tuple(warnings)

from __future__ import annotations

import shutil
import signal
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from rift_ros.buffer import RollingEventBuffer
from rift_ros.clock import ClockGuard
from rift_ros.analysis import fault_fingerprint
from rift_ros.dedup import append_duplicate_occurrence, find_recent_duplicate
from rift_ros.collectors import (
    LifecycleExpectation,
    TopicExpectation,
    collect_cycle,
    ros_available,
    runtime_metadata,
)
from rift_ros.io import register_attachment, write_incident
from rift_ros.lock import RecorderLock
from rift_ros.markers import MarkerReader
from rift_ros.models import Event, Incident, Severity
from rift_ros.retention import prune_incidents
from rift_ros.rosbag import BagSnapshotConfig, RosbagSnapshotSidecar
from rift_ros.status import atomic_json_write
from rift_ros.session import write_session_report
from rift_ros.telemetry import RecorderMetrics, performance_budget
from rift_ros.transitions import StateTracker


@dataclass(slots=True)
class WatchConfig:
    window_seconds: float = 60.0
    interval_seconds: float = 5.0
    duration_seconds: float | None = 60.0
    post_trigger_seconds: float = 10.0
    expect_nodes: list[str] = field(default_factory=list)
    expect_topics: list[TopicExpectation] = field(default_factory=list)
    expect_tf: list[tuple[str, str]] = field(default_factory=list)
    expect_lifecycle: list[LifecycleExpectation] = field(default_factory=list)
    output_dir: Path = Path("rift-incidents")
    stop_on_failure: bool = False
    consecutive_failures: int = 2
    cooldown_seconds: float = 30.0
    max_incidents: int = 10
    profile: str | None = None
    robot_id: str | None = None
    site_id: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    trigger_on_warning: bool = False
    trigger_min_events_per_cycle: int = 1
    trigger_operator_markers: bool = False
    trigger_exclude_kinds: tuple[str, ...] = ("probe_error", "recorder_overrun", "recorder_storage", "clock_jump", "rosbag_sidecar", "recorder_probe_health")
    sample_seconds: float = 1.2
    workers: int = 8
    status_file: Path | None = Path("rift-status.json")
    lock_file: Path | None = Path("rift-recorder.lock")
    marker_file: Path | None = Path("rift-markers.jsonl")
    clock_jump_threshold_seconds: float = 2.0
    probe_degraded_after_cycles: int = 3
    dedup_window_seconds: float = 120.0
    max_p95_cycle_seconds: float | None = None
    startup_grace_seconds: float = 15.0
    arm_after_healthy_cycles: int = 0
    include_hostname: bool = False
    min_free_storage_mb: float = 128.0
    max_saved_incidents: int | None = 100
    max_storage_mb: float | None = 2048.0
    config_id: str | None = None
    bag_snapshot: BagSnapshotConfig = field(default_factory=BagSnapshotConfig)
    session_id: str | None = None


def _runtime(config: WatchConfig) -> dict[str, str | int | float | None]:
    return runtime_metadata(include_hostname=config.include_hostname)


def capture_snapshot(
    expect_nodes: list[str],
    expect_topics: list[TopicExpectation],
    expect_tf: list[tuple[str, str]],
    output_dir: Path,
    expect_lifecycle: list[LifecycleExpectation] | None = None,
    profile: str | None = None,
    sample_seconds: float = 1.2,
    workers: int = 8,
    include_hostname: bool = False,
    robot_id: str | None = None,
    site_id: str | None = None,
    labels: dict[str, str] | None = None,
) -> Path:
    if not ros_available():
        raise RuntimeError("ROS 2 environment unavailable; source your ROS setup first")
    events = collect_cycle(
        expect_nodes,
        expect_topics,
        expect_tf,
        expect_lifecycle or [],
        sample_seconds=sample_seconds,
        workers=workers,
    )
    incident_id = time.strftime("snapshot-%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    incident = Incident(
        incident_id,
        time.time(),
        "manual snapshot",
        events,
        {
            "capture": "snapshot",
            "profile": profile,
            "runtime": runtime_metadata(include_hostname=include_hostname),
            "collector": {"sample_seconds": sample_seconds, "workers": workers},
            "identity": {"robot_id": robot_id, "site_id": site_id, "labels": dict(sorted((labels or {}).items()))},
        },
    )
    return write_incident(output_dir, incident)


def _preview_incident_events(config: WatchConfig, buffer: RollingEventBuffer, trigger_wall: float | None) -> list[Event]:
    events = buffer.snapshot()
    if trigger_wall is not None:
        cutoff = trigger_wall - config.window_seconds
        events = [event for event in events if event.ts >= cutoff]
    return events


def _write_triggered_incident(
    config: WatchConfig,
    buffer: RollingEventBuffer,
    trigger_wall: float | None,
    reason: str,
    trigger_evidence: list[str],
    *,
    armed_at: float | None,
    bag_sidecar: RosbagSnapshotSidecar | None = None,
    metrics: RecorderMetrics | None = None,
) -> Path:
    incident_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    incident_dir = config.output_dir / incident_id
    events = buffer.snapshot()
    if trigger_wall is not None:
        cutoff = trigger_wall - config.window_seconds
        events = [event for event in events if event.ts >= cutoff]

    bag_archive: Path | None = None
    bag_metadata: dict[str, object] = {"enabled": config.bag_snapshot.enabled}
    if bag_sidecar is not None:
        try:
            bag_archive = bag_sidecar.capture_archive(incident_dir / "rosbag2.zip")
            bag_metadata.update({
                "captured": True,
                "topics": list(config.bag_snapshot.topics),
                "max_cache_mb": config.bag_snapshot.max_cache_mb,
                "storage_id": config.bag_snapshot.storage_id,
                "attachment": "rosbag2.zip",
            })
            events.append(
                Event(
                    time.time(),
                    "rosbag_snapshot",
                    "rift",
                    "rosbag2 snapshot captured",
                    Severity.INFO,
                    tags=("rift", "rosbag2", "evidence"),
                    evidence={"topics": list(config.bag_snapshot.topics)},
                )
            )
        except Exception as exc:
            bag_metadata.update({"captured": False, "error": str(exc)})
            events.append(
                Event(
                    time.time(),
                    "rosbag_snapshot",
                    "rift",
                    f"rosbag2 snapshot capture failed: {exc}",
                    Severity.WARN,
                    tags=("rift", "rosbag2", "evidence"),
                )
            )

    incident = Incident(
        incident_id,
        time.time(),
        reason,
        events,
        {
            "pre_trigger_seconds": config.window_seconds,
            "post_trigger_seconds": config.post_trigger_seconds,
            "trigger_time": trigger_wall,
            "trigger_evidence": trigger_evidence,
            "consecutive_failures": config.consecutive_failures,
            "cooldown_seconds": config.cooldown_seconds,
            "startup_grace_seconds": config.startup_grace_seconds,
            "arm_after_healthy_cycles": config.arm_after_healthy_cycles,
            "armed_at": armed_at,
            "profile": config.profile,
            "identity": {
                "robot_id": config.robot_id,
                "site_id": config.site_id,
                "labels": dict(sorted(config.labels.items())),
            },
            "trigger_on_warning": config.trigger_on_warning,
            "trigger_policy": {
                "min_events_per_cycle": config.trigger_min_events_per_cycle,
                "operator_markers": config.trigger_operator_markers,
                "exclude_kinds": list(config.trigger_exclude_kinds),
            },
            "config_id": config.config_id,
            "session_id": config.session_id,
            "rosbag_snapshot": bag_metadata,
            "runtime": _runtime(config),
            "collector": {
                "sample_seconds": config.sample_seconds,
                "workers": config.workers,
                "interval_seconds": config.interval_seconds,
                "performance": metrics.to_dict() if metrics is not None else None,
                "performance_budget": performance_budget(metrics, config.max_p95_cycle_seconds) if metrics is not None else None,
            },
        },
    )
    path = write_incident(incident_dir, incident)
    if bag_archive is not None and bag_archive.exists():
        register_attachment(
            incident_dir,
            bag_archive,
            name="rosbag2.zip",
            role="rosbag2-snapshot",
            media_type="application/zip",
        )
    prune_incidents(
        config.output_dir,
        max_saved_incidents=config.max_saved_incidents,
        max_storage_mb=config.max_storage_mb,
    )
    return path


def _triggerable_events(events: list[Event], config: WatchConfig) -> list[Event]:
    output: list[Event] = []
    excluded = set(config.trigger_exclude_kinds)
    for event in events:
        if event.kind in excluded:
            continue
        if event.kind == "operator_marker" and not config.trigger_operator_markers:
            continue
        anomalous = event.severity != Severity.INFO if config.trigger_on_warning else event.severity == Severity.FAIL
        if anomalous:
            output.append(event)
    return output


def _cycle_failed(events: list[Event], config: WatchConfig | bool) -> bool:
    # Boolean form is kept for compatibility with the v0.5 internal helper tests.
    if isinstance(config, bool):
        return any(
            event.severity != Severity.INFO if config else event.severity == Severity.FAIL
            for event in events
        )
    return len(_triggerable_events(events, config)) >= config.trigger_min_events_per_cycle


def _trigger_evidence(events: list[Event], config: WatchConfig) -> list[str]:
    return [
        f"{event.kind}:{event.source} — {event.message}"
        for event in _triggerable_events(events, config)
    ]

def _storage_event(config: WatchConfig) -> Event:
    target = config.output_dir if config.output_dir.exists() else config.output_dir.parent
    if not target.exists():
        target = Path(".")
    free_mb = shutil.disk_usage(target).free / (1024 * 1024)
    low = free_mb < config.min_free_storage_mb
    return Event(
        time.time(),
        "recorder_storage",
        str(config.output_dir),
        (
            f"free storage {free_mb:.1f} MB below configured minimum {config.min_free_storage_mb:.1f} MB"
            if low
            else f"free storage {free_mb:.1f} MB"
        ),
        Severity.WARN if low else Severity.INFO,
        round(free_mb, 1),
        "MB",
        tags=("rift", "storage"),
        evidence={"minimum_free_mb": config.min_free_storage_mb},
    )


def _write_status(
    config: WatchConfig,
    *,
    state: str,
    cycles: int,
    written: list[Path],
    buffer: RollingEventBuffer,
    failure_streak: int,
    healthy_streak: int,
    trigger_wall: float | None,
    last_cycle_seconds: float | None,
    started_wall: float,
    armed: bool,
    armed_at: float | None,
    last_healthy_at: float | None,
    last_anomaly_at: float | None,
    metrics: RecorderMetrics | None = None,
    probe_error_streak: int = 0,
    recorder_degraded: bool = False,
    last_error: str | None = None,
    deduplicated_incidents: int = 0,
) -> None:
    if config.status_file is None:
        return
    now = time.time()
    atomic_json_write(
        config.status_file,
        {
            "schema": "rift.status/v4",
            "state": state,
            "updated_at": now,
            "started_at": started_wall,
            "uptime_seconds": max(0.0, now - started_wall),
            "profile": config.profile,
            "identity": {"robot_id": config.robot_id, "site_id": config.site_id, "labels": dict(sorted(config.labels.items()))},
            "config_id": config.config_id,
            "session_id": config.session_id,
            "cycles": cycles,
            "incidents_captured": len(written),
            "deduplicated_incidents": deduplicated_incidents,
            "last_incident": str(written[-1]) if written else None,
            "buffer_events": len(buffer),
            "failure_streak": failure_streak,
            "healthy_streak": healthy_streak,
            "armed": armed,
            "armed_at": armed_at,
            "trigger_armed": trigger_wall is not None,
            "trigger_time": trigger_wall,
            "last_healthy_at": last_healthy_at,
            "last_anomaly_at": last_anomaly_at,
            "last_cycle_seconds": last_cycle_seconds,
            "performance": metrics.to_dict() if metrics is not None else None,
            "performance_budget": performance_budget(metrics, config.max_p95_cycle_seconds) if metrics is not None else None,
            "probe_error_streak": probe_error_streak,
            "recorder_degraded": recorder_degraded,
            "marker_file": str(config.marker_file) if config.marker_file is not None else None,
            "rosbag_snapshot": {
                "enabled": config.bag_snapshot.enabled,
                "topics": list(config.bag_snapshot.topics),
                "max_cache_mb": config.bag_snapshot.max_cache_mb,
            },
            "last_error": last_error,
        },
    )


def _validate_watch_config(config: WatchConfig) -> None:
    if config.consecutive_failures <= 0:
        raise ValueError("consecutive_failures must be positive")
    if config.trigger_min_events_per_cycle <= 0:
        raise ValueError("trigger_min_events_per_cycle must be positive")
    if config.max_incidents <= 0 or config.workers <= 0:
        raise ValueError("max_incidents and workers must be positive")
    if config.sample_seconds <= 0 or config.interval_seconds <= 0 or config.window_seconds <= 0:
        raise ValueError("sample_seconds, interval_seconds and window_seconds must be positive")
    if config.post_trigger_seconds < 0 or config.startup_grace_seconds < 0:
        raise ValueError("post_trigger_seconds and startup_grace_seconds must be non-negative")
    if config.arm_after_healthy_cycles < 0:
        raise ValueError("arm_after_healthy_cycles must be non-negative")
    if config.min_free_storage_mb <= 0:
        raise ValueError("min_free_storage_mb must be positive")
    if config.clock_jump_threshold_seconds <= 0:
        raise ValueError("clock_jump_threshold_seconds must be positive")
    if config.probe_degraded_after_cycles <= 0:
        raise ValueError("probe_degraded_after_cycles must be positive")
    if config.dedup_window_seconds < 0:
        raise ValueError("dedup_window_seconds must be non-negative")
    if config.max_p95_cycle_seconds is not None and config.max_p95_cycle_seconds <= 0:
        raise ValueError("max_p95_cycle_seconds must be positive when configured")
    config.bag_snapshot.validate()


def watch(config: WatchConfig) -> list[Path]:
    if not ros_available():
        raise RuntimeError("ROS 2 environment unavailable; source your ROS setup first")
    _validate_watch_config(config)
    with RecorderLock(config.lock_file):
        return _watch_locked(config)


def _watch_locked(config: WatchConfig) -> list[Path]:
    if config.session_id is None:
        config.session_id = time.strftime("session-%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    buffer = RollingEventBuffer(config.window_seconds + config.post_trigger_seconds)
    tracker = StateTracker()
    marker_reader = MarkerReader(config.marker_file)
    clock_guard = ClockGuard(config.clock_jump_threshold_seconds)
    metrics = RecorderMetrics()
    marker_scenarios: Counter[str] = Counter()
    written: list[Path] = []
    deduplicated_incidents = 0
    started_mono = time.monotonic()
    started_wall = time.time()
    deadline = None if config.duration_seconds is None else started_mono + config.duration_seconds
    trigger_wall: float | None = None
    trigger_mono: float | None = None
    trigger_evidence: list[str] = []
    last_incident_mono: float | None = None
    failure_streak = 0
    healthy_streak = 0
    probe_error_streak = 0
    recorder_degraded = False
    cycles = 0
    interrupted = False
    stop_requested = False
    next_cycle_mono = started_mono
    armed = config.arm_after_healthy_cycles == 0
    armed_at = started_wall if armed and config.startup_grace_seconds == 0 else None
    last_healthy_at: float | None = None
    last_anomaly_at: float | None = None
    bag_sidecar: RosbagSnapshotSidecar | None = None
    bag_start_error: str | None = None
    if config.bag_snapshot.enabled:
        bag_sidecar = RosbagSnapshotSidecar(
            config.bag_snapshot,
            config.output_dir / ".rift-rosbag-cache",
        )
        try:
            bag_sidecar.start()
        except Exception as exc:
            bag_start_error = str(exc)
            bag_sidecar = None

    previous_sigterm = None
    if threading.current_thread() is threading.main_thread():
        previous_sigterm = signal.getsignal(signal.SIGTERM)

        def request_stop(_signum: int, _frame: object) -> None:
            nonlocal stop_requested
            stop_requested = True

        signal.signal(signal.SIGTERM, request_stop)

    _write_status(
        config,
        state="starting",
        cycles=0,
        written=written,
        buffer=buffer,
        failure_streak=0,
        healthy_streak=0,
        trigger_wall=None,
        last_cycle_seconds=None,
        started_wall=started_wall,
        armed=armed,
        armed_at=armed_at,
        last_healthy_at=None,
        last_anomaly_at=None,
        metrics=metrics,
        probe_error_streak=probe_error_streak,
        recorder_degraded=recorder_degraded,
        last_error=bag_start_error,
        deduplicated_incidents=deduplicated_incidents,
    )
    if bag_start_error is not None:
        buffer.append(
            Event(
                time.time(),
                "rosbag_sidecar",
                "rift",
                f"rosbag2 snapshot sidecar unavailable: {bag_start_error}",
                Severity.WARN,
                tags=("rift", "rosbag2"),
            )
        )
    elif bag_sidecar is not None:
        buffer.append(
            Event(
                time.time(),
                "rosbag_sidecar",
                "rift",
                "rosbag2 snapshot sidecar armed",
                Severity.INFO,
                tags=("rift", "rosbag2"),
                evidence={"topics": list(config.bag_snapshot.topics)},
            )
        )

    try:
        try:
            while (deadline is None or time.monotonic() < deadline) and not stop_requested:
                cycle_started = time.monotonic()
                try:
                    cycle = collect_cycle(
                        config.expect_nodes,
                        config.expect_topics,
                        config.expect_tf,
                        config.expect_lifecycle,
                        sample_seconds=config.sample_seconds,
                        workers=config.workers,
                    )
                except RuntimeError as exc:
                    _write_status(
                        config,
                        state="error",
                        cycles=cycles,
                        written=written,
                        buffer=buffer,
                        failure_streak=failure_streak,
                        healthy_streak=healthy_streak,
                        trigger_wall=trigger_wall,
                        last_cycle_seconds=time.monotonic() - cycle_started,
                        started_wall=started_wall,
                        armed=armed,
                        armed_at=armed_at,
                        last_healthy_at=last_healthy_at,
                        last_anomaly_at=last_anomaly_at,
                        metrics=metrics,
                        probe_error_streak=probe_error_streak,
                        recorder_degraded=recorder_degraded,
                        last_error=str(exc),
                        deduplicated_incidents=deduplicated_incidents,
                    )
                    raise

                now_wall_probe = time.time()
                now_mono_probe = time.monotonic()
                clock_event = clock_guard.observe(now_wall_probe, now_mono_probe)
                if clock_event is not None:
                    cycle.append(clock_event)
                for marker in marker_reader.read_new():
                    if marker.session_id is None or marker.session_id == config.session_id:
                        cycle.append(marker.to_event())
                        if marker.scenario:
                            marker_scenarios[marker.scenario] += 1
                cycle.append(_storage_event(config))
                cycle.extend(tracker.update(cycle))

                cycle_probe_errors = sum(event.kind == "probe_error" for event in cycle)
                if cycle_probe_errors:
                    probe_error_streak += 1
                else:
                    probe_error_streak = 0
                now_degraded = probe_error_streak >= config.probe_degraded_after_cycles
                if now_degraded != recorder_degraded:
                    recorder_degraded = now_degraded
                    cycle.append(
                        Event(
                            time.time(),
                            "recorder_probe_health",
                            "rift",
                            (
                                f"recorder degraded after {probe_error_streak} consecutive probe-error cycles"
                                if recorder_degraded
                                else "recorder probe health recovered"
                            ),
                            Severity.WARN if recorder_degraded else Severity.INFO,
                            probe_error_streak,
                            "cycles",
                            tags=("rift", "recorder", "probe"),
                            evidence={"degraded_after_cycles": config.probe_degraded_after_cycles},
                        )
                    )
                cycle_seconds = time.monotonic() - cycle_started
                if cycle_seconds > config.interval_seconds:
                    cycle.append(
                        Event(
                            time.time(),
                            "recorder_overrun",
                            "rift",
                            f"collector cycle {cycle_seconds:.3f}s exceeded interval {config.interval_seconds:.3f}s",
                            Severity.WARN,
                            cycle_seconds,
                            "s",
                            tags=("rift", "performance", "timing"),
                            evidence={"interval_seconds": config.interval_seconds},
                        )
                    )

                for event in cycle:
                    buffer.append(event)
                cycles += 1

                now_mono = time.monotonic()
                now_wall = time.time()
                in_grace = now_mono - started_mono < config.startup_grace_seconds
                triggerable = _triggerable_events(cycle, config)
                metrics.observe(cycle_seconds, cycle, config.interval_seconds, len(triggerable))
                failed = len(triggerable) >= config.trigger_min_events_per_cycle

                if failed:
                    last_anomaly_at = now_wall
                else:
                    last_healthy_at = now_wall

                if in_grace:
                    failure_streak = 0
                    healthy_streak = 0
                    state = "grace"
                else:
                    if failed:
                        failure_streak += 1
                        healthy_streak = 0
                        for item in _trigger_evidence(cycle, config):
                            if item not in trigger_evidence:
                                trigger_evidence.append(item)
                    else:
                        failure_streak = 0
                        healthy_streak += 1
                        if trigger_mono is None:
                            trigger_evidence = []

                    if not armed and healthy_streak >= config.arm_after_healthy_cycles:
                        armed = True
                        armed_at = now_wall
                        buffer.append(
                            Event(
                                now_wall,
                                "recorder_armed",
                                "rift",
                                f"armed after {healthy_streak} healthy cycles",
                                tags=("rift", "state"),
                            )
                        )
                    if armed and armed_at is None:
                        armed_at = now_wall
                    state = "watching" if armed else "waiting-for-healthy"

                cooled_down = (
                    last_incident_mono is None
                    or now_mono - last_incident_mono >= config.cooldown_seconds
                )

                if (
                    not in_grace
                    and armed
                    and trigger_mono is None
                    and failure_streak >= config.consecutive_failures
                    and cooled_down
                    and len(written) + deduplicated_incidents < config.max_incidents
                ):
                    trigger_mono = now_mono
                    trigger_wall = now_wall
                    buffer.append(
                        Event(
                            trigger_wall,
                            "incident_trigger",
                            "rift",
                            f"armed after {failure_streak} consecutive anomalous cycles",
                            tags=("rift", "trigger"),
                            evidence={"evidence": list(trigger_evidence), "minimum_events_per_cycle": config.trigger_min_events_per_cycle},
                        )
                    )

                if trigger_mono is not None and now_mono - trigger_mono >= config.post_trigger_seconds:
                    preview_events = _preview_incident_events(config, buffer, trigger_wall)
                    preview_fingerprint = fault_fingerprint(preview_events)
                    duplicate_of = find_recent_duplicate(
                        config.output_dir, preview_fingerprint, now=now_wall,
                        window_seconds=config.dedup_window_seconds, robot_id=config.robot_id, site_id=config.site_id,
                    )
                    if duplicate_of is not None:
                        append_duplicate_occurrence(
                            config.output_dir, fingerprint=preview_fingerprint, canonical_path=duplicate_of,
                            session_id=config.session_id, robot_id=config.robot_id, site_id=config.site_id,
                            reason="automatic anomaly trigger", ts=now_wall,
                        )
                        deduplicated_incidents += 1
                        buffer.append(Event(now_wall, "incident_deduplicated", "rift", f"suppressed duplicate of {duplicate_of}", Severity.INFO, tags=("rift", "dedup"), evidence={"fingerprint": preview_fingerprint, "canonical_path": str(duplicate_of)}))
                    else:
                        path = _write_triggered_incident(
                            config, buffer, trigger_wall, "automatic anomaly trigger", trigger_evidence,
                            armed_at=armed_at, bag_sidecar=bag_sidecar, metrics=metrics,
                        )
                        written.append(path)
                    last_incident_mono = now_mono
                    occurrence_count = len(written) + deduplicated_incidents
                    if config.bag_snapshot.enabled and duplicate_of is None and occurrence_count < config.max_incidents and not config.stop_on_failure:
                        if bag_sidecar is None:
                            bag_sidecar = RosbagSnapshotSidecar(
                                config.bag_snapshot,
                                config.output_dir / ".rift-rosbag-cache",
                            )
                        try:
                            bag_sidecar.start()
                        except Exception as exc:
                            buffer.append(
                                Event(
                                    time.time(),
                                    "rosbag_sidecar",
                                    "rift",
                                    f"rosbag2 snapshot sidecar restart failed: {exc}",
                                    Severity.WARN,
                                    tags=("rift", "rosbag2"),
                                )
                            )
                            bag_sidecar = None
                    trigger_mono = None
                    trigger_wall = None
                    trigger_evidence = []
                    failure_streak = 0
                    if config.stop_on_failure or occurrence_count >= config.max_incidents:
                        break

                _write_status(
                    config,
                    state=state,
                    cycles=cycles,
                    written=written,
                    buffer=buffer,
                    failure_streak=failure_streak,
                    healthy_streak=healthy_streak,
                    trigger_wall=trigger_wall,
                    last_cycle_seconds=cycle_seconds,
                    started_wall=started_wall,
                    armed=armed,
                    armed_at=armed_at,
                    last_healthy_at=last_healthy_at,
                    last_anomaly_at=last_anomaly_at,
                    metrics=metrics,
                    probe_error_streak=probe_error_streak,
                    recorder_degraded=recorder_degraded,
                    deduplicated_incidents=deduplicated_incidents,
                )

                next_cycle_mono += config.interval_seconds
                if deadline is not None:
                    next_cycle_mono = min(next_cycle_mono, deadline)
                sleep_for = max(0.0, next_cycle_mono - time.monotonic())
                if sleep_for:
                    time.sleep(sleep_for)
        except KeyboardInterrupt:
            interrupted = True
    finally:
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)

    if trigger_mono is not None and len(written) + deduplicated_incidents < config.max_incidents:
        reason = (
            "automatic anomaly trigger (recorder interrupted during post-window)"
            if interrupted or stop_requested
            else "automatic anomaly trigger (watch ended during post-window)"
        )
        preview_events = _preview_incident_events(config, buffer, trigger_wall)
        preview_fingerprint = fault_fingerprint(preview_events)
        duplicate_of = find_recent_duplicate(
            config.output_dir, preview_fingerprint, now=time.time(),
            window_seconds=config.dedup_window_seconds, robot_id=config.robot_id, site_id=config.site_id,
        )
        if duplicate_of is not None:
            append_duplicate_occurrence(
                config.output_dir, fingerprint=preview_fingerprint, canonical_path=duplicate_of,
                session_id=config.session_id, robot_id=config.robot_id, site_id=config.site_id, reason=reason,
            )
            deduplicated_incidents += 1
        else:
            written.append(_write_triggered_incident(
                config, buffer, trigger_wall, reason, trigger_evidence, armed_at=armed_at,
                bag_sidecar=bag_sidecar, metrics=metrics,
            ))

    if bag_sidecar is not None:
        bag_sidecar.stop(cleanup=True)

    if interrupted:
        stopped_reason = "keyboard-interrupt"
    elif stop_requested:
        stopped_reason = "signal"
    elif len(written) + deduplicated_incidents >= config.max_incidents:
        stopped_reason = "max-incidents"
    elif config.stop_on_failure and written:
        stopped_reason = "stop-on-failure"
    else:
        stopped_reason = "duration-complete" if config.duration_seconds is not None else "stopped"

    write_session_report(
        config.output_dir,
        session_id=config.session_id or "unknown-session",
        started_at=started_wall,
        stopped_at=time.time(),
        profile=config.profile,
        config_id=config.config_id,
        robot_id=config.robot_id,
        site_id=config.site_id,
        labels=config.labels,
        incidents=written,
        metrics=metrics.to_dict(),
        marker_scenarios=dict(marker_scenarios),
        armed_at=armed_at,
        last_healthy_at=last_healthy_at,
        last_anomaly_at=last_anomaly_at,
        stopped_reason=stopped_reason,
        deduplicated_incidents=deduplicated_incidents,
    )

    _write_status(
        config,
        state="stopped",
        cycles=cycles,
        written=written,
        buffer=buffer,
        failure_streak=failure_streak,
        healthy_streak=healthy_streak,
        trigger_wall=trigger_wall,
        last_cycle_seconds=None,
        started_wall=started_wall,
        armed=armed,
        armed_at=armed_at,
        last_healthy_at=last_healthy_at,
        last_anomaly_at=last_anomaly_at,
        metrics=metrics,
        probe_error_streak=probe_error_streak,
        recorder_degraded=recorder_degraded,
        deduplicated_incidents=deduplicated_incidents,
    )
    return written

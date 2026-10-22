from __future__ import annotations

import json
import os
import shutil
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from rift_ros.collectors import (
    LifecycleExpectation,
    TopicExpectation,
    collect_cycle,
    ros_available,
    runtime_metadata,
)
from rift_ros.config import FileConfig, config_warnings
from rift_ros.diagnostics import runtime_checks
from rift_ros.models import Severity
from rift_ros.rosbag import rosbag_snapshot_supported


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    name: str
    ok: bool
    required: bool
    message: str


@dataclass(frozen=True, slots=True)
class ValidationCriteria:
    max_probe_error_rate: float = 0.0
    max_overrun_rate: float = 0.05
    max_failed_cycle_rate: float = 0.0
    max_p95_cycle_seconds: float | None = None

    def validate(self) -> None:
        for name, value in (
            ("max_probe_error_rate", self.max_probe_error_rate),
            ("max_overrun_rate", self.max_overrun_rate),
            ("max_failed_cycle_rate", self.max_failed_cycle_rate),
        ):
            if value < 0 or value > 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.max_p95_cycle_seconds is not None and self.max_p95_cycle_seconds <= 0:
            raise ValueError("max_p95_cycle_seconds must be positive when configured")


@dataclass(frozen=True, slots=True)
class LiveValidationResult:
    schema: str
    config_id: str | None
    started_at: float
    runtime: dict[str, Any]
    cycles: int
    failed_cycles: int
    warning_cycles: int
    probe_errors: int
    total_events: int
    mean_cycle_seconds: float
    p95_cycle_seconds: float
    max_cycle_seconds: float
    overrun_cycles: int
    failures_by_kind: dict[str, int]
    failures_by_source: dict[str, int]
    criteria: ValidationCriteria

    @property
    def probe_error_rate(self) -> float:
        return self.probe_errors / max(1, self.total_events)

    @property
    def overrun_rate(self) -> float:
        return self.overrun_cycles / max(1, self.cycles)

    @property
    def failed_cycle_rate(self) -> float:
        return self.failed_cycles / max(1, self.cycles)

    @property
    def acceptance_reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if self.probe_error_rate > self.criteria.max_probe_error_rate:
            reasons.append(
                f"probe error rate {self.probe_error_rate:.1%} exceeds {self.criteria.max_probe_error_rate:.1%}"
            )
        if self.overrun_rate > self.criteria.max_overrun_rate:
            reasons.append(
                f"overrun rate {self.overrun_rate:.1%} exceeds {self.criteria.max_overrun_rate:.1%}"
            )
        if self.failed_cycle_rate > self.criteria.max_failed_cycle_rate:
            reasons.append(
                f"failed-cycle rate {self.failed_cycle_rate:.1%} exceeds {self.criteria.max_failed_cycle_rate:.1%}"
            )
        if (
            self.criteria.max_p95_cycle_seconds is not None
            and self.p95_cycle_seconds > self.criteria.max_p95_cycle_seconds
        ):
            reasons.append(
                f"p95 cycle time {self.p95_cycle_seconds:.3f}s exceeds "
                f"{self.criteria.max_p95_cycle_seconds:.3f}s budget"
            )
        return tuple(reasons)

    @property
    def healthy(self) -> bool:
        return not self.acceptance_reasons

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["healthy"] = self.healthy
        payload["probe_error_rate"] = round(self.probe_error_rate, 6)
        payload["overrun_rate"] = round(self.overrun_rate, 6)
        payload["failed_cycle_rate"] = round(self.failed_cycle_rate, 6)
        payload["acceptance_reasons"] = list(self.acceptance_reasons)
        return payload


def _available_memory_mb() -> float | None:
    path = Path("/proc/meminfo")
    if not path.exists():
        return None
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("MemAvailable:"):
                parts = line.split()
                if len(parts) >= 2:
                    return float(parts[1]) / 1024.0
    except OSError:
        return None
    return None


def preflight(config: FileConfig) -> list[PreflightCheck]:
    checks = [PreflightCheck(item.name, item.ok, item.required, item.message) for item in runtime_checks()]
    for warning in config_warnings(config):
        checks.append(PreflightCheck("config-warning", False, False, warning))

    output = Path(config.output_dir)
    parent = output if output.exists() else output.parent
    if not parent.exists():
        parent = Path(".")
    writable = os.access(parent, os.W_OK)
    checks.append(
        PreflightCheck(
            "output-writable",
            writable,
            True,
            f"{parent} is writable" if writable else f"{parent} is not writable",
        )
    )
    try:
        free_mb = shutil.disk_usage(parent).free / (1024 * 1024)
        checks.append(
            PreflightCheck(
                "free-storage",
                free_mb >= config.min_free_storage_mb,
                True,
                f"{free_mb:.1f} MB free; minimum {config.min_free_storage_mb:.1f} MB",
            )
        )
    except OSError as exc:
        checks.append(PreflightCheck("free-storage", False, True, str(exc)))

    if config.marker_file is not None:
        marker_parent = Path(config.marker_file).parent
        if not marker_parent.exists():
            marker_parent = Path(".")
        checks.append(
            PreflightCheck(
                "marker-journal-writable",
                os.access(marker_parent, os.W_OK),
                False,
                f"operator marker journal: {config.marker_file}",
            )
        )

    if config.bag_snapshot.enabled:
        if not ros_available():
            checks.append(
                PreflightCheck(
                    "rosbag2-snapshot",
                    False,
                    True,
                    "ROS 2 environment unavailable; cannot validate rosbag2 snapshot mode",
                )
            )
        else:
            ok, message = rosbag_snapshot_supported()
            checks.append(PreflightCheck("rosbag2-snapshot", ok, True, message))
        available_mb = _available_memory_mb()
        if available_mb is not None:
            pessimistic_mb = config.bag_snapshot.max_cache_mb * 2
            comfortable = available_mb >= pessimistic_mb + 512
            checks.append(
                PreflightCheck(
                    "rosbag-cache-memory",
                    comfortable,
                    False,
                    (
                        f"{available_mb:.0f} MB available; snapshot cache budget may use up to "
                        f"~{pessimistic_mb} MB before recorder/process overhead"
                    ),
                )
            )
    return checks


def preflight_ok(checks: list[PreflightCheck]) -> bool:
    return all(item.ok or not item.required for item in checks)


def _percentile95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[index]


def run_live_validation(
    expect_nodes: list[str],
    expect_topics: list[TopicExpectation],
    expect_tf: list[tuple[str, str]],
    expect_lifecycle: list[LifecycleExpectation],
    *,
    cycles: int = 5,
    interval_seconds: float = 2.0,
    sample_seconds: float = 1.2,
    workers: int = 8,
    config_id: str | None = None,
    criteria: ValidationCriteria | None = None,
) -> LiveValidationResult:
    if cycles <= 0:
        raise ValueError("cycles must be positive")
    if interval_seconds <= 0 or sample_seconds <= 0 or workers <= 0:
        raise ValueError("validation timing/workers must be positive")
    if not ros_available():
        raise RuntimeError("ROS 2 environment unavailable; source your ROS setup first")
    criteria = criteria or ValidationCriteria()
    criteria.validate()

    started_at = time.time()
    durations: list[float] = []
    failed_cycles = 0
    warning_cycles = 0
    probe_errors = 0
    overruns = 0
    total_events = 0
    failures_by_kind: dict[str, int] = {}
    failures_by_source: dict[str, int] = {}

    for index in range(cycles):
        started = time.monotonic()
        events = collect_cycle(
            expect_nodes,
            expect_topics,
            expect_tf,
            expect_lifecycle,
            sample_seconds=sample_seconds,
            workers=workers,
        )
        duration = time.monotonic() - started
        durations.append(duration)
        total_events += len(events)
        if duration > interval_seconds:
            overruns += 1
        failures = [event for event in events if event.severity == Severity.FAIL]
        warnings = [event for event in events if event.severity == Severity.WARN]
        if failures:
            failed_cycles += 1
        if warnings:
            warning_cycles += 1
        probe_errors += sum(event.kind == "probe_error" for event in events)
        for event in failures:
            failures_by_kind[event.kind] = failures_by_kind.get(event.kind, 0) + 1
            failures_by_source[event.source] = failures_by_source.get(event.source, 0) + 1
        if index + 1 < cycles:
            time.sleep(max(0.0, interval_seconds - duration))

    return LiveValidationResult(
        schema="rift.live-validation/v2",
        config_id=config_id,
        started_at=started_at,
        runtime=runtime_metadata(include_hostname=False),
        cycles=cycles,
        failed_cycles=failed_cycles,
        warning_cycles=warning_cycles,
        probe_errors=probe_errors,
        total_events=total_events,
        mean_cycle_seconds=round(statistics.fmean(durations), 6),
        p95_cycle_seconds=round(_percentile95(durations), 6),
        max_cycle_seconds=round(max(durations, default=0.0), 6),
        overrun_cycles=overruns,
        failures_by_kind=dict(sorted(failures_by_kind.items())),
        failures_by_source=dict(sorted(failures_by_source.items())),
        criteria=criteria,
    )


def write_validation_report(path: str | Path, result: LiveValidationResult) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target

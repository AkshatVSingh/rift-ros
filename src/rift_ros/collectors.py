from __future__ import annotations

import os
import re
import shutil
import socket
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from rift_ros.models import Event, Severity
from rift_ros.shell import run

_RATE_RE = re.compile(r"average rate:\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_STATS_RE = re.compile(
    r"min:\s*([-+0-9.eE]+)s\s+max:\s*([-+0-9.eE]+)s\s+std dev:\s*([-+0-9.eE]+)s\s+window:\s*(\d+)",
    re.IGNORECASE,
)
_DELAY_RE = re.compile(r"average delay:\s*([-+0-9.eE]+)", re.IGNORECASE)
_PUB_RE = re.compile(r"Publisher count:\s*(\d+)", re.IGNORECASE)
_SUB_RE = re.compile(r"Subscription count:\s*(\d+)", re.IGNORECASE)
_LIFECYCLE_RE = re.compile(r"^\s*([A-Za-z_]+)(?:\s*\[\d+\])?\s*$")
_ENDPOINT_RE = re.compile(r"Endpoint type:\s*(PUBLISHER|SUBSCRIPTION)", re.IGNORECASE)
_RELIABILITY_RE = re.compile(r"Reliability:\s*([A-Z_]+)", re.IGNORECASE)
_DURABILITY_RE = re.compile(r"Durability:\s*([A-Z_]+)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class TopicExpectation:
    topic: str
    min_hz: float | None = None
    max_hz: float | None = None
    max_jitter_seconds: float | None = None
    max_delay_seconds: float | None = None
    require_publishers: bool = False
    require_subscribers: bool = False
    check_qos: bool = False


@dataclass(frozen=True, slots=True)
class LifecycleExpectation:
    node: str
    expected_state: str = "active"


@dataclass(frozen=True, slots=True)
class QoSProfile:
    endpoint_type: str
    reliability: str | None = None
    durability: str | None = None


@dataclass(frozen=True, slots=True)
class TopicInfo:
    publishers: int | None
    subscribers: int | None
    raw: str = ""
    publisher_qos: tuple[QoSProfile, ...] = ()
    subscriber_qos: tuple[QoSProfile, ...] = ()


@dataclass(frozen=True, slots=True)
class RateStats:
    average_hz: float | None
    min_period_seconds: float | None = None
    max_period_seconds: float | None = None
    stddev_period_seconds: float | None = None
    window: int | None = None


@dataclass(frozen=True, slots=True)
class DelayStats:
    average_seconds: float | None
    min_seconds: float | None = None
    max_seconds: float | None = None
    stddev_seconds: float | None = None
    window: int | None = None


def ros_available() -> bool:
    return bool(shutil.which("ros2") and os.environ.get("ROS_DISTRO"))


def runtime_metadata(include_hostname: bool = False) -> dict[str, str | int | float | None]:
    metadata: dict[str, str | int | float | None] = {
        "ros_distro": os.environ.get("ROS_DISTRO"),
        "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", "0"),
        "rmw_implementation": os.environ.get("RMW_IMPLEMENTATION"),
    }
    if include_hostname:
        metadata["hostname"] = socket.gethostname()
    try:
        metadata["load_1m"] = round(os.getloadavg()[0], 3)
    except (AttributeError, OSError):
        metadata["load_1m"] = None
    return metadata


def list_nodes(timeout: float = 4.0) -> set[str]:
    result = run(["ros2", "node", "list"], timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "could not list ROS 2 nodes")
    return {item.strip() for item in result.stdout.splitlines() if item.strip()}


def list_topics(timeout: float = 4.0) -> set[str]:
    result = run(["ros2", "topic", "list"], timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "could not list ROS 2 topics")
    return {item.strip() for item in result.stdout.splitlines() if item.strip()}


def _parse_stats(output: str) -> tuple[float | None, float | None, float | None, int | None]:
    match = _STATS_RE.search(output)
    if not match:
        return None, None, None, None
    return float(match.group(1)), float(match.group(2)), float(match.group(3)), int(match.group(4))


def topic_rate_stats(topic: str, seconds: float = 1.5) -> RateStats:
    result = run(["ros2", "topic", "hz", topic], seconds)
    output = f"{result.stdout}\n{result.stderr}"
    matches = _RATE_RE.findall(output)
    if result.returncode not in {0, 124} and not matches:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"ros2 topic hz failed for {topic}")
    average = float(matches[-1]) if matches else None
    min_period, max_period, stddev, window = _parse_stats(output)
    return RateStats(average, min_period, max_period, stddev, window)


def topic_rate(topic: str, seconds: float = 1.5) -> float | None:
    return topic_rate_stats(topic, seconds).average_hz


def topic_delay_stats(topic: str, seconds: float = 1.5) -> DelayStats:
    result = run(["ros2", "topic", "delay", topic], seconds)
    output = f"{result.stdout}\n{result.stderr}"
    matches = _DELAY_RE.findall(output)
    if result.returncode not in {0, 124} and not matches:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"ros2 topic delay failed for {topic}")
    average = float(matches[-1]) if matches else None
    min_delay, max_delay, stddev, window = _parse_stats(output)
    return DelayStats(average, min_delay, max_delay, stddev, window)


def _parse_qos_profiles(raw: str) -> tuple[tuple[QoSProfile, ...], tuple[QoSProfile, ...]]:
    publishers: list[QoSProfile] = []
    subscribers: list[QoSProfile] = []
    current_type: str | None = None
    reliability: str | None = None
    durability: str | None = None

    def flush() -> None:
        nonlocal current_type, reliability, durability
        if current_type is None:
            return
        profile = QoSProfile(current_type, reliability, durability)
        if current_type == "PUBLISHER":
            publishers.append(profile)
        else:
            subscribers.append(profile)
        current_type = None
        reliability = None
        durability = None

    for line in raw.splitlines():
        endpoint = _ENDPOINT_RE.search(line)
        if endpoint:
            flush()
            current_type = endpoint.group(1).upper()
            continue
        if current_type is None:
            continue
        match = _RELIABILITY_RE.search(line)
        if match:
            reliability = match.group(1).upper()
            continue
        match = _DURABILITY_RE.search(line)
        if match:
            durability = match.group(1).upper()
    flush()
    return tuple(publishers), tuple(subscribers)


def topic_info(topic: str, timeout: float = 2.0) -> TopicInfo:
    result = run(["ros2", "topic", "info", topic, "-v"], timeout)
    raw = f"{result.stdout}\n{result.stderr}".strip()
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"ros2 topic info failed for {topic}")
    pub = _PUB_RE.search(raw)
    sub = _SUB_RE.search(raw)
    publisher_qos, subscriber_qos = _parse_qos_profiles(raw)
    return TopicInfo(
        publishers=int(pub.group(1)) if pub else None,
        subscribers=int(sub.group(1)) if sub else None,
        raw=raw,
        publisher_qos=publisher_qos,
        subscriber_qos=subscriber_qos,
    )


def qos_compatibility_issues(info: TopicInfo) -> tuple[str, ...]:
    """Return deterministic requested/offered QoS incompatibilities we can infer.

    ROS 2 reliability is requested/offered: a RELIABLE subscription cannot match a
    BEST_EFFORT-only publisher set. Durability is similar: a TRANSIENT_LOCAL
    subscription requires at least one TRANSIENT_LOCAL publisher. We intentionally
    avoid guessing about policies that are not represented in `ros2 topic info -v`.
    """

    if not info.publisher_qos or not info.subscriber_qos:
        return ()
    issues: list[str] = []
    pub_reliability = {item.reliability for item in info.publisher_qos}
    pub_durability = {item.durability for item in info.publisher_qos}
    for index, subscriber in enumerate(info.subscriber_qos, 1):
        if subscriber.reliability == "RELIABLE" and "RELIABLE" not in pub_reliability:
            issues.append(f"subscriber {index} requests RELIABLE but no publisher offers RELIABLE")
        if subscriber.durability == "TRANSIENT_LOCAL" and "TRANSIENT_LOCAL" not in pub_durability:
            issues.append(
                f"subscriber {index} requests TRANSIENT_LOCAL but no publisher offers TRANSIENT_LOCAL"
            )
    return tuple(issues)


def lifecycle_state(node: str, timeout: float = 2.0) -> str | None:
    result = run(["ros2", "lifecycle", "get", node], timeout)
    text = result.stdout.strip()
    if result.returncode != 0 or not text:
        return None
    match = _LIFECYCLE_RE.match(text)
    return match.group(1).lower() if match else text.split()[0].lower()


def tf_available(parent: str, child: str, seconds: float = 1.2) -> bool:
    result = run(["ros2", "run", "tf2_ros", "tf2_echo", parent, child], seconds)
    output = f"{result.stdout}\n{result.stderr}"
    return "Translation:" in output and "Rotation:" in output


def _memory_available_mb() -> float | None:
    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return None
    for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("MemAvailable:"):
            parts = line.split()
            if len(parts) >= 2:
                return round(float(parts[1]) / 1024.0, 1)
    return None


def system_snapshot(now: float | None = None) -> Event:
    now = time.time() if now is None else now
    load = None
    try:
        load = round(os.getloadavg()[0], 3)
    except (AttributeError, OSError):
        pass
    disk = shutil.disk_usage("/")
    memory_mb = _memory_available_mb()
    disk_gb = round(disk.free / (1024**3), 2)
    cpu_count = os.cpu_count() or 1
    reasons: list[str] = []
    if load is not None and load > cpu_count * 1.5:
        reasons.append(f"1m load {load} exceeds 1.5x CPU count")
    if memory_mb is not None and memory_mb < 512:
        reasons.append(f"available memory low ({memory_mb:.0f} MB)")
    if disk_gb < 1.0:
        reasons.append(f"root filesystem free space low ({disk_gb:.2f} GB)")
    evidence = {
        "load_1m": load,
        "cpu_count": cpu_count,
        "memory_available_mb": memory_mb,
        "disk_free_gb": disk_gb,
        "pressure_reasons": reasons,
    }
    if reasons:
        return Event(
            now,
            "system_pressure",
            "host",
            "; ".join(reasons),
            Severity.WARN,
            tags=("system", "timing"),
            evidence=evidence,
        )
    return Event(
        now,
        "system_snapshot",
        "host",
        "host resource snapshot",
        tags=("system",),
        evidence=evidence,
    )


def _qos_to_dict(profile: QoSProfile) -> dict[str, str | None]:
    return {
        "endpoint_type": profile.endpoint_type,
        "reliability": profile.reliability,
        "durability": profile.durability,
    }


def _probe_error(source: str, probe: str, exc: Exception) -> Event:
    return Event(
        time.time(),
        "probe_error",
        source,
        f"{probe} probe failed: {exc}",
        Severity.WARN,
        tags=("rift", "probe"),
        evidence={"probe": probe, "error_type": type(exc).__name__},
    )


def collect_cycle(
    expect_nodes: list[str],
    expect_topics: list[TopicExpectation],
    expect_tf: list[tuple[str, str]],
    expect_lifecycle: list[LifecycleExpectation] | None = None,
    sample_seconds: float = 1.2,
    workers: int = 8,
) -> list[Event]:
    """Collect one runtime evidence cycle.

    Expensive topic-rate, delay, QoS, TF and lifecycle probes run concurrently so
    recorder cadence scales with the slowest probe rather than the sum of every probe.
    """

    started_mono = time.monotonic()
    now = time.time()
    nodes = list_nodes()
    topics = list_topics()
    events: list[Event] = [
        Event(
            now,
            "graph_snapshot",
            "ros_graph",
            f"{len(nodes)} nodes / {len(topics)} topics",
            evidence={"node_count": len(nodes), "topic_count": len(topics)},
        ),
        system_snapshot(now),
    ]

    for node in expect_nodes:
        present = node in nodes
        events.append(
            Event(
                now,
                "node_presence",
                node,
                "node present" if present else "expected node missing",
                Severity.INFO if present else Severity.FAIL,
                present,
                tags=("graph", "node"),
            )
        )

    present_topics: list[TopicExpectation] = []
    for expectation in expect_topics:
        present = expectation.topic in topics
        events.append(
            Event(
                now,
                "topic_presence",
                expectation.topic,
                "topic present" if present else "expected topic missing",
                Severity.INFO if present else Severity.FAIL,
                present,
                tags=("graph", "topic"),
            )
        )
        if present:
            present_topics.append(expectation)

    tasks: list[tuple[str, str, object, Callable[[object], list[Event]]]] = []
    pool_workers = max(1, int(workers))
    with ThreadPoolExecutor(max_workers=pool_workers, thread_name_prefix="rift-probe") as executor:
        for expectation in present_topics:
            needs_info = (
                expectation.require_publishers
                or expectation.require_subscribers
                or expectation.check_qos
            )
            if needs_info:
                future = executor.submit(topic_info, expectation.topic, max(2.0, sample_seconds))

                def build_info(value: object, exp: TopicExpectation = expectation) -> list[Event]:
                    info = value
                    assert isinstance(info, TopicInfo)
                    output: list[Event] = []
                    evidence = {
                        "publishers": info.publishers,
                        "subscribers": info.subscribers,
                        "publisher_qos": [_qos_to_dict(item) for item in info.publisher_qos],
                        "subscriber_qos": [_qos_to_dict(item) for item in info.subscriber_qos],
                    }
                    if exp.require_publishers:
                        ok = info.publishers is not None and info.publishers > 0
                        output.append(
                            Event(
                                time.time(),
                                "topic_publishers",
                                exp.topic,
                                f"publisher count {info.publishers}"
                                if info.publishers is not None
                                else "publisher count unavailable",
                                Severity.INFO if ok else Severity.FAIL,
                                info.publishers,
                                evidence=evidence,
                                tags=("topic", "connectivity"),
                            )
                        )
                    if exp.require_subscribers:
                        ok = info.subscribers is not None and info.subscribers > 0
                        output.append(
                            Event(
                                time.time(),
                                "topic_subscribers",
                                exp.topic,
                                f"subscriber count {info.subscribers}"
                                if info.subscribers is not None
                                else "subscriber count unavailable",
                                Severity.INFO if ok else Severity.FAIL,
                                info.subscribers,
                                evidence=evidence,
                                tags=("topic", "connectivity"),
                            )
                        )
                    if exp.check_qos:
                        issues = qos_compatibility_issues(info)
                        output.append(
                            Event(
                                time.time(),
                                "qos_compatibility",
                                exp.topic,
                                "; ".join(issues) if issues else "no requested/offered QoS mismatch detected",
                                Severity.FAIL if issues else Severity.INFO,
                                not bool(issues),
                                tags=("topic", "qos", "connectivity"),
                                evidence={**evidence, "issues": list(issues)},
                            )
                        )
                    return output

                tasks.append((expectation.topic, "topic_info", future, build_info))

            if (
                expectation.min_hz is not None
                or expectation.max_hz is not None
                or expectation.max_jitter_seconds is not None
            ):
                future = executor.submit(topic_rate_stats, expectation.topic, sample_seconds)

                def build_rate(value: object, exp: TopicExpectation = expectation) -> list[Event]:
                    stats = value
                    assert isinstance(stats, RateStats)
                    hz = stats.average_hz
                    too_low = exp.min_hz is not None and (hz is None or hz < exp.min_hz)
                    too_high = exp.max_hz is not None and hz is not None and hz > exp.max_hz
                    failed = too_low or too_high
                    message = "rate unavailable" if hz is None else f"topic rate {hz:.2f} Hz"
                    evidence = {
                        "minimum_hz": exp.min_hz,
                        "maximum_hz": exp.max_hz,
                        "min_period_seconds": stats.min_period_seconds,
                        "max_period_seconds": stats.max_period_seconds,
                        "stddev_period_seconds": stats.stddev_period_seconds,
                        "window": stats.window,
                    }
                    output = [
                        Event(
                            time.time(),
                            "topic_rate",
                            exp.topic,
                            message,
                            Severity.FAIL if failed else Severity.INFO,
                            hz,
                            "Hz",
                            tags=("topic", "timing"),
                            evidence=evidence,
                        )
                    ]
                    if exp.max_jitter_seconds is not None:
                        jitter = stats.stddev_period_seconds
                        jitter_failed = jitter is None or jitter > exp.max_jitter_seconds
                        output.append(
                            Event(
                                time.time(),
                                "topic_jitter",
                                exp.topic,
                                "jitter unavailable"
                                if jitter is None
                                else f"period stddev {jitter:.5f} s",
                                Severity.FAIL if jitter_failed else Severity.INFO,
                                jitter,
                                "s",
                                tags=("topic", "timing", "jitter"),
                                evidence={"maximum_jitter_seconds": exp.max_jitter_seconds},
                            )
                        )
                    return output

                tasks.append((expectation.topic, "topic_rate", future, build_rate))

            if expectation.max_delay_seconds is not None:
                future = executor.submit(topic_delay_stats, expectation.topic, sample_seconds)

                def build_delay(value: object, exp: TopicExpectation = expectation) -> list[Event]:
                    stats = value
                    assert isinstance(stats, DelayStats)
                    delay = stats.average_seconds
                    failed = delay is None or delay > float(exp.max_delay_seconds)
                    evidence = {
                        "maximum_delay_seconds": exp.max_delay_seconds,
                        "min_seconds": stats.min_seconds,
                        "max_seconds": stats.max_seconds,
                        "stddev_seconds": stats.stddev_seconds,
                        "window": stats.window,
                    }
                    return [
                        Event(
                            time.time(),
                            "topic_delay",
                            exp.topic,
                            "delay unavailable"
                            if delay is None
                            else f"average header delay {delay:.3f} s",
                            Severity.FAIL if failed else Severity.INFO,
                            delay,
                            "s",
                            tags=("topic", "timing", "timestamp"),
                            evidence=evidence,
                        )
                    ]

                tasks.append((expectation.topic, "topic_delay", future, build_delay))

        for parent, child in expect_tf:
            source = f"{parent}->{child}"
            future = executor.submit(tf_available, parent, child, sample_seconds)

            def build_tf(value: object, p: str = parent, c: str = child) -> list[Event]:
                available = bool(value)
                return [
                    Event(
                        time.time(),
                        "tf_presence",
                        f"{p}->{c}",
                        "transform available" if available else "transform unavailable",
                        Severity.INFO if available else Severity.FAIL,
                        available,
                        tags=("tf", "localization"),
                        evidence={"parent": p, "child": c},
                    )
                ]

            tasks.append((source, "tf", future, build_tf))

        for expectation in expect_lifecycle or []:
            future = executor.submit(lifecycle_state, expectation.node, max(2.0, sample_seconds))

            def build_lifecycle(
                value: object, exp: LifecycleExpectation = expectation
            ) -> list[Event]:
                state = value if isinstance(value, str) else None
                ok = state == exp.expected_state.lower()
                return [
                    Event(
                        time.time(),
                        "lifecycle_state",
                        exp.node,
                        f"lifecycle state {state or 'unavailable'}",
                        Severity.INFO if ok else Severity.FAIL,
                        state,
                        tags=("lifecycle", "nav2"),
                        evidence={"expected_state": exp.expected_state},
                    )
                ]

            tasks.append((expectation.node, "lifecycle", future, build_lifecycle))

        for source, probe, future, builder in tasks:
            try:
                events.extend(builder(future.result()))
            except Exception as exc:  # individual probes must not kill the recorder
                events.append(_probe_error(source, probe, exc))

    duration = time.monotonic() - started_mono
    events.append(
        Event(
            time.time(),
            "collector_cycle",
            "rift",
            f"cycle completed in {duration:.3f} s with {len(tasks)} concurrent probes",
            tags=("rift", "performance"),
            evidence={
                "duration_seconds": round(duration, 6),
                "probe_count": len(tasks),
                "worker_count": pool_workers,
            },
        )
    )
    return events

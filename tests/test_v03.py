import json
import time

from rift_ros import collectors
from rift_ros.collectors import QoSProfile, TopicInfo, qos_compatibility_issues
from rift_ros.config import load_config, write_config_template
from rift_ros.models import Event, Severity
from rift_ros.retention import prune_incidents
from rift_ros.selftest import run_self_test
from rift_ros.status import atomic_json_write, read_status
from rift_ros.transitions import StateTracker


def test_rate_stats_parses_ros2_output(monkeypatch):
    class R:
        returncode = 124
        stdout = "average rate: 19.500\n\tmin: 0.049s max: 0.055s std dev: 0.00120s window: 42\n"
        stderr = ""
        timed_out = True

    monkeypatch.setattr(collectors, "run", lambda *a, **k: R())
    stats = collectors.topic_rate_stats("/scan", 0.1)
    assert stats.average_hz == 19.5
    assert stats.stddev_period_seconds == 0.0012
    assert stats.window == 42


def test_delay_stats_parses_ros2_output(monkeypatch):
    class R:
        returncode = 124
        stdout = "average delay: 0.123\n\tmin: 0.100s max: 0.150s std dev: 0.01000s window: 10\n"
        stderr = ""
        timed_out = True

    monkeypatch.setattr(collectors, "run", lambda *a, **k: R())
    stats = collectors.topic_delay_stats("/imu/data", 0.1)
    assert stats.average_seconds == 0.123
    assert stats.max_seconds == 0.15


def test_qos_parser_and_mismatch(monkeypatch):
    class R:
        returncode = 0
        stdout = """Publisher count: 1
Endpoint type: PUBLISHER
QoS profile:
  Reliability: BEST_EFFORT
  Durability: VOLATILE
Subscription count: 1
Endpoint type: SUBSCRIPTION
QoS profile:
  Reliability: RELIABLE
  Durability: VOLATILE
"""
        stderr = ""
        timed_out = False

    monkeypatch.setattr(collectors, "run", lambda *a, **k: R())
    info = collectors.topic_info("/scan")
    assert info.publisher_qos[0].reliability == "BEST_EFFORT"
    assert qos_compatibility_issues(info)


def test_qos_compatible_when_reliable_publisher_exists():
    info = TopicInfo(
        1,
        1,
        publisher_qos=(QoSProfile("PUBLISHER", "RELIABLE", "VOLATILE"),),
        subscriber_qos=(QoSProfile("SUBSCRIPTION", "RELIABLE", "VOLATILE"),),
    )
    assert qos_compatibility_issues(info) == ()


def test_state_tracker_emits_degrade_and_recovery():
    tracker = StateTracker()
    assert tracker.update([Event(1, "topic_rate", "/odom", "ok")]) == []
    degraded = tracker.update([Event(2, "topic_rate", "/odom", "low", Severity.FAIL)])
    assert degraded and degraded[0].severity == Severity.FAIL
    recovered = tracker.update([Event(3, "topic_rate", "/odom", "ok")])
    assert recovered and "recovered" in recovered[0].message


def test_config_v2_roundtrip_fields(tmp_path):
    path = write_config_template(tmp_path / "rift.json")
    data = json.loads(path.read_text())
    assert data["schema"] in {"rift.config/v3", "rift.config/v4", "rift.config/v5", "rift.config/v6", "rift.config/v7"}
    config = load_config(path)
    assert config.workers == 8
    assert config.max_saved_incidents == 100
    assert config.expect_topics == []


def test_retention_prunes_oldest(tmp_path):
    for index in range(3):
        directory = tmp_path / f"i{index}"
        directory.mkdir()
        (directory / "bundle.json").write_text("{}")
        (directory / "payload").write_text("x" * 10)
        time.sleep(0.01)
    result = prune_incidents(tmp_path, max_saved_incidents=2)
    assert result.kept == 2
    assert not (tmp_path / "i0").exists()


def test_status_atomic_roundtrip(tmp_path):
    path = atomic_json_write(tmp_path / "status.json", {"state": "watching", "cycles": 3})
    assert read_status(path)["cycles"] == 3


def test_self_test_exercises_all_scenarios(tmp_path):
    results = run_self_test(tmp_path)
    assert len(results) >= 7
    assert all(item.passed for item in results)


def test_collect_cycle_runs_probe_failures_as_evidence(monkeypatch):
    monkeypatch.setattr(collectors, "list_nodes", lambda: set())
    monkeypatch.setattr(collectors, "list_topics", lambda: {"/scan"})
    monkeypatch.setattr(collectors, "topic_rate_stats", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    events = collectors.collect_cycle([], [collectors.TopicExpectation("/scan", min_hz=5)], [], workers=2)
    assert any(event.kind == "probe_error" for event in events)
    assert any(event.kind == "collector_cycle" for event in events)

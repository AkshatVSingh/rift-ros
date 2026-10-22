import pytest

from rift_ros.analysis import fault_fingerprint, summarize
from rift_ros.collectors import (
    LifecycleExpectation,
    TopicExpectation,
    lifecycle_state,
    topic_info,
)
from rift_ros.demo import generate_demo, scenarios
from rift_ros.io import verify_bundle, write_incident
from rift_ros.models import Event, Incident, Severity
from rift_ros.profiles import get_profile


def test_schema_v2():
    assert Incident("x", 0, "r", []).to_dict()["schema"] == "rift.incident/v2"


def test_fingerprint_stable_across_order():
    a = Event(1, "topic_rate", "/odom", "low", Severity.FAIL)
    b = Event(2, "tf_presence", "map->odom", "gone", Severity.FAIL)
    assert fault_fingerprint([a, b]) == fault_fingerprint([b, a])


def test_healthy_fingerprint():
    assert fault_fingerprint([Event(1, "x", "s", "ok")]) == "healthy"


def test_summary_has_first_anomaly():
    s = summarize([Event(1, "x", "ok", "ok"), Event(2, "y", "bad", "no", Severity.FAIL)])
    assert s.first_anomaly == "y:bad"


def test_nav2_profile_namespace():
    p = get_profile("nav2", "robot1")
    assert "/robot1/controller_server" in p.nodes
    assert ("robot1/map", "robot1/odom") in p.transforms
    assert p.lifecycle[0].expected_state == "active"


def test_topic_info_parse(monkeypatch):
    class R:
        returncode = 0
        stdout = "Publisher count: 2\nSubscription count: 3\n"
        stderr = ""
        timed_out = False

    import rift_ros.collectors as collectors

    monkeypatch.setattr(collectors, "run", lambda *a, **k: R())
    info = topic_info("/scan")
    assert info.publishers == 2 and info.subscribers == 3


def test_lifecycle_state_parse(monkeypatch):
    class R:
        returncode = 0
        stdout = "active [3]\n"
        stderr = ""
        timed_out = False

    import rift_ros.collectors as collectors

    monkeypatch.setattr(collectors, "run", lambda *a, **k: R())
    assert lifecycle_state("/controller_server") == "active"


def test_bundle_integrity(tmp_path):
    path = write_incident(tmp_path / "i", Incident("id", 2, "why", [Event(1, "x", "s", "m")]))
    ok, problems = verify_bundle(path)
    assert ok and not problems
    (tmp_path / "i" / "events.jsonl").write_text("tampered", encoding="utf-8")
    ok, problems = verify_bundle(tmp_path / "i")
    assert not ok and "events.jsonl checksum mismatch" in problems


def test_all_demo_scenarios_are_incidents():
    for scenario in scenarios():
        incident = generate_demo(scenario)
        assert incident.metadata["scenario"] == scenario
        assert any(e.severity == Severity.FAIL for e in incident.events)


def test_topic_expectation_supports_max():
    exp = TopicExpectation("/scan", min_hz=5, max_hz=20, require_publishers=True)
    assert exp.max_hz == 20 and exp.require_publishers


def test_lifecycle_expectation_default_active():
    assert LifecycleExpectation("/foo").expected_state == "active"


def test_pack_and_read_zip(tmp_path):
    from rift_ros.io import pack_bundle, read_incident

    write_incident(tmp_path / "bundle", Incident("zip-id", 2, "why", [Event(1, "x", "s", "m")]))
    archive = pack_bundle(tmp_path / "bundle")
    assert archive.suffix == ".zip"
    assert verify_bundle(archive)[0]
    assert read_incident(archive).incident_id == "zip-id"


def test_pack_rejects_tampered_bundle(tmp_path):
    from rift_ros.io import pack_bundle

    write_incident(tmp_path / "bundle", Incident("zip-id", 2, "why", []))
    (tmp_path / "bundle" / "summary.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        pack_bundle(tmp_path / "bundle")

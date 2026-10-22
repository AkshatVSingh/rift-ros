import json

from rift_ros.analysis import fault_fingerprint
from rift_ros.config import config_template, load_config
from rift_ros.dedup import append_duplicate_occurrence, find_recent_duplicate, list_duplicate_occurrences
from rift_ros.io import write_incident
from rift_ros.models import Event, Incident, Severity
from rift_ros.reviews import list_reviews, update_review
from rift_ros.session import list_session_reports, write_session_report


def _failed_incident(path, iid="i", robot="amr-1"):
    event = Event(10, "topic_rate", "/odom", "slow", Severity.FAIL, 5.0, "Hz")
    write_incident(path, Incident(iid, 10, "test", [event], {"identity": {"robot_id": robot, "site_id": "lab", "labels": {}}, "session_id": "s1"}))
    return event


def test_config_v7_adds_dedup_window(tmp_path):
    data = config_template()
    assert data["schema"] == "rift.config/v7"
    assert data["watch"]["dedup_window_seconds"] == 120
    path = tmp_path / "rift.json"
    path.write_text(json.dumps(data))
    assert load_config(path).dedup_window_seconds == 120


def test_find_recent_duplicate_is_identity_scoped(tmp_path):
    event = _failed_incident(tmp_path / "a")
    fingerprint = fault_fingerprint([event])
    assert find_recent_duplicate(tmp_path, fingerprint, now=10**12, window_seconds=10**12, robot_id="amr-1", site_id="lab") == tmp_path / "a"
    assert find_recent_duplicate(tmp_path, fingerprint, now=10**12, window_seconds=10**12, robot_id="amr-2", site_id="lab") is None


def test_duplicate_ledger_roundtrip(tmp_path):
    append_duplicate_occurrence(tmp_path, fingerprint="abc", canonical_path=tmp_path / "a", session_id="s", robot_id="r", site_id="lab", reason="same fault", ts=4)
    rows = list_duplicate_occurrences(tmp_path)
    assert len(rows) == 1
    assert rows[0].fingerprint == "abc"
    assert rows[0].robot_id == "r"


def test_review_store_does_not_modify_incident(tmp_path):
    incident = tmp_path / "incident"
    _failed_incident(incident, "incident-1")
    before = (incident / "incident.json").read_bytes()
    record = update_review(tmp_path / "reviews.json", incident, status="acknowledged", owner="akshat", note="checking odom", actor="akshat", labels={"priority": "p1"})
    after = (incident / "incident.json").read_bytes()
    assert before == after
    assert record.status == "acknowledged"
    assert record.labels["priority"] == "p1"
    assert list_reviews(tmp_path / "reviews.json")[0].notes[0].text == "checking odom"


def test_session_v3_tracks_deduplicated_occurrences(tmp_path):
    write_session_report(tmp_path, session_id="s", started_at=1, stopped_at=2, profile=None, config_id=None, metrics={"cycles": 1, "anomalous_cycles": 1}, marker_scenarios={}, armed_at=1, last_healthy_at=None, last_anomaly_at=2, stopped_reason="done", deduplicated_incidents=3)
    row = list_session_reports(tmp_path)[0]
    assert row.deduplicated_incidents == 3


def test_watcher_deduplicates_repeated_same_fault(monkeypatch, tmp_path):
    import time
    from rift_ros import watcher

    monkeypatch.setattr(watcher, "ros_available", lambda: True)
    monkeypatch.setattr(
        watcher,
        "collect_cycle",
        lambda *args, **kwargs: [Event(time.time(), "topic_rate", "/odom", "slow", Severity.FAIL)],
    )
    cfg = watcher.WatchConfig(
        interval_seconds=0.001,
        duration_seconds=0.02,
        post_trigger_seconds=0,
        startup_grace_seconds=0,
        consecutive_failures=1,
        cooldown_seconds=0,
        dedup_window_seconds=60,
        max_incidents=3,
        output_dir=tmp_path / "incidents",
        status_file=None,
        lock_file=None,
        marker_file=None,
        min_free_storage_mb=1,
    )
    written = watcher.watch(cfg)
    assert len(written) == 1
    assert len(list_duplicate_occurrences(cfg.output_dir)) == 2
    session = list_session_reports(cfg.output_dir)[0]
    assert session.incidents_captured == 1
    assert session.deduplicated_incidents == 2

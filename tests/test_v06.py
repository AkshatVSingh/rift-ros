import json

from rift_ros.catalog import catalog
from rift_ros.clock import ClockGuard
from rift_ros.config import config_template, load_config
from rift_ros.io import write_incident
from rift_ros.markers import MarkerReader, append_marker
from rift_ros.migration import upgrade_config_dict
from rift_ros.models import Event, Incident, Severity
from rift_ros.telemetry import RecorderMetrics
from rift_ros.validation import ValidationCriteria, run_live_validation
from rift_ros import validation, watcher


def test_v5_config_template_contains_trigger_marker_and_validation():
    data = config_template("nav2")
    assert data["schema"] in {"rift.config/v6", "rift.config/v7"}
    assert data["watch"]["marker_file"] == "rift-markers.jsonl"
    assert data["trigger"]["min_events_per_cycle"] == 1
    assert "probe_error" in data["trigger"]["exclude_kinds"]
    assert data["validation"]["max_overrun_rate"] == 0.05


def test_upgrade_config_v4_to_v5_preserves_user_values():
    old = {
        "schema": "rift.config/v4",
        "profile": "nav2",
        "watch": {"interval_seconds": 7},
        "expectations": {},
    }
    upgraded = upgrade_config_dict(old)
    assert upgraded["schema"] in {"rift.config/v6", "rift.config/v7"}
    assert upgraded["watch"]["interval_seconds"] == 7
    assert upgraded["watch"]["marker_file"] == "rift-markers.jsonl"
    assert upgraded["trigger"]["operator_markers"] is False


def test_load_old_config_is_migrated(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"schema": "rift.config/v4", "watch": {}, "expectations": {}}))
    cfg = load_config(path)
    assert cfg.marker_file == "rift-markers.jsonl"
    assert cfg.trigger_min_events_per_cycle == 1


def test_marker_journal_incremental_read(tmp_path):
    path = tmp_path / "markers.jsonl"
    reader = MarkerReader(path)
    append_marker(path, "fault injected", severity=Severity.WARN, scenario="tf-loss", tags=("validation",))
    first = reader.read_new()
    assert len(first) == 1
    assert first[0].message == "fault injected"
    assert first[0].scenario == "tf-loss"
    assert reader.read_new() == []
    append_marker(path, "fault recovered")
    assert [item.message for item in reader.read_new()] == ["fault recovered"]


def test_trigger_policy_filters_infrastructure_and_operator_marker_by_default():
    config = watcher.WatchConfig()
    events = [
        Event(1, "recorder_storage", "rift", "low", Severity.FAIL),
        Event(2, "operator_marker", "operator", "test", Severity.FAIL),
        Event(3, "topic_rate", "/odom", "slow", Severity.FAIL),
    ]
    triggerable = watcher._triggerable_events(events, config)
    assert [(event.kind, event.source) for event in triggerable] == [("topic_rate", "/odom")]


def test_trigger_quorum_requires_multiple_events():
    config = watcher.WatchConfig(trigger_min_events_per_cycle=2)
    one = [Event(1, "topic_rate", "/odom", "slow", Severity.FAIL)]
    two = one + [Event(1.1, "tf_presence", "map->odom", "missing", Severity.FAIL)]
    assert not watcher._cycle_failed(one, config)
    assert watcher._cycle_failed(two, config)


def test_clock_guard_detects_wall_clock_jump():
    guard = ClockGuard(1.0)
    assert guard.observe(100.0, 10.0) is None
    event = guard.observe(105.0, 11.0)
    assert event is not None
    assert event.kind == "clock_jump"
    assert event.severity == Severity.WARN


def test_recorder_metrics_tracks_percentiles_and_markers():
    metrics = RecorderMetrics()
    metrics.observe(0.5, [Event(1, "operator_marker", "operator", "x")], 1.0, 0)
    metrics.observe(1.5, [Event(2, "probe_error", "x", "bad", Severity.WARN)], 1.0, 1)
    data = metrics.to_dict()
    assert data["cycles"] == 2
    assert data["overrun_cycles"] == 1
    assert data["probe_errors"] == 1
    assert data["markers_ingested"] == 1
    assert data["cycle_seconds_p95"] == 1.5


def test_catalog_reads_bundle(tmp_path):
    incident = Incident("i-1", 10.0, "test", [Event(10.0, "topic_rate", "/odom", "slow", Severity.FAIL)])
    write_incident(tmp_path / "i-1", incident)
    rows = catalog([tmp_path])
    assert len(rows) == 1
    assert rows[0].incident_id == "i-1"
    assert rows[0].failures == 1
    assert rows[0].integrity_ok


def test_live_validation_acceptance_thresholds(monkeypatch):
    monkeypatch.setattr(validation, "ros_available", lambda: True)
    monkeypatch.setattr(validation, "runtime_metadata", lambda include_hostname=False: {})
    monkeypatch.setattr(
        validation,
        "collect_cycle",
        lambda *args, **kwargs: [Event(1, "probe_error", "scan", "timeout", Severity.WARN)],
    )
    result = run_live_validation(
        [], [], [], [], cycles=2, interval_seconds=0.01, sample_seconds=0.001, workers=1,
        criteria=ValidationCriteria(max_probe_error_rate=0.0, max_overrun_rate=1.0, max_failed_cycle_rate=1.0),
    )
    assert not result.healthy
    assert result.probe_error_rate == 1.0
    assert any("probe error rate" in reason for reason in result.acceptance_reasons)


def test_watcher_writes_healthy_session_report(monkeypatch, tmp_path):
    from rift_ros.session import list_session_reports
    monkeypatch.setattr(watcher, "ros_available", lambda: True)
    monkeypatch.setattr(
        watcher,
        "collect_cycle",
        lambda *args, **kwargs: [Event(1, "topic_rate", "/odom", "healthy", Severity.INFO, 50.0, "Hz")],
    )
    cfg = watcher.WatchConfig(
        interval_seconds=0.001,
        duration_seconds=0.004,
        startup_grace_seconds=0,
        output_dir=tmp_path / "incidents",
        status_file=None,
        lock_file=None,
        marker_file=None,
        min_free_storage_mb=1,
    )
    assert watcher.watch(cfg) == []
    rows = list_session_reports(cfg.output_dir)
    assert len(rows) == 1
    assert rows[0].incidents_captured == 0
    assert rows[0].anomalous_cycles == 0
    assert rows[0].cycles > 0


def test_field_validation_scores_healthy_session_without_incident(tmp_path):
    from rift_ros.fieldlab import score_validation, validation_plan
    from rift_ros.session import write_session_report

    session = write_session_report(
        tmp_path,
        session_id="session-test",
        started_at=1.0,
        stopped_at=101.0,
        profile="nav2",
        config_id="cfg",
        incidents=[],
        metrics={"cycles": 20, "anomalous_cycles": 0},
        marker_scenarios={"healthy-long-run": 1},
        armed_at=2.0,
        last_healthy_at=100.0,
        last_anomaly_at=None,
        stopped_reason="duration-complete",
    )
    result = score_validation(validation_plan(), [session])
    healthy = next(row for row in result["results"] if row["scenario_id"] == "healthy-long-run")
    assert healthy["passed"] is True
    assert healthy["session_ids"] == ["session-test"]


def test_export_timeline_csv_and_json(tmp_path):
    from rift_ros.export import export_timeline
    incident = Incident(
        "i-export",
        10.0,
        "test",
        [
            Event(10.0, "topic_rate", "/odom", "50", Severity.INFO, 50.0, "Hz"),
            Event(11.5, "topic_rate", "/odom", "5", Severity.FAIL, 5.0, "Hz"),
        ],
    )
    directory = tmp_path / "incident"
    write_incident(directory, incident)
    csv_path = export_timeline(directory, tmp_path / "timeline.csv")
    json_path = export_timeline(directory, tmp_path / "timeline.json", "json")
    assert "relative_seconds" in csv_path.read_text()
    payload = json.loads(json_path.read_text())
    assert payload[1]["relative_seconds"] == 1.5


import json

from rift_ros.compatibility import inspect_compatibility
from rift_ros.config import config_template, load_config, write_config_template
from rift_ros.io import write_incident
from rift_ros.models import Event, Incident, Severity
from rift_ros.replay import ReplayFilter, replay_records
from rift_ros.session import list_session_reports, write_session_report
from rift_ros.telemetry import RecorderMetrics, performance_budget
from rift_ros.validation import ValidationCriteria, run_live_validation
from rift_ros import validation, watcher


def test_v6_config_identity_and_budget_roundtrip(tmp_path):
    path = write_config_template(tmp_path / "rift.json")
    data = json.loads(path.read_text())
    assert data["schema"] in {"rift.config/v6", "rift.config/v7"}
    data["identity"] = {"robot_id": "amr-17", "site_id": "pune-lab", "labels": {"model": "dynamo"}}
    data["validation"]["max_p95_cycle_seconds"] = 1.5
    data["watch"]["probe_degraded_after_cycles"] = 4
    path.write_text(json.dumps(data))
    cfg = load_config(path)
    assert cfg.robot_id == "amr-17"
    assert cfg.site_id == "pune-lab"
    assert cfg.labels == {"model": "dynamo"}
    assert cfg.validation_max_p95_cycle_seconds == 1.5
    assert cfg.probe_degraded_after_cycles == 4


def test_performance_budget_reports_pass_and_fail():
    metrics = RecorderMetrics()
    metrics.observe(0.4, [], 1.0, 0)
    metrics.observe(0.6, [], 1.0, 0)
    assert performance_budget(metrics, 0.7)["within_budget"] is True
    assert performance_budget(metrics, 0.5)["within_budget"] is False


def test_live_validation_rejects_p95_budget(monkeypatch):
    monkeypatch.setattr(validation, "ros_available", lambda: True)
    monkeypatch.setattr(validation, "runtime_metadata", lambda include_hostname=False: {})
    monkeypatch.setattr(validation, "collect_cycle", lambda *args, **kwargs: [])
    times = iter([0.0, 0.2, 1.0, 1.2])
    monkeypatch.setattr(validation.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(validation.time, "sleep", lambda _seconds: None)
    result = run_live_validation(
        [], [], [], [], cycles=2, interval_seconds=1.0, sample_seconds=0.1, workers=1,
        criteria=ValidationCriteria(max_probe_error_rate=1, max_overrun_rate=1, max_failed_cycle_rate=1, max_p95_cycle_seconds=0.1),
    )
    assert not result.healthy
    assert any("p95 cycle time" in reason for reason in result.acceptance_reasons)


def test_replay_filters_by_kind_source_and_time(tmp_path):
    directory = tmp_path / "incident"
    write_incident(directory, Incident("i", 10, "test", [
        Event(10, "topic_rate", "/odom", "ok", Severity.INFO),
        Event(11, "topic_rate", "/odom", "slow", Severity.FAIL),
        Event(12, "tf_presence", "map->odom", "missing", Severity.FAIL),
    ]))
    records = replay_records(directory, ReplayFilter(anomalies_only=True, kinds=("topic_rate",), sources=("/odom",)))
    assert len(records) == 1
    assert records[0]["message"] == "slow"


def test_bundle_compatibility_reports_current_schemas(tmp_path):
    directory = tmp_path / "incident"
    write_incident(directory, Incident("i", 1, "test", []))
    result = inspect_compatibility(directory)
    assert result.readable
    assert result.integrity_ok
    assert result.bundle_schema == "rift.bundle/v3"
    assert result.incident_schema == "rift.incident/v2"


def test_session_v2_keeps_robot_identity_and_reads_back(tmp_path):
    write_session_report(
        tmp_path,
        session_id="s1",
        started_at=1,
        stopped_at=2,
        profile="nav2",
        config_id="cfg",
        robot_id="amr-1",
        site_id="lab",
        labels={"model": "d1500"},
        metrics={"cycles": 2, "anomalous_cycles": 0},
        marker_scenarios={},
        armed_at=1,
        last_healthy_at=2,
        last_anomaly_at=None,
        stopped_reason="done",
    )
    row = list_session_reports(tmp_path)[0]
    assert row.robot_id == "amr-1"
    assert row.site_id == "lab"
    assert row.labels["model"] == "d1500"


def test_watcher_probe_degradation_is_recorder_evidence_not_robot_trigger(monkeypatch, tmp_path):
    monkeypatch.setattr(watcher, "ros_available", lambda: True)
    monkeypatch.setattr(
        watcher,
        "collect_cycle",
        lambda *args, **kwargs: [Event(1, "probe_error", "/scan", "timeout", Severity.WARN)],
    )
    cfg = watcher.WatchConfig(
        duration_seconds=0.006,
        interval_seconds=0.001,
        sample_seconds=0.001,
        startup_grace_seconds=0,
        probe_degraded_after_cycles=2,
        output_dir=tmp_path / "incidents",
        status_file=None,
        lock_file=None,
        marker_file=None,
        min_free_storage_mb=1,
    )
    assert watcher.watch(cfg) == []
    sessions = list_session_reports(cfg.output_dir)
    assert sessions and sessions[0].incidents_captured == 0


def test_init_config_template_can_scope_robot_identity():
    data = config_template("nav2", robot_id="amr-42", site_id="site-a", labels={"model": "d1500"})
    assert data["identity"]["robot_id"] == "amr-42"
    assert data["identity"]["site_id"] == "site-a"
    assert data["identity"]["labels"]["model"] == "d1500"


def test_invalid_identity_labels_are_rejected(tmp_path):
    path = tmp_path / "bad.json"
    data = config_template()
    data["identity"]["labels"] = ["not", "a", "mapping"]
    path.write_text(json.dumps(data))
    try:
        load_config(path)
    except ValueError as exc:
        assert "identity.labels" in str(exc)
    else:
        raise AssertionError("invalid identity labels were accepted")


def test_cli_watch_defaults_to_success_when_incident_is_captured(monkeypatch, tmp_path):
    from rift_ros import cli
    incident = tmp_path / "incident" / "incident.json"
    incident.parent.mkdir()
    incident.write_text("{}")
    monkeypatch.setattr(cli, "watch", lambda _cfg: [incident])
    monkeypatch.setattr(cli, "_merge_profile", lambda _args: ([], [], [], [], None))
    assert cli.main(["watch", "--duration", "1", "--out", str(tmp_path / "out")]) == 0
    assert cli.main(["watch", "--duration", "1", "--out", str(tmp_path / "out"), "--fail-on-incident"]) == 1


def test_bundle_manifest_indexes_identity_for_fast_cataloging(tmp_path):
    from rift_ros.io import read_bundle_manifest
    directory = tmp_path / "incident"
    write_incident(directory, Incident("i", 1, "test", [], {
        "session_id": "s-1",
        "identity": {"robot_id": "amr-9", "site_id": "site-x", "labels": {"model": "d1500"}},
    }))
    manifest = read_bundle_manifest(directory)
    assert manifest["incident_schema"] == "rift.incident/v2"
    assert manifest["session_id"] == "s-1"
    assert manifest["identity"]["robot_id"] == "amr-9"

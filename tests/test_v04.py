import json
from pathlib import Path

import pytest

from rift_ros import collectors, watcher
from rift_ros.config import config_digest, config_warnings, load_config, write_config_template
from rift_ros.io import inspect_bundle, pack_bundle, sanitize_bundle, verify_bundle, write_incident
from rift_ros.lock import RecorderLock
from rift_ros.models import Event, Incident, Severity
from rift_ros.privacy import sanitize_incident


def test_config_v3_has_startup_privacy_and_lock(tmp_path):
    path = write_config_template(tmp_path / "rift.json")
    data = json.loads(path.read_text())
    assert data["schema"] in {"rift.config/v3", "rift.config/v4", "rift.config/v5", "rift.config/v6", "rift.config/v7"}
    assert data["watch"]["startup_grace_seconds"] == 15
    assert data["watch"]["lock_file"] == "rift-recorder.lock"
    assert data["privacy"]["include_hostname"] is False
    config = load_config(path)
    assert config.arm_after_healthy_cycles == 0
    assert len(config_digest(config)) == 16


def test_config_warning_for_impossible_cadence(tmp_path):
    path = write_config_template(tmp_path / "rift.json")
    data = json.loads(path.read_text())
    data["watch"]["interval_seconds"] = 1
    data["watch"]["sample_seconds"] = 1.2
    path.write_text(json.dumps(data))
    assert any("overruns" in item for item in config_warnings(load_config(path)))


def test_runtime_metadata_hides_hostname_by_default(monkeypatch):
    monkeypatch.setattr(collectors.socket, "gethostname", lambda: "secret-host")
    assert "hostname" not in collectors.runtime_metadata()
    assert collectors.runtime_metadata(include_hostname=True)["hostname"] == "secret-host"


def test_bundle_v2_manifest_and_inspect(tmp_path):
    path = write_incident(tmp_path / "incident", Incident("i", 2, "why", [Event(1, "x", "s", "m")]))
    manifest = json.loads((path.parent / "bundle.json").read_text())
    assert manifest["schema"] in {"rift.bundle/v2", "rift.bundle/v3"}
    assert manifest["event_count"] == 1
    assert manifest["files"]["events.jsonl"]["bytes"] > 0
    result = inspect_bundle(path.parent)
    assert result["integrity_ok"]
    assert result["summary"]["total"] == 1


def test_sanitize_bundle_redacts_hostname_home_and_ip(tmp_path):
    incident = Incident(
        "raw",
        2,
        "failure on /home/akshat/ws from 10.0.0.7",
        [Event(1, "probe_error", "rift", "opened /home/akshat/ws at 10.0.0.7", evidence={"hostname": "robot-1"})],
        {"runtime": {"hostname": "robot-1"}, "workspace_path": "/home/akshat/ws"},
    )
    write_incident(tmp_path / "raw", incident)
    output = sanitize_bundle(tmp_path / "raw", tmp_path / "safe.rift.zip")
    assert verify_bundle(output)[0]
    from rift_ros.io import read_incident
    safe = read_incident(output)
    blob = json.dumps(safe.to_dict())
    assert "robot-1" not in blob
    assert "/home/akshat" not in blob
    assert "10.0.0.7" not in blob
    assert safe.metadata["sanitized"] is True


def test_recorder_lock_blocks_second_holder(tmp_path):
    lock = tmp_path / "rift.lock"
    with RecorderLock(lock):
        with pytest.raises(RuntimeError):
            with RecorderLock(lock):
                pass


def test_watch_can_arm_after_healthy_cycle_then_capture(monkeypatch, tmp_path):
    monkeypatch.setattr(watcher, "ros_available", lambda: True)
    cycles = iter([
        [Event(1, "topic_rate", "/odom", "ok")],
        [Event(2, "topic_rate", "/odom", "low", Severity.FAIL)],
    ])
    last = [Event(3, "topic_rate", "/odom", "low", Severity.FAIL)]

    def fake_collect(*args, **kwargs):
        try:
            return next(cycles)
        except StopIteration:
            return last

    monkeypatch.setattr(watcher, "collect_cycle", fake_collect)
    config = watcher.WatchConfig(
        interval_seconds=0.001,
        duration_seconds=0.03,
        post_trigger_seconds=0,
        startup_grace_seconds=0,
        arm_after_healthy_cycles=1,
        consecutive_failures=1,
        cooldown_seconds=0,
        max_incidents=1,
        output_dir=tmp_path / "incidents",
        status_file=None,
        lock_file=None,
        min_free_storage_mb=1,
    )
    written = watcher.watch(config)
    assert len(written) == 1
    assert verify_bundle(written[0].parent)[0]


def test_sanitize_incident_marks_provenance():
    safe = sanitize_incident(Incident("x", 1, "ok", [], {"hostname": "secret"}))
    assert safe.incident_id.endswith("-sanitized")
    assert safe.metadata["hostname"] == "<redacted>"


def test_pack_still_verifies_v2_bundle(tmp_path):
    write_incident(tmp_path / "bundle", Incident("i", 1, "why", []))
    archive = pack_bundle(tmp_path / "bundle")
    assert verify_bundle(archive) == (True, [])


def test_builtin_nav2_profile_does_not_enable_expensive_header_delay_by_default():
    from rift_ros.profiles import get_profile
    profile = get_profile("nav2")
    assert all(topic.max_delay_seconds is None for topic in profile.topics)


def test_watch_acquires_lock_before_writing_status(monkeypatch, tmp_path):
    monkeypatch.setattr(watcher, "ros_available", lambda: True)
    lock = tmp_path / "rift.lock"
    status = tmp_path / "rift-status.json"
    config = watcher.WatchConfig(
        duration_seconds=0.01,
        output_dir=tmp_path / "incidents",
        status_file=status,
        lock_file=lock,
        min_free_storage_mb=1,
    )
    with RecorderLock(lock):
        with pytest.raises(RuntimeError, match="another RIFT recorder"):
            watcher.watch(config)
    assert not status.exists()

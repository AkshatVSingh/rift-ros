import json
from pathlib import Path

import pytest

from rift_ros import rosbag, validation, watcher
from rift_ros.config import config_digest, load_config, write_config_template
from rift_ros.io import (
    inspect_bundle,
    pack_bundle,
    read_bundle_manifest,
    read_incident,
    register_attachment,
    sanitize_bundle,
    verify_bundle,
    write_incident,
)
from rift_ros.models import Event, Incident, Severity
from rift_ros.rosbag import BagSnapshotConfig, RosbagSnapshotSidecar, build_record_command


def test_config_v4_has_opt_in_rosbag_snapshot(tmp_path):
    path = write_config_template(tmp_path / "rift.json", profile="nav2")
    data = json.loads(path.read_text())
    assert data["schema"] in {"rift.config/v4", "rift.config/v5", "rift.config/v6", "rift.config/v7"}
    assert data["rosbag_snapshot"]["enabled"] is False
    assert "/odom" in data["rosbag_snapshot"]["topics"]
    assert "/tf_static" in data["rosbag_snapshot"]["topics"]
    cfg = load_config(path)
    assert cfg.bag_snapshot.enabled is False
    assert len(config_digest(cfg)) == 16


def test_rosbag_config_requires_absolute_topics():
    cfg = BagSnapshotConfig(enabled=True, topics=["odom"])
    with pytest.raises(ValueError, match="absolute"):
        cfg.validate()


def test_rosbag_command_is_jazzy_snapshot_compatible(tmp_path):
    cfg = BagSnapshotConfig(enabled=True, topics=["/odom", "/scan"], max_cache_mb=128)
    command = build_record_command(cfg, tmp_path / "bag")
    assert command[:3] == ["ros2", "bag", "record"]
    assert "--snapshot-mode" in command
    assert command[command.index("--max-cache-size") + 1] == str(128 * 1024 * 1024)
    assert command[-3:] == ["--topics", "/odom", "/scan"]


def test_bundle_v3_supports_verified_binary_attachment(tmp_path):
    directory = tmp_path / "incident"
    write_incident(directory, Incident("i", 1, "why", [Event(1, "x", "s", "m")]))
    raw = tmp_path / "rosbag2.zip"
    raw.write_bytes(b"fake-bag")
    register_attachment(directory, raw, name="rosbag2.zip", role="rosbag2-snapshot")
    assert verify_bundle(directory) == (True, [])
    manifest = read_bundle_manifest(directory)
    assert manifest["schema"] == "rift.bundle/v3"
    assert manifest["attachments"]["rosbag2.zip"]["role"] == "rosbag2-snapshot"
    archive = pack_bundle(directory)
    assert verify_bundle(archive) == (True, [])
    assert inspect_bundle(archive)["attachments"]["rosbag2.zip"]["role"] == "rosbag2-snapshot"


def test_sanitizer_drops_unredactable_binary_attachments(tmp_path):
    directory = tmp_path / "incident"
    write_incident(directory, Incident("i", 1, "why", [Event(1, "x", "s", "m")]))
    bag = tmp_path / "rosbag2.zip"
    bag.write_bytes(b"private raw robot payload")
    register_attachment(directory, bag, name="rosbag2.zip", role="rosbag2-snapshot")
    safe = sanitize_bundle(directory, tmp_path / "safe.rift.zip")
    manifest = read_bundle_manifest(safe)
    assert manifest["attachments"] == {}
    incident = read_incident(safe)
    assert incident.metadata["attachments_omitted_by_sanitizer"] is True


def test_live_validation_aggregates_cycles(monkeypatch):
    monkeypatch.setattr(validation, "ros_available", lambda: True)
    cycles = iter([
        [Event(1, "topic_rate", "/odom", "ok")],
        [Event(2, "topic_rate", "/odom", "low", Severity.FAIL)],
    ])
    monkeypatch.setattr(validation, "collect_cycle", lambda *a, **k: next(cycles))
    result = validation.run_live_validation([], [], [], [], cycles=2, interval_seconds=0.001)
    assert result.cycles == 2
    assert result.failed_cycles == 1
    assert result.healthy is False
    assert result.failures_by_source["/odom"] == 1


def test_preflight_checks_rosbag_when_enabled(monkeypatch, tmp_path):
    config_path = write_config_template(tmp_path / "rift.json")
    data = json.loads(config_path.read_text())
    data["rosbag_snapshot"]["enabled"] = True
    config_path.write_text(json.dumps(data))
    cfg = load_config(config_path)
    monkeypatch.setattr(validation, "runtime_checks", lambda: [])
    monkeypatch.setattr(validation, "ros_available", lambda: True)
    monkeypatch.setattr(validation, "rosbag_snapshot_supported", lambda: (True, "ok"))
    checks = validation.preflight(cfg)
    assert any(item.name == "rosbag2-snapshot" and item.ok for item in checks)


def test_watcher_attaches_rosbag_snapshot_without_real_ros(monkeypatch, tmp_path):
    monkeypatch.setattr(watcher, "ros_available", lambda: True)
    monkeypatch.setattr(
        watcher,
        "collect_cycle",
        lambda *a, **k: [Event(1, "topic_rate", "/odom", "low", Severity.FAIL)],
    )

    class FakeSidecar:
        def __init__(self, config, cache_root):
            self.config = config
        def start(self):
            return Path("fake")
        def capture_archive(self, destination):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"bag")
            return destination
        def stop(self, cleanup=True):
            return None

    monkeypatch.setattr(watcher, "RosbagSnapshotSidecar", FakeSidecar)
    cfg = watcher.WatchConfig(
        interval_seconds=0.001,
        duration_seconds=0.02,
        post_trigger_seconds=0,
        startup_grace_seconds=0,
        consecutive_failures=1,
        cooldown_seconds=0,
        max_incidents=1,
        output_dir=tmp_path / "incidents",
        status_file=None,
        lock_file=None,
        min_free_storage_mb=1,
        bag_snapshot=BagSnapshotConfig(enabled=True, topics=["/odom"]),
    )
    written = watcher.watch(cfg)
    assert len(written) == 1
    manifest = read_bundle_manifest(written[0].parent)
    assert "rosbag2.zip" in manifest["attachments"]
    incident = read_incident(written[0])
    assert incident.metadata["rosbag_snapshot"]["captured"] is True


def test_rosbag_sidecar_service_failure_is_explicit(monkeypatch, tmp_path):
    cfg = BagSnapshotConfig(enabled=True, topics=["/odom"])
    sidecar = RosbagSnapshotSidecar(cfg, tmp_path)
    class Process:
        returncode = None
        def poll(self): return None
        def terminate(self): pass
        def wait(self, timeout=None): return 0
    sidecar.process = Process()
    sidecar.uri = tmp_path / "bag"
    monkeypatch.setattr(rosbag, "run", lambda *a, **k: type("R", (), {"returncode": 1, "stdout": "", "stderr": "no service"})())
    with pytest.raises(RuntimeError, match="no service"):
        sidecar.take_snapshot()


def test_extract_attachment_from_packed_bundle(tmp_path):
    from rift_ros.io import extract_attachment
    directory = tmp_path / "incident"
    write_incident(directory, Incident("i", 1, "why", []))
    raw = tmp_path / "rosbag2.zip"
    raw.write_bytes(b"bag-bytes")
    register_attachment(directory, raw, name="rosbag2.zip", role="rosbag2-snapshot")
    archive = pack_bundle(directory)
    output = extract_attachment(archive, "rosbag2.zip", tmp_path / "extracted.zip")
    assert output.read_bytes() == b"bag-bytes"


def test_extract_rejects_unknown_attachment(tmp_path):
    from rift_ros.io import extract_attachment
    directory = tmp_path / "incident"
    write_incident(directory, Incident("i", 1, "why", []))
    with pytest.raises(ValueError, match="not found"):
        extract_attachment(directory, "missing.zip", tmp_path / "x.zip")

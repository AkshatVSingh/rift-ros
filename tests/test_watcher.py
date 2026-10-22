from rift_ros import watcher
from rift_ros.models import Event


def test_capture_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(watcher, "ros_available", lambda: True)
    monkeypatch.setattr(watcher, "collect_cycle", lambda *a, **k: [Event(1, "x", "s", "ok")])
    path = watcher.capture_snapshot([], [], [], tmp_path / "snap")
    assert path.exists()
    assert path.name == "incident.json"


def test_snapshot_rejects_missing_ros(monkeypatch, tmp_path):
    import pytest
    monkeypatch.setattr(watcher, "ros_available", lambda: False)
    with pytest.raises(RuntimeError):
        watcher.capture_snapshot([], [], [], tmp_path / "snap")


def test_warning_trigger_policy():
    from rift_ros.models import Severity
    warn = [Event(1, "system_pressure", "host", "warn", Severity.WARN)]
    assert not watcher._cycle_failed(warn, False)
    assert watcher._cycle_failed(warn, True)

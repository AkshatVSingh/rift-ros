from ros_doctor.collectors import tf
from ros_doctor.shell import CommandResult


def test_tf_detects_transform_output(monkeypatch):
    output = "At time 12.0\n- Translation: [0, 0, 0]\n- Rotation: [0, 0, 0, 1]\n"
    monkeypatch.setattr(tf, "run", lambda *a, **k: CommandResult(124, output, "", True))
    result = tf.check_transform("map", "odom")
    assert result.available


def test_tf_timeout_without_transform_is_failure(monkeypatch):
    monkeypatch.setattr(tf, "run", lambda *a, **k: CommandResult(124, "", "", True))
    result = tf.check_transform("map", "odom")
    assert not result.available


def test_tf_timestamp_without_transform_is_not_success(monkeypatch):
    output = "At time 12.0\nWaiting for transform...\n"
    monkeypatch.setattr(tf, "run", lambda *a, **k: CommandResult(124, output, "", True))
    result = tf.check_transform("map", "odom")
    assert not result.available

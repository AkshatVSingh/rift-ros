import json

import pytest

from rift_ros.config import load_config, write_config_template


def test_write_and_load_template(tmp_path):
    path = write_config_template(tmp_path / "rift.json", "nav2", "robot1")
    config = load_config(path)
    assert config.profile == "nav2"
    assert config.namespace == "robot1"
    assert config.duration_seconds is None
    assert config.expect_topics == []


def test_config_rejects_unknown_profile(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema": "rift.config/v1", "profile": "nope"}))
    with pytest.raises(ValueError):
        load_config(path)


def test_config_parses_transform_string(tmp_path):
    path = tmp_path / "rift.json"
    path.write_text(json.dumps({
        "schema": "rift.config/v1",
        "expectations": {"transforms": ["map:odom"]},
    }))
    assert load_config(path).expect_tf == [("map", "odom")]


def test_config_rejects_negative_post(tmp_path):
    path = tmp_path / "rift.json"
    path.write_text(json.dumps({
        "schema": "rift.config/v1",
        "watch": {"post_trigger_seconds": -1},
    }))
    with pytest.raises(ValueError):
        load_config(path)

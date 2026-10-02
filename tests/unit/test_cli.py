import argparse

import pytest

from ros_doctor.cli import _positive_seconds, _tf_pair, build_parser


def test_tf_pair():
    assert _tf_pair("map:odom") == ("map", "odom")


def test_parser_accepts_scan_expectations():
    args = build_parser().parse_args([
        "scan", "--expect-node", "/amcl", "--expect-topic", "/scan", "--expect-tf", "map:odom"
    ])
    assert args.expect_node == ["/amcl"]
    assert args.expect_topic == ["/scan"]
    assert args.expect_tf == [("map", "odom")]


def test_positive_seconds_rejects_zero():
    with pytest.raises(argparse.ArgumentTypeError):
        _positive_seconds("0")


def test_positive_seconds_accepts_fraction():
    assert _positive_seconds("0.5") == 0.5

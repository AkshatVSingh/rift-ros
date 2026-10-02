from __future__ import annotations

import argparse
import sys

from ros_doctor import __version__
from ros_doctor.collectors.environment import collect_environment
from ros_doctor.collectors.graph import list_nodes, list_topics
from ros_doctor.collectors.rate import sample_rate
from ros_doctor.collectors.tf import check_transform
from ros_doctor.models import Severity
from ros_doctor.reporting import render_json, render_text
from ros_doctor.scan import ScanRequest, run_scan


def _positive_seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("seconds must be a number") from exc
    if seconds <= 0:
        raise argparse.ArgumentTypeError("seconds must be greater than zero")
    return seconds


def _tf_pair(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise argparse.ArgumentTypeError("TF pairs must use parent:child, for example map:odom")
    parent, child = value.split(":", 1)
    if not parent or not child:
        raise argparse.ArgumentTypeError("TF pairs must contain both parent and child")
    return parent, child


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ros-doctor", description="Read-only ROS 2 diagnostics")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="run first-pass diagnostics")
    scan.add_argument("--expect-node", action="append", default=[], metavar="NODE")
    scan.add_argument("--expect-topic", action="append", default=[], metavar="TOPIC")
    scan.add_argument("--expect-tf", action="append", default=[], type=_tf_pair, metavar="PARENT:CHILD")
    scan.add_argument("--json", action="store_true", help="print JSON instead of terminal output")

    sub.add_parser("nodes", help="list ROS 2 nodes")
    sub.add_parser("topics", help="list ROS 2 topics and types")

    tf = sub.add_parser("tf", help="check whether a transform is available")
    tf.add_argument("parent")
    tf.add_argument("child")
    tf.add_argument("--seconds", type=_positive_seconds, default=2.0)

    hz = sub.add_parser("hz", help="sample a topic rate")
    hz.add_argument("topic")
    hz.add_argument("--seconds", type=_positive_seconds, default=4.0)

    return parser


def _require_ros() -> bool:
    env = collect_environment()
    if not env.ros_available:
        print("ROS 2 environment not available. Source your ROS setup and try again.", file=sys.stderr)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "scan":
        request = ScanRequest(args.expect_node, args.expect_topic, args.expect_tf)
        results, runnable = run_scan(request)
        print(render_json(results) if args.json else render_text(results))
        if not runnable:
            return 2
        return 1 if any(item.severity == Severity.FAIL for item in results) else 0

    if not _require_ros():
        return 2

    try:
        if args.command == "nodes":
            for node in list_nodes():
                print(node)
            return 0

        if args.command == "topics":
            for topic in list_topics():
                suffix = f" [{', '.join(topic.types)}]" if topic.types else ""
                print(f"{topic.name}{suffix}")
            return 0

        if args.command == "tf":
            result = check_transform(args.parent, args.child, timeout=args.seconds)
            state = "available" if result.available else "unavailable"
            print(f"{args.parent} -> {args.child}: {state} ({result.evidence})")
            return 0 if result.available else 1

        if args.command == "hz":
            result = sample_rate(args.topic, seconds=args.seconds)
            if result.hz is None:
                print(f"{args.topic}: no rate measured ({result.evidence})")
                return 1
            print(f"{args.topic}: {result.hz:.2f} Hz")
            return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

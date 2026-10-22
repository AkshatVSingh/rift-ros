from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from rift_ros import __version__
from rift_ros.analysis import render_summary, summarize
from rift_ros.catalog import catalog as catalog_incidents
from rift_ros.compatibility import inspect_compatibility
from rift_ros.collectors import LifecycleExpectation, TopicExpectation, ros_available
from rift_ros.config import (
    config_digest,
    config_to_dict,
    config_warnings,
    load_config,
    write_config_template,
)
from rift_ros.demo import generate_demo, scenarios
from rift_ros.dedup import list_duplicate_occurrences
from rift_ros.reviews import VALID_REVIEW_STATUSES, list_reviews, review_for, update_review
from rift_ros.export import export_timeline
from rift_ros.fieldlab import read_validation_plan, score_validation, write_validation_plan
from rift_ros.markers import append_marker
from rift_ros.migration import upgrade_config_file
from rift_ros.models import Severity
from rift_ros.diagnostics import diagnostics_exit_code, runtime_checks
from rift_ros.io import (
    extract_attachment,
    inspect_bundle,
    pack_bundle,
    read_incident,
    sanitize_bundle,
    verify_bundle,
    write_incident,
)
from rift_ros.profiles import available_profiles, get_profile
from rift_ros.retention import prune_incidents
from rift_ros.replay import ReplayFilter, replay_records, write_replay_jsonl
from rift_ros.rosbag import BagSnapshotConfig
from rift_ros.selftest import run_self_test
from rift_ros.status import read_status
from rift_ros.session import list_session_reports
from rift_ros.validation import ValidationCriteria, preflight, preflight_ok, run_live_validation, write_validation_report
from rift_ros.watcher import WatchConfig, capture_snapshot, watch


def _pair(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise argparse.ArgumentTypeError("use PARENT:CHILD")
    parent, child = value.split(":", 1)
    if not parent or not child:
        raise argparse.ArgumentTypeError("both TF frames are required")
    return parent, child


def _topic(value: str) -> TopicExpectation:
    if "=" not in value:
        return TopicExpectation(value)
    name, raw = value.rsplit("=", 1)
    try:
        if ":" in raw:
            low, high = raw.split(":", 1)
            min_hz = float(low) if low else None
            max_hz = float(high) if high else None
        else:
            min_hz = float(raw)
            max_hz = None
    except ValueError as exc:
        raise argparse.ArgumentTypeError("topic rates must be numeric") from exc
    if min_hz is not None and min_hz <= 0:
        raise argparse.ArgumentTypeError("minimum topic rate must be positive")
    if max_hz is not None and max_hz <= 0:
        raise argparse.ArgumentTypeError("maximum topic rate must be positive")
    if min_hz is not None and max_hz is not None and min_hz > max_hz:
        raise argparse.ArgumentTypeError("minimum topic rate cannot exceed maximum")
    return TopicExpectation(name, min_hz=min_hz, max_hz=max_hz)


def _lifecycle(value: str) -> LifecycleExpectation:
    if "=" not in value:
        return LifecycleExpectation(value, "active")
    node, state = value.rsplit("=", 1)
    if not node or not state:
        raise argparse.ArgumentTypeError("use NODE[=STATE]")
    return LifecycleExpectation(node, state)



def _label_pair(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("use KEY=VALUE")
    key, item = value.split("=", 1)
    key = key.strip()
    if not key:
        raise argparse.ArgumentTypeError("label key is required")
    return key, item


def _topic_dict(topic: TopicExpectation) -> dict[str, object]:
    return {
        "topic": topic.topic,
        "min_hz": topic.min_hz,
        "max_hz": topic.max_hz,
        "max_jitter_seconds": topic.max_jitter_seconds,
        "max_delay_seconds": topic.max_delay_seconds,
        "require_publishers": topic.require_publishers,
        "require_subscribers": topic.require_subscribers,
        "check_qos": topic.check_qos,
    }


def _merge_profile(
    args: argparse.Namespace,
) -> tuple[
    list[str],
    list[TopicExpectation],
    list[tuple[str, str]],
    list[LifecycleExpectation],
    str | None,
]:
    nodes = list(getattr(args, "expect_node", []))
    topics = list(getattr(args, "expect_topic", []))
    transforms = list(getattr(args, "expect_tf", []))
    lifecycle = list(getattr(args, "expect_lifecycle", []))
    profile_name = getattr(args, "profile", None)
    if profile_name:
        profile = get_profile(profile_name, getattr(args, "namespace", ""))
        nodes = list(profile.nodes) + nodes
        topics = list(profile.topics) + topics
        transforms = list(profile.transforms) + transforms
        lifecycle = list(profile.lifecycle) + lifecycle
    return nodes, topics, transforms, lifecycle, profile_name


def _add_runtime_expectations(command: argparse.ArgumentParser) -> None:
    command.add_argument("--profile", choices=available_profiles())
    command.add_argument("--namespace", default="", help="namespace applied to built-in profiles")
    command.add_argument("--expect-node", action="append", default=[])
    command.add_argument(
        "--expect-topic",
        action="append",
        default=[],
        type=_topic,
        metavar="TOPIC[=MIN_HZ[:MAX_HZ]]",
    )
    command.add_argument("--expect-tf", action="append", default=[], type=_pair, metavar="PARENT:CHILD")
    command.add_argument(
        "--expect-lifecycle",
        action="append",
        default=[],
        type=_lifecycle,
        metavar="NODE[=STATE]",
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="rift", description="ROS 2 runtime incident forensics")
    root.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = root.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="check whether the ROS 2 runtime is available")
    doctor = sub.add_parser("doctor", help="check whether this host is ready to run RIFT")
    doctor.add_argument("--json", action="store_true")

    profile = sub.add_parser("profiles", help="list built-in runtime profiles")
    profile.add_argument("name", nargs="?", choices=available_profiles())
    profile.add_argument("--namespace", default="")

    init_config = sub.add_parser("init-config", help="write a deployable JSON recorder configuration")
    init_config.add_argument("--profile", choices=available_profiles(), default="nav2")
    init_config.add_argument("--namespace", default="")
    init_config.add_argument("--robot-id")
    init_config.add_argument("--site-id")
    init_config.add_argument("--label", action="append", default=[], type=_label_pair, metavar="KEY=VALUE")
    init_config.add_argument("-o", "--out", default="rift.json")

    upgrade_config = sub.add_parser("upgrade-config", help="upgrade an older RIFT config to the current schema")
    upgrade_config.add_argument("path")
    upgrade_config.add_argument("-o", "--out")

    validate_config = sub.add_parser("validate-config", help="validate and summarize a recorder configuration")
    validate_config.add_argument("path")
    validate_config.add_argument("--json", action="store_true")

    preflight_cmd = sub.add_parser("preflight", help="verify host/config readiness before deploying the recorder")
    preflight_cmd.add_argument("--config", required=True)
    preflight_cmd.add_argument("--json", action="store_true")

    validate_live = sub.add_parser("validate-live", help="measure live collector health and timing without creating incidents")
    validate_live.add_argument("--config", required=True)
    validate_live.add_argument("--cycles", type=int, default=5)
    validate_live.add_argument("--interval", type=float)
    validate_live.add_argument("--sample-seconds", type=float)
    validate_live.add_argument("--workers", type=int)
    validate_live.add_argument("--json", action="store_true")
    validate_live.add_argument("-o", "--out", help="optional JSON validation report path")
    validate_live.add_argument("--max-probe-error-rate", type=float)
    validate_live.add_argument("--max-overrun-rate", type=float)
    validate_live.add_argument("--max-failed-cycle-rate", type=float)
    validate_live.add_argument("--max-p95-cycle-seconds", type=float)

    demo = sub.add_parser("demo", help="generate and analyze a built-in synthetic incident")
    demo.add_argument("--scenario", choices=scenarios(), default="nav2-odom")
    demo.add_argument("--out", default="rift-demo-incident")

    self_test = sub.add_parser("self-test", help="exercise bundle/analysis paths without ROS installed")
    self_test.add_argument("--out", help="optionally keep generated test bundles here")

    snap = sub.add_parser("snapshot", help="capture one live ROS 2 evidence snapshot")
    snap.add_argument("--config")
    _add_runtime_expectations(snap)
    snap.add_argument("--sample-seconds", type=float)
    snap.add_argument("--workers", type=int)
    snap.add_argument("--include-hostname", action="store_true")
    snap.add_argument("--out", default="rift-snapshot")

    analyze = sub.add_parser("analyze", help="analyze an incident bundle offline")
    analyze.add_argument("path")
    analyze.add_argument("--json", action="store_true")

    show = sub.add_parser("show", help="print an incident timeline")
    show.add_argument("path")
    show.add_argument("--anomalies-only", action="store_true")

    verify = sub.add_parser("verify", help="verify incident-bundle file integrity")
    verify.add_argument("path")

    inspect_cmd = sub.add_parser("inspect", help="inspect bundle manifest, integrity and summary")
    inspect_cmd.add_argument("path")
    inspect_cmd.add_argument("--json", action="store_true")

    compatibility = sub.add_parser("compatibility", help="report whether a bundle is readable by this RIFT version")
    compatibility.add_argument("path")
    compatibility.add_argument("--json", action="store_true")

    replay = sub.add_parser("replay", help="replay/filter a recorded incident deterministically without ROS")
    replay.add_argument("path")
    replay.add_argument("--anomalies-only", action="store_true")
    replay.add_argument("--kind", action="append", default=[])
    replay.add_argument("--source", action="append", default=[])
    replay.add_argument("--from-seconds", type=float)
    replay.add_argument("--to-seconds", type=float)
    replay.add_argument("--jsonl", action="store_true")
    replay.add_argument("-o", "--out")

    pack = sub.add_parser("pack", help="pack a verified bundle into a portable .rift.zip archive")
    pack.add_argument("path")
    pack.add_argument("-o", "--out")

    extract = sub.add_parser("extract", help="extract one verified bundle attachment")
    extract.add_argument("path")
    extract.add_argument("name")
    extract.add_argument("-o", "--out", required=True)

    sanitize = sub.add_parser("sanitize", help="create a share-safe copy with sensitive metadata redacted")
    sanitize.add_argument("path")
    sanitize.add_argument("-o", "--out", required=True)

    mark = sub.add_parser("mark", help="append an operator annotation to a running recorder journal")
    mark.add_argument("message")
    mark.add_argument("--file", default="rift-markers.jsonl")
    mark.add_argument("--status-file", default="rift-status.json", help="use recorder session id when available")
    mark.add_argument("--severity", choices=("info", "warn", "fail"), default="info")
    mark.add_argument("--tag", action="append", default=[])
    mark.add_argument("--scenario")
    mark.add_argument("--actor", default="operator")

    catalog_cmd = sub.add_parser("catalog", help="list local incident bundles and archives")
    catalog_cmd.add_argument("paths", nargs="*", default=["rift-incidents"])
    catalog_cmd.add_argument("--json", action="store_true")
    catalog_cmd.add_argument("--review-file", default="rift-reviews.json")


    review_cmd = sub.add_parser("review", help="acknowledge/resolve an incident without modifying evidence")
    review_cmd.add_argument("incident")
    review_cmd.add_argument("--status", choices=VALID_REVIEW_STATUSES)
    review_cmd.add_argument("--owner")
    review_cmd.add_argument("--note")
    review_cmd.add_argument("--actor")
    review_cmd.add_argument("--label", action="append", default=[], type=_label_pair, metavar="KEY=VALUE")
    review_cmd.add_argument("--file", default="rift-reviews.json")
    review_cmd.add_argument("--json", action="store_true")

    reviews_cmd = sub.add_parser("reviews", help="list incident review state")
    reviews_cmd.add_argument("--file", default="rift-reviews.json")
    reviews_cmd.add_argument("--json", action="store_true")

    duplicates_cmd = sub.add_parser("duplicates", help="list incidents suppressed by fingerprint deduplication")
    duplicates_cmd.add_argument("path", nargs="?", default="rift-incidents")
    duplicates_cmd.add_argument("--json", action="store_true")

    sessions_cmd = sub.add_parser("sessions", help="list recorder session summaries, including healthy runs with no incident")
    sessions_cmd.add_argument("path", nargs="?", default="rift-incidents")
    sessions_cmd.add_argument("--json", action="store_true")

    export_cmd = sub.add_parser("export", help="export an incident timeline as CSV or JSON")
    export_cmd.add_argument("path")
    export_cmd.add_argument("-o", "--out", required=True)
    export_cmd.add_argument("--format", choices=("csv", "json"), default="csv")

    field_plan = sub.add_parser("field-plan", help="write a safe operator-driven field-validation plan")
    field_plan.add_argument("--profile", choices=("nav2",), default="nav2")
    field_plan.add_argument("-o", "--out", default="rift-field-plan.json")

    field_score = sub.add_parser("field-score", help="score marked validation incidents and healthy session reports")
    field_score.add_argument("plan")
    field_score.add_argument("evidence", nargs="+")
    field_score.add_argument("--json", action="store_true")

    status = sub.add_parser("status", help="read a running recorder heartbeat/status file")
    status.add_argument("--file", default="rift-status.json")
    status.add_argument("--json", action="store_true")

    prune = sub.add_parser("prune", help="enforce incident retention/storage limits")
    prune.add_argument("path", nargs="?", default="rift-incidents")
    prune.add_argument("--max-count", type=int)
    prune.add_argument("--max-mb", type=float)

    watcher = sub.add_parser("watch", help="record a rolling incident window from a live ROS 2 graph")
    watcher.add_argument("--config", help="JSON configuration generated by rift init-config")
    watcher.add_argument("--window", type=float)
    watcher.add_argument("--interval", type=float)
    watcher.add_argument("--duration", type=float)
    watcher.add_argument("--forever", action="store_true", help="run until interrupted")
    watcher.add_argument("--post", type=float, help="seconds to keep recording after a trigger")
    watcher.add_argument("--startup-grace", type=float, help="seconds to observe without triggering after startup")
    watcher.add_argument("--arm-after-healthy", type=int, help="healthy cycles required before triggering is enabled")
    watcher.add_argument("--consecutive", type=int, help="failed cycles required before trigger")
    watcher.add_argument("--cooldown", type=float, help="minimum seconds between incidents")
    watcher.add_argument("--dedup-window", type=float, help="suppress same-fingerprint incidents within this many seconds; 0 disables")
    watcher.add_argument("--max-incidents", type=int)
    watcher.add_argument("--sample-seconds", type=float)
    watcher.add_argument("--workers", type=int)
    watcher.add_argument("--status-file")
    watcher.add_argument("--no-status", action="store_true")
    watcher.add_argument("--lock-file")
    watcher.add_argument("--no-lock", action="store_true")
    watcher.add_argument("--marker-file")
    watcher.add_argument("--no-markers", action="store_true")
    watcher.add_argument("--clock-jump-threshold", type=float)
    watcher.add_argument("--trigger-min-events", type=int)
    watcher.add_argument("--trigger-operator-markers", action="store_true")
    watcher.add_argument("--trigger-exclude-kind", action="append")
    watcher.add_argument("--max-saved-incidents", type=int)
    watcher.add_argument("--max-storage-mb", type=float)
    watcher.add_argument("--min-free-storage-mb", type=float)
    watcher.add_argument("--trigger-on-warning", action="store_true")
    watcher.add_argument("--include-hostname", action="store_true")
    _add_runtime_expectations(watcher)
    watcher.add_argument("--out")
    watcher.add_argument("--stop-on-failure", action="store_true")
    watcher.add_argument("--fail-on-incident", action="store_true", help="exit 1 when any incident was captured; useful for CI")
    return root


def _read_incident_or_error(path: str):
    try:
        return read_incident(path), None
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return None, str(exc)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)

    if args.cmd == "health":
        ok = ros_available()
        print("ROS 2 runtime available" if ok else "ROS 2 runtime unavailable")
        return 0 if ok else 1

    if args.cmd == "doctor":
        checks = runtime_checks()
        if args.json:
            print(json.dumps([asdict(check) for check in checks], indent=2, sort_keys=True))
        else:
            for check in checks:
                print(f"{'PASS' if check.ok else ('WARN' if not check.required else 'FAIL')} {check.name}: {check.message}")
        return diagnostics_exit_code(checks)

    if args.cmd == "profiles":
        if not args.name:
            for name in available_profiles():
                profile = get_profile(name, args.namespace)
                print(f"{name}: {profile.description}")
            return 0
        profile = get_profile(args.name, args.namespace)
        print(json.dumps({
            "name": profile.name,
            "description": profile.description,
            "nodes": list(profile.nodes),
            "topics": [_topic_dict(topic) for topic in profile.topics],
            "transforms": list(profile.transforms),
            "lifecycle": [
                {"node": item.node, "expected_state": item.expected_state}
                for item in profile.lifecycle
            ],
        }, indent=2))
        return 0

    if args.cmd == "init-config":
        try:
            print(write_config_template(args.out, args.profile, args.namespace, args.robot_id, args.site_id, dict(args.label)))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        return 0

    if args.cmd == "upgrade-config":
        try:
            print(upgrade_config_file(args.path, args.out))
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(f"could not upgrade config: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.cmd == "validate-config":
        try:
            cfg = load_config(args.path)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(f"invalid config: {exc}", file=sys.stderr)
            return 2
        warnings = config_warnings(cfg)
        payload = {"valid": True, "config_id": config_digest(cfg), "warnings": list(warnings), "config": config_to_dict(cfg)}
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Config OK: {payload['config_id']}")
            for warning in warnings:
                print(f"WARN: {warning}")
        return 0

    if args.cmd == "preflight":
        try:
            cfg = load_config(args.config)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(f"invalid config: {exc}", file=sys.stderr)
            return 2
        checks = preflight(cfg)
        if args.json:
            print(json.dumps([asdict(item) for item in checks], indent=2, sort_keys=True))
        else:
            for item in checks:
                label = "PASS" if item.ok else ("WARN" if not item.required else "FAIL")
                print(f"{label} {item.name}: {item.message}")
        return 0 if preflight_ok(checks) else 1

    if args.cmd == "validate-live":
        try:
            cfg = load_config(args.config)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(f"invalid config: {exc}", file=sys.stderr)
            return 2
        nodes = list(cfg.expect_nodes)
        topics = list(cfg.expect_topics)
        transforms = list(cfg.expect_tf)
        lifecycle = list(cfg.expect_lifecycle)
        if cfg.profile:
            profile = get_profile(cfg.profile, cfg.namespace)
            nodes = list(profile.nodes) + nodes
            topics = list(profile.topics) + topics
            transforms = list(profile.transforms) + transforms
            lifecycle = list(profile.lifecycle) + lifecycle
        interval = args.interval if args.interval is not None else cfg.interval_seconds
        sample = args.sample_seconds if args.sample_seconds is not None else cfg.sample_seconds
        workers = args.workers if args.workers is not None else cfg.workers
        criteria = ValidationCriteria(
            max_probe_error_rate=(args.max_probe_error_rate if args.max_probe_error_rate is not None else cfg.validation_max_probe_error_rate),
            max_overrun_rate=(args.max_overrun_rate if args.max_overrun_rate is not None else cfg.validation_max_overrun_rate),
            max_failed_cycle_rate=(args.max_failed_cycle_rate if args.max_failed_cycle_rate is not None else cfg.validation_max_failed_cycle_rate),
            max_p95_cycle_seconds=(args.max_p95_cycle_seconds if args.max_p95_cycle_seconds is not None else cfg.validation_max_p95_cycle_seconds),
        )
        try:
            result = run_live_validation(
                nodes, topics, transforms, lifecycle,
                cycles=args.cycles,
                interval_seconds=interval,
                sample_seconds=sample,
                workers=workers,
                config_id=config_digest(cfg),
                criteria=criteria,
            )
        except (RuntimeError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if args.out:
            write_validation_report(args.out, result)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        else:
            print(f"Cycles: {result.cycles}")
            print(f"Failed cycles: {result.failed_cycles}; warning cycles: {result.warning_cycles}")
            print(f"Probe errors: {result.probe_errors} ({result.probe_error_rate:.1%}); overruns: {result.overrun_cycles} ({result.overrun_rate:.1%})")
            print(f"Failed-cycle rate: {result.failed_cycle_rate:.1%}")
            print(
                f"Collector seconds mean/p95/max: {result.mean_cycle_seconds:.3f} / "
                f"{result.p95_cycle_seconds:.3f} / {result.max_cycle_seconds:.3f}"
            )
            print(f"Result: {'ACCEPTED' if result.healthy else 'REJECTED'}")
            for reason in result.acceptance_reasons:
                print(f"- {reason}")
            if args.out:
                print(f"Report: {args.out}")
        return 0 if result.healthy else 1

    if args.cmd == "demo":
        incident = generate_demo(args.scenario)
        manifest = write_incident(args.out, incident)
        print(render_summary(incident.events))
        print(f"\nBundle: {manifest}")
        return 0

    if args.cmd == "self-test":
        results = run_self_test(args.out)
        for result in results:
            print(f"{'PASS' if result.passed else 'FAIL'} {result.scenario}: {result.details}")
        passed = sum(result.passed for result in results)
        print(f"\n{passed}/{len(results)} scenarios passed")
        return 0 if passed == len(results) else 1

    if args.cmd == "snapshot":
        try:
            file_config = load_config(args.config) if args.config else None
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(f"invalid config: {exc}", file=sys.stderr)
            return 2
        if file_config is not None:
            if args.profile is None:
                args.profile = file_config.profile
            if not args.namespace:
                args.namespace = file_config.namespace
            args.expect_node = file_config.expect_nodes + args.expect_node
            args.expect_topic = file_config.expect_topics + args.expect_topic
            args.expect_tf = file_config.expect_tf + args.expect_tf
            args.expect_lifecycle = file_config.expect_lifecycle + args.expect_lifecycle
        nodes, topics, transforms, lifecycle, profile_name = _merge_profile(args)
        sample_seconds = args.sample_seconds or (file_config.sample_seconds if file_config else 1.2)
        workers = args.workers or (file_config.workers if file_config else 8)
        include_hostname = args.include_hostname or (file_config.include_hostname if file_config else False)
        try:
            path = capture_snapshot(
                nodes, topics, transforms, Path(args.out), lifecycle, profile_name,
                sample_seconds, workers, include_hostname,
                file_config.robot_id if file_config else None,
                file_config.site_id if file_config else None,
                dict(file_config.labels) if file_config else {},
            )
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(path)
        return 0

    if args.cmd in {"analyze", "show"}:
        incident, error = _read_incident_or_error(args.path)
        if error:
            print(f"could not read incident: {error}", file=sys.stderr)
            return 2
        assert incident is not None
        if args.cmd == "show":
            ordered = sorted(incident.events, key=lambda event: event.ts)
            if args.anomalies_only:
                ordered = [event for event in ordered if event.severity.value != "info"]
            start = ordered[0].ts if ordered else incident.created_at
            for event in ordered:
                print(
                    f"+{event.ts - start:7.3f}s {event.severity.value.upper():4} "
                    f"{event.kind:<20} {event.source}: {event.message}"
                )
            return 0
        summary = summarize(incident.events)
        print(json.dumps(summary.to_dict(), indent=2, sort_keys=True) if args.json else render_summary(incident.events))
        return 1 if summary.failures else 0

    if args.cmd == "verify":
        ok, problems = verify_bundle(args.path)
        if ok:
            print("Bundle integrity OK")
            return 0
        for problem in problems:
            print(f"FAIL: {problem}")
        return 1

    if args.cmd == "inspect":
        result = inspect_bundle(args.path)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Integrity: {'OK' if result['integrity_ok'] else 'FAILED'}")
            manifest = result.get("manifest") or {}
            print(f"Schema: {manifest.get('schema', 'unknown')}")
            print(f"RIFT version: {manifest.get('rift_version', 'unknown')}")
            print(f"Incident: {manifest.get('incident_id', 'unknown')}")
            print(f"Events: {manifest.get('event_count', 'unknown')}")
            print(f"Fingerprint: {manifest.get('fingerprint', 'unknown')}")
            attachments = result.get("attachments") or {}
            if attachments:
                print("Attachments: " + ", ".join(sorted(attachments)))
            for problem in result["problems"]:
                print(f"FAIL: {problem}")
        return 0 if result["integrity_ok"] else 1

    if args.cmd == "compatibility":
        result = inspect_compatibility(args.path)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        else:
            print(f"Readable: {result.readable}")
            print(f"Integrity: {result.integrity_ok}")
            print(f"Bundle schema: {result.bundle_schema}")
            print(f"Incident schema: {result.incident_schema}")
            print(f"Producer version: {result.producer_version}")
            for reason in result.reasons:
                print(f"- {reason}")
        return 0 if result.readable and result.integrity_ok else 1

    if args.cmd == "replay":
        if args.from_seconds is not None and args.from_seconds < 0:
            print("--from-seconds must be non-negative", file=sys.stderr)
            return 2
        if args.to_seconds is not None and args.to_seconds < 0:
            print("--to-seconds must be non-negative", file=sys.stderr)
            return 2
        if args.from_seconds is not None and args.to_seconds is not None and args.from_seconds > args.to_seconds:
            print("--from-seconds cannot exceed --to-seconds", file=sys.stderr)
            return 2
        filters = ReplayFilter(
            anomalies_only=args.anomalies_only,
            kinds=tuple(args.kind),
            sources=tuple(args.source),
            start_seconds=args.from_seconds,
            end_seconds=args.to_seconds,
        )
        try:
            if args.out:
                print(write_replay_jsonl(args.path, args.out, filters))
                return 0
            records = replay_records(args.path, filters)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"could not replay incident: {exc}", file=sys.stderr)
            return 1
        if args.jsonl:
            for record in records:
                print(json.dumps(record, sort_keys=True))
        else:
            for record in records:
                print(
                    f"{record['relative_seconds']:8.3f}s {str(record['severity']).upper():5} "
                    f"{record['kind']} {record['source']} — {record['message']}"
                )
            print(f"{len(records)} replay event(s)")
        return 0

    if args.cmd == "pack":
        try:
            print(pack_bundle(args.path, args.out))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    if args.cmd == "extract":
        try:
            print(extract_attachment(args.path, args.name, args.out))
        except (OSError, ValueError) as exc:
            print(f"could not extract attachment: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.cmd == "sanitize":
        try:
            print(sanitize_bundle(args.path, args.out))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"could not sanitize bundle: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.cmd == "mark":
        session_id = None
        try:
            status_payload = read_status(args.status_file)
            session_id = status_payload.get("session_id")
        except (OSError, json.JSONDecodeError):
            pass
        try:
            record = append_marker(
                args.file,
                args.message,
                severity=Severity(args.severity),
                tags=args.tag,
                scenario=args.scenario,
                session_id=str(session_id) if session_id else None,
                actor=args.actor,
            )
        except (OSError, ValueError) as exc:
            print(f"could not write marker: {exc}", file=sys.stderr)
            return 1
        print(f"Marker written: {record.message}")
        if record.session_id:
            print(f"Session: {record.session_id}")
        return 0

    if args.cmd == "review":
        try:
            record = update_review(args.file, args.incident, status=args.status, owner=args.owner, note=args.note, actor=args.actor, labels=dict(args.label))
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"could not update review: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(record.to_dict(), indent=2, sort_keys=True))
        else:
            print(f"{record.incident_id}: {record.status} owner={record.owner or '-'} notes={len(record.notes)}")
        return 0

    if args.cmd == "reviews":
        try:
            rows = list_reviews(args.file)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"could not read reviews: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps([row.to_dict() for row in rows], indent=2, sort_keys=True))
        else:
            for row in rows:
                print(f"{row.incident_id}  {row.status:<12} owner={row.owner or '-'} notes={len(row.notes)}")
            print(f"{len(rows)} review record(s)")
        return 0

    if args.cmd == "duplicates":
        try:
            rows = list_duplicate_occurrences(args.path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"could not read duplicate ledger: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps([row.to_dict() for row in rows], indent=2, sort_keys=True))
        else:
            for row in rows:
                scope = "/".join(item for item in (row.site_id, row.robot_id) if item) or "unscoped"
                print(f"{row.fingerprint}  [{scope}]  -> {row.canonical_path}  session={row.session_id or '-'}")
            print(f"{len(rows)} deduplicated occurrence(s)")
        return 0

    if args.cmd == "catalog":
        rows = catalog_incidents(args.paths)
        if args.json:
            payload = []
            for row in rows:
                item = row.to_dict()
                review = review_for(args.review_file, row.incident_id)
                item["review_status"] = review.status if review else "open"
                item["review_owner"] = review.owner if review else None
                payload.append(item)
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for row in rows:
                bag = " bag" if row.has_rosbag else ""
                integrity = "OK" if row.integrity_ok else "BAD"
                scope = "/".join(item for item in (row.site_id, row.robot_id) if item) or "unscoped"
                review = review_for(args.review_file, row.incident_id)
                review_text = review.status if review else "open"
                print(f"{row.incident_id}  [{scope}]  {review_text:<12} F={row.failures} W={row.warnings}  {row.fingerprint}  {integrity}{bag}  {row.path}")
            print(f"{len(rows)} incident(s)")
        return 0

    if args.cmd == "sessions":
        rows = list_session_reports(args.path)
        if args.json:
            print(json.dumps([row.to_dict() for row in rows], indent=2, sort_keys=True))
        else:
            for row in rows:
                scenarios = ",".join(f"{key}x{value}" for key, value in sorted(row.marker_scenarios.items())) or "-"
                print(
                    f"{row.session_id}  robot={row.robot_id or '-'} site={row.site_id or '-'}  cycles={row.cycles} anomalies={row.anomalous_cycles} "
                    f"incidents={row.incidents_captured} dedup={row.deduplicated_incidents} duration={row.duration_seconds:.1f}s "
                    f"markers={scenarios}  {row.path}"
                )
            print(f"{len(rows)} session(s)")
        return 0

    if args.cmd == "export":
        try:
            print(export_timeline(args.path, args.out, args.format))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"could not export timeline: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.cmd == "field-plan":
        try:
            print(write_validation_plan(args.out, args.profile))
        except (OSError, ValueError) as exc:
            print(f"could not write validation plan: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.cmd == "field-score":
        try:
            result = score_validation(read_validation_plan(args.plan), args.evidence)
        except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
            print(f"could not score validation evidence: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            rate = result.get("pass_rate")
            rate_text = "n/a" if rate is None else f"{rate:.0%}"
            print(
                f"Field validation: {result['passed_scenarios']}/{result['scored_scenarios']} "
                f"scored scenarios passed ({rate_text})"
            )
            for row in result["results"]:
                status = "UNRUN" if row["passed"] is None else ("PASS" if row["passed"] else "FAIL")
                print(
                    f"{status:5} {row['scenario_id']}: "
                    f"{row['successful_runs']}/{row['marked_runs']} successful marked run(s)"
                )
        return 0 if result["scored_scenarios"] and result["passed_scenarios"] == result["scored_scenarios"] else 1

    if args.cmd == "status":
        try:
            status = read_status(args.file)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"could not read status: {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(status, indent=2, sort_keys=True))
        else:
            print(f"State: {status.get('state')}")
            identity = status.get("identity") or {}
            if identity.get("robot_id") or identity.get("site_id"):
                print(f"Robot: {identity.get('robot_id') or '-'}; site: {identity.get('site_id') or '-'}")
            print(f"Armed: {status.get('armed')}")
            print(f"Uptime: {status.get('uptime_seconds', 0):.1f}s")
            print(f"Cycles: {status.get('cycles')}")
            print(f"Incidents: {status.get('incidents_captured')}")
            print(f"Failure streak: {status.get('failure_streak')}")
            print(f"Trigger armed: {status.get('trigger_armed')}")
            performance = status.get("performance") or {}
            if performance:
                print(f"Cycle p95: {performance.get('cycle_seconds_p95')}s; overrun rate: {float(performance.get('overrun_rate', 0)):.1%}")
                print(f"Probe errors: {performance.get('probe_errors')}; probe-error cycles: {performance.get('probe_error_cycles')}; markers: {performance.get('markers_ingested')}")
            budget = status.get("performance_budget") or {}
            if budget.get("configured"):
                print(f"Performance budget: {'PASS' if budget.get('within_budget') else 'FAIL'} (p95 {budget.get('observed_p95_seconds')}s <= {budget.get('max_p95_seconds')}s)")
            if status.get("recorder_degraded"):
                print(f"Recorder health: DEGRADED ({status.get('probe_error_streak')} consecutive probe-error cycles)")
            if status.get("last_incident"):
                print(f"Last incident: {status['last_incident']}")
            if status.get("last_error"):
                print(f"Last error: {status['last_error']}")
        return 0

    if args.cmd == "prune":
        if args.max_count is None and args.max_mb is None:
            print("provide --max-count and/or --max-mb", file=sys.stderr)
            return 2
        try:
            result = prune_incidents(args.path, args.max_count, args.max_mb)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"Kept {result.kept}; removed {len(result.removed)}; {result.bytes_after} bytes remain")
        for name in result.removed:
            print(f"removed {name}")
        return 0

    if args.cmd == "watch":
        try:
            file_config = load_config(args.config) if args.config else None
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(f"invalid config: {exc}", file=sys.stderr)
            return 2

        defaults = file_config
        window = args.window if args.window is not None else (defaults.window_seconds if defaults else 60.0)
        interval = args.interval if args.interval is not None else (defaults.interval_seconds if defaults else 5.0)
        if args.forever:
            duration = None
        elif args.duration is not None:
            duration = args.duration
        else:
            duration = defaults.duration_seconds if defaults else 60.0
        post = args.post if args.post is not None else (defaults.post_trigger_seconds if defaults else 10.0)
        startup_grace = args.startup_grace if args.startup_grace is not None else (defaults.startup_grace_seconds if defaults else 15.0)
        arm_after_healthy = args.arm_after_healthy if args.arm_after_healthy is not None else (defaults.arm_after_healthy_cycles if defaults else 0)
        consecutive = args.consecutive if args.consecutive is not None else (defaults.consecutive_failures if defaults else 2)
        cooldown = args.cooldown if args.cooldown is not None else (defaults.cooldown_seconds if defaults else 30.0)
        dedup_window = args.dedup_window if args.dedup_window is not None else (defaults.dedup_window_seconds if defaults else 120.0)
        max_incidents = args.max_incidents if args.max_incidents is not None else (defaults.max_incidents if defaults else 10)
        output = args.out if args.out is not None else (defaults.output_dir if defaults else "rift-incidents")
        sample_seconds = args.sample_seconds if args.sample_seconds is not None else (defaults.sample_seconds if defaults else 1.2)
        workers = args.workers if args.workers is not None else (defaults.workers if defaults else 8)
        trigger_on_warning = args.trigger_on_warning or (defaults.trigger_on_warning if defaults else False)
        include_hostname = args.include_hostname or (defaults.include_hostname if defaults else False)
        max_saved = args.max_saved_incidents if args.max_saved_incidents is not None else (defaults.max_saved_incidents if defaults else 100)
        max_storage = args.max_storage_mb if args.max_storage_mb is not None else (defaults.max_storage_mb if defaults else 2048.0)
        min_free = args.min_free_storage_mb if args.min_free_storage_mb is not None else (defaults.min_free_storage_mb if defaults else 128.0)
        if args.no_status:
            status_file = None
        elif args.status_file is not None:
            status_file = args.status_file
        else:
            status_file = defaults.status_file if defaults else "rift-status.json"
        if args.no_lock:
            lock_file = None
        elif args.lock_file is not None:
            lock_file = args.lock_file
        else:
            lock_file = defaults.lock_file if defaults else "rift-recorder.lock"
        if args.no_markers:
            marker_file = None
        elif args.marker_file is not None:
            marker_file = args.marker_file
        else:
            marker_file = defaults.marker_file if defaults else "rift-markers.jsonl"
        clock_jump_threshold = args.clock_jump_threshold if args.clock_jump_threshold is not None else (defaults.clock_jump_threshold_seconds if defaults else 2.0)
        trigger_min_events = args.trigger_min_events if args.trigger_min_events is not None else (defaults.trigger_min_events_per_cycle if defaults else 1)
        trigger_operator_markers = args.trigger_operator_markers or (defaults.trigger_operator_markers if defaults else False)
        trigger_exclude_kinds = (args.trigger_exclude_kind if args.trigger_exclude_kind is not None else (defaults.trigger_exclude_kinds if defaults else ["probe_error", "recorder_overrun", "recorder_storage", "clock_jump", "rosbag_sidecar", "recorder_probe_health"]))

        if defaults is not None:
            if args.profile is None:
                args.profile = defaults.profile
            if not args.namespace:
                args.namespace = defaults.namespace
            args.expect_node = defaults.expect_nodes + args.expect_node
            args.expect_topic = defaults.expect_topics + args.expect_topic
            args.expect_tf = defaults.expect_tf + args.expect_tf
            args.expect_lifecycle = defaults.expect_lifecycle + args.expect_lifecycle

        if window <= 0 or interval <= 0 or (duration is not None and duration <= 0) or post < 0:
            print("window/interval/duration must be positive; post must be non-negative", file=sys.stderr)
            return 2
        if consecutive <= 0 or cooldown < 0 or dedup_window < 0 or max_incidents <= 0 or sample_seconds <= 0 or workers <= 0:
            print("invalid watch timing/count configuration", file=sys.stderr)
            return 2
        if startup_grace < 0 or arm_after_healthy < 0 or min_free <= 0 or clock_jump_threshold <= 0 or trigger_min_events <= 0:
            print("startup grace/arm count/storage/trigger configuration is invalid", file=sys.stderr)
            return 2

        nodes, topics, transforms, lifecycle, profile_name = _merge_profile(args)
        config = WatchConfig(
            window_seconds=window,
            interval_seconds=interval,
            duration_seconds=duration,
            post_trigger_seconds=post,
            expect_nodes=nodes,
            expect_topics=topics,
            expect_tf=transforms,
            expect_lifecycle=lifecycle,
            output_dir=Path(output),
            stop_on_failure=args.stop_on_failure,
            consecutive_failures=consecutive,
            cooldown_seconds=cooldown,
            dedup_window_seconds=dedup_window,
            max_incidents=max_incidents,
            profile=profile_name,
            robot_id=defaults.robot_id if defaults else None,
            site_id=defaults.site_id if defaults else None,
            labels=dict(defaults.labels) if defaults else {},
            trigger_on_warning=trigger_on_warning,
            trigger_min_events_per_cycle=trigger_min_events,
            trigger_operator_markers=trigger_operator_markers,
            trigger_exclude_kinds=tuple(trigger_exclude_kinds),
            sample_seconds=sample_seconds,
            workers=workers,
            status_file=Path(status_file) if status_file else None,
            lock_file=Path(lock_file) if lock_file else None,
            marker_file=Path(marker_file) if marker_file else None,
            clock_jump_threshold_seconds=clock_jump_threshold,
            probe_degraded_after_cycles=(defaults.probe_degraded_after_cycles if defaults else 3),
            max_p95_cycle_seconds=(defaults.validation_max_p95_cycle_seconds if defaults else None),
            startup_grace_seconds=startup_grace,
            arm_after_healthy_cycles=arm_after_healthy,
            include_hostname=include_hostname,
            min_free_storage_mb=min_free,
            max_saved_incidents=max_saved,
            max_storage_mb=max_storage,
            config_id=config_digest(defaults) if defaults else None,
            bag_snapshot=defaults.bag_snapshot if defaults else BagSnapshotConfig(),
        )
        try:
            written = watch(config)
        except (RuntimeError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"Captured {len(written)} incident(s)")
        for path in written:
            print(path)
        return 1 if written and args.fail_on_incident else 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

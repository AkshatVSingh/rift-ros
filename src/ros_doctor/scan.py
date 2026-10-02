from __future__ import annotations

from dataclasses import dataclass, field

from ros_doctor.checks import environment_results, expected_nodes, expected_topics, graph_summary
from ros_doctor.collectors.environment import collect_environment
from ros_doctor.collectors.graph import list_nodes, list_topics
from ros_doctor.collectors.tf import check_transform
from ros_doctor.models import DiagnosticResult, Severity


@dataclass(slots=True)
class ScanRequest:
    expect_nodes: list[str] = field(default_factory=list)
    expect_topics: list[str] = field(default_factory=list)
    expect_tf: list[tuple[str, str]] = field(default_factory=list)


def run_scan(request: ScanRequest) -> tuple[list[DiagnosticResult], bool]:
    env = collect_environment()
    results = environment_results(env)
    if not env.ros_available:
        return results, False

    try:
        nodes = list_nodes()
        topics = list_topics()
    except RuntimeError as exc:
        results.append(DiagnosticResult(Severity.FAIL, "graph", "could not inspect ROS graph", str(exc)))
        return results, False

    results.extend(graph_summary(nodes, topics))
    results.extend(expected_nodes(nodes, request.expect_nodes))
    results.extend(expected_topics(topics, request.expect_topics))

    for parent, child in request.expect_tf:
        tf = check_transform(parent, child)
        severity = Severity.PASS if tf.available else Severity.FAIL
        results.append(
            DiagnosticResult(
                severity,
                "tf",
                f"transform {'available' if tf.available else 'unavailable'}: {parent} -> {child}",
                tf.evidence,
            )
        )

    return results, True

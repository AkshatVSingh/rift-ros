from __future__ import annotations

from collections.abc import Iterable

from ros_doctor.collectors.environment import EnvironmentSnapshot
from ros_doctor.collectors.graph import TopicInfo
from ros_doctor.models import DiagnosticResult, Severity


def environment_results(env: EnvironmentSnapshot) -> list[DiagnosticResult]:
    out: list[DiagnosticResult] = []
    if env.ros2_executable:
        out.append(DiagnosticResult(Severity.PASS, "environment", "ros2 executable found", env.ros2_executable))
    else:
        out.append(DiagnosticResult(Severity.FAIL, "environment", "ros2 executable not found"))

    if env.ros_distro:
        out.append(DiagnosticResult(Severity.PASS, "environment", f"ROS_DISTRO={env.ros_distro}"))
    else:
        out.append(DiagnosticResult(Severity.FAIL, "environment", "ROS_DISTRO is not set"))
    return out


def graph_summary(nodes: Iterable[str], topics: Iterable[TopicInfo]) -> list[DiagnosticResult]:
    nodes = list(nodes)
    topics = list(topics)
    return [
        DiagnosticResult(Severity.PASS, "graph", f"discovered {len(nodes)} nodes"),
        DiagnosticResult(Severity.PASS, "graph", f"discovered {len(topics)} topics"),
    ]


def expected_nodes(nodes: Iterable[str], expected: Iterable[str]) -> list[DiagnosticResult]:
    existing = set(nodes)
    results = []
    for name in expected:
        if name in existing:
            results.append(DiagnosticResult(Severity.PASS, "node", f"expected node present: {name}"))
        else:
            results.append(DiagnosticResult(Severity.FAIL, "node", f"expected node missing: {name}"))
    return results


def expected_topics(topics: Iterable[TopicInfo], expected: Iterable[str]) -> list[DiagnosticResult]:
    existing = {topic.name for topic in topics}
    results = []
    for name in expected:
        if name in existing:
            results.append(DiagnosticResult(Severity.PASS, "topic", f"expected topic present: {name}"))
        else:
            results.append(DiagnosticResult(Severity.FAIL, "topic", f"expected topic missing: {name}"))
    return results

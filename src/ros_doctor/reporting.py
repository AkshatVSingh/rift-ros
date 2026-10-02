from __future__ import annotations

import json
from collections import Counter
from typing import Iterable

from ros_doctor.models import DiagnosticResult, Severity


_LABELS = {
    Severity.PASS: "PASS",
    Severity.WARN: "WARN",
    Severity.FAIL: "FAIL",
    Severity.INFO: "INFO",
}


def render_text(results: Iterable[DiagnosticResult]) -> str:
    results = list(results)
    lines = ["ROS Doctor", "─" * 40]
    for item in results:
        label = _LABELS[item.severity]
        line = f"{label:<5} {item.component:<13} {item.message}"
        if item.evidence:
            line += f" ({item.evidence})"
        lines.append(line)

    counts = Counter(item.severity for item in results)
    lines.append("")
    lines.append(
        "Summary: "
        f"{counts[Severity.PASS]} pass, "
        f"{counts[Severity.WARN]} warning, "
        f"{counts[Severity.FAIL]} failure"
    )
    return "\n".join(lines)


def render_json(results: Iterable[DiagnosticResult]) -> str:
    return json.dumps([item.to_dict() for item in results], indent=2, sort_keys=True)

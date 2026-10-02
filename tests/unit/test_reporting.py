import json

from ros_doctor.models import DiagnosticResult, Severity
from ros_doctor.reporting import render_json, render_text


def test_text_report_contains_summary():
    text = render_text([DiagnosticResult(Severity.PASS, "graph", "ok")])
    assert "1 pass" in text


def test_json_report_is_machine_readable():
    payload = json.loads(render_json([DiagnosticResult(Severity.WARN, "topic", "slow")]))
    assert payload[0]["severity"] == "warning"

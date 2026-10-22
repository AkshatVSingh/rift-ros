from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from rift_ros.analysis import summarize
from rift_ros.demo import generate_demo, scenarios
from rift_ros.io import pack_bundle, read_incident, verify_bundle, write_incident


@dataclass(frozen=True, slots=True)
class SelfTestResult:
    scenario: str
    passed: bool
    details: str


def run_self_test(output: str | Path | None = None) -> list[SelfTestResult]:
    if output is None:
        temporary = tempfile.TemporaryDirectory(prefix="rift-self-test-")
        root = Path(temporary.name)
    else:
        temporary = None
        root = Path(output)
        root.mkdir(parents=True, exist_ok=True)

    results: list[SelfTestResult] = []
    try:
        for scenario in scenarios():
            try:
                incident = generate_demo(scenario)
                directory = root / scenario
                write_incident(directory, incident)
                ok, problems = verify_bundle(directory)
                if not ok:
                    raise RuntimeError("; ".join(problems))
                archive = pack_bundle(directory)
                ok, problems = verify_bundle(archive)
                if not ok:
                    raise RuntimeError("; ".join(problems))
                restored = read_incident(archive)
                summary = summarize(restored.events)
                if summary.failures <= 0:
                    raise RuntimeError("synthetic incident had no failure evidence")
                results.append(
                    SelfTestResult(
                        scenario,
                        True,
                        f"{summary.failures} failures; fingerprint {summary.fingerprint}",
                    )
                )
            except Exception as exc:
                results.append(SelfTestResult(scenario, False, str(exc)))
    finally:
        if temporary is not None:
            temporary.cleanup()
    return results

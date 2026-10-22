from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from rift_ros.io import read_incident
from rift_ros.session import read_session_report


@dataclass(frozen=True, slots=True)
class ValidationScenario:
    scenario_id: str
    description: str
    expected_kinds: tuple[str, ...]
    marker_example: str
    safety_note: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["expected_kinds"] = list(self.expected_kinds)
        return data


NAV2_SCENARIOS = (
    ValidationScenario(
        "odom-dropout",
        "Interrupt or pause odometry in a controlled simulation/test environment.",
        ("topic_rate",),
        'rift mark "odom fault started" --scenario odom-dropout --severity warn',
        "Do not inject this fault on an operating production robot or around people/equipment.",
    ),
    ValidationScenario(
        "lidar-dropout",
        "Interrupt the configured LiDAR topic in a controlled test.",
        ("topic_rate",),
        'rift mark "lidar fault started" --scenario lidar-dropout --severity warn',
        "Use simulation or a physically safe, stationary test setup.",
    ),
    ValidationScenario(
        "tf-loss",
        "Remove or stop one expected transform in a controlled test.",
        ("tf_presence",),
        'rift mark "tf fault started" --scenario tf-loss --severity warn',
        "Prefer simulation; do not disrupt TF while a production robot is moving.",
    ),
    ValidationScenario(
        "lifecycle-drop",
        "Deactivate one monitored Nav2 lifecycle node in a controlled test.",
        ("lifecycle_state",),
        'rift mark "lifecycle fault started" --scenario lifecycle-drop --severity warn',
        "Run while the robot is stationary and the test area is controlled.",
    ),
    ValidationScenario(
        "qos-mismatch",
        "Use a test publisher/subscriber with deliberately incompatible QoS.",
        ("qos_compatibility",),
        'rift mark "qos mismatch started" --scenario qos-mismatch --severity warn',
        "Use a dedicated test topic or simulation; do not alter production QoS blindly.",
    ),
    ValidationScenario(
        "timestamp-delay",
        "Publish delayed/stale stamped test messages on a dedicated validation topic.",
        ("topic_delay",),
        'rift mark "timestamp delay started" --scenario timestamp-delay --severity warn',
        "Use a test topic or simulator rather than falsifying production sensor time.",
    ),
    ValidationScenario(
        "healthy-long-run",
        "Run without injecting a fault to measure false incident rate and recorder overhead.",
        (),
        'rift mark "healthy validation window started" --scenario healthy-long-run',
        "This is the safest and most important false-positive validation case.",
    ),
)


def validation_plan(profile: str = "nav2") -> dict:
    if profile != "nav2":
        raise ValueError("only the nav2 field-validation plan is available in v0.6")
    return {
        "schema": "rift.field-validation-plan/v1",
        "profile": profile,
        "principle": "RIFT never injects robot faults automatically; the operator performs controlled tests and annotates them with rift mark.",
        "scenarios": [scenario.to_dict() for scenario in NAV2_SCENARIOS],
    }


def write_validation_plan(output: str | Path, profile: str = "nav2") -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(validation_plan(profile), indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return target


def score_validation(plan: dict, evidence_paths: Iterable[str | Path]) -> dict:
    if plan.get("schema") != "rift.field-validation-plan/v1":
        raise ValueError("unsupported validation plan")
    scenarios = {item["scenario_id"]: item for item in plan.get("scenarios", [])}
    observations: dict[str, dict] = {
        key: {"marked": 0, "detected": 0, "incident_ids": [], "session_ids": []}
        for key in scenarios
    }

    for raw_path in evidence_paths:
        path = Path(raw_path)
        # Session reports make healthy-long-run measurable even when no incident fires.
        if path.is_file() and path.suffix == ".json":
            try:
                session = read_session_report(path)
            except (OSError, ValueError, json.JSONDecodeError):
                session = None
            if session is not None:
                markers = session.get("marker_scenarios", {})
                if isinstance(markers, dict):
                    for scenario_id, count_raw in markers.items():
                        if scenario_id not in observations:
                            continue
                        count = max(0, int(count_raw))
                        row = observations[scenario_id]
                        # Fault scenarios are scored from incident evidence to avoid
                        # double-counting the same marker in both session and incident.
                        if scenario_id == "healthy-long-run":
                            row["marked"] += count
                            metrics = session.get("metrics", {}) if isinstance(session.get("metrics"), dict) else {}
                            healthy = (
                                int(session.get("incidents_captured", 0)) == 0
                                and int(metrics.get("anomalous_cycles", 0)) == 0
                            )
                            if healthy:
                                row["detected"] += count
                            row["session_ids"].append(str(session.get("session_id", path.stem)))
                continue

        incident = read_incident(path)
        marked = {
            str(event.evidence.get("scenario"))
            for event in incident.events
            if event.kind == "operator_marker" and event.evidence.get("scenario")
        }
        kinds = {event.kind for event in incident.events}
        for scenario_id in marked:
            if scenario_id not in observations or scenario_id == "healthy-long-run":
                continue
            row = observations[scenario_id]
            row["marked"] += 1
            expected = set(scenarios[scenario_id].get("expected_kinds", []))
            if expected.intersection(kinds):
                row["detected"] += 1
            row["incident_ids"].append(incident.incident_id)

    scored = 0
    passed = 0
    results: list[dict] = []
    for scenario_id, scenario in scenarios.items():
        row = observations[scenario_id]
        if row["marked"]:
            scored += 1
            ok = row["detected"] == row["marked"]
            if ok:
                passed += 1
        else:
            ok = False
        results.append({
            "scenario_id": scenario_id,
            "description": scenario.get("description"),
            "marked_runs": row["marked"],
            "successful_runs": row["detected"],
            "passed": ok if row["marked"] else None,
            "incident_ids": row["incident_ids"],
            "session_ids": row["session_ids"],
        })
    return {
        "schema": "rift.field-validation-result/v2",
        "scored_scenarios": scored,
        "passed_scenarios": passed,
        "pass_rate": (passed / scored if scored else None),
        "results": results,
    }


def read_validation_plan(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))

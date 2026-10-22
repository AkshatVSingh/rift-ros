from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


LATEST_CONFIG_SCHEMA = "rift.config/v7"


def upgrade_config_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Upgrade any supported historical config to the current schema without dropping user keys."""

    upgraded = copy.deepcopy(data)
    schema = upgraded.get("schema")
    if schema not in {None, "rift.config/v1", "rift.config/v2", "rift.config/v3", "rift.config/v4", "rift.config/v5", "rift.config/v6", "rift.config/v7"}:
        raise ValueError(f"unsupported config schema: {schema}")

    identity = upgraded.setdefault("identity", {})
    watch = upgraded.setdefault("watch", {})
    trigger = upgraded.setdefault("trigger", {})
    validation = upgraded.setdefault("validation", {})

    identity.setdefault("robot_id", None)
    identity.setdefault("site_id", None)
    identity.setdefault("labels", {})
    watch.setdefault("marker_file", "rift-markers.jsonl")
    watch.setdefault("clock_jump_threshold_seconds", 2.0)
    watch.setdefault("probe_degraded_after_cycles", 3)
    watch.setdefault("dedup_window_seconds", 120.0)
    trigger.setdefault("min_events_per_cycle", 1)
    trigger.setdefault("operator_markers", False)
    trigger.setdefault(
        "exclude_kinds",
        ["probe_error", "recorder_overrun", "recorder_storage", "clock_jump", "rosbag_sidecar", "recorder_probe_health"],
    )
    validation.setdefault("max_probe_error_rate", 0.0)
    validation.setdefault("max_overrun_rate", 0.05)
    validation.setdefault("max_failed_cycle_rate", 0.0)
    validation.setdefault("max_p95_cycle_seconds", None)
    upgraded["schema"] = LATEST_CONFIG_SCHEMA
    return upgraded


def upgrade_config_file(path: str | Path, output: str | Path | None = None) -> Path:
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    upgraded = upgrade_config_dict(data)
    target = Path(output) if output is not None else source
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(upgraded, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return target

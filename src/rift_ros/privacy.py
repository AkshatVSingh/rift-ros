from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from rift_ros.models import Event, Incident

_SENSITIVE_KEYS = {
    "hostname",
    "host",
    "username",
    "user",
    "home",
    "cwd",
    "workspace",
    "workspace_path",
    "ip",
    "ip_address",
    "address",
    "serial",
    "serial_number",
}
_HOME_RE = re.compile(r"/home/[^/\s]+")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def redact_text(value: str) -> str:
    value = _HOME_RE.sub("/home/<redacted>", value)
    value = _IPV4_RE.sub("<redacted-ip>", value)
    return value


def sanitize_value(value: Any, *, parent_key: str | None = None) -> Any:
    if parent_key and parent_key.lower() in _SENSITIVE_KEYS:
        return "<redacted>"
    if isinstance(value, dict):
        return {
            str(key): sanitize_value(item, parent_key=str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_value(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value


def sanitize_event(event: Event) -> Event:
    return replace(
        event,
        message=redact_text(event.message),
        evidence=sanitize_value(event.evidence),
    )


def sanitize_incident(incident: Incident) -> Incident:
    metadata = sanitize_value(incident.metadata)
    metadata["sanitized"] = True
    metadata["sanitized_from"] = incident.incident_id
    return Incident(
        incident_id=f"{incident.incident_id}-sanitized",
        created_at=incident.created_at,
        reason=redact_text(incident.reason),
        events=[sanitize_event(event) for event in incident.events],
        metadata=metadata,
    )

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class Severity(str, Enum):
    PASS = "pass"
    WARN = "warning"
    FAIL = "failure"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    severity: Severity
    component: str
    message: str
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data

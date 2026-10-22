from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RetentionResult:
    kept: int
    removed: tuple[str, ...]
    bytes_after: int


def _incident_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        [item for item in root.iterdir() if item.is_dir() and (item / "bundle.json").exists()],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )


def _size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def prune_incidents(
    root: str | Path,
    max_saved_incidents: int | None = None,
    max_storage_mb: float | None = None,
) -> RetentionResult:
    root = Path(root)
    if max_saved_incidents is not None and max_saved_incidents <= 0:
        raise ValueError("max_saved_incidents must be positive")
    if max_storage_mb is not None and max_storage_mb <= 0:
        raise ValueError("max_storage_mb must be positive")

    incidents = _incident_dirs(root)
    sizes = {item: _size(item) for item in incidents}
    removed: list[str] = []

    if max_saved_incidents is not None:
        for item in incidents[max_saved_incidents:]:
            removed.append(item.name)
            shutil.rmtree(item)
            sizes.pop(item, None)
        incidents = incidents[:max_saved_incidents]

    if max_storage_mb is not None:
        budget = int(max_storage_mb * 1024 * 1024)
        total = sum(sizes.values())
        for item in reversed(incidents):
            if total <= budget:
                break
            total -= sizes.get(item, 0)
            removed.append(item.name)
            shutil.rmtree(item)
            sizes.pop(item, None)
        incidents = [item for item in incidents if item.exists()]

    return RetentionResult(len(incidents), tuple(removed), sum(sizes.values()))

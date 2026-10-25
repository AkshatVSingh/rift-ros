from __future__ import annotations

import os
from pathlib import Path


def _acquire_platform_lock(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write("\0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise BlockingIOError from exc
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release_platform_lock(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class RecorderLock:
    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path is not None else None
        self._handle = None

    def __enter__(self) -> "RecorderLock":
        if self.path is None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        handle = self.path.open("r+", encoding="utf-8")
        try:
            _acquire_platform_lock(handle)
        except BlockingIOError as exc:
            handle.close()
            raise RuntimeError(f"another RIFT recorder is already using lock {self.path}") from exc
        handle.seek(0)
        handle.write(f"{os.getpid()}\n")
        handle.truncate()
        handle.flush()
        self._handle = handle
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._handle is None:
            return
        try:
            _release_platform_lock(self._handle)
        finally:
            self._handle.close()
            self._handle = None
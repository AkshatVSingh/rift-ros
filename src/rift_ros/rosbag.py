from __future__ import annotations

import shutil
import subprocess
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from rift_ros.shell import run


@dataclass(slots=True)
class BagSnapshotConfig:
    """Optional rosbag2 snapshot sidecar configuration.

    Jazzy snapshot mode is memory-size bounded, so ``max_cache_mb`` is a memory
    budget, not an exact time window. RIFT triggers the snapshot after its own
    post-trigger window so the bag contains the freshest pre/post-failure data
    that still fits in the cache.
    """

    enabled: bool = False
    topics: list[str] = field(default_factory=list)
    max_cache_mb: int = 256
    storage_id: str = "mcap"
    node_name: str = "rift_rosbag2_recorder"
    use_sim_time: bool = False
    startup_timeout_seconds: float = 8.0
    snapshot_timeout_seconds: float = 8.0
    settle_seconds: float = 0.4
    keep_failed_session: bool = False

    @property
    def service_name(self) -> str:
        return f"/{self.node_name.strip('/')}/snapshot"

    def validate(self) -> None:
        if not self.enabled:
            return
        if not self.topics:
            raise ValueError("rosbag_snapshot.enabled requires at least one topic")
        if self.max_cache_mb <= 0:
            raise ValueError("rosbag_snapshot.max_cache_mb must be positive")
        if self.startup_timeout_seconds <= 0 or self.snapshot_timeout_seconds <= 0:
            raise ValueError("rosbag snapshot timeouts must be positive")
        if self.settle_seconds < 0:
            raise ValueError("rosbag_snapshot.settle_seconds must be non-negative")
        if not self.node_name.strip("/"):
            raise ValueError("rosbag_snapshot.node_name must not be empty")
        for topic in self.topics:
            if not topic.startswith("/"):
                raise ValueError(f"rosbag snapshot topic must be absolute: {topic!r}")


def rosbag_snapshot_supported(timeout: float = 4.0) -> tuple[bool, str]:
    """Check whether the installed ros2 bag recorder exposes snapshot mode."""

    result = run(["ros2", "bag", "record", "--help"], timeout)
    text = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0:
        return False, result.stderr.strip() or result.stdout.strip() or "ros2 bag record unavailable"
    if "--snapshot-mode" not in text or "--max-cache-size" not in text:
        return False, "installed rosbag2 recorder does not expose snapshot mode/cache controls"
    interface = run(["ros2", "interface", "show", "rosbag2_interfaces/srv/Snapshot"], timeout)
    if interface.returncode != 0:
        return False, "rosbag2_interfaces/srv/Snapshot is unavailable"
    return True, "rosbag2 snapshot mode available"


def build_record_command(config: BagSnapshotConfig, uri: Path) -> list[str]:
    config.validate()
    command = [
        "ros2",
        "bag",
        "record",
        "--snapshot-mode",
        "--max-cache-size",
        str(int(config.max_cache_mb) * 1024 * 1024),
        "--node-name",
        config.node_name.strip("/"),
        "--disable-keyboard-controls",
        "--storage",
        config.storage_id,
        "-o",
        str(uri),
    ]
    if config.use_sim_time:
        command.append("--use-sim-time")
    command.extend(["--topics", *config.topics])
    return command


def _zip_directory(source: Path, destination: Path) -> Path:
    if not source.exists() or not any(item.is_file() for item in source.rglob("*")):
        raise RuntimeError("rosbag snapshot produced no files")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for item in sorted(source.rglob("*")):
                if item.is_file():
                    archive.write(item, arcname=item.relative_to(source).as_posix())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


class RosbagSnapshotSidecar:
    """Own one rosbag2 snapshot recorder and rotate it after each incident."""

    def __init__(self, config: BagSnapshotConfig, cache_root: Path):
        self.config = config
        self.cache_root = Path(cache_root)
        self.process: subprocess.Popen[bytes] | None = None
        self.uri: Path | None = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self) -> Path:
        self.config.validate()
        if not self.config.enabled:
            raise RuntimeError("rosbag snapshot sidecar is disabled")
        if self.running:
            assert self.uri is not None
            return self.uri

        supported, message = rosbag_snapshot_supported()
        if not supported:
            raise RuntimeError(message)

        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.uri = self.cache_root / f"session-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        command = build_record_command(self.config, self.uri)
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        deadline = time.monotonic() + self.config.startup_timeout_seconds
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                code = self.process.returncode
                self.process = None
                raise RuntimeError(f"rosbag2 snapshot recorder exited during startup (code {code})")
            services = run(["ros2", "service", "list"], timeout=2.0)
            if services.returncode == 0 and self.config.service_name in services.stdout.splitlines():
                return self.uri
            time.sleep(0.2)

        self.stop(cleanup=not self.config.keep_failed_session)
        raise RuntimeError(
            f"rosbag2 snapshot service {self.config.service_name} did not appear within "
            f"{self.config.startup_timeout_seconds:.1f}s"
        )

    def take_snapshot(self) -> None:
        if not self.running:
            raise RuntimeError("rosbag2 snapshot recorder is not running")
        result = run(
            [
                "ros2",
                "service",
                "call",
                self.config.service_name,
                "rosbag2_interfaces/srv/Snapshot",
                "{}",
            ],
            timeout=self.config.snapshot_timeout_seconds,
        )
        output = f"{result.stdout}\n{result.stderr}".lower()
        if result.returncode != 0 or "success: true" not in output:
            raise RuntimeError(
                result.stderr.strip()
                or result.stdout.strip()
                or "rosbag2 snapshot service did not report success"
            )
        if self.config.settle_seconds:
            time.sleep(self.config.settle_seconds)

    def capture_archive(self, destination: Path) -> Path:
        """Flush the cache, stop the recorder, and package its bag directory."""

        if self.uri is None:
            raise RuntimeError("rosbag2 snapshot session has no output URI")
        self.take_snapshot()
        source = self.uri
        self.stop(cleanup=False)
        try:
            return _zip_directory(source, destination)
        finally:
            if source.exists() and not self.config.keep_failed_session:
                shutil.rmtree(source, ignore_errors=True)
            self.uri = None

    def stop(self, *, cleanup: bool = True) -> None:
        process = self.process
        self.process = None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
        if cleanup and self.uri is not None:
            shutil.rmtree(self.uri, ignore_errors=True)
            self.uri = None

    def restart(self) -> Path:
        self.stop(cleanup=True)
        return self.start()

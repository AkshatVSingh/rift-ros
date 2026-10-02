from __future__ import annotations

from dataclasses import dataclass

from ros_doctor.shell import run


@dataclass(frozen=True, slots=True)
class TopicInfo:
    name: str
    types: tuple[str, ...] = ()


def list_nodes(timeout: float = 5.0) -> list[str]:
    result = run(["ros2", "node", "list"], timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "failed to list ROS 2 nodes")
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})


def list_topics(timeout: float = 5.0) -> list[TopicInfo]:
    result = run(["ros2", "topic", "list", "-t"], timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "failed to list ROS 2 topics")

    topics: list[TopicInfo] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if " [" in line and line.endswith("]"):
            name, raw_types = line.split(" [", 1)
            types = tuple(t.strip() for t in raw_types[:-1].split(",") if t.strip())
            topics.append(TopicInfo(name=name.strip(), types=types))
        else:
            topics.append(TopicInfo(name=line))
    return sorted(topics, key=lambda item: item.name)

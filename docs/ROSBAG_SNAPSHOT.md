# Rosbag2 snapshot integration

RIFT v0.6 can optionally pair its lightweight structured recorder with rosbag2 snapshot mode.

## Why

Structured RIFT events are fast to inspect and compare. Raw bags are heavier but preserve message payloads for replay and deeper forensic work. The two evidence types complement each other.

## Lifecycle

1. RIFT starts rosbag2 in snapshot mode.
2. rosbag2 caches selected topics in memory.
3. RIFT detects and debounces an incident.
4. RIFT continues through its configured post-trigger window.
5. RIFT calls the recorder's snapshot service.
6. RIFT stops/finalizes that rosbag session.
7. The bag directory is packaged as `rosbag2.zip` and checksummed in the incident manifest.
8. If continuous recording continues, RIFT starts a fresh snapshot sidecar for the next incident.

## Jazzy cache semantics

ROS 2 Jazzy exposes `--snapshot-mode`, `--max-cache-size`, and a snapshot service. The cache is byte bounded rather than time bounded. Topic bandwidth therefore determines how much history fits.

Jazzy's recorder help also documents double buffering, meaning pessimistic cache memory can approach twice `max-cache-size`.

## Topic selection

Record only data that materially helps incident investigation. High-rate cameras and point clouds can consume the cache quickly.

A reasonable mobile-robot starting set may include:

```text
/tf
/tf_static
/rosout
/odom
/scan
```

Add robot-specific topics only after measuring bandwidth and memory.

## Privacy

Raw bags can contain sensitive or proprietary payloads. RIFT does not claim to sanitize them. `rift sanitize` drops attachments by design.

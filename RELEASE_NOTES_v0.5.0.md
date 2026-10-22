# RIFT-ROS Community v0.5.0

v0.5 turns the recorder into a field-validation-ready incident capture tool.

## Major additions

- optional rosbag2 snapshot sidecar for raw pre/post-failure message evidence
- verified binary attachments in `rift.bundle/v3`
- safe attachment extraction with `rift extract`
- `rift preflight` deployment checks
- `rift validate-live` collector timing/error validation without incident creation
- stable recorder session IDs across status and incidents
- privacy-safe sanitization that deliberately omits unredactable binary attachments
- rosbag cache-memory advisory checks
- richer heartbeat metadata for snapshot capture configuration

## Rosbag2 snapshot integration

Snapshot capture is opt-in. RIFT starts rosbag2 in snapshot mode with a bounded in-memory cache, waits through RIFT's normal post-trigger window, triggers the rosbag snapshot service, then packages the finalized bag directory as `rosbag2.zip` inside the incident bundle.

On ROS 2 Jazzy the cache is byte-bounded via `--max-cache-size`; it is not an exact time-duration guarantee. Size the cache using measured data rates on the actual robot.

## Bundle schema

New bundles use `rift.bundle/v3`. Core JSON evidence remains inspectable and attachments are individually checksummed. RIFT continues to read and verify legacy bundle versions.

## Deployment gate

Before long-running deployment:

```bash
rift preflight --config rift.json
rift validate-live --config rift.json --cycles 10 -o validation.json
```

A production candidate should show no required preflight failures, no probe errors, and collector timing comfortably below the configured interval.

## Privacy

`rift sanitize` rebuilds a share-safe structured bundle and intentionally drops raw attachments such as rosbag snapshots. Raw ROS message payloads can contain proprietary maps, sensor data, identifiers, or other material RIFT cannot safely redact generically.

## Compatibility

- target: ROS 2 Jazzy / Ubuntu 24.04
- Python 3.10+
- offline incident analysis remains ROS-independent
- loading legacy `rift.config/v1-v3` remains supported

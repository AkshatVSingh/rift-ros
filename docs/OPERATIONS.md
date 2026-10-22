# Recorder operations

## Commission before deployment

```bash
source /opt/ros/jazzy/setup.bash
source /path/to/robot/install/setup.bash
rift doctor
rift validate-config /etc/rift/rift.json
rift preflight --config /etc/rift/rift.json
rift validate-live --config /etc/rift/rift.json --cycles 10 -o commissioning.json
```

`validate-live` does not create incidents. It measures collector timing/errors against the actual graph.

## Startup and arming

- `startup_grace_seconds`: observe but never trigger during initial startup
- `arm_after_healthy_cycles`: optionally require N healthy cycles before automatic triggering
- `consecutive_failures`: persistence debounce
- `cooldown_seconds`: minimum gap between captured incidents

Keep `arm_after_healthy_cycles=0` if faults present from boot must remain capturable after the grace period.

## Recorder sessions

Each `rift watch` run gets a stable `session_id`. The ID is written to status and all incidents from that run. Pro corpus analysis can use it to distinguish repeated failures inside one robot session from failures across restarts.

## Single-recorder lock

RIFT uses `rift-recorder.lock` by default. Disable it only deliberately with `--no-lock`.

## Heartbeat

`rift-status.json` reports state, uptime, session ID, arming/trigger state, healthy/failure streaks, last healthy/anomaly time, latest incident, collector timing, and rosbag snapshot configuration.

```bash
rift status --file /var/lib/rift/status.json
```

## Cadence and overhead

Probes run concurrently. If a cycle exceeds `interval_seconds`, RIFT emits `recorder_overrun` rather than hiding missed cadence.

Keep `sample_seconds` comfortably below `interval_seconds`. Use `rift validate-live` to measure p95/max collector duration on the actual robot.

## Rosbag snapshot sidecar

The sidecar is disabled by default. When enabled:

- selected topics are cached by rosbag2 in memory
- RIFT snapshots after its post-trigger window
- the finalized bag becomes `rosbag2.zip`
- a new sidecar starts for the next incident

A failed sidecar does not crash the structured RIFT recorder. The failure is recorded as evidence and surfaced by preflight/status where possible.

## Storage

- `min_free_storage_mb`: warning threshold
- `max_saved_incidents`: incident count limit
- `max_storage_mb`: incident storage budget

Manual enforcement:

```bash
rift prune /var/lib/rift/incidents --max-count 100 --max-mb 2048
```

Raw bag attachments count toward storage once captured.

## Privacy

Hostnames remain excluded by default. `rift sanitize` rebuilds a share-safe structured bundle and intentionally omits binary attachments. Raw rosbag payloads must be reviewed separately.

## Threshold calibration

Built-in rates/jitter are examples. Establish healthy ranges on each robot class before production thresholds are enforced.


## Recorder exit semantics (v0.7)

A captured robot incident is not a recorder-process failure. `rift watch` therefore exits 0 after a successful lifecycle by default. Use `--fail-on-incident` only when an incident should fail CI or a controlled validation job.

Repeated probe failures are tracked as recorder degradation and exposed through `rift status`; recorder-health events remain excluded from robot incident triggering by default.

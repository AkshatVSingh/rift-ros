# Configuration

Generate a starting point:

```bash
rift init-config --profile nav2 -o rift.json
rift validate-config rift.json
```

Current schema: `rift.config/v7`. RIFT migrates older v1-v5 configs forward when loading or with `rift upgrade-config`.

## Watch controls

- `window_seconds`: structured pre-trigger history kept by RIFT
- `interval_seconds`: desired cycle cadence
- `post_trigger_seconds`: evidence collection after trigger
- `startup_grace_seconds`: startup observation period where incidents cannot trigger
- `arm_after_healthy_cycles`: optional healthy cycles required before arming (`0` disables the gate)
- `consecutive_failures`: persistence debounce
- `cooldown_seconds`: minimum time between incidents
- `sample_seconds`: sampling window for rate/timing probes
- `workers`: concurrent probe workers
- `lock_file`: single-recorder process lock

## Rosbag snapshot sidecar

The `rosbag_snapshot` section is optional and disabled by default:

```json
{
  "rosbag_snapshot": {
    "enabled": false,
    "topics": ["/tf", "/tf_static", "/rosout", "/odom", "/scan"],
    "max_cache_mb": 256,
    "storage_id": "mcap",
    "node_name": "rift_rosbag2_recorder",
    "use_sim_time": false,
    "startup_timeout_seconds": 8,
    "snapshot_timeout_seconds": 8,
    "settle_seconds": 0.4,
    "keep_failed_session": false
  }
}
```

`max_cache_mb` is a byte-memory budget, not an exact time duration. On Jazzy rosbag2 uses double buffering, so pessimistic cache memory can approach roughly twice this value before other process overhead.

`keep_failed_session` is a troubleshooting option. Leave it false normally so failed/unused cache directories are removed.

## Retention

- `max_saved_incidents`
- `max_storage_mb`
- `min_free_storage_mb`

Raw bag attachments count toward incident storage after capture.

## Privacy

- `include_hostname`: false by default

Raw rosbag attachments are not redacted by RIFT. `rift sanitize` deliberately omits binary attachments from the share-safe copy.

## Expectations

Topic expectations can include minimum/maximum frequency, maximum jitter, optional maximum header delay, publisher/subscriber requirements and QoS checking.

Header-delay probing is intentionally opt-in because it adds measurement overhead and needs careful clock semantics in simulation/replay.


## Identity and performance budget (v6)

```json
{
  "identity": {
    "robot_id": "amr-17",
    "site_id": "pune-lab",
    "labels": {"model": "dynamo1500"}
  },
  "watch": {"probe_degraded_after_cycles": 3},
  "validation": {"max_p95_cycle_seconds": 1.5}
}
```

Identity is descriptive only; it never changes ROS names or robot behavior. `max_p95_cycle_seconds` is optional and should be calibrated from the actual deployment host.

## Incident deduplication

`watch.dedup_window_seconds` suppresses a repeated full bundle when the same failure fingerprint recurs on the same robot/site inside the configured window. The occurrence is still written to `_duplicates/occurrences.jsonl` and counted in the session report. Set it to `0` to disable deduplication.

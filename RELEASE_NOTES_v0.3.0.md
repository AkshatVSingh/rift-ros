# RIFT-ROS Community v0.3.0

v0.3 turns the recorder into a more credible long-running robot-side component.

## Added

- concurrent live probes
- topic frequency min/max/stddev parsing
- configurable topic jitter thresholds
- header timestamp delay checks
- publisher/subscriber QoS capture
- deterministic reliability/durability mismatch checks
- degradation/recovery state-transition events
- recorder cycle timing and overrun warnings
- heartbeat/status JSON
- graceful SIGTERM handling
- trigger evidence in incident metadata
- atomic JSON/JSONL writes
- automatic retention by count and disk budget
- seven-scenario synthetic fault lab
- offline `rift self-test`
- `rift status` and `rift prune`

## Compatibility

Existing v0.1/v0.2 incident JSON remains readable. v0.3 config files use `rift.config/v2`; the loader continues to accept `rift.config/v1`.

## Validation status

The offline/unit suite is automated. Live ROS 2/Jazzy field validation remains required before production claims.

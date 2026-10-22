# RIFT-ROS v0.8.0

v0.8 adds team-oriented incident operations on top of the v0.7 multi-robot recorder.

## Highlights

- Same-fingerprint incidents can be deduplicated within a configurable window while every occurrence is still counted in a durable JSONL ledger.
- Review state is stored outside immutable incident evidence: open, acknowledged, resolved or ignored, with owner, labels and notes.
- Session schema v3 tracks full incident captures and deduplicated repeats separately.
- Config schema v7 adds `watch.dedup_window_seconds` (120 s default, `0` disables).
- Catalog output can include review state and owner.
- New commands: `rift review`, `rift reviews`, `rift duplicates`.

RIFT remains read-only with respect to robot motion, parameters and lifecycle state.

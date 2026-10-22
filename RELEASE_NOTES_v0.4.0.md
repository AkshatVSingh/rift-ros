# RIFT-ROS Community v0.4.0

Release-hardening update.

## Highlights

- startup grace period and optional healthy-state arming
- single-recorder process lock
- privacy-by-default hostname handling
- `rift doctor` host readiness check
- `rift validate-config` with stable config ID and warnings
- `rift inspect` bundle metadata/integrity summary
- `rift sanitize` share-safe bundle copy
- `rift.bundle/v2` manifest with checksums, byte sizes, event count and fingerprint
- hardened ZIP verification and atomic archive publishing
- richer `rift.status/v2` heartbeat
- storage-headroom evidence
- safer probe-error handling
- header-delay checks made opt-in in built-in profiles
- Python module entry point (`python -m rift_ros`)

Synthetic tests remain a regression suite, not a field-accuracy claim.

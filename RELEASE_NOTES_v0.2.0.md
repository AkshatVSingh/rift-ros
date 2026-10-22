# RIFT-ROS Community v0.2.0

v0.2.0 moves RIFT from a proof-of-concept recorder toward a usable incident-forensics alpha.

## Added

- consecutive-failure trigger debouncing
- incident cooldown and maximum-capture limits
- built-in `nav2` and `sensors` runtime profiles
- namespace support for profiles
- Nav2 lifecycle-state checks
- publisher/subscriber evidence for profile topics
- minimum and optional maximum topic-rate thresholds
- host load / memory / disk evidence
- stable fault fingerprints
- `bundle.json` with SHA-256 integrity hashes
- `rift verify`
- `rift pack` portable `.rift.zip` archives
- direct offline analysis of packed archives
- four synthetic fault scenarios
- stronger real-robot validation plan

## Safety

The Community recorder remains read-only. It does not change lifecycle state, parameters, processes, or robot motion.

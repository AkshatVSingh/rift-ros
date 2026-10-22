# RIFT-ROS v0.6.0

v0.6 is the field-validation and evidence-quality release.

## Added

- operator marker journal (`rift mark`) with session-aware annotations
- trigger quorum and infrastructure-event filtering
- host wall-clock jump detection
- recorder performance telemetry including anomalous/healthy cycle counts
- config schema v5 plus migration from older configs
- local incident catalog
- recorder session summaries, including healthy runs that produce no incident
- `rift sessions` to inspect session summaries
- `rift export` for CSV/JSON incident timelines
- `rift field-plan` for safe operator-driven validation scenarios
- `rift field-score` for scoring marked fault runs and healthy long-run sessions
- threshold-based `validate-live` acceptance criteria

## Reliability changes

- recorder/infrastructure warnings such as probe errors, storage pressure and clock jumps are excluded from robot-failure triggering by default
- trigger quorum can require multiple independent failure events per cycle
- session summaries are written atomically and do not include host identity by default
- healthy long-run validation can now measure false incident behavior even when no incident bundle is created

## Validation boundary

Synthetic tests verify software behavior only. Real-robot claims still require the field-validation plan across controlled Jazzy/Nav2 environments. RIFT does not inject robot faults automatically.

# RIFT-ROS v0.7.0

Release focus: multi-robot attribution, recorder health separation, deterministic replay, compatibility reporting and performance-budget enforcement.

## Highlights

- `rift.config/v6` adds `identity.robot_id`, `identity.site_id`, labels, probe-degradation threshold and optional p95 cycle budget.
- Incident bundles, status heartbeats and session reports preserve robot/site identity.
- Session reports now write `rift.session/v2` while readers remain compatible with v1.
- `rift replay` filters captured events offline by anomaly, kind, source and time window.
- `rift compatibility` reports bundle/incident schemas, producer version and integrity.
- Consecutive probe-error cycles produce recorder-health evidence without automatically becoming robot incidents.
- `validate-live` can enforce an explicit p95 cycle-time budget.
- `rift watch` defaults to exit 0 after a successful recording lifecycle; use `--fail-on-incident` for CI gates.

## Validation

The release is gated by unit tests, the seven-scenario synthetic Community fault lab, the seven-family deterministic Pro benchmark, wheel installation smoke tests and bundle replay/compatibility checks. Real-robot accuracy remains a separate field-validation requirement.

# Changelog

## 0.8.0

- Added fingerprint-based incident deduplication with persistent occurrence ledgers.
- Added external incident review workflow (`open`, `acknowledged`, `resolved`, `ignored`) without mutating evidence bundles.
- Session reports now track deduplicated fault occurrences plus recorder overrun/probe-error cycle counts.
- `rift catalog` can surface review ownership/state; `rift duplicates` and `rift reviews` expose operational state.
- Config schema v7 adds `watch.dedup_window_seconds`.

## 0.7.0

- Added robot/site identity and labels to config, status, incident and session artifacts.
- Added config schema v6 migration and backwards-compatible session schema v2 reads.
- Added p95 recorder performance budgets to live validation and heartbeat status.
- Added recorder probe-health degradation/recovery tracking that remains separate from robot fault triggering.
- Added deterministic offline `replay` filtering and bundle `compatibility` reporting.
- Added identity-aware catalog/session output and fast identity/session indexing in bundle manifests.
- Changed `rift watch` to exit successfully after a valid recording session even when incidents were captured; `--fail-on-incident` restores CI-style non-zero behavior.


## 0.6.0

- Added operator markers, trigger quorum/filtering and host-clock jump detection.
- Added atomic recorder session summaries so healthy long runs remain measurable without incidents.
- Added `sessions`, `export`, `field-plan`, and `field-score` workflows.
- Added config schema v5 migration and threshold-based live validation acceptance.
- Added richer recorder performance telemetry including healthy/anomalous cycle counts.

## 0.5.0

- Added optional rosbag2 snapshot sidecar and verified raw evidence attachments.
- Added `preflight`, `validate-live`, and attachment extraction workflows.
- Added bundle schema v3 with dynamic attachment manifests.
- Added recorder session IDs and rosbag settings to heartbeat metadata.
- Sanitized bundles now intentionally omit raw binary attachments.
- Added deployment checks for snapshot support, storage, and cache-memory headroom.

## 0.4.0

- Added startup grace and optional healthy-cycle arming.
- Added single-recorder process locking and richer heartbeat state.
- Added privacy-by-default metadata and bundle sanitization.
- Added config validation/digests and host readiness diagnostics.
- Added bundle manifest v2, inspect command and hardened archive verification.
- Made header-delay probing opt-in in built-in profiles.

## 0.3.0

Concurrent probes, QoS/delay/jitter evidence, state transitions, status heartbeat, graceful shutdown, retention, atomic writes, expanded synthetic lab and self-test.

## 0.2.0

Continuous recorder, JSON configuration, debounce/cooldown, Nav2 lifecycle checks, incident fingerprints, verified packed bundles, richer Pro integration.

## 0.1.0

Initial incident recorder and portable bundle format.

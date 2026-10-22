# Architecture

RIFT is an offline-first ROS 2 incident recorder. The public package owns capture, evidence integrity and deterministic offline summaries; the private Pro package consumes the same bundle format for investigation support.

## 1. Collect

Collectors invoke read-only ROS 2 CLI operations and lightweight Linux host inspection concurrently. They normalize observations into `Event` objects instead of mutating the robot or declaring a root cause.

Current evidence includes graph/node/topic presence, publisher/subscriber counts, topic rate and jitter, optional message-header delay, offered/requested QoS, TF presence, lifecycle state, host resource snapshots and recorder timing/probe failures.

## 2. Buffer and arm

`RollingEventBuffer` keeps a bounded pre-trigger window. `watch` has startup grace, optional healthy-state arming, consecutive-failure debounce and incident cooldown. This is intended to separate robot bring-up noise from an actual runtime incident.

A recorder session receives one stable session ID, which is copied into its heartbeat and every incident it creates.

## 3. Trigger and preserve

Once armed, a configured failure starts an incident. RIFT continues collecting for the post-trigger window and then seals the structured evidence. If optional rosbag2 snapshot capture is enabled, a sidecar recorder keeps a byte-bounded rosbag2 snapshot cache and RIFT requests a snapshot when the incident is sealed.

The structured recorder remains independent: failure to start or snapshot rosbag2 is recorded as evidence rather than silently erasing the structured incident.

## 4. Seal and verify

The current bundle schema is `rift.bundle/v3`.

Core evidence:

- `incident.json`
- `events.jsonl`
- `summary.json`
- `bundle.json`

Optional manifest-declared attachments can include `rosbag2.zip`. Every declared file has size and SHA-256 metadata. Archives reject duplicate, undeclared, missing, unsafe-path, oversized or checksum-invalid members.

`rift sanitize` rebuilds a share-safe structured bundle and deliberately drops raw binary attachments because arbitrary ROS message payloads cannot be generically redacted safely.

## 5. Validate before deployment

`rift preflight` checks configuration/host readiness. `rift validate-live` repeatedly runs collectors without creating incidents and reports cycle timing, overruns, probe errors and failed cycles. These commands are the intended commissioning gate before `rift watch --forever`.

## 6. Analyze

Community analysis provides ordered anomaly timelines, deterministic summaries, failed sources and stable symptom fingerprints.

The private Pro package adds temporal hypothesis ranking, evidence quality, ambiguity assessment, comparisons, graphs, clustering, corpus/triage views, reports, regression artifacts and case-file export.

## Safety boundary

Community does not activate lifecycle nodes, set robot parameters, restart robot processes or publish motion commands. Collection and sidecar failures become evidence. RIFT is diagnostic tooling, not a safety controller.

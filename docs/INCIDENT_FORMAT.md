# Incident format

RIFT uses inspectable JSON/JSONL for its structured evidence and can optionally carry binary attachments.

## `incident.json`

Contains the incident ID, creation time, trigger reason, recorder/runtime metadata and complete event list. Current incident schema remains `rift.incident/v2`.

v0.6 metadata includes a stable recorder `session_id` and rosbag snapshot capture status when configured.

## `events.jsonl`

One event per line with timestamp, kind, source, message, severity, optional value/unit, tags and structured evidence.

## `summary.json`

Derived counts, capture duration, failed sources, first anomaly and deterministic fault fingerprint.

## `bundle.json`

Current manifest schema: `rift.bundle/v3`.

It records:

- RIFT version
- incident ID
- capture/completion timestamps
- event count
- deterministic fingerprint
- SHA-256 digest and byte size for each core file and attachment
- attachment roles/media types
- whether the structured bundle is sanitized

`bundle.json` is written last for the core evidence. Attachments are then registered atomically into the manifest.

RIFT continues to verify legacy v1/v2 manifests.

## Optional `rosbag2.zip`

When snapshot capture is enabled and succeeds, the finalized rosbag2 directory is stored as a top-level attachment named `rosbag2.zip` with role `rosbag2-snapshot`.

```bash
rift inspect incident.rift.zip
rift extract incident.rift.zip rosbag2.zip -o rosbag2.zip
```

## `.rift.zip`

`rift pack` creates a standard ZIP archive with the `.rift.zip` suffix. v0.6 packs the files declared by the manifest, including verified attachments.

Verification rejects:

- duplicate names
- unsafe member paths
- undeclared members
- missing declared members
- checksum/size mismatches
- excessive uncompressed payload sizes

## Sharing

```bash
rift sanitize incident.rift.zip -o share-safe.rift.zip
rift verify share-safe.rift.zip
```

Sanitization rebuilds the structured incident with common host/user/path/IP metadata redacted and **omits all binary attachments**. RIFT cannot safely redact arbitrary ROS message payloads.

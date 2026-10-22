# Privacy model

RIFT is designed for local/offline incident capture. It does not upload incident data by itself.

## Default metadata

Runtime metadata includes ROS distro, domain ID, RMW implementation and coarse host load. Hostname collection is disabled by default in v0.4.

## Sanitization

`rift sanitize` creates a new incident with common hostname, username, home-path and IPv4 information redacted. It also marks the output as sanitized and records provenance to the source incident ID.

Sanitization is deliberately conservative and cannot recognize every customer/project identifier. Treat it as a helper, not a substitute for data-classification policy or manual review.

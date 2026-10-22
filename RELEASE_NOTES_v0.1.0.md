# RIFT-ROS Community v0.1.0

Initial alpha release.

Highlights:
- rolling pre-trigger event buffer
- configurable post-trigger capture window
- automatic incident sealing on configured ROS health failures
- manual snapshot bundles for healthy baselines
- expected node/topic/TF checks
- minimum topic-rate checks
- offline JSON/JSONL incident analysis
- built-in synthetic Nav2 failure demo
- read-only behavior by design

Validation in the release workspace: 27 Community unit tests passing. Live ROS 2 integration still requires validation on ROS 2 Jazzy / Ubuntu 24.04 before production claims.

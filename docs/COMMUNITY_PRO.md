# Community and Pro boundary

Community is the recorder, evidence format and deterministic first-pass analysis. It must remain useful without Pro.

## Community

- concurrent read-only ROS/runtime collection
- rolling pre/post-trigger evidence capture
- startup grace, healthy-state arming, debounce and cooldown
- nodes/topics/TF/lifecycle checks
- publisher/subscriber, rate/jitter/QoS and optional header-delay evidence
- recorder heartbeat, session ID, process lock and retention
- optional rosbag2 snapshot attachment triggered by the same incident
- preflight and live collector validation
- verified `rift.bundle/v3` portable bundles
- attachment extraction
- privacy-by-default metadata and share-safe sanitization
- deterministic seven-scenario synthetic self-test

## Pro

Pro consumes Community bundles and adds:

- evidence-ranked temporal hypotheses
- evidence-quality/readiness scoring
- weak/ambiguous/evidence-limited assessment
- private/company deterministic rule packs
- score breakdown and recommended next checks
- evidence graph
- healthy-vs-incident comparison
- exact/similarity clustering
- session-aware corpus and triage views
- incident-to-regression generation/checking
- HTML engineering report
- self-contained engineering case-file export

Pro scores are investigation support heuristics, not calibrated probabilities or proof of root cause. Raw rosbag attachments remain outside the Pro case file by default.

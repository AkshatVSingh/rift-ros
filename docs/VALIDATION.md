# Validation status

RIFT v0.8.0 has automated unit coverage for event models, rolling buffers, CLI/config parsing, profiles, collectors, trigger behavior, retention, locking, privacy, verified bundle packing, binary attachments, rosbag2-sidecar orchestration, live-validation aggregation, synthetic incidents and offline analysis.

The deterministic synthetic fault lab covers seven families:

- odometry degradation followed by localization / Nav2 failure
- lidar stream dropout followed by localization / control failure
- managed Nav2 lifecycle state loss
- localization TF loss
- QoS incompatibility
- timestamp delay/jitter degradation
- host resource pressure followed by timing / navigation degradation

These scenarios validate software behavior, not real-robot detection accuracy.

## v0.6 commissioning gate

Before leaving RIFT running on a robot:

```bash
rift self-test
rift validate-config rift.json
rift preflight --config rift.json
rift validate-live --config rift.json --cycles 20 -o rift-live-validation.json
```

The live validation report should be reviewed for probe errors, failed cycles, collector overruns and timing headroom.

If rosbag2 snapshot capture is enabled, preflight also checks the required snapshot-mode CLI/service support. The actual snapshot must still be tested on the target ROS/RMW/storage combination.

## Claims we can make

- The software can record configured read-only observations into a bounded incident window.
- It preserves pre- and post-trigger structured evidence.
- It can optionally attach a verified rosbag2 snapshot when configured and supported.
- It can integrity-check, pack, inspect, extract and sanitize its own bundle format.
- Community offline analysis and synthetic self-tests are deterministic.
- Pro ranks explicit evidence-backed hypotheses using deterministic rules and event ordering.

## Claims we should not make yet

- percentage of real robot failures detected
- percentage of correct root-cause diagnoses
- production-grade uptime or recorder overhead targets
- universal Nav2/custom robot compatibility
- successful rosbag snapshot behavior across every RMW/storage plugin
- safety certification

Those require measured field results across independent live ROS 2 systems.


### v0.7 recorder budget

`validation.max_p95_cycle_seconds` can reject a live validation run even when the raw overrun rate remains below its limit. This catches a recorder whose p95 latency is already too close to the robot-side budget before it crosses the configured interval.

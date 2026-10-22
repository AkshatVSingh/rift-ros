# Field validation gate

Synthetic tests prove deterministic software behavior. They do not prove that thresholds, sampling windows, CPU overhead, DDS behavior, or failure detection are correct on a real robot.

## 1. Preflight

```bash
rift preflight --config rift.json
```

Required checks should pass. If rosbag snapshots are enabled, preflight also checks that the installed rosbag2 exposes snapshot mode and warns about cache-memory headroom.

## 2. Healthy live run

```bash
rift validate-live --config rift.json --cycles 20 -o healthy-validation.json
```

Desired result:

- 0 failed cycles
- 0 probe errors
- 0 interval overruns
- p95 collector duration comfortably below `interval_seconds`

If a healthy robot fails this gate, calibrate thresholds before testing faults.

## 3. Controlled faults

Recommended validation matrix:

1. `/odom` publisher stopped
2. `/odom` slowed below threshold
3. `/scan` publisher stopped
4. `/scan` jitter increased
5. `map -> odom` unavailable
6. `odom -> base_link` unavailable
7. controller server deactivated
8. planner server deactivated
9. QoS incompatibility on a test topic
10. delayed/stale header timestamps on a test topic
11. host CPU pressure
12. low storage condition
13. recorder SIGTERM during post-trigger window
14. two recorder instances competing for the lock
15. namespaced Nav2 deployment
16. rosbag snapshot enabled under normal load
17. rosbag snapshot during a high-bandwidth incident
18. repeated incidents across one recorder session
19. long healthy run for false-positive measurement
20. restart/reboot recovery

## 4. Measure

Record at minimum:

- detection success/failure
- trigger latency
- false-positive count
- collector mean/p95/max duration
- CPU/RAM overhead
- rosbag sidecar RAM overhead when enabled
- incident bundle size
- whether the top Pro investigation priority was useful

Do not publish field-accuracy claims until this matrix has been run across multiple independent ROS 2 installations.

## v0.6 session evidence

The recorder now writes `rift-incidents/_sessions/<session-id>.json` at shutdown. This is intentionally useful for a healthy long-run test where no incident should exist. The report contains recorder performance counters, incident count, scenario marker counts and the session/config identifiers, without adding host identity by default.

Use:

```bash
rift sessions rift-incidents
rift field-plan -o rift-field-plan.json
rift field-score rift-field-plan.json rift-incidents/<incident> rift-incidents/_sessions/<session>.json
```

For `healthy-long-run`, a marked session is counted successful only when it captured zero incidents and recorded zero triggerable anomalous cycles.

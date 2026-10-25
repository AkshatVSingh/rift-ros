# RIFT-ROS

**Offline-first ROS 2 runtime incident forensics, black-box recording, failure analysis, and debugging for autonomous robots.**

RIFT runs beside a ROS 2 robot, keeps a rolling window of deterministic runtime evidence, and preserves what happened before and after a persistent failure as a portable incident bundle.

It is deliberately read-only with respect to the robot: RIFT does not activate lifecycle nodes, rewrite parameters, restart drivers, or command motion.

> Current target: ROS 2 Jazzy / Ubuntu 24.04. Offline bundle analysis is ROS-independent.

## v0.8 incident operations

RIFT now separates immutable evidence from operational workflow. Repeating the same fingerprint inside the configured deduplication window records an occurrence without writing another full bundle, and incident review state lives in a separate review store.

```bash
rift review rift-incidents/INCIDENT --status acknowledged --owner akshat --note "checking odometry"
rift catalog rift-incidents --review-file rift-reviews.json
rift duplicates rift-incidents
```

Set `watch.dedup_window_seconds` to `0` to disable deduplication.


## Why RIFT exists

Intermittent failures are difficult because the evidence engineers need is often gone by the time debugging begins. RIFT is built around one question:

> **What changed in the seconds before this robot failed?**

Community captures and preserves evidence. RIFT Pro is developed separately and adds evidence-ranked investigation, evidence-quality scoring, custom rule packs, evidence graphs, recurring-incident analysis, regression checks, engineering reports, and case-file export.

## Install

```bash
git clone https://github.com/AkshatVSingh/rift-ros.git
cd rift-ros
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Verify the offline core without ROS:

```bash
rift self-test
```

## Commission a robot before continuous recording

Generate a Nav2-oriented configuration:

```bash
rift init-config --profile nav2 -o rift.json
rift validate-config rift.json
```

Run host/dependency checks:

```bash
source /opt/ros/jazzy/setup.bash
source /path/to/robot/install/setup.bash   # if needed
rift preflight --config rift.json
```

Measure the live collector without creating incidents:

```bash
rift validate-live --config rift.json --cycles 10 -o rift-live-validation.json
```

This reports failed/warning cycles, probe errors, collector mean/p95/max duration, interval overruns, failed event kinds/sources, and the ROS runtime identity.

Only after those checks look reasonable should you leave the recorder running continuously:

```bash
rift watch --config rift.json --forever
```

From another terminal:

```bash
rift status
```


## New in v0.7: multi-robot attribution and recorder budgets

Scope a deployment when you create its config:

```bash
rift init-config --profile nav2 \
  --robot-id amr-17 \
  --site-id pune-lab \
  --label model=dynamo1500 \
  -o rift.json
```

Identity is carried into status, session reports and incident metadata so an exported bundle can be attributed without relying on its filename.

You can enforce a collector performance budget in `rift.json`:

```json
{
  "validation": {
    "max_probe_error_rate": 0.0,
    "max_overrun_rate": 0.05,
    "max_failed_cycle_rate": 0.0,
    "max_p95_cycle_seconds": 1.5
  }
}
```

Then `rift validate-live` rejects a deployment if its measured p95 collector time exceeds that budget. Long-running status also exposes the observed budget result and recorder probe-health state. Probe failures are recorder evidence and are excluded from robot-trigger logic by default.

Offline bundles can now be checked and replayed without ROS:

```bash
rift compatibility incident.rift.zip
rift replay incident.rift.zip --anomalies-only
rift replay incident.rift.zip --kind topic_rate --source /odom --from-seconds 5 --to-seconds 15
```

`rift watch` now exits 0 when the recorder itself completed successfully, even if it captured incidents. For CI/test gates use:

```bash
rift watch --config rift.json --duration 60 --fail-on-incident
```

## New in v0.6: field-validation workflow

Operator annotations can be written into the same recorder timeline without changing the robot:

```bash
rift mark "disabled AMCL for controlled test" --scenario tf-loss --severity warn
```

Create the safe validation plan:

```bash
rift field-plan -o rift-field-plan.json
```

RIFT now writes a compact session summary at shutdown even when **no incident fired**. This makes healthy long-run validation measurable instead of disappearing simply because nothing failed:

```bash
rift sessions rift-incidents
```

After controlled validation runs, score the marked incident bundles plus healthy session reports:

```bash
rift field-score rift-field-plan.json \
  rift-incidents/20261012-incident \
  rift-incidents/_sessions/session-*.json
```

RIFT never injects faults automatically. Validation faults must be performed by the operator in simulation or a controlled stationary test environment.

You can also export a portable timeline for external analysis:

```bash
rift export incident.rift.zip -o timeline.csv
rift export incident.rift.zip --format json -o timeline.json
```

## Incident workflow

After a captured failure:

```bash
rift analyze rift-incidents/<incident>
rift show rift-incidents/<incident> --anomalies-only
rift verify rift-incidents/<incident>
rift inspect rift-incidents/<incident>
rift pack rift-incidents/<incident>
```

The resulting `.rift.zip` can be verified and analyzed on another machine without ROS installed.

## Optional raw rosbag2 snapshot evidence

RIFT's structured evidence is intentionally lightweight. For difficult intermittent failures you may also want the actual ROS messages around the incident.

RIFT can run an **optional rosbag2 snapshot sidecar**. It keeps a bounded in-memory rosbag cache while RIFT watches the robot. After RIFT's normal post-trigger window, it asks rosbag2 to flush the cache and attaches the finalized bag as `rosbag2.zip` to the incident.

Enable it in `rift.json`:

```json
{
  "rosbag_snapshot": {
    "enabled": true,
    "topics": ["/tf", "/tf_static", "/rosout", "/odom", "/scan"],
    "max_cache_mb": 256,
    "storage_id": "mcap",
    "node_name": "rift_rosbag2_recorder",
    "use_sim_time": false
  }
}
```

Then re-run:

```bash
rift validate-config rift.json
rift preflight --config rift.json
```

ROS 2 Jazzy snapshot mode is memory-size bounded with `--max-cache-size`; it is **not an exact time-window guarantee**. Measure the robot's aggregate topic bandwidth before choosing a cache size. Jazzy rosbag2 also uses double buffering, so peak cache memory can approach roughly twice the configured cache budget.

Inspect an incident with raw evidence:

```bash
rift inspect incident.rift.zip
```

Extract only the attached rosbag:

```bash
rift extract incident.rift.zip rosbag2.zip -o rosbag2.zip
unzip rosbag2.zip -d rosbag2
ros2 bag info rosbag2
```

### Privacy rule for raw bags

Raw ROS messages can contain proprietary maps, images, point clouds, identifiers, and customer data. `rift sanitize` therefore **does not copy raw binary attachments** into the share-safe bundle:

```bash
rift sanitize incident.rift.zip -o share-safe.rift.zip
rift verify share-safe.rift.zip
```

Always review data before external sharing.

## What Community records

Depending on profile/configuration, RIFT can preserve:

- expected node/topic presence
- publisher/subscriber counts
- requested/offered QoS evidence and deterministic reliability/durability incompatibilities
- topic frequency and period jitter
- optional header timestamp delay
- TF availability
- Nav2 lifecycle state
- host load, memory and disk headroom
- recorder cycle timing and overruns
- degradation/recovery transitions
- trigger evidence plus pre/post-trigger history
- recorder session ID across multiple incidents
- optional verified rosbag2 snapshot attachment

Runtime probes execute concurrently.

## False-trigger controls

Robot stacks often look unhealthy while starting. RIFT supports:

```json
{
  "watch": {
    "startup_grace_seconds": 15,
    "arm_after_healthy_cycles": 0,
    "consecutive_failures": 2,
    "cooldown_seconds": 30
  }
}
```

- `startup_grace_seconds` observes startup without triggering.
- `arm_after_healthy_cycles` can require a known-healthy period before arming.
- `consecutive_failures` debounces transient faults.
- `cooldown_seconds` prevents incident storms.

## Bundle integrity

A v0.7 incident directory can contain:

```text
incident-id/
├── bundle.json
├── incident.json
├── events.jsonl
├── summary.json
└── rosbag2.zip          # optional
```

`rift.bundle/v3` stores SHA-256 and byte size for every core file and attachment. Packing/verification reject duplicate members, unsafe paths, unexpected files, integrity mismatches, and excessive archive expansion.

## Long-running operation

RIFT v0.7 includes:

- continuous `--forever` mode
- single-recorder process lock
- stable session ID
- graceful SIGTERM handling
- heartbeat/status JSON
- configurable incident retention by count/storage budget
- low-storage warnings
- atomic core evidence writes
- optional rosbag snapshot sidecar rotation

See [`docs/OPERATIONS.md`](docs/OPERATIONS.md) and [`docs/SERVICE.md`](docs/SERVICE.md).

## Built-in profiles

```bash
rift profiles
rift profiles nav2
rift profiles sensors
```

Profiles are starting points, not universal thresholds. Calibrate them with healthy captures from the actual robot.

## Synthetic fault lab

```bash
rift demo --scenario nav2-odom
rift demo --scenario lidar-dropout
rift demo --scenario lifecycle-drop
rift demo --scenario tf-loss
rift demo --scenario qos-mismatch
rift demo --scenario timestamp-delay
rift demo --scenario resource-pressure
rift self-test
```

These are deterministic software regression cases, **not field-accuracy claims**.

## Community vs Pro

| Capability | Community | Pro |
| --- | :---: | :---: |
| Rolling pre/post-trigger recorder | ✓ | ✓ |
| Node/topic/rate/TF/lifecycle evidence | ✓ | ✓ |
| QoS/jitter/optional delay evidence | ✓ | ✓ |
| Verified portable bundles | ✓ | ✓ |
| Optional rosbag2 snapshot attachment | ✓ | ✓ |
| Preflight + live validation gate | ✓ | ✓ |
| Operator-marked field validation + healthy session summaries | ✓ | ✓ |
| Share-safe structured sanitization | ✓ | ✓ |
| Evidence-ranked temporal hypotheses | — | ✓ |
| Evidence-quality scoring | — | ✓ |
| Ambiguity / weak-evidence warning | — | ✓ |
| Custom company rule packs | — | ✓ |
| Evidence graph | — | ✓ |
| Healthy-vs-incident comparison | — | ✓ |
| Similarity clustering / triage / corpus | — | ✓ |
| Session-aware corpus summaries | — | ✓ |
| Incident → regression spec + check | — | ✓ |
| HTML engineering report | — | ✓ |
| Engineering case-file export | — | ✓ |

See [`docs/COMMUNITY_PRO.md`](docs/COMMUNITY_PRO.md).

## Development

```bash
python -m pip install -e '.[dev]'
pytest
ruff check src
rift self-test
```

## Scope

RIFT v0.6 is still alpha software. The offline core, bundle logic, deterministic fault lab, and package tests are automated. Live ROS collector behavior and rosbag snapshot overhead must still be validated on actual robots, RMW implementations, sensors, and Nav2 configurations before production claims are made.

RIFT Pro scores are heuristic **evidence support**, not calibrated probabilities and not proof of physical root cause.

## Security

Never attach credentials, production maps, private bag files, proprietary robot configurations, or customer data to public issues. `rift sanitize` helps with structured RIFT metadata but deliberately removes raw attachments rather than pretending to redact arbitrary ROS messages safely.

See [`SECURITY.md`](SECURITY.md).

## License

Community edition: Apache License 2.0.

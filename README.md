# ROS Doctor

A small read-only diagnostic tool for ROS 2 systems.

I built ROS Doctor around a simple problem: when a robot stops behaving properly, the first few minutes are usually spent checking the same things again — whether the expected nodes are alive, whether sensor topics are publishing, whether TF is connected, and whether a topic is running at a sensible rate.

ROS Doctor collects those checks into one CLI so the first pass is repeatable.

> Current target: ROS 2 Jazzy on Ubuntu 24.04.

## Status

This is an early Community release. The current build focuses on safe, read-only diagnostics and deliberately avoids changing parameters, lifecycle states, or robot motion.

## Install

From source:

```bash
git clone https://github.com/AkshatVSingh/ros-doctor.git
cd ros-doctor
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Then check that the CLI is available:

```bash
ros-doctor --help
```

## First scan

Source your ROS environment first, then run:

```bash
source /opt/ros/jazzy/setup.bash
ros-doctor scan
```

A scan checks the ROS environment and graph and prints a compact result:

```text
ROS Doctor
────────────────────────────────────────
PASS  environment   ROS_DISTRO=jazzy
PASS  graph         discovered 24 nodes
PASS  graph         discovered 61 topics
WARN  topic         expected topic missing: /imu/data
FAIL  tf            transform unavailable: map -> odom

Summary: 3 pass, 1 warning, 1 failure
```

The exact output depends on the robot and the checks you ask ROS Doctor to run.

## Useful commands

List nodes:

```bash
ros-doctor nodes
```

List topics and types:

```bash
ros-doctor topics
```

Check a TF pair:

```bash
ros-doctor tf map odom
```

Run a scan with explicit expectations:

```bash
ros-doctor scan \
  --expect-node /controller_server \
  --expect-node /amcl \
  --expect-topic /scan \
  --expect-topic /odom \
  --expect-tf map:odom \
  --expect-tf odom:base_link
```

Sample a topic rate:

```bash
ros-doctor hz /scan --seconds 4
```

Machine-readable output:

```bash
ros-doctor scan --json
```

More command-line examples are in [`examples/README.md`](examples/README.md).

## What Community checks today

- ROS environment and CLI availability
- node discovery
- topic discovery and topic types
- expected node presence
- expected topic presence
- basic topic-rate sampling
- basic TF availability checks
- terminal and JSON output
- non-zero exit status when requested checks fail

## Why keep it read-only?

A diagnostic tool should be safe to run on a robot you are already trying to understand. ROS Doctor does not silently activate lifecycle nodes, rewrite parameters, restart drivers, or send motion commands. It reports what it can observe and leaves changes to the engineer.

## Community vs Pro

The public Community edition stays focused on first-pass health checks. Deeper correlation and incident tooling are being developed separately.

| Capability | Community | Pro |
| --- | :---: | :---: |
| Environment, node and topic checks | ✓ | ✓ |
| Basic TF checks | ✓ | ✓ |
| Topic-rate sampling | ✓ | ✓ |
| Text / JSON results | ✓ | ✓ |
| QoS reasoning | — | ✓ |
| Odometry and localization analysis | — | ✓ |
| Nav2 dependency diagnosis | — | ✓ |
| rosbag / incident analysis | — | ✓ |
| Historical correlation | — | ✓ |
| HTML engineering reports | — | ✓ |
| CI / readiness workflows | — | ✓ |

See [`docs/PRO.md`](docs/PRO.md) for the planned split.

## Exit codes

`ros-doctor scan` is intended to work in scripts as well as terminals.

- `0`: requested checks passed (warnings may still be present)
- `1`: at least one requested diagnostic check failed
- `2`: ROS 2 is unavailable or the command could not run

## Development

```bash
python -m pip install -e '.[dev]'
pytest
```

The unit tests do not require a running ROS graph. Real ROS integration tests are kept separate so they can be run in a sourced ROS environment.

## Contributing

Small, reproducible diagnostics are welcome. If you are proposing a new check, include the failure mode, observable evidence, and a minimal way to reproduce it.

Please do not attach company/customer source code, credentials, private maps, production bag files, or other confidential robot data to public issues.

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

Apache License 2.0. See [`LICENSE`](LICENSE).

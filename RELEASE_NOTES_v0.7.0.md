# ROS Doctor Community v0.7.0

First public Community release.

## Included

- ROS 2 environment checks
- node discovery
- topic discovery with message types
- expected node/topic checks
- basic TF availability checks
- topic-rate sampling
- terminal and JSON output
- script-friendly exit codes
- unit-test suite
- GitHub Actions test workflow

## Current validation target

ROS 2 Jazzy on Ubuntu 24.04.

This release is intentionally read-only. ROS Doctor does not activate lifecycle nodes, rewrite parameters, restart drivers, or command robot motion.

## Known limits

Community v0.7.0 is a first-pass diagnostic tool. It does not yet provide historical TF correlation, QoS reasoning, odometry/localization analysis, Nav2 dependency diagnosis, incident forensics, or rosbag analysis.

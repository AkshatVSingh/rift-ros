# Examples

`rift-nav2.json` is the current `rift.config/v7` Nav2 template. It is deliberately conservative: edit the expected nodes/topics/transforms for the actual robot before deployment.

Commission it with:

```bash
rift validate-config examples/rift-nav2.json
rift preflight --config examples/rift-nav2.json
rift validate-live --config examples/rift-nav2.json --cycles 20
```

The optional `rosbag_snapshot` section is disabled by default. Enable it only after choosing an explicit topic allow-list and validating storage/memory impact on the target computer.

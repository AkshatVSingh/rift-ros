# Long-running recorder deployment

RIFT can run continuously with `rift watch --forever` or `duration_seconds: null`.

Before enabling a service, commission the target environment manually:

```bash
source /opt/ros/jazzy/setup.bash
source /opt/robot/install/setup.bash
rift validate-config /etc/rift/rift.json
rift preflight --config /etc/rift/rift.json
rift validate-live --config /etc/rift/rift.json --cycles 10 -o /var/lib/rift/commissioning.json
```

## Example systemd unit

```ini
[Unit]
Description=RIFT-ROS runtime incident recorder
After=network.target

[Service]
Type=simple
User=robot
WorkingDirectory=/var/lib/rift
ExecStartPre=/bin/bash -lc 'source /opt/ros/jazzy/setup.bash && source /opt/robot/install/setup.bash && /opt/rift/bin/rift preflight --config /etc/rift/rift.json'
ExecStart=/bin/bash -lc 'source /opt/ros/jazzy/setup.bash && source /opt/robot/install/setup.bash && exec /opt/rift/bin/rift watch --config /etc/rift/rift.json --forever --status-file /var/lib/rift/status.json --out /var/lib/rift/incidents'
Restart=on-failure
RestartSec=3
KillSignal=SIGTERM
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
```

Adjust executable paths, robot workspace, user, and storage locations for the deployment.

## Rosbag snapshot note

When `rosbag_snapshot.enabled=true`, the service also launches a rosbag2 child recorder. Size `max_cache_mb` only after measuring memory pressure on the target computer. Raw bag attachments can dominate disk usage, so configure retention accordingly.

## Safety

RIFT remains read-only with respect to robot control state. It still consumes CPU, memory, storage, DDS discovery traffic, and optional rosbag cache memory. Validate these costs on the target platform before production use.

# Troubleshooting

## `ROS 2 environment not available`

Source the ROS distribution before running ROS Doctor:

```bash
source /opt/ros/jazzy/setup.bash
```

If you use a workspace, source that after the base ROS setup.

## No nodes or topics are found

Check `ROS_DOMAIN_ID`, DDS/RMW configuration, container networking, and whether the target nodes are running.

## TF check fails

Confirm `tf2_ros` is installed and compare the same frames directly:

```bash
ros2 run tf2_ros tf2_echo map odom
```

## Topic-rate sample fails

`ros-doctor hz` only reports a rate after messages are observed during the sampling window. Increase `--seconds` for low-frequency topics.

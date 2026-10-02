# Examples

ROS Doctor does not need a robot-specific package. Add expectations on the command line for the system you are checking.

For a typical Nav2 setup:

```bash
ros-doctor scan \
  --expect-node /amcl \
  --expect-node /controller_server \
  --expect-node /planner_server \
  --expect-topic /scan \
  --expect-topic /odom \
  --expect-tf map:odom \
  --expect-tf odom:base_link
```

To inspect a specific stream before looking deeper into the stack:

```bash
ros-doctor hz /scan --seconds 5
ros-doctor tf map odom --seconds 3
```

These examples are deliberately generic. Keep robot/customer-specific checks in your own scripts or configuration rather than committing private system details to a public repository.

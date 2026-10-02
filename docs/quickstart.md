# Quick start

ROS Doctor Community currently targets ROS 2 Jazzy on Ubuntu 24.04.

```bash
git clone https://github.com/AkshatVSingh/ros-doctor.git
cd ros-doctor
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
source /opt/ros/jazzy/setup.bash
ros-doctor scan
```

A plain scan reports environment and graph health. Add expectations to make it useful for a specific robot:

```bash
ros-doctor scan \
  --expect-node /controller_server \
  --expect-topic /scan \
  --expect-topic /odom \
  --expect-tf map:odom
```

Use `--json` when another script needs to consume the results.

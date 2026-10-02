# Contributing

Contributions are welcome, especially small diagnostics with a clear failure mode and a repeatable test.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check src tests
```

## A good diagnostic check should

- observe rather than mutate the robot,
- state the evidence it used,
- have a clear pass/fail condition,
- avoid claiming a root cause when the evidence only supports a symptom,
- include a unit test or reproducible integration case.

## Before opening an issue

Include your ROS 2 distribution, Ubuntu version, ROS Doctor version, command, expected behavior, actual behavior, and sanitized output.

Do not publish employer/customer source code, credentials, private maps, production bag files, or other confidential data.

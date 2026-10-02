# Architecture

ROS Doctor Community has four small layers:

1. **Collectors** read information from the ROS 2 CLI and environment.
2. **Checks** turn observations into deterministic pass/fail results.
3. **Models** provide a stable diagnostic result structure.
4. **Reporting** renders the same results for a terminal or JSON consumer.

The current release intentionally keeps the implementation simple. Community checks should be understandable from their evidence and should not mutate the running robot.

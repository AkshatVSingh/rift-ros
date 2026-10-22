# Real robot validation gate

Synthetic tests protect behavior and packaging but do not establish field performance.

Before calling RIFT production-ready, validate on multiple independent ROS 2 Jazzy systems and record false positives, missed incidents, capture overhead and investigation usefulness.

Minimum controlled scenarios:

1. healthy run (30+ minutes)
2. `/odom` publisher loss
3. odometry frequency degradation
4. odometry jitter
5. lidar publisher loss
6. lidar frequency degradation
7. sensor timestamp delay
8. deliberate QoS incompatibility
9. `map -> odom` loss
10. `odom -> base_link` loss
11. Nav2 lifecycle server inactive
12. Nav2 server crash/restart
13. CPU saturation / scheduling pressure
14. low available memory
15. namespaced robot
16. alternate RMW implementation
17. recorder SIGTERM during armed post-window
18. storage retention under repeated incidents
19. healthy-vs-failed baseline comparison
20. repeated recreation of the same fault fingerprint

For each scenario record expected signal, whether RIFT triggered, time-to-trigger, false-positive status, CPU/RAM overhead, bundle size, and whether Pro ranked the intended subsystem first.

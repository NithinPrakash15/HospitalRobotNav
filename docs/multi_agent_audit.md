# Multi-Agent Architecture Audit

## Confirmed working subsystems

- Pygame simulator with hospital map, dynamic obstacles, robot physics, path planners, HUD, and dashboard panels.
- Semantic map with 65 rooms, including Pharmacy and Room 205.
- Offline speech pipeline components: audio capture, Vosk recognizer fallback, wake-word detector, intent parser, entity extraction, dialogue manager, and TTS.
- Mission planner/executor, medicine inventory, robot state/battery model, A*, D* Lite, Theta*, Hybrid A*, and collision checking.
- ROS2 Jazzy workspace with message, core, node, and bringup packages. The launch stack includes speech, semantic map, planner, obstacle tracking, robot control, mission execution, fleet coordination, and optional simulator bridge.
- Thirteen specialized logical agents, registry heartbeats, contract-net bidding, structured agent message envelope, and coordinator assignment events.

## Architecture findings and changes

The repository already contained the required specialized agent classes and ROS2-compatible interfaces. The runtime gap was that a speech/demo mission could enter the visible mission executor without a single authoritative fleet allocation and completion lifecycle.

The simulator now routes every submitted mission through the coordinator before planning. The selected agent remains `EXECUTING` while the mission executor drives the visible robot and is marked complete only when that plan completes. The professor demo uses the semantic Room 205 destination and avoids repeated no-bid broadcasts while the delivery agent is busy.

`HospitalWorldState` provides a controlled, serialisable snapshot of robot state, agent states, active mission/task queue, obstacles, semantic locations, medicine stock, navigation status, and a bounded structured communication history. The simulator is the sole writer; agents and UI consume snapshots.

## Retained items

No source files were deleted. Root diagnostic output files, Python bytecode caches, and ROS2 `build`/`install` artifacts were retained because the audit cannot prove they are not part of the user's local workflow. They are candidates for a separate, explicitly approved cleanup after the workspace is moved off OneDrive or rebuilt cleanly.

## Known limits

- This checkout contains no URDF, Xacro, SDF, or Gazebo world files, so Gazebo integration cannot be truthfully completed without new robot/world specifications.
- ROS2 mission execution currently contains bounded simulated step delays; replacing that with Nav2 action feedback is the next hardware/Gazebo integration task.
- WSL builds warn about clock skew because the workspace is on a Windows-mounted OneDrive path; the build succeeds after sourcing `/opt/ros/jazzy/setup.bash`.

## Verification

- `python -m pytest tests/ -q --tb=short`: 76 passed.
- `source /opt/ros/jazzy/setup.bash && colcon build --packages-select hospital_robot_nav_msgs hospital_robot_nav_core hospital_robot_nav_nodes hospital_robot_nav_bringup`: succeeded.

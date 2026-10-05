# HospitalRobotNav — ROS 2 Workspace

A complete ROS 2 (Jazzy/Humble-compatible) colcon workspace generated from the
HospitalRobotNav simulator. It preserves the full autonomous hospital assistant
platform — including the offline Speech → STT → NLU → Dialogue → TTS pipeline —
as first-class ROS 2 nodes.

## Layout

```
hospital_robot_nav_ws/
├── src/
│   ├── hospital_robot_nav_msgs/     # Custom msg / srv / action interfaces
│   ├── hospital_robot_nav_core/     # Pure-Python logic library (no ROS2)
│   ├── hospital_robot_nav_nodes/    # ROS 2 node implementations
│   └── hospital_robot_nav_bringup/  # Launch files + YAML params
```

## Build (on a ROS 2 system — WSL2 Ubuntu / Linux robot PC)

```bash
cd hospital_robot_nav_ws
colcon build --symlink-install
source install/setup.bash
```

## Run the full hospital system (speech + navigation + mission)

Because `ros2` only exists inside WSL (Ubuntu-24.04), use the wrapper scripts:

```powershell
# From PowerShell (recommended)
.\launch_hospital_robot.ps1              # full system
.\launch_hospital_robot.ps1 speech       # speech pipeline only
```

```bash
# From WSL directly
bash launch_hospital_robot.sh            # full system
bash launch_hospital_robot.sh speech     # speech pipeline only
```

Or manually inside WSL:

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch hospital_robot_nav_bringup hospital_robot.launch.py
```

## Run only the speech/TTS analysis pipeline

```bash
ros2 launch hospital_robot_nav_bringup speech_pipeline.launch.py
ros2 topic echo /robot/speech_analysis
```

## Smoke tests & diagnostics

```bash
bash smoke_test_speech.sh         # end-to-end speech pipeline (text mode)
bash verify_workspace.sh          # packages + nodes + interfaces + launch files
bash check_smoke_result.sh        # inspect latest smoke-test output
bash diag_nodes.sh                # node-level diagnostics
bash diag_launch.sh               # launch diagnostics
```

## Run the legacy Pygame simulator (no ROS 2 needed)

```bash
cd ..   # back to project root
python main.py
```

## Topics Overview

| Topic | Type | Producer |
| --- | --- | --- |
| `/audio/raw` | `AudioChunk` | audio_capture_node |
| `/speech/transcript` | `RecognitionResult` | asr_node |
| `/speech/transcript_partial` | `RecognitionResult` | asr_node |
| `/wake_word/active` | `std_msgs/Bool` | wake_word_node |
| `/mission/request` | `MissionRequest` | nlu_node |
| `/robot/say` | `std_msgs/String` | dialogue_node |
| `/robot/speech_analysis` | `SpeechAnalysis` | speech_analysis_node |
| `/robot/cmd_vel` | `geometry_msgs/Twist` | robot_controller_node |
| `/odom` | `nav_msgs/Odometry` | robot_controller_node |
| `/robot/state` | `std_msgs/String` | robot_controller_node |
| `/obstacles` | `Detection[]` | obstacle_tracker_node |
| `/mission/status` | `MissionPlan` | mission_executor_node |
| `/fleet/status` | `AgentStatus[]` | fleet_coordinator_node |

## Services

| Service | Type | Server |
| --- | --- | --- |
| `/semantic_map/resolve_destination` | `ResolveDestination` | semantic_map_node |
| `/planner/plan_path` | `PlanPath` | planner_node |
| `/emr/verify_prescription` | `VerifyPrescription` | emr_bridge_node |

## Actions

| Action | Type | Server |
| --- | --- | --- |
| `/mission/execute` | `ExecuteMission` | mission_executor_node |


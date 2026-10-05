# HospitalRobotNav

Research-grade simulator for:

**Multi-Agent Embodied AI Robot for Autonomous Hospital Assistance using Vision-Language Reasoning**

HospitalRobotNav is a modular hospital service robot platform for autonomous navigation, speech-driven mission planning, medicine delivery simulation, patient assistance workflows, multi-agent task allocation, dashboard visualization, and future ROS2/Nav2 deployment.

## What It Does

- Builds a semantic hospital map with reception, pharmacy, emergency, ICU, operation theatre, patient rooms, laboratory, radiology, nurse station, storage, and charging dock.
- Plans paths with A*, Dijkstra, Theta*, Hybrid A*, and D* Lite style dynamic replanning support.
- Understands offline spoken/text commands through wake word, speech recognition adapters, rule-based NLU, entity extraction, and dialogue management.
- Converts one request into ordered mission steps such as navigate, collect medicine, deliver item, call nurse, guide patient, or return to dock.
- Simulates medicine pickup and delivery with mission lifecycle events.
- Displays a live Pygame dashboard with robot state, battery, mission progress, analytics, transcript, and event log.
- Supports multi-agent fleet allocation through delivery, reception, and emergency agent roles.
- Provides AI integration boundaries for LLMs, VLMs, object detection, QR verification, patient identification, and EMR connectivity.
- Keeps a ROS2-ready architecture through clean module boundaries and an event bus that maps naturally to topics, services, and actions.

## Quick Start (Legacy Pygame Simulator)

```bash
pip install -r requirements.txt
python main.py
```

Run tests:

```bash
python -m pytest tests/ --tb=short -q
```

## ROS 2 Workspace

The repository includes a complete, build-ready **ROS 2 (Jazzy/Humble)** colcon
workspace at [`hospital_robot_nav_ws/`](hospital_robot_nav_ws/README.md). It
migrates the entire platform — including the full offline
**Speech → STT → NLU → Dialogue → TTS** pipeline — into first-class ROS 2
nodes, while keeping the legacy Pygame simulator runnable.

Workspace layout:

```
hospital_robot_nav_ws/
├── src/
│   ├── hospital_robot_nav_msgs/     # Custom msg / srv / action interfaces
│   ├── hospital_robot_nav_core/     # Pure-Python logic library (no ROS2)
│   ├── hospital_robot_nav_nodes/    # 14 ROS 2 node implementations
│   └── hospital_robot_nav_bringup/  # Launch files + YAML params
```

Build & run (on a ROS 2 system — e.g., WSL2 Ubuntu or a Linux robot PC):

```bash
cd hospital_robot_nav_ws
colcon build --symlink-install
source install/setup.bash

# Launch the full hospital system (speech + navigation + mission)
ros2 launch hospital_robot_nav_bringup hospital_robot.launch.py

# Or launch only the speech/TTS analysis pipeline
ros2 launch hospital_robot_nav_bringup speech_pipeline.launch.py
ros2 topic echo /robot/speech_analysis
```

Key topics include `/audio/raw`, `/speech/transcript`,
`/speech/transcript_partial`, `/wake_word/active`, `/mission/request`,
`/mission/status`, `/robot/say`, `/robot/speech_analysis`, `/odom`,
`/obstacles`, and `/fleet/status`.

Services: `/semantic_map/resolve_destination`, `/planner/plan_path`,
`/emr/verify_prescription`.

Action: `/mission/execute` (`ExecuteMission`).

## Demo Controls

| Control | Action |
| --- | --- |
| Left click | Navigate to a room or grid cell |
| Mouse wheel | Zoom |
| Middle mouse drag | Pan |
| Space | Pause or resume |
| R | Reset simulation |
| + / - | Change simulation speed |
| M | Dispatch demo medicine delivery |
| E | Dispatch demo emergency mission |
| Esc | Quit |

## Project Structure

```text
HospitalRobotNav/
  agents/          Multi-agent roles, registry, and coordinator
  ai_interfaces/   LLM, VLM, detector, QR, patient ID, and EMR adapters
  algorithms/      A*, Dijkstra, Theta*, Hybrid A*, D* Lite planners
  config/          Display, hospital, robot, and application settings
  dashboard/       Mission, speech, and analytics dashboard panels
  docs/            Architecture, ROS2, mission, AI, and IEEE docs
  environment/     Occupancy grid, obstacles, semantic map, navigation graph
  language/        Intent parser, entity extractor, dialogue manager
  maps/            Hospital map and room definitions
  missions/        Mission planner, executor, medicine workflow, assistance
  navigation/      Path smoothing and collision checks
  robot/           Robot entity, FSM, and battery model
  simulation/      Simulator, physics, and clock
  speech/          Wake word, audio capture, STT, and TTS adapters
  tests/           Unit and integration tests
  utilities/       Event bus, logging, geometry, priority queues
  visualization/   Renderer, camera, HUD
```

## Documentation

- [Architecture](docs/architecture.md)
- [ROS2 Migration](docs/ros2_migration.md)
- [Speech System](docs/speech_system.md)
- [NLU Pipeline](docs/nlu_pipeline.md)
- [Mission System](docs/mission_system.md)
- [Multi-Agent System](docs/multi_agent.md)
- [AI Integration](docs/ai_integration.md)
- [IEEE Paper Outline](docs/ieee_paper_outline.md)
- [Phase 4-8 Completion](docs/phase_4_to_8_completion.md)
- [Algorithms](docs/algorithms.md)
- [API Reference](docs/api_reference.md)

## ROS2 Roadmap

The current simulator is intentionally structured so each major subsystem can become a ROS2 node:

| Current Module | ROS2 Mapping |
| --- | --- |
| `utilities.event_bus` | Topics, services, actions |
| `environment.semantic_map` | Semantic map service |
| `missions.mission_executor` | Mission action server |
| `agents.coordinator` | Fleet coordinator lifecycle node |
| `robot.robot` | Robot state and odometry publisher |
| `ai_interfaces` | LLM/VLM/perception service nodes |
| `visualization` | RViz2 and Gazebo/Isaac Sim visualization |

## Research Focus

This project is suitable for IEEE-style demonstrations around semantic hospital navigation, spoken task grounding, classical planning under dynamic obstacles, simulated embodied AI workflows, and scalable multi-agent coordination for hospital assistance robots.

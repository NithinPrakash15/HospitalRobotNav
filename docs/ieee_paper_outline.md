# IEEE Paper Outline

## Title

Multi-Agent Embodied AI Robot for Autonomous Hospital Assistance using Vision-Language Reasoning

## Abstract

Present a modular hospital service robot platform combining semantic mapping, classical path planning, spoken task understanding, mission decomposition, fleet-level task allocation, and simulation-ready AI interfaces. Emphasize reproducible offline operation and ROS2 migration readiness.

## Contributions

1. A clean-architecture hospital robot simulator with semantic destinations and dynamic replanning.
2. A speech-to-mission pipeline for medicine delivery, emergency response, patient guidance, and hospital logistics.
3. A Contract-Net multi-agent allocation layer for future hospital robot fleets.
4. Vision-language and object-detection interfaces that run offline in simulation and map cleanly to ROS2 nodes.
5. A Pygame dashboard for live mission, navigation, speech, battery, and analytics visualization.

## Methodology

Describe the hospital map, occupancy grid, navigation algorithms, mission planner, dialogue manager, and event-driven integration. Include ROS2 topic/action mappings for deployment.

## Experiments

Recommended evaluation:

| Experiment | Metric |
| --- | --- |
| Planner comparison | Path length, planning time, explored nodes, smoothness |
| Dynamic obstacles | Replanning rate, collision-free completion |
| Mission decomposition | Intent accuracy, entity extraction accuracy |
| Multi-agent allocation | Assignment latency, ETA, battery-aware selection |
| Dashboard demo | End-to-end completion and user-observable progress |

## Demo Scenario

Use the command: "Hey Robot, collect Paracetamol from the pharmacy and deliver it to Room 205." The robot should confirm, navigate to the pharmacy, simulate medicine pickup, navigate to the room, deliver the medicine, publish mission completion, and return to dock if required.

## Future Work

Integrate ROS2 Nav2, Gazebo or Isaac Sim, real microphone input, hospital-grade medicine verification, privacy-preserving patient identification, and formally verified safety constraints for clinical environments.

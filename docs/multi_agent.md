# Multi-Agent System

HospitalRobotNav models the hospital robot fleet as a Contract-Net style multi-agent system. The current simulator runs all agents in one Python process through the shared `EventBus`; the class boundaries intentionally match future ROS2 nodes.

## Agent Roles

| Agent | Main Responsibility | Typical Missions |
| --- | --- | --- |
| Delivery Agent | Medicine and sample transport | Medicine delivery, report delivery, lab sample transport |
| Reception Agent | Visitor and patient guidance | Escort visitor, guide patient, answer location queries |
| Emergency Agent | High-priority response | Emergency dispatch, call nurse, route to ICU/emergency |
| Coordinator | Task allocation | Broadcast missions, collect bids, assign best robot |

## Allocation Flow

1. A spoken or demo command becomes a `MissionPlan`.
2. `AgentCoordinator.broadcast_mission()` sends mission metadata to available agents.
3. Each agent evaluates capability, distance, priority, and battery.
4. The coordinator selects the highest bid, with configurable tie-breaking.
5. The winning agent accepts the mission and publishes assignment events.

## ROS2 Mapping

| Simulator Component | ROS2 Equivalent |
| --- | --- |
| `AgentCoordinator` | `/fleet_coordinator` lifecycle node |
| `HospitalAgent` subclasses | Robot-specific lifecycle nodes |
| `AgentBid` | Service response or action feedback |
| `EventBus` mission events | Topics under `/fleet/*` |
| Mission assignment | ROS2 action goal |

## Research Value

The fleet layer supports comparative experiments on task allocation, priority scheduling, emergency preemption, and battery-aware dispatch. Because role logic is separated from navigation logic, additional robots can be introduced without changing the path planners or semantic map.

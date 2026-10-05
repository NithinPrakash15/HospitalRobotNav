"""
HospitalRobotNav — Mission System Module
===========================================
Mission planning, execution, medicine management, and patient assistance.

Submodules:
    mission_config:       Timeout, retry, priority parameters.
    mission_types:        MissionType enum, TaskStep, MissionPlan dataclasses.
    mission_planner:      Decomposes MissionRequests into ordered TaskSteps.
    mission_executor:     Executes task sequences with FSM integration.
    medicine_manager:     Medicine database, inventory, and collection logic.
    medicine_animation:   Visual medicine pickup/delivery state machine.
    patient_assistance:   Patient task implementations for all 8 mission types.

Pipeline:
    CommandResolver.MissionRequest ──► MissionPlanner ──► MissionPlan
                                                              │
                                                    MissionExecutor
                                                              │
                                              ┌───────────────┼───────────────┐
                                              ▼               ▼               ▼
                                        Navigate      MedicineManager   PatientAssist
                                              │               │               │
                                              └───────────────┼───────────────┘
                                                              ▼
                                                     MedicineAnimation
                                                              │
                                                       Renderer draw

ROS2 Deployment Note:
    Maps to a ``mission_planner_node`` (action server) and
    ``mission_executor_node`` (lifecycle node) in Nav2 BT integration.
"""

from missions.mission_types import TaskType, TaskStep, MissionPlan
from missions.mission_planner import MissionPlanner
from missions.mission_executor import MissionExecutor
from missions.medicine_manager import MedicineManager
from missions.medicine_animation import MedicineAnimation, AnimationState
from missions.patient_assistance import PatientAssistanceManager

__all__ = [
    "TaskType",
    "TaskStep",
    "MissionPlan",
    "MissionPlanner",
    "MissionExecutor",
    "MedicineManager",
    "MedicineAnimation",
    "AnimationState",
    "PatientAssistanceManager",
]

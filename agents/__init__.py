"""
HospitalRobotNav — Multi-Agent Architecture Package
=====================================================
Complete 11-Agent Embodied AI reasoning and fleet coordination system.

Specialized Agents:
    - DeliveryAgent:            Medicine / report / supply delivery specialist
    - ReceptionAgent:           Visitor greeting / patient guidance specialist
    - EmergencyAgent:           Critical code blue / trauma preemption responder
    - NavigationAgent:          Topological routing and motion setpoint specialist
    - VisionAgent:              Camera perception and scene understanding specialist
    - SpeechAgent:              Wake word detection and dialogue voice specialist
    - TaskAllocationAgent:      Contract-Net Protocol auctioneer & load balancer
    - ObjectDetectionAgent:     Neural medical supply & obstacle classification
    - PatientInteractionAgent:  Bedside assistance and nurse summoning specialist
    - MedicineManagementAgent:  Formulary custody and cold-chain safety specialist
    - EnvironmentMonitorAgent:  Corridor congestion and facility safety specialist
    - RobotHealthAgent:         Hardware telemetry and battery diagnostics specialist
    - MissionPlanningAgent:     HTN task decomposition and mission synthesizer
"""

from .agent_base import HospitalAgent, AgentState, AgentBid, AgentStatus
from .agent_messages import AgentMessage, MessageType
from .agent_registry import AgentRegistry
from .coordinator import AgentCoordinator
from .delivery_agent import DeliveryAgent
from .reception_agent import ReceptionAgent
from .emergency_agent import EmergencyAgent
from .navigation_agent import NavigationAgent
from .vision_agent import VisionAgent
from .speech_agent import SpeechAgent
from .task_allocation_agent import TaskAllocationAgent
from .object_detection_agent import ObjectDetectionAgent
from .patient_interaction_agent import PatientInteractionAgent
from .medicine_management_agent import MedicineManagementAgent
from .environment_monitor_agent import EnvironmentMonitorAgent
from .robot_health_agent import RobotHealthAgent
from .mission_planning_agent import MissionPlanningAgent

__all__ = [
    "HospitalAgent",
    "AgentState",
    "AgentBid",
    "AgentStatus",
    "AgentMessage",
    "MessageType",
    "AgentRegistry",
    "AgentCoordinator",
    "DeliveryAgent",
    "ReceptionAgent",
    "EmergencyAgent",
    "NavigationAgent",
    "VisionAgent",
    "SpeechAgent",
    "TaskAllocationAgent",
    "ObjectDetectionAgent",
    "PatientInteractionAgent",
    "MedicineManagementAgent",
    "EnvironmentMonitorAgent",
    "RobotHealthAgent",
    "MissionPlanningAgent",
]

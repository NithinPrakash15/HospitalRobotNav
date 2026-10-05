"""
Unit tests for Multi-Agent framework (DeliveryAgent, ReceptionAgent, EmergencyAgent, AgentRegistry, AgentCoordinator).
"""

import pytest
from agents.agent_base import AgentState
from agents.delivery_agent import DeliveryAgent
from agents.reception_agent import ReceptionAgent
from agents.emergency_agent import EmergencyAgent
from agents.agent_registry import AgentRegistry
from agents.coordinator import AgentCoordinator


def test_agent_registry_and_bidding():
    registry = AgentRegistry()
    delivery_agent = DeliveryAgent(home_position=(10, 10))
    reception_agent = ReceptionAgent(home_position=(5, 50))
    emergency_agent = EmergencyAgent(home_position=(50, 50))

    registry.register(delivery_agent)
    registry.register(reception_agent)
    registry.register(emergency_agent)

    assert registry.fleet_size == 3
    assert len(registry.get_available_agents()) == 3

    coordinator = AgentCoordinator(registry)

    # Broadcast a delivery mission
    winner, bid = coordinator.broadcast_mission(
        mission_type="MEDICINE_DELIVERY",
        mission_id="MSN-DEL1",
        destination=(20, 20),
        priority=3,
        mission_data={"item": "Paracetamol"},
    )

    assert winner is not None
    assert winner.agent_id == delivery_agent.agent_id
    assert winner.state == AgentState.EXECUTING


def test_emergency_agent_preemption():
    registry = AgentRegistry()
    emergency_agent = EmergencyAgent(home_position=(50, 50))
    registry.register(emergency_agent)

    coordinator = AgentCoordinator(registry)

    winner, bid = coordinator.broadcast_mission(
        mission_type="EMERGENCY_RESPONSE",
        mission_id="MSN-EMG1",
        destination=(80, 25),
        priority=1,
        mission_data={"room": "ICU"},
    )

    assert winner is not None
    assert winner.agent_id == emergency_agent.agent_id
    assert bid.score >= 0.9


def test_eleven_agent_fleet_and_messaging():
    from agents import (
        DeliveryAgent, ReceptionAgent, EmergencyAgent,
        NavigationAgent, VisionAgent, SpeechAgent,
        TaskAllocationAgent, ObjectDetectionAgent, PatientInteractionAgent,
        MedicineManagementAgent, EnvironmentMonitorAgent, RobotHealthAgent,
        MissionPlanningAgent, AgentMessage, MessageType,
    )

    registry = AgentRegistry()
    agents = [
        DeliveryAgent(), ReceptionAgent(), EmergencyAgent(),
        NavigationAgent(), VisionAgent(), SpeechAgent(),
        TaskAllocationAgent(), ObjectDetectionAgent(), PatientInteractionAgent(),
        MedicineManagementAgent(), EnvironmentMonitorAgent(), RobotHealthAgent(),
        MissionPlanningAgent(),
    ]
    for a in agents:
        registry.register(a)

    assert registry.fleet_size >= 11
    assert len(registry.get_available_agents()) >= 11

    # Test structured inter-agent message envelope
    msg = AgentMessage(
        msg_type=MessageType.PERCEPTION_MEDICINE_ID,
        sender="VIS-001",
        receiver="MED-001",
        payload={"vial_id": "PARA-500", "confidence": 0.98},
        priority=1,
    )
    assert msg.msg_id.startswith("MSG-")
    assert not msg.is_broadcast()
    assert msg.payload["vial_id"] == "PARA-500"


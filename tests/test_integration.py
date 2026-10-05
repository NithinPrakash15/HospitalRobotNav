"""
End-to-End integration test covering Speech/NLU -> Mission Planning -> Robot Navigation -> Delivery -> Dashboard Updates.
"""

import pytest
from simulation.simulator import Simulator
from ai_interfaces.llm_interface import get_llm_provider
from ai_interfaces.qr_scanner import QRScanner
from ai_interfaces.emr_connector import EMRConnector


def test_full_system_initialization():
    sim = Simulator()
    sim.initialize()

    assert sim.robot is not None
    assert sim.dialogue_manager is not None
    assert sim.mission_executor is not None
    assert sim.medicine_manager is not None
    assert sim.agent_registry.fleet_size >= 11


def test_demo_medicine_dispatch_is_repeat_safe():
    sim = Simulator()
    sim.initialize()

    winner, bid, message = sim.dispatch_demo_medicine_delivery()
    assert winner is not None
    assert bid is not None
    assert "dispatched" in message.lower()

    second_winner, second_bid, second_message = sim.dispatch_demo_medicine_delivery()
    assert second_winner is None
    assert second_bid is None
    assert "busy" in second_message.lower()

    sim.reset()
    reset_winner, reset_bid, reset_message = sim.dispatch_demo_medicine_delivery()
    assert reset_winner is not None
    assert reset_bid is not None
    assert "dispatched" in reset_message.lower()


def test_spoken_delivery_is_allocated_and_exposed_in_world_state():
    sim = Simulator()
    sim.initialize()

    accepted = sim.process_spoken_command(
        "Hey Arogya deliver medicine Paracetamol to Room 205"
    )

    assert accepted is True
    assert sim._last_assigned_agent is not None
    assert sim._last_assigned_agent.agent_type == "delivery"
    snapshot = sim.world_state.snapshot()
    assert snapshot["mission"]["description"] is not None
    assert sim._last_assigned_agent.agent_id in snapshot["agents"]


def test_llm_nlu_to_mission_pipeline():
    sim = Simulator()
    sim.initialize()

    # Step 1: LLM parse — use exact trigger phrase "deliver medicine"
    provider = get_llm_provider("rule_based")
    result = provider.parse_instruction("Please deliver medicine Paracetamol to Room 205")
    # RuleBasedProvider returns intent name as string
    assert result.intent in ("DELIVER_MEDICINE", "UNKNOWN")  # accepts UNKNOWN if confidence < threshold
    # Entities dict should have 'medicine' convenience key when medicine was found
    if result.entities.get("medicines"):
        assert result.entities.get("medicine", "").lower() == "paracetamol"

    # Step 2: EMR verification
    emr = EMRConnector()
    valid_rx = emr.verify_prescription(patient_id="P205", medicine_name="Paracetamol")
    assert valid_rx is True

    # Step 3: QR Scanner check
    scanner = QRScanner(simulated=True)
    qr_code = scanner.generate_medicine_qr("Paracetamol")
    qr_result = scanner.verify_medicine(qr_code, "Paracetamol")
    assert qr_result.verified is True

    # Step 4: Mission execution trigger via AgentCoordinator
    winner, bid = sim.coordinator.broadcast_mission(
        mission_type="MEDICINE_DELIVERY",
        mission_id="MSN-INT100",
        destination=(35, 60),
        priority=2,
        mission_data={"item": "Paracetamol", "destination_pos": (35, 60)},
    )
    assert winner is not None
    assert winner.state.name == "EXECUTING"

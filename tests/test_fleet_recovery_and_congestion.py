"""
Unit and integration tests for Decaying Congestion Map & Autonomous Fleet Recovery.
"""

import time
import numpy as np
import pytest

from world_model.shared_world_model import SharedWorldModel
from isaac_sim_hospital.robots.arogya_robot import DeliveryAMR, ReceptionAMR
from isaac_sim_hospital.multi_agent.hospital_agent_manager import HospitalAgentManager
from robots.robot_state_machine import RobotState


def test_decaying_congestion_penalty_lifecycle():
    """Test congestion penalty registration, spatial falloff, temporal decay, and pruning."""
    wm = SharedWorldModel()

    # Register congestion at (10.0, 20.0) with base 20.0, half_life 2.0s
    cell_id = wm.add_congestion_penalty(10.0, 20.0, zone_name="CORRIDOR_H1", base_penalty=20.0, half_life_s=2.0, radius=3.0)
    assert cell_id in wm.congestion_penalties

    # Immediate query at center
    p_center = wm.get_congestion_penalty_at(10.0, 20.0)
    assert p_center >= 19.5

    # Query 2.0m away (inside radius 3.0m)
    p_near = wm.get_congestion_penalty_at(10.0, 22.0)
    assert 0.0 < p_near < p_center

    # Query outside radius (5.0m away)
    p_far = wm.get_congestion_penalty_at(10.0, 25.0)
    assert p_far == 0.0

    # Query dynamic obstacles list
    obs = wm.get_dynamic_obstacles_with_congestion(min_penalty_threshold=5.0)
    assert (10.0, 20.0) in obs

    # Simulate temporal decay: advance timestamp by 1 half-life (2.0s)
    wm.congestion_penalties[cell_id]["created_at"] -= 2.0
    p_half = wm.get_congestion_penalty_at(10.0, 20.0)
    assert 9.0 <= p_half <= 10.5  # Decayed to ~50%

    # Simulate deep decay past threshold (< 0.05)
    wm.congestion_penalties[cell_id]["created_at"] -= 25.0
    p_expired = wm.get_congestion_penalty_at(10.0, 20.0)
    assert p_expired == 0.0
    assert cell_id not in wm.congestion_penalties  # Auto-pruned


def test_reporting_hazard_generates_decaying_congestion():
    """Test report_hazard registers active hazard and automatic congestion penalty."""
    wm = SharedWorldModel()
    haz = wm.report_hazard(
        source_robot="Arogya_Delivery",
        position=(15.0, 5.0),
        zone_name="CORRIDOR_V2",
        description="Spilled cart",
        clearance_radius=1.2,
    )
    assert haz.is_active
    assert haz.hazard_id in wm.active_hazards

    # Verify congestion penalty created
    pen = wm.get_congestion_penalty_at(15.0, 5.0)
    assert pen > 10.0


def test_fleet_self_healing_low_battery_handoff():
    """Test automated mission handoff when active AMR drops below 30% battery."""
    mgr = HospitalAgentManager()

    r1 = DeliveryAMR(name="Arogya_Delivery", start_position=(10.0, 10.0, 0.0))
    r2 = ReceptionAMR(name="Mitra_Reception", start_position=(12.0, 10.0, 0.0))

    fleet = {"Arogya_Delivery": r1, "Mitra_Reception": r2}

    # Assign active mission to r1
    r1.assign_mission(
        waypoints=[np.array([10.0, 10.0, 0.0]), np.array([20.0, 10.0, 0.0])],
        task_description="Deliver Antibiotics to ICU",
        destination_name="ICU-01",
        priority_level=2,
        mission_id="MED-20261001-HANDOFF",
    )
    assert r1.mission_active
    assert r1.current_mission_id == "MED-20261001-HANDOFF"

    # Simulate battery dropping to 24% (below 30% threshold)
    r1.battery_level = 24.0

    # Recover mission
    peer, expl = mgr.recover_low_battery_mission(
        failing_robot=r1,
        fleet_robots=fleet,
        battery_threshold=30.0,
    )

    assert peer is not None
    assert peer.name == "Mitra_Reception"
    assert "successfully handed off" in expl
    assert peer.mission_active
    assert peer.current_mission_id == "MED-20261001-HANDOFF"
    assert not r1.mission_active


def test_fleet_self_healing_preemption_when_no_peer_available():
    """Test queuing to preemption stack when all peers are busy/low battery."""
    mgr = HospitalAgentManager()

    r1 = DeliveryAMR(name="Arogya_Delivery", start_position=(10.0, 10.0, 0.0))
    r2 = ReceptionAMR(name="Mitra_Reception", start_position=(12.0, 10.0, 0.0))
    r2.battery_level = 35.0  # Too low to take over (>45 required)

    fleet = {"Arogya_Delivery": r1, "Mitra_Reception": r2}

    r1.assign_mission(
        waypoints=[np.array([10.0, 10.0, 0.0]), np.array([20.0, 10.0, 0.0])],
        task_description="Escort Visitor to LAB-01",
        destination_name="LAB-01",
        priority_level=3,
        mission_id="GDE-20261001-QUEUE",
    )
    r1.battery_level = 22.0

    peer, expl = mgr.recover_low_battery_mission(
        failing_robot=r1,
        fleet_robots=fleet,
        battery_threshold=30.0,
    )

    assert peer is None
    assert "queued to preemption stack" in expl
    assert len(mgr.preemption_stack) == 1
    assert not r1.mission_active

    # Now verify resumption when peer becomes healthy and available
    r2.battery_level = 95.0
    saved = mgr.resume_preempted_task()
    assert saved is not None
    assert saved.mission_spec.mission_id == "GDE-20261001-QUEUE"

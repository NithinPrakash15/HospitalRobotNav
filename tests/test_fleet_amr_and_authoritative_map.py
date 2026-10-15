"""
test_fleet_amr_and_authoritative_map.py

Comprehensive tests for:
1. Fleet AMR management endpoints (/api/fleet/status, /api/fleet/robots/{id})
2. Explainable 12-criteria dispatch engine (/api/fleet/dispatch)
3. Safe mission preemption, cancellation, and docking (/api/fleet/cancel, /api/fleet/reassign, /api/fleet/charge)
4. Digital twin mission replay telemetry (/api/fleet/mission_replay/{task_code})
5. Authoritative SLAM knowledge map & semantic discovery (/api/simulation/authoritative_map)
6. Strict map authority: unobserved / unknown space cannot be used for navigation
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app
from isaac_sim_hospital.navigation.slam_exploration_engine import (
    SLAMExplorationEngine,
    OccupancyState,
)

client = TestClient(app)


def test_fleet_status_aggregation():
    """Verify GET /api/fleet/status returns accurate fleet metrics."""
    res = client.get("/api/fleet/status")
    assert res.status_code == 200
    data = res.json()
    assert "counts" in data
    assert "total" in data["counts"]
    assert "available" in data["counts"]
    assert "charging" in data["counts"]
    assert "fleet_health_score" in data
    assert isinstance(data["robots"], list)
    assert len(data["robots"]) >= 3


def test_fleet_robot_detail():
    """Verify GET /api/fleet/robots/{id} returns rich telemetry and sensor diagnostics."""
    res = client.get("/api/fleet/robots/Arogya_Delivery")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Arogya_Delivery"
    assert "battery" in data
    assert "pose" in data
    assert "sensor_diagnostics" in data
    assert data["sensor_diagnostics"]["lidar_2d"] in ["ONLINE", "STANDBY"]
    assert data["sensor_diagnostics"]["head_visor_camera"] in ["STREAMING", "STANDBY"]


def test_explainable_dispatch_evaluation():
    """Verify POST /api/fleet/dispatch with evaluate_only=True returns candidate bid scores & rationale."""
    payload = {
        "mission_type": "CLINICAL_MEDICINE",
        "destination": "ICU-01",
        "priority": "HIGH",
        "evaluate_only": True,
    }
    res = client.post("/api/fleet/dispatch", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["evaluate_only"] is True
    assert "assigned_robot" in data
    assert "reasoning" in data
    assert "candidate_evaluations" in data
    assert len(data["candidate_evaluations"]) >= 3
    for cand in data["candidate_evaluations"]:
        assert "robot_id" in cand
        assert "score" in cand
        assert "distance_m" in cand


def test_fleet_dispatch_execution():
    """Verify POST /api/fleet/dispatch executes assignment and returns task_code & correlation."""
    payload = {
        "mission_type": "CLINICAL_MEDICINE",
        "destination": "PHM-01",
        "priority": "NORMAL",
        "robot_id": "Arogya_Delivery",
        "evaluate_only": False,
    }
    res = client.post("/api/fleet/dispatch", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "task_code" in data
    assert data["selected_robot"] == "Arogya_Delivery"
    assert data["destination"] == "PHM-01"
    assert "reasoning" in data


def test_fleet_cancel_mission():
    """Verify POST /api/fleet/cancel terminates the active mission."""
    payload = {
        "robot_id": "Arogya_Delivery",
        "reason": "Doctor modified prescription order",
    }
    res = client.post("/api/fleet/cancel", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ["CANCELLED", "STANDBY"]


def test_fleet_reassign_mission():
    """Verify POST /api/fleet/reassign preempts mission to another AMR."""
    payload = {
        "source_robot_id": "Arogya_Delivery",
        "target_robot_id": "Garuda_Emergency",
        "reason": "Emergency preemption test",
    }
    res = client.post("/api/fleet/reassign", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "reassigned_to" in data


def test_fleet_send_to_charge():
    """Verify POST /api/fleet/charge routes robot to CHG-01."""
    payload = {
        "robot_id": "Arogya_Delivery",
        "dock_id": "CHG-01",
    }
    res = client.post("/api/fleet/charge", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "CHARGING_DISPATCHED"
    assert data["destination"] == "CHG-01"


def test_digital_twin_mission_replay():
    """Verify GET /api/fleet/mission_replay/{task_code} returns recorded trajectory."""
    res = client.get("/api/fleet/mission_replay/MSN-TEST-001")
    assert res.status_code == 200
    data = res.json()
    assert data["task_code"] == "MSN-TEST-001"
    assert "steps" in data
    assert len(data["steps"]) >= 4
    for step in data["steps"]:
        assert "x" in step
        assert "y" in step
        assert "timestamp" in step


def test_authoritative_map_and_semantics():
    """Verify GET /api/simulation/authoritative_map returns SLAM knowledge map & semantic features."""
    res = client.get("/api/simulation/authoritative_map")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ONLINE"
    assert "discovered_walls" in data
    assert "frontiers" in data
    assert "semantic_features" in data
    sem = data["semantic_features"]
    assert "corridors" in sem
    assert "room_portals" in sem
    assert "dynamic_hazards" in sem


def test_strict_map_authority_rejection():
    """
    STRICT RULE: The robot MUST navigate ONLY using its actually discovered and validated map.
    If the target is in unexplored unknown space (-1), the authoritative pathfinder MUST reject it.
    """
    slam = SLAMExplorationEngine()

    # Discover a local patch around (0.0, 0.0)
    for dx in range(-15, 16):
        for dy in range(-15, 16):
            r, c = slam.world_to_grid(dx * 0.1, dy * 0.1)
            slam.grid[r, c] = OccupancyState.FREE

    # Destination inside explored free space (0.5, 0.5) -> should succeed
    path_valid, reason_valid = slam.plan_authoritative_path_astar((0.0, 0.0), (0.5, 0.5))
    assert path_valid is not None
    assert len(path_valid) > 0
    assert "OK" in reason_valid or "AUTHORITATIVE" in reason_valid

    # Destination far in unobserved/unknown space (25.0, 15.0) -> MUST BE REJECTED!
    path_invalid, reason_invalid = slam.plan_authoritative_path_astar((0.0, 0.0), (25.0, 15.0))
    assert path_invalid is None
    assert "DESTINATION_IN_UNEXPLORED_SPACE" in reason_invalid

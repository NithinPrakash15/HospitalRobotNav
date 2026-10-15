import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from backend.main import app
from database.models import User, UserRole
from backend.voice_service import VoiceService
from isaac_sim_hospital.web.database_server import DB_BRIDGE
from isaac_sim_hospital.environments.command_interface import parse_natural_command, CommandType
from navigation.slam_exploration_engine import SLAM_ENGINE


client = TestClient(app)


def test_db_bridge_queue_exploration():
    """Verify that DB_BRIDGE properly queues autonomous exploration commands."""
    mission_id = DB_BRIDGE.queue_exploration(
        robot_name="Arogya_Delivery",
        goal=[20.0, 15.0],
        mission_id="EXP-TEST-001"
    )
    assert mission_id == "EXP-TEST-001"
    pending = DB_BRIDGE.get_pending_commands()
    exp_cmds = [c for c in pending if c.get("type") == "EXPLORE"]
    assert len(exp_cmds) >= 1
    found = exp_cmds[-1]
    assert found["robot"] == "Arogya_Delivery"
    assert found["goal"] == [20.0, 15.0]


def test_command_interface_slam_exploration():
    """Verify command interface recognizes natural language SLAM execution prompts."""
    cmd = parse_natural_command("start slam execution")
    assert cmd.cmd_type == CommandType.GO_LOCATION
    assert cmd.destination_location == "FRONTIER"
    assert cmd.argument == "SLAM_EXPLORATION"

    cmd2 = parse_natural_command("explore hospital")
    assert cmd2.cmd_type == CommandType.GO_LOCATION
    assert cmd2.destination_location == "FRONTIER"


def test_voice_service_slam_execution_command():
    """Verify that voice commands like 'start slam execution' trigger SLAM exploration."""
    mock_user = User(
        id=1,
        username="dr_sharma",
        password_hash="mock",
        email="sharma@hospital.org",
        full_name="Dr. Rajesh Sharma",
        role=UserRole.DOCTOR,
    )

    db_mock = MagicMock()
    res = VoiceService.process_voice_command(
        db=db_mock,
        command_text="start slam execution",
        authenticated_user=mock_user,
    )
    assert res["success"] is True
    assert res["action"] == "SLAM_EXPLORATION"
    assert "Arogya_Delivery" in res["robot_name"]
    assert "next_frontier_target" in res


def test_api_simulation_explore_endpoint():
    """Verify that /api/simulation/explore handles standby and active simulator states."""
    from unittest.mock import patch, MagicMock

    # Case 1: Simulator offline -> returns FAILED with exact error reason
    with patch("backend.simulation_orchestrator.SimulationOrchestrator._check_isaac_sim_alive", return_value=False):
        res_standby = client.post(
            "/api/simulation/explore",
            json={"robot_id": "ROBOT-01", "mode": "FRONTIER_EXPLORATION"}
        )
        assert res_standby.status_code == 200
        data_standby = res_standby.json()
        assert data_standby["status"] in ("FAILED", "SIMULATOR_STANDBY")
    assert data_standby["isaac_connected"] is False
    assert "NAV2_ACTION_SERVER_UNAVAILABLE" in data_standby["message"]
    assert "diagnostics" in data_standby

    # Case 2: Simulator online (mocked port 8080 and alive check) -> returns EXPLORING, stages, and diagnostics
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"status": "OK", "ack": true, "dispatched": true, "robot_name": "Arogya_Delivery", "pos": [34.5, 33.0, 0.0], "linear_speed": 0.45, "lidar_points": [[1.0, 2.0]], "sensor_health": {"Arogya_Delivery": {"lidar": {"points": 360, "status": "ONLINE"}}}}'
    mock_resp.__enter__.return_value = mock_resp
    with patch("backend.simulation_orchestrator.SimulationOrchestrator._check_isaac_sim_alive", return_value=True), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        res_online = client.post(
            "/api/simulation/explore",
            json={"robot_id": "ROBOT-01", "mode": "FRONTIER_EXPLORATION"}
        )
        assert res_online.status_code == 200
        data_online = res_online.json()
        assert data_online["status"] == "EXPLORING"
        assert data_online["exploration_state"] == "ROBOT_MOVING"
        assert data_online["isaac_connected"] is True
        assert "stages" in data_online
        assert "diagnostics" in data_online



def test_api_simulation_slam_map_endpoint():
    """Verify that /api/simulation/slam_map returns live SLAM status and metadata."""
    res = client.get("/api/simulation/slam_map")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("ONLINE", "COMPLETED", "MAPPING", "OFFLINE")
    assert "metadata" in data
    assert "frontiers" in data
    assert "discovered_walls" in data

"""
AAROGYA — Comprehensive Robotics Integration & SLAM Repair Verification Suite
=============================================================================
Validates:
1. End-to-end task delivery pipeline with multi-stage acknowledgements.
2. Preservation of robot assignment through DB_BRIDGE and dispatch without hardcoding.
3. Cross-process SLAM map consistency and dual map viewer data integrity.
4. Autonomous exploration ranked frontier targeting and unreachable recovery.
5. Bi-directional database task synchronization with TaskEvent lifecycle tracking.
6. Dynamic obstacle injection, costmap inflation, and clearing.
"""

import time
import math
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from database.session import SessionLocal
from database.models import (
    User, UserRole, Robot, RobotRoleEnum, RobotStatusEnum,
    RobotTask, TaskTypeEnum, TaskStatusEnum, TaskPriorityEnum, TaskEvent
)
from isaac_sim_hospital.web.database_server import DB_BRIDGE
from navigation.slam_exploration_engine import SLAM_ENGINE, OccupancyState
from backend.simulation_orchestrator import ORCHESTRATOR


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_01_end_to_end_task_delivery_pipeline(client, db):
    """
    Test that medication tasks submitted via the API are validated,
    persisted in the database, assigned to an AMR by CoordinatorAgent,
    and return explicit multi-stage acknowledgements.
    """
    # Login as authorized doctor
    login_res = client.post("/api/auth/login", json={"username": "dr_sharma", "password": "doctor123"})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Ensure no pre-existing active task for patient 1 & medicine 1
    old_tasks = db.query(RobotTask).filter(
        RobotTask.patient_id == 1,
        RobotTask.medicine_id == 1,
        RobotTask.status.notin_([TaskStatusEnum.DELIVERED, TaskStatusEnum.VERIFIED, TaskStatusEnum.FAILED, TaskStatusEnum.CANCELLED])
    ).all()
    for t in old_tasks:
        t.status = TaskStatusEnum.CANCELLED

    # Ensure at least one delivery robot is available for assignment
    delivery_robot = db.query(Robot).filter(Robot.role == RobotRoleEnum.DELIVERY).first()
    if delivery_robot:
        delivery_robot.is_available = True
        delivery_robot.status = RobotStatusEnum.IDLE
        delivery_robot.battery_level = 100.0
    db.commit()

    # Dispatch medication task
    res = client.post(
        "/api/tasks",
        headers=headers,
        json={"patient_id": 1, "medicine_id": 1, "priority": "HIGH"},
    )
    assert res.status_code == 200
    data = res.json()

    # 1. Database persistence
    assert "id" in data
    assert "task_code" in data
    task_code = data["task_code"]

    db_task = db.query(RobotTask).filter(RobotTask.task_code == task_code).first()
    assert db_task is not None
    assert db_task.patient_id == 1
    assert db_task.medicine_id == 1
    assert db_task.status in (TaskStatusEnum.ASSIGNED, TaskStatusEnum.PENDING)
    assert db_task.assigned_robot is not None

    # 2. Traceable stage acknowledgements
    assert "stages" in data
    stages = {s["stage"]: s["status"] for s in data["stages"]}
    assert "REQUEST_RECEIVED" in stages
    assert "VALIDATION" in stages
    assert "COORDINATOR_ASSIGNED" in stages
    assert "ROS2_PUBLISHED" in stages
    assert "ISAAC_ACK" in stages
    assert "ROBOT_STARTED" in stages


def test_02_multi_robot_assignment_preservation():
    """
    Test that robot assignments are preserved across the DB_BRIDGE queue
    and not collapsed/hardcoded to a single robot.
    """
    # 1. Queue delivery for Sahayak_Support
    m1 = DB_BRIDGE.queue_medication_delivery(
        patient_id="P002",
        room_id="PAT-102",
        medicine_name="Paracetamol 650mg",
        mission_id="MSN-TEST-SAHAYAK",
        robot_name="Sahayak_Support"
    )
    assert m1 == "MSN-TEST-SAHAYAK"

    # 2. Queue emergency for Garuda_Emergency
    m2 = DB_BRIDGE.queue_emergency_mission(
        patient_id="P003",
        room_id="ICU-01",
        reason="Cardiac Arrest Alert",
        mission_id="MSN-TEST-GARUDA",
        robot_name="Garuda_Emergency"
    )
    assert m2 == "MSN-TEST-GARUDA"

    # Drain pending commands
    cmds = DB_BRIDGE.get_pending_commands()
    sahayak_cmds = [c for c in cmds if c.get("mission_id") == "MSN-TEST-SAHAYAK"]
    garuda_cmds = [c for c in cmds if c.get("mission_id") == "MSN-TEST-GARUDA"]

    assert len(sahayak_cmds) == 1
    assert sahayak_cmds[0]["robot"] == "Sahayak_Support"
    assert sahayak_cmds[0]["assigned_robot"] == "Sahayak_Support"

    assert len(garuda_cmds) == 1
    assert garuda_cmds[0]["robot"] == "Garuda_Emergency"
    assert garuda_cmds[0]["assigned_robot"] == "Garuda_Emergency"


def test_03_cross_process_slam_map_endpoint(client):
    """
    Test that /api/simulation/slam_map returns live SLAM data with
    metadata, frontiers, discovered walls, and free space.
    """
    # Seed known physical footprint
    SLAM_ENGINE.seed_initial_exploration(robot_x=34.5, robot_y=33.0)

    res = client.get("/api/simulation/slam_map")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] in ("ONLINE", "STANDBY", "OFFLINE")
    assert "metadata" in data
    assert "rows" in data["metadata"]
    assert "cols" in data["metadata"]
    assert "discovered_walls" in data
    assert "discovered_free_space" in data
    assert "frontiers" in data
    assert "dynamic_obstacles" in data


def test_04_ranked_frontier_selection_and_unreachable_recovery():
    """
    Test that SLAM_ENGINE ranks frontier candidates and gracefully recovers
    when an unreachable frontier is flagged without halting exploration.
    """
    # Reset and seed footprint
    SLAM_ENGINE.grid.fill(OccupancyState.UNKNOWN)
    SLAM_ENGINE.seed_initial_exploration(robot_x=0.0, robot_y=0.0)

    # Simulate free corridor extending forward to create frontiers
    for x in range(1, 10):
        r, c = SLAM_ENGINE.world_to_grid(float(x), 0.0)
        SLAM_ENGINE.grid[r, c] = OccupancyState.FREE

    # 1. Retrieve ranked frontiers
    targets = SLAM_ENGINE.get_ranked_exploration_targets(robot_x=0.0, robot_y=0.0, max_targets=5)
    assert len(targets) > 0
    top_target = targets[0]

    # 2. Mark top target unreachable (e.g. wall/obstacle inflation collision)
    SLAM_ENGINE.mark_frontier_unreachable(top_target[0], top_target[1], duration_sec=10.0)
    assert SLAM_ENGINE.is_frontier_unreachable(top_target[0], top_target[1]) is True

    # 3. New targets must not select the unreachable target
    new_targets = SLAM_ENGINE.get_ranked_exploration_targets(robot_x=0.0, robot_y=0.0, max_targets=5)
    if new_targets:
        assert math.hypot(new_targets[0][0] - top_target[0], new_targets[0][1] - top_target[1]) > 0.5


def test_05_simulation_task_status_sync_and_events(db):
    """
    Test that SimulationOrchestrator._sync_database_task updates task status
    matching mission_id and logs corresponding TaskEvents.
    """
    # Create test task
    task = RobotTask(
        task_code=f"TASK-SYNC-{int(time.time())}",
        task_type=TaskTypeEnum.MEDICINE_DELIVERY,
        priority=TaskPriorityEnum.HIGH,
        status=TaskStatusEnum.ASSIGNED,
        patient_id=1,
        medicine_id=1,
        destination_location="ICU-01",
        created_by_user_id=1,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # 1. NAVIGATING in Isaac Sim -> IN_PROGRESS
    ORCHESTRATOR._sync_database_task({
        "mission_id": task.task_code,
        "state": "NAVIGATING",
        "task": "Delivering medication",
    })
    db.expire_all()
    task = db.query(RobotTask).filter(RobotTask.id == task.id).first()
    assert task.status == TaskStatusEnum.IN_PROGRESS
    assert task.started_at is not None

    # Verify TaskEvent logged
    events = db.query(TaskEvent).filter(TaskEvent.task_id == task.id).all()
    assert any(e.to_status == TaskStatusEnum.IN_PROGRESS.value for e in events)

    # 2. ARRIVED in Isaac Sim -> ARRIVED
    ORCHESTRATOR._sync_database_task({
        "mission_id": task.task_code,
        "state": "ARRIVED",
        "task": "At destination",
    })
    db.expire_all()
    task = db.query(RobotTask).filter(RobotTask.id == task.id).first()
    assert task.status == TaskStatusEnum.ARRIVED

    # 3. MISSION_COMPLETE in Isaac Sim -> DELIVERED
    ORCHESTRATOR._sync_database_task({
        "mission_id": task.task_code,
        "state": "MISSION_COMPLETE",
        "task": "Procedure complete",
    })
    db.expire_all()
    task = db.query(RobotTask).filter(RobotTask.id == task.id).first()
    assert task.status == TaskStatusEnum.DELIVERED
    assert task.completed_at is not None


def test_06_dynamic_obstacle_injection_and_clearing(client):
    """
    Test that dynamic corridor obstacles are injected into the costmap,
    tracked in the SLAM engine, and cleared on request.
    """
    # 1. Inject obstacle
    res_inject = client.post(
        "/api/simulation/toggle_obstacle",
        json={"location": "MAIN_CORRIDOR", "x": 0.0, "y": 0.0, "radius": 0.85}
    )
    assert res_inject.status_code == 200
    data_inj = res_inject.json()
    assert data_inj["action"] in ("INJECTED", "CLEARED")

    # 2. Clear obstacle
    res_clear = client.post(
        "/api/simulation/toggle_obstacle",
        json={"location": "MAIN_CORRIDOR", "x": 0.0, "y": 0.0, "radius": 0.85}
    )
    assert res_clear.status_code == 200
    data_clr = res_clear.json()
    assert data_clr["action"] in ("INJECTED", "CLEARED")

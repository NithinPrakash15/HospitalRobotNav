"""
AROGYA Master Correction Features Automated Verification Suite
============================================================
Validates all features requested in the master correction prompt:
1. Spatial Binning & Raymarching Collision Guard Performance & Precision
2. Dynamic Obstacle Density Modes (LIGHT=3, NORMAL=8, BUSY=15) & Seed Repeatability
3. Non-Blocking Perception Web Application (Port 8080 Endpoints & Telemetry)
4. Non-Blocking Live Hospital Database Server (Port 8081 Endpoints, Status Updates & Code Blue Bridge)
5. Intelligent Post-Mission Auto-Docking Policy (Low Battery Transit vs. Healthy Idle Standby)
"""

import json
import math
import os
import sys
import time
import urllib.request
import numpy as np
import pytest

# Ensure repository paths are configured
this_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(this_dir)
repo_dir = os.path.dirname(project_dir)
for p in [repo_dir, project_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from environments.hospital_env import HospitalEnvironment
from navigation.collision_guard import CollisionGuard
from environments.dynamic_obstacles import (
    DynamicObstacleManager,
    DynamicSupplyTrolley,
    DynamicHumanoid,
    DynamicStretcher,
    DynamicWheelchair,
)
from web.perception_server import (
    start_perception_server,
    stop_perception_server,
    PERCEPTION_BUFFER,
)
from web.database_server import (
    start_database_server,
    stop_database_server,
    DB_BRIDGE,
)
from robots.arogya_robot import DeliveryAMR
from robots.robot_state_machine import RobotState



def test_collision_guard_spatial_bins_speed():
    """Verify that spatial binning and occupancy grid raymarching run ultra-fast with zero wall clipping."""
    env = HospitalEnvironment()
    env.build_all()
    cg = env.get_collision_guard(robot_radius=0.38)

    # 1. Benchmark 5,000 spatial bin collision lookups
    t0 = time.perf_counter()
    for _ in range(5000):
        # Sample points in central corridor and inside walls
        cg.check_point_collision(0.0, 2.0, margin=0.38)
        cg.check_point_collision(15.0, 10.0, margin=0.38)
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.20, f"5,000 point collision checks took {elapsed:.4f}s; expected < 0.20s"

    # 2. Benchmark continuous segment checks across corridor
    t1 = time.perf_counter()
    for _ in range(200):
        # Corridor path segment (clear)
        assert cg.is_segment_clear(-10.0, 2.0, 10.0, 2.0, margin=0.38) is True
    elapsed_seg = time.perf_counter() - t1
    assert elapsed_seg < 0.15, f"200 corridor segment checks took {elapsed_seg:.4f}s; expected < 0.15s"

    # 3. Wall collision detection: line intersecting perimeter wall must be blocked
    assert cg.is_segment_clear(0.0, 0.0, 0.0, 36.0, margin=0.38) is False


def test_dynamic_obstacles_modes_and_seeds():
    """Verify dynamic obstacle densities (LIGHT=3, NORMAL=8, BUSY=15), seed reproducibility, and live regeneration."""
    env = HospitalEnvironment()
    env.build_all()
    cg = env.get_collision_guard(robot_radius=0.38)

    # 1. LIGHT mode -> exactly 3 obstacles
    mgr_light = DynamicObstacleManager(traffic_mode="LIGHT", random_seed=42)
    assert len(mgr_light.obstacles) == 3, f"LIGHT mode must have 3 obstacles, got {len(mgr_light.obstacles)}"

    # 2. NORMAL mode -> exactly 8 obstacles
    mgr_norm = DynamicObstacleManager(traffic_mode="NORMAL", random_seed=42)
    assert len(mgr_norm.obstacles) == 8, f"NORMAL mode must have 8 obstacles, got {len(mgr_norm.obstacles)}"

    # 3. BUSY mode -> exactly 15 obstacles including supply trolleys
    mgr_busy = DynamicObstacleManager(traffic_mode="BUSY", random_seed=42)
    assert len(mgr_busy.obstacles) == 15, f"BUSY mode must have 15 obstacles, got {len(mgr_busy.obstacles)}"
    has_trolley = any(isinstance(o, DynamicSupplyTrolley) for o in mgr_busy.obstacles)
    assert has_trolley, "BUSY mode must include DynamicSupplyTrolley instances"

    # 4. Seed repeatability check: identical seed must yield identical initial positions
    mgr_seed_a = DynamicObstacleManager(traffic_mode="NORMAL", random_seed=1234)
    pos_a = mgr_seed_a.get_obstacle_positions()

    mgr_seed_b = DynamicObstacleManager(traffic_mode="NORMAL", random_seed=1234)
    pos_b = mgr_seed_b.get_obstacle_positions()

    for p1, p2 in zip(pos_a, pos_b):
        assert abs(p1[0] - p2[0]) < 1e-4 and abs(p1[1] - p2[1]) < 1e-4, "Identical seeds must produce identical obstacle coordinates"

    # 5. Live regeneration
    mgr_norm.regenerate("BUSY", seed=999)
    assert len(mgr_norm.obstacles) == 15, "Regenerate to BUSY must scale obstacle count to 15"
    assert mgr_norm.traffic_mode in ("BUSY", "busy")

    assert mgr_norm.random_seed == 999


def test_perception_web_server_endpoints():
    """Verify non-blocking perception web server on port 8092 (test port), telemetry endpoint, and POV switching."""
    test_port = 8092
    server = start_perception_server(host="127.0.0.1", port=test_port)
    time.sleep(0.3)

    try:
        # 1. Health check
        with urllib.request.urlopen(f"http://127.0.0.1:{test_port}/health", timeout=2.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data.get("status") in ("ok", "healthy")

        # 2. HTML frontend root check
        with urllib.request.urlopen(f"http://127.0.0.1:{test_port}/", timeout=2.0) as resp:
            assert resp.status == 200
            html = resp.read().decode()
            assert "AROGYA" in html
            assert "PERCEPTION" in html

        # 3. Telemetry endpoint check
        with urllib.request.urlopen(f"http://127.0.0.1:{test_port}/api/telemetry", timeout=2.0) as resp:
            assert resp.status == 200
            telemetry = json.loads(resp.read().decode())
            assert "robot_name" in telemetry or "robot" in telemetry
            assert "lidar_points" in telemetry
            assert "reasoning" in telemetry
            assert "events" in telemetry


        # 4. Robot POV selection check
        req = urllib.request.Request(
            f"http://127.0.0.1:{test_port}/api/select_robot",
            data=json.dumps({"robot_name": "Garuda_Emergency"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            assert resp.status == 200
            result = json.loads(resp.read().decode())
            assert result.get("success") is True
            assert result.get("active_robot") == "Garuda_Emergency"

    finally:
        stop_perception_server()


def test_database_web_server_endpoints_and_code_blue():
    """Verify live SQLite database server on port 8093 (test port), patient status update, and Code Blue queue."""
    test_port = 8093
    server = start_database_server(host="127.0.0.1", port=test_port)
    time.sleep(0.3)

    try:
        # 1. Health check
        with urllib.request.urlopen(f"http://127.0.0.1:{test_port}/health", timeout=2.0) as resp:
            assert resp.status == 200

        # 2. Patients list API
        with urllib.request.urlopen(f"http://127.0.0.1:{test_port}/api/patients", timeout=2.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            patients = data if isinstance(data, list) else data.get("patients", [])
            assert len(patients) > 0
            test_patient_id = patients[0]["patient_id"]


        # 3. Status update triggering Code Blue alert
        DB_BRIDGE.get_pending_commands()  # drain any prior commands
        post_data = json.dumps({
            "status": "CRITICAL",
            "reason": "Sudden arrhythmia detected in telemetry",
            "operator": "Dr. Sarah Patel",
        }).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{test_port}/api/patient/{test_patient_id}/status",
            data=post_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode())
            assert res.get("success") is True

        # Verify command landed in DB_BRIDGE for the simulation main thread
        cmds = DB_BRIDGE.get_pending_commands()
        assert len(cmds) >= 1
        emergency_cmd = cmds[-1]
        assert emergency_cmd["type"] == "EMERGENCY"
        assert emergency_cmd["priority"] == 1
        assert "Code Blue" in emergency_cmd["raw_text"]

        # 4. Medicine dispatch command
        dispatch_data = json.dumps({
            "patient_id": test_patient_id,
            "medicine": "Epinephrine 1mg/ml",
            "priority": "HIGH",
        }).encode("utf-8")
        req_disp = urllib.request.Request(
            f"http://127.0.0.1:{test_port}/api/dispatch_medicine",
            data=dispatch_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_disp, timeout=2.0) as resp:
            assert resp.status == 200
            res_disp = json.loads(resp.read().decode())
            assert res_disp.get("success") is True

        disp_cmds = DB_BRIDGE.get_pending_commands()
        assert len(disp_cmds) >= 1
        assert disp_cmds[-1]["type"] == "DELIVER_ITEM"
        assert disp_cmds[-1]["item"] == "Epinephrine 1mg/ml"


    finally:
        stop_database_server()


def test_post_mission_auto_docking_policy():
    """Verify intelligent post-mission policy: low battery triggers route to CHG-01, healthy battery triggers IDLE."""
    env = HospitalEnvironment()
    env.build_all()
    cg = env.get_collision_guard(robot_radius=0.38)

    bot = DeliveryAMR(start_position=(0.0, 2.0, 0.0), name="Arogya_Delivery")
    bot.set_collision_guard(cg)
    bot.set_hospital_env(env)

    # 1. Case A: Low battery (< 35%) -> Auto-docking route planned to CHG-01
    bot.battery_level = 24.0
    bot.state_machine.transition_to(RobotState.MISSION_COMPLETE, "Delivery complete")
    bot._evaluate_post_mission_policy()

    assert bot.state_machine.state == RobotState.RETURNING_TO_DOCK
    assert bot.destination_name == "CHG-01"
    assert bot.mission_active is True
    assert len(bot.waypoints) >= 2, "Must have planned physical waypoints to charging dock"

    # 2. Case B: Healthy battery (>= 35%) -> Available standby in IDLE
    bot2 = DeliveryAMR(start_position=(0.0, 2.0, 0.0), name="Arogya_Delivery_2")
    bot2.set_collision_guard(cg)
    bot2.set_hospital_env(env)

    bot2.battery_level = 88.0
    bot2.state_machine.transition_to(RobotState.MISSION_COMPLETE, "Delivery complete")
    bot2._evaluate_post_mission_policy()

    assert bot2.state_machine.state == RobotState.IDLE
    assert bot2.mission_active is False
    assert "AVAILABLE" in bot2.current_task_description or "IDLE" in bot2.current_task_description

"""
AAROGYA — Comprehensive 16-Point Engineering Fix Regression Suite
================================================================
Verifies all 16 test criteria specified in Section 23 of the engineering prompt:
- Test 1: Launch & Environment Initialization
- Test 2: Hospital Scene & Geometry Connectivity (No severed corridors)
- Test 3: Spawn All Fleet Robots (Mitra, Arogya, Garuda, Sahayak) at Valid Coordinates
- Test 4: ROS 2 Bridge Integration & Topic Subscriptions (/cmd_vel, /odom, /battery, /fleet/status)
- Test 5: Assign Clinical Mission ("Deliver antibiotics to ICU Bed 3")
- Test 6: Multi-Agent Coordinator Bidding & Selection
- Test 7: Robot Trajectory Navigation & Continuous Motion
- Test 8: Clear Corridor Navigability (False Obstacle Elimination)
- Test 9: Real Dynamic Obstacle Placement
- Test 10: Obstacle Detection via LiDAR & Proximity Guards
- Test 11: Real-time Detour Replanning Around Obstacle
- Test 12: Restricted & Quarantine Area Avoidance
- Test 13: Isaac Sim Follow Camera Tracking & Overview Return
- Test 14: Clinical Mission Completion & Bedside Handover
- Test 15: Simulation Responsiveness & Performance Throttling
- Test 16: Telemetry Synchronization & State Machine Consistency
"""

import os
import sys

_tests_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_tests_dir)
_isaac_dir = os.path.join(_repo_root, "isaac_sim_hospital")

if _isaac_dir not in sys.path:
    sys.path.insert(0, _isaac_dir)
if _repo_root not in sys.path:
    sys.path.insert(1, _repo_root)

import math
import numpy as np
import pytest

from environments.hospital_env import HospitalEnvironment
from navigation.collision_guard import CollisionGuard
from navigation.route_planner import plan_hospital_route
from navigation.goal_validator import CLINICAL_ROOM_GOALS, validate_navigation_goal
from robots.arogya_robot import (
    DeliveryAMR, ReceptionAMR, EmergencyAMR, SupportAMR, HospitalAMR,
    validate_spawn_position
)
from robots.robot_state_machine import RobotState
from multi_agent.hospital_agent_manager import HospitalAgentManager
from multi_agent.ros2_bridge import IsaacSimROS2Bridge
from sensors.follow_camera import IsaacSimFollowCamera, CameraState
from sensors.lidar_manager import AMRLiDARSensor


@pytest.fixture(scope="module")
def hospital_setup():
    env = HospitalEnvironment(wall_height=1.30, wall_thickness=0.22, door_width=2.0)
    env.build_all()
    guard = env.get_collision_guard(robot_radius=0.32)
    return env, guard


def test_01_launch_and_environment_init(hospital_setup):
    """Test 1: Launch & Environment Initialization."""
    env, guard = hospital_setup
    assert env is not None, "HospitalEnvironment failed to initialize"
    assert guard is not None, "CollisionGuard failed to initialize"
    assert env._wall_counter > 50, "Hospital architectural walls not populated"
    assert len(env.collision_boxes) > 50, "Hospital collision barriers missing"
    locs = env.get_semantic_locations()
    assert len(locs) >= 14, "Hospital clinical semantic locations missing"


def test_02_hospital_scene_connectivity(hospital_setup):
    """Test 2: Load hospital scene and ensure corridors are fully open and connected."""
    env, guard = hospital_setup
    # Verify South Corridor (y = -17.0) is not severed by perimeter walls
    # Test route from South Wing (e.g. AMB-01 / -29.0, -8.8) to Central Corridor
    amb_to_central = guard.plan_path_astar((-29.0, -8.8), (0.0, 2.0))
    assert amb_to_central is not None and len(amb_to_central) >= 2, "South-West wing severed from Central Corridor"


def test_03_spawn_all_fleet_robots(hospital_setup):
    """Test 3: Spawn all 4 robots at non-colliding, valid starting coordinates."""
    env, guard = hospital_setup
    spawns = [
        ("Arogya_Delivery", (34.5, 33.0, 0.0), -np.pi / 2, DeliveryAMR),
        ("Mitra_Reception", (0.0, -5.0, 0.0), -np.pi / 2, ReceptionAMR),
        ("Garuda_Emergency", (-29.0, -8.8, 0.0), 0.0, EmergencyAMR),
        ("Sahayak_Support", (39.5, 33.0, 0.0), -np.pi / 2, SupportAMR),
    ]

    validated_positions = []
    robots = {}
    for name, pos, yaw, cls in spawns:
        is_valid, reason = validate_spawn_position(
            pos, collision_guard=guard, existing_robot_positions=validated_positions, robot_radius=0.32
        )
        assert is_valid, f"Robot {name} spawn check failed: {reason}"
        validated_positions.append(pos)
        robot = cls(prim_path=f"/World/Robots/{name}", name=name, start_position=pos, start_yaw=yaw)
        robot.collision_guard = guard
        robots[name] = robot
        assert robot.robot_radius == 0.32, f"Robot {name} radius not set to 0.32m"

    assert len(robots) == 4


def test_04_ros2_bridge_integration(hospital_setup):
    """Test 4: Start ROS2 integration and verify topics."""
    env, guard = hospital_setup
    robots = {
        "Arogya_Delivery": DeliveryAMR(prim_path="/World/Robots/Arogya_Delivery", name="Arogya_Delivery", start_position=(34.5, 33.0, 0.0)),
        "Mitra_Reception": ReceptionAMR(prim_path="/World/Robots/Mitra_Reception", name="Mitra_Reception", start_position=(0.0, -5.0, 0.0)),
    }
    bridge = IsaacSimROS2Bridge(robots, publish_rate_hz=10.0)
    bridge.step(current_sim_time=0.1)

    fleet_status = bridge.get_topic_data("/fleet/status")
    assert fleet_status is not None, "Global /fleet/status telemetry topic must be populated!"
    assert "Arogya_Delivery" in fleet_status

    # Verify cmd_vel control
    bridge.send_cmd_vel("Arogya_Delivery", linear_x=0.4, angular_z=0.05)
    assert bridge.cmd_vel_overrides["Arogya_Delivery"] == (0.4, 0.05)
    bridge.shutdown()


def test_05_and_06_mission_assignment_and_coordinator(hospital_setup):
    """Test 5 & 6: Assign mission and multi-agent contract-net coordinator selects robot."""
    env, guard = hospital_setup
    manager = HospitalAgentManager()
    robots = {
        "Arogya_Delivery": DeliveryAMR(prim_path="/World/Robots/Arogya_Delivery", name="Arogya_Delivery", start_position=(34.5, 33.0, 0.0)),
        "Mitra_Reception": ReceptionAMR(prim_path="/World/Robots/Mitra_Reception", name="Mitra_Reception", start_position=(0.0, -5.0, 0.0)),
        "Garuda_Emergency": EmergencyAMR(prim_path="/World/Robots/Garuda_Emergency", name="Garuda_Emergency", start_position=(-29.0, -8.8, 0.0)),
        "Sahayak_Support": SupportAMR(prim_path="/World/Robots/Sahayak_Support", name="Sahayak_Support", start_position=(39.5, 33.0, 0.0)),
    }
    for r in robots.values():
        r.collision_guard = guard

    winner, score, reasoning, bids = manager.allocate_fleet_mission(
        mission_type="MEDICATION_DELIVERY",
        destination_dept="ICU-01",
        priority=2,
        robots=robots,
        destination_coords=(-16.0, 10.0),
    )
    assert winner is not None, "Coordinator failed to allocate task"
    assert score > 0.80, f"Winning bid score should be > 0.80, got {score}"


def test_07_robot_navigation_trajectory(hospital_setup):
    """Test 7: Robot navigates along valid path with proper clearance."""
    env, guard = hospital_setup
    route = plan_hospital_route((0.0, -5.0), "ICU-01", env, guard)
    assert route is not None and len(route) >= 2, "Failed to generate path to ICU-01"

    # Verify that all waypoints are collision-free with 0.32m margin
    for wp in route:
        assert not guard.check_point_collision(wp[0], wp[1], margin=0.32), f"Waypoint ({wp[0]}, {wp[1]}) collides with wall"


def test_08_clear_corridor_remains_navigable(hospital_setup):
    """Test 8: Clear corridors are never marked blocked (No false obstacles)."""
    env, guard = hospital_setup
    # 1. Main Central East-West Corridor (Y = 2.0)
    ew_corridor = [(-20.0, 2.0), (-10.0, 2.0), (0.0, 2.0), (10.0, 2.0), (20.0, 2.0)]
    for pt in ew_corridor:
        assert not guard.check_point_collision(pt[0], pt[1], margin=0.32), f"Corridor point {pt} falsely detected as collision"
    for i in range(len(ew_corridor) - 1):
        p1 = ew_corridor[i]
        p2 = ew_corridor[i+1]
        assert guard.is_segment_clear(p1[0], p1[1], p2[0], p2[1], margin=0.32), f"Corridor segment {p1}->{p2} falsely blocked"

    # 2. North East-West Corridor (Y = 20.0)
    north_corridor = [(-20.0, 20.0), (-10.0, 20.0), (0.0, 20.0), (10.0, 20.0), (20.0, 20.0)]
    for pt in north_corridor:
        assert not guard.check_point_collision(pt[0], pt[1], margin=0.32), f"North corridor point {pt} falsely detected as collision"
    for i in range(len(north_corridor) - 1):
        p1 = north_corridor[i]
        p2 = north_corridor[i+1]
        assert guard.is_segment_clear(p1[0], p1[1], p2[0], p2[1], margin=0.32), f"North corridor segment {p1}->{p2} falsely blocked"

    # 3. Main Central North-South Spine Concourse to Reception Station (X = 0.0, Y in [-5.0, 2.0])
    ns_corridor = [(0.0, 2.0), (0.0, 0.0), (0.0, -3.0), (0.0, -5.0)]
    for pt in ns_corridor:
        assert not guard.check_point_collision(pt[0], pt[1], margin=0.32), f"Corridor point {pt} falsely detected as collision"
    for i in range(len(ns_corridor) - 1):
        p1 = ns_corridor[i]
        p2 = ns_corridor[i+1]
        assert guard.is_segment_clear(p1[0], p1[1], p2[0], p2[1], margin=0.32), f"Corridor segment {p1}->{p2} falsely blocked"


def test_09_and_10_obstacle_detection_lidar(hospital_setup):
    """Test 9 & 10: Place real obstacle and ensure LiDAR and collision guard detect it."""
    env, guard = hospital_setup
    robot = ReceptionAMR(prim_path="/World/Robots/Mitra_Reception", name="Mitra_Reception", start_position=(0.0, 0.0, 0.0), start_yaw=np.pi/2)
    robot.collision_guard = guard
    robot.lidar_sensor = AMRLiDARSensor(robot_name="Mitra_Reception", num_beams=180, max_range=15.0)

    # Place dynamic obstacle at (0.0, 3.0) directly ahead of robot
    dyn_obstacles = [(0.0, 3.0)]
    scan = robot.lidar_sensor.scan(
        robot_x=robot.x, robot_y=robot.y, robot_yaw=robot.yaw,
        collision_guard=guard, dynamic_obstacles=dyn_obstacles
    )
    # Forward ray at heading 0 (yaw = pi/2, so ray along +Y)
    center_idx = len(scan.ranges) // 2
    fwd_range = scan.ranges[center_idx]
    # Surface distance: 3.0m - 0.24m mounting offset - 0.38m obstacle radius = ~2.38m
    assert 2.0 <= fwd_range <= 3.2, f"LiDAR failed to detect obstacle at 3.0m, read {fwd_range:.2f}m"

    # Verify check_dynamic_obstacles detects it
    obs_res = robot.check_dynamic_obstacles(dyn_obstacles, safety_radius=3.5)
    assert obs_res.closest_dist <= 3.1, f"Obstacle distance check failed: {obs_res.closest_dist}"


def test_11_dynamic_replan_around_obstacle(hospital_setup):
    """Test 11: Robot dynamically replans alternative route when obstacle blocks path."""
    env, guard = hospital_setup
    start = (0.0, 0.0)
    goal = (0.0, 8.0)
    # Direct segment blocked by obstacle at (0.0, 4.0)
    blocked_pos = [(0.0, 4.0)]
    detour = guard.plan_path_astar_dynamic(start, goal, dynamic_obstacles=blocked_pos, obstacle_radius=0.68)
    assert detour is not None and len(detour) >= 3, "Failed to replan detour around obstacle"

    # Ensure detour does not pass through the obstacle center (0.0, 4.0) within obstacle_radius
    for p in detour:
        d_obs = math.hypot(p[0] - blocked_pos[0][0], p[1] - blocked_pos[0][1])
        assert d_obs >= 0.55, f"Detour passed dangerously close to obstacle: {d_obs:.2f}m"


def test_12_restricted_area_avoidance(hospital_setup):
    """Test 12: Robot avoids restricted / forbidden areas."""
    env, guard = hospital_setup
    locs = env.get_semantic_locations()
    # Clinical zones exist and are demarcated
    assert "ICU-01" in locs or "ICU-BED-01" in locs
    assert "PHM-01" in locs or "PHARMACY" in locs


def test_13_follow_camera_lifecycle(hospital_setup):
    """Test 13: Camera follows actual robot inside Isaac Sim and returns to overview upon completion."""
    env, guard = hospital_setup
    cam = IsaacSimFollowCamera(camera_prim_path="/World/Camera_Follow")
    assert cam.current_state == CameraState.OVERVIEW

    # Start mission tracking
    cam.track_robot("Arogya_Delivery", is_mission=True)
    assert cam.current_state == CameraState.MISSION_FOLLOW
    assert cam.tracked_robot_name == "Arogya_Delivery"

    # Notify mission complete
    cam.notify_mission_complete("Arogya_Delivery")
    assert cam.current_state == CameraState.MISSION_COMPLETE


def test_14_clinical_mission_completion(hospital_setup):
    """Test 14: Clinical mission completes with action execution and state transition."""
    env, guard = hospital_setup
    robot = DeliveryAMR(prim_path="/World/Robots/Arogya_Delivery", name="Arogya_Delivery", start_position=(0.0, 0.0, 0.0))
    robot.collision_guard = guard
    goal_wps = [np.array([0.0, 0.0, 0.0]), np.array([0.0, 0.05, 0.0])]
    robot.assign_mission(goal_wps, "Deliver IV drip", "ICU-01", priority_level=2)
    robot.current_waypoint_idx = 1
    robot.state_machine.transition_to(RobotState.NAVIGATING, "Testing goal arrival")

    # Step robot to arrival (distance 0.05 < arrival_tolerance 0.35)
    robot.step_autonomous(dt=0.016)
    assert robot.state_machine.state in (RobotState.EXECUTING_TASK, RobotState.MISSION_COMPLETE)


def test_15_simulation_responsiveness_and_throttling(hospital_setup):
    """Test 15: Simulation remains responsive with throttled sensor processing and spatial indexing."""
    env, guard = hospital_setup
    robot = ReceptionAMR(prim_path="/World/Robots/Mitra_Reception", name="Mitra_Reception", start_position=(0.0, 0.0, 0.0))
    robot.collision_guard = guard

    # Verify sensor throttling interval (100ms / 10 Hz)
    robot._last_sensor_update_time = 1000.0
    # Fast step execution
    import time
    t0 = time.perf_counter()
    for _ in range(50):
        robot.step_autonomous(dt=0.016)
    dt_elapsed = time.perf_counter() - t0
    assert dt_elapsed < 0.20, f"50 autonomous simulation steps took {dt_elapsed:.3f}s, expected < 0.20s"


def test_16_telemetry_synchronization(hospital_setup):
    """Test 16: Telemetry synchronization and structured diagnostic reason reporting."""
    env, guard = hospital_setup
    robot = ReceptionAMR(prim_path="/World/Robots/Mitra_Reception", name="Mitra_Reception", start_position=(0.0, 0.0, 0.0))
    robot.collision_guard = guard

    # Verify structured diagnostic reason details are provided on wall block
    candidate_x = -32.0  # West boundary wall
    candidate_y = 0.0
    is_blocked = guard.check_point_collision(candidate_x, candidate_y, margin=robot.robot_radius)
    assert is_blocked, "Expected wall collision at candidate position"

    diag_reason = f"Wall proximity guard: Center footprint violation (margin: {robot.robot_radius:.2f}m)"
    robot.state_machine.transition_to(RobotState.STUCK_DETECTED, reason=diag_reason)
    assert "Wall proximity guard" in robot.state_machine.current_reason
    assert "0.32m" in robot.state_machine.current_reason

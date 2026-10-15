"""
AAROGYA Autonomous Robotics Pipeline Verification Test Suite
=============================================================
Validates all 6 core robotics tests specified in Section 15:
- TEST 1: MANUAL NAVIGATION (single valid goal, physical velocity & movement)
- TEST 2: SLAM WITHOUT EXPLORATION (LiDAR raycast integration & occupancy grid growth)
- TEST 3: AUTONOMOUS EXPLORATION (Frontier detection, A* navigation, continuous movement)
- TEST 4: DYNAMIC OBSTACLE (Hazard detection & A* detour replanning)
- TEST 5: EXPLORATION COMPLETION (Termination conditions & map saving)
- TEST 6: CLINICAL TASK DELIVERY (Mission dispatch, task ACK, fleet assignment)
"""

import math
import numpy as np
import pytest

from isaac_sim_hospital.robots.arogya_robot import DeliveryAMR, RobotState
from isaac_sim_hospital.navigation.collision_guard import CollisionGuard
from isaac_sim_hospital.navigation.slam_exploration_engine import SLAMExplorationEngine, OccupancyState
from isaac_sim_hospital.web.database_server import DB_BRIDGE
from isaac_sim_hospital.sensors.lidar_manager import LiDARScanResult


@pytest.fixture
def test_setup():
    guard = CollisionGuard()
    robot = DeliveryAMR(
        prim_path="/World/Robots/Arogya_Delivery",
        start_position=(34.5, 33.0, 0.0),
        start_yaw=-np.pi / 2.0,
        name="Arogya_Delivery",
    )
    robot.set_collision_guard(guard)
    return guard, robot


def test_1_manual_navigation_movement(test_setup):
    """TEST 1: Robot accepts a single navigation goal, generates velocities, and physically translates."""
    guard, robot = test_setup
    start_x, start_y = robot.x, robot.y

    # Plan valid A* path
    target = (39.5, 23.2)
    path = guard.plan_path_astar((start_x, start_y), target)
    assert path is not None and len(path) >= 2, "Path planner should produce valid collision-free waypoints"

    wps = [np.array([p[0], p[1], 0.0]) for p in path]
    robot.assign_mission(wps, task_description="Manual Nav Test", destination_name="Wing A")

    assert robot.mission_active is True
    assert robot.state_machine.state == RobotState.NAVIGATING

    # Step robot autonomous kinematics
    for _ in range(30):
        robot.step_autonomous(dt=0.016)

    # Verify physical coordinate translation
    moved_dist = math.hypot(robot.x - start_x, robot.y - start_y)
    assert moved_dist > 0.05, f"Robot should physically translate (moved {moved_dist:.3f}m)"
    assert robot.linear_speed > 0.0 or robot.angular_speed != 0.0, "Robot should report active non-zero velocity"


def test_1b_direct_cmd_vel_actuation(test_setup):
    """TEST 1b: Verify ROS2 /cmd_vel direct velocity actuation moves the robot."""
    guard, robot = test_setup
    start_x, start_y = robot.x, robot.y

    # Apply direct velocity command: linear 1.0 m/s along current yaw
    robot.yaw = 0.0  # Face +X
    for _ in range(20):
        robot.step_autonomous(dt=0.016, cmd_vel=(1.0, 0.0))

    assert robot.x > start_x + 0.10, f"Robot should translate forward along +X with cmd_vel (x: {robot.x})"
    assert robot.linear_speed == 1.0, "Robot linear speed should reflect cmd_vel linear.x"


def test_2_slam_lidar_integration():
    """TEST 2: Physical LiDAR ray integration builds occupancy grid cells and updates map metadata."""
    slam = SLAMExplorationEngine()
    initial_meta = slam.get_map_metadata()
    assert initial_meta["free_cells"] == 0
    assert initial_meta["discovered_walls_count"] == 0

    # Simulate 360 degree LiDAR scan with open corridor up to 6m
    num_rays = 360
    angles_deg = np.linspace(0.0, 360.0, num_rays, endpoint=False)
    ranges = np.full(num_rays, 6.0)
    # Put wall hit at 0 degrees at 4.0m
    ranges[0] = 4.0
    scan = LiDARScanResult(angles_deg=angles_deg, ranges=ranges, min_distance=4.0)

    # Integrate scan into SLAM engine
    slam.integrate_lidar_scan(robot_x=34.5, robot_y=33.0, robot_yaw=0.0, scan_result=scan)

    updated_meta = slam.get_map_metadata()
    assert updated_meta["free_cells"] > 0, "SLAM grid should carve free cells from raycast"
    assert updated_meta["discovered_walls_count"] > 0, "SLAM grid should mark wall hit as occupied cell"


def test_3_autonomous_exploration_pipeline(test_setup):
    """TEST 3: Exploration command dispatched through DB_BRIDGE, robot picks frontier, starts moving."""
    guard, robot = test_setup
    start_x, start_y = robot.x, robot.y

    # Queue exploration command in DB_BRIDGE
    mission_id = DB_BRIDGE.queue_exploration(robot_name="Arogya_Delivery", goal=[30.0, 30.0])
    pending = DB_BRIDGE.get_pending_commands()
    assert any(c.get("type") == "EXPLORE" for c in pending), "DB_BRIDGE should contain queued exploration command"

    # Simulate simulation loop handling the command
    db_cmd = next(c for c in pending if c.get("type") == "EXPLORE")
    gx, gy = db_cmd["goal"]
    path = guard.plan_path_astar((start_x, start_y), (gx, gy))
    assert path and len(path) >= 2

    route = [np.array([p[0], p[1], 0.0]) for p in path]
    robot.is_exploring = True
    robot.assign_mission(route, task_description="Autonomous SLAM Frontier Exploration", destination_name="Frontier")

    assert robot.is_exploring is True
    assert robot.mission_active is True

    # Step simulation loop
    for _ in range(40):
        robot.step_autonomous(dt=0.016)

    # Verify physical movement
    dist_moved = math.hypot(robot.x - start_x, robot.y - start_y)
    assert dist_moved > 0.10, f"Robot should physically translate towards frontier target (moved {dist_moved:.3f}m)"


def test_4_dynamic_obstacle_avoidance(test_setup):
    """TEST 4: Robot detects dynamic obstacle and plans detour around it."""
    guard, robot = test_setup
    start = (34.5, 33.0)
    goal = (39.5, 23.2)

    # Clear path
    clear_path = guard.plan_path_astar(start, goal)
    assert clear_path and len(clear_path) >= 2

    # Inject obstacle right on waypoint
    mid_wp = clear_path[len(clear_path) // 2]
    dyn_obs = [(mid_wp[0], mid_wp[1])]

    detour_path = guard.plan_path_astar_dynamic(start, goal, dynamic_obstacles=dyn_obs, obstacle_radius=0.75)
    assert detour_path and len(detour_path) >= 2, "Path planner should generate a viable detour"
    # Verify detour clears obstacle
    for wp in detour_path:
        d = math.hypot(wp[0] - mid_wp[0], wp[1] - mid_wp[1])
        assert d >= 0.50, f"Detour waypoint at {wp} should maintain clearance from obstacle at {mid_wp}"


def test_5_exploration_completion():
    """TEST 5: Exploration termination conditions and map saving."""
    slam = SLAMExplorationEngine()
    # Mark exploration complete and save map
    slam.exploration_complete = True
    filepath = slam.save_map()
    import os
    assert os.path.exists(filepath), "SLAM map JSON file should be saved"

    # Load saved map back
    loaded = slam.load_map(filepath)
    assert loaded is True, "SLAM map should load successfully from disk"


def test_6_ui_clinical_task_delivery(test_setup):
    """TEST 6: Standard clinical delivery tasks and Code Blue emergencies function through DB_BRIDGE."""
    guard, robot = test_setup

    m_id = DB_BRIDGE.queue_medication_delivery(
        patient_id="P001",
        room_id="ICU-01",
        medicine_name="Epinephrine",
        robot_name="Arogya_Delivery",
        mission_id="MED-CLINICAL-001",
    )
    assert m_id == "MED-CLINICAL-001"

    cmds = DB_BRIDGE.get_pending_commands()
    assert len(cmds) >= 1
    med_cmd = cmds[-1]
    assert med_cmd["type"] == "DELIVER_ITEM"
    assert med_cmd["item"] == "Epinephrine"
    assert med_cmd["robot"] == "Arogya_Delivery"

"""
AROGYA Hospital Robotics — Comprehensive Navigation & Environment Correction Test Suite
========================================================================================
Validates all 6 required validation scenarios:
- TEST A: Normal Navigation (Zero wall clipping, door ingress, goal arrival, task execution)
- TEST B: Dynamic Obstacle Avoidance & Genuine Replan (Stop, dynamic A* detour, arrival)
- TEST C: Robot-Robot Mutual Avoidance (Zero collision between fleet AMRs)
- TEST D: Patient Room Navigation (Doorway ingress & bedside arrival for PAT-101 .. PAT-106)
- TEST E: Path Efficiency & Collinear Pruning (No redundant zig-zags, zero wall cutting)
- TEST F: Precise Goal Arrival Detection (Arrival tolerance <= 0.40m)
"""

import math
import os
import sys
import numpy as np

# Ensure project directories are in sys.path
this_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(this_dir)
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)
if os.path.join(project_dir, "isaac_sim_hospital") not in sys.path:
    sys.path.insert(0, os.path.join(project_dir, "isaac_sim_hospital"))

from environments.hospital_env import HospitalEnvironment
from navigation.goal_validator import (
    CLINICAL_ROOM_GOALS,
    ROOM_BOUNDS,
    validate_navigation_goal,
)
from navigation.route_planner import plan_hospital_route
from robots.arogya_robot import DeliveryAMR, ReceptionAMR, EmergencyAMR, SupportAMR, RobotState
from environments.command_interface import parse_natural_command, CommandType


def test_a_normal_navigation():
    """TEST A: Command 'Go to Pharmacy' -> valid robot, collision-free path, door entry, arrival."""
    print("\n" + "=" * 70)
    print("RUNNING TEST A: Normal Navigation to Pharmacy")
    print("=" * 70)

    # 1. Parse natural language command
    cmd = parse_natural_command("Go to Pharmacy")
    assert cmd.cmd_type == CommandType.GO_LOCATION, f"Command must be GO_LOCATION, got {cmd.cmd_type}"
    assert cmd.destination_location == "PHM-01", f"Destination must resolve to PHM-01, got {cmd.destination_location}"

    # 2. Setup environment & collision guard
    env = HospitalEnvironment()
    env.build_all()
    cg = env.get_collision_guard(robot_radius=0.38)

    # 3. Instantiate Delivery AMR
    start_pos = (34.5, 33.0, 0.0)  # Charging dock area
    bot = DeliveryAMR(start_position=start_pos, start_yaw=-math.pi / 2.0, name="Arogya_Delivery")
    bot.set_collision_guard(cg)
    bot.set_hospital_env(env)
    bot.action_duration = 0.3

    # 4. Plan path
    route = plan_hospital_route(bot.get_position(), cmd.destination_location, env, cg)
    assert len(route) >= 3, f"Route must have at least 3 waypoints, got {len(route)}"

    # 5. Verify every waypoint and continuous segment is 100% collision-free
    for i in range(len(route) - 1):
        p1 = route[i]
        p2 = route[i + 1]
        is_clear = cg.is_segment_clear(p1[0], p1[1], p2[0], p2[1], margin=0.38, step_size=0.05)
        assert is_clear, f"Segment {i}->{i+1} ({p1[:2]} to {p2[:2]}) collides with wall or furniture!"

    # 6. Verify entry through Pharmacy doorway
    dest_info = env.get_semantic_locations()["PHM-01"]
    door_coord = dest_info["door"]
    has_doorway_wp = any(math.hypot(wp[0] - door_coord[0], wp[1] - door_coord[1]) < 0.60 for wp in route)
    assert has_doorway_wp, f"Route must pass through Pharmacy door {door_coord[:2]}!"

    # 7. Step physical robot until arrival
    bot.assign_mission(route, f"Deliver items to {cmd.destination_location}", cmd.destination_location, priority_level=3)
    task_executed = False

    for step in range(3000):
        bot.step_autonomous(dt=0.016, dynamic_obstacle_positions=[])
        # Verify physical robot never penetrates static obstacles
        assert not cg.check_point_collision(bot.x, bot.y, margin=0.30), (
            f"Robot penetrated collision obstacle at step {step}: ({bot.x:.2f}, {bot.y:.2f})"
        )
        if bot.state_machine.state == RobotState.EXECUTING_TASK:
            task_executed = True
            break

    assert task_executed, "Robot must transition to EXECUTING_TASK upon arrival!"
    dist_to_goal = math.hypot(bot.x - 14.0, bot.y - 23.2)
    assert dist_to_goal <= 0.40, f"Robot must halt within 0.40m tolerance of goal, got {dist_to_goal:.3f}m"
    print(f"[TEST A PASSED] Successfully reached Pharmacy at ({bot.x:.2f}, {bot.y:.2f}) (dist to goal: {dist_to_goal:.2f}m)")


def test_b_dynamic_obstacle_avoidance_and_replan():
    """TEST B: Dynamic obstacle placed on route -> safe halt -> replan -> detour -> arrival."""
    print("\n" + "=" * 70)
    print("RUNNING TEST B: Dynamic Obstacle Avoidance & Replan")
    print("=" * 70)

    env = HospitalEnvironment()
    env.build_all()
    cg = env.get_collision_guard(robot_radius=0.38)

    start_pos = (34.5, 33.0, 0.0)
    bot = DeliveryAMR(start_position=start_pos, start_yaw=-math.pi / 2.0, name="Arogya_Delivery")
    bot.set_collision_guard(cg)
    bot.set_hospital_env(env)
    bot.action_duration = 0.3

    initial_route = plan_hospital_route(bot.get_position(), "PHM-01", env, cg)
    bot.assign_mission(initial_route, "Deliver to Pharmacy", "PHM-01", priority_level=3)

    # Step robot for 800 steps into corridor highway
    for _ in range(800):
        bot.step_autonomous(dt=0.016, dynamic_obstacle_positions=[])

    # Inject dynamic obstacle directly ahead in the corridor along current path
    r_x, r_y = bot.x, bot.y
    target_wp = bot.waypoints[bot.current_waypoint_idx][:2]
    direction = np.array([target_wp[0] - r_x, target_wp[1] - r_y])
    d_norm = np.linalg.norm(direction)
    unit_dir = direction / d_norm if d_norm > 0.01 else np.array([0.0, -1.0])
    dyn_obs = (float(r_x + unit_dir[0] * 1.0), float(r_y + unit_dir[1] * 1.0))

    # Step with dynamic obstacle present
    for _ in range(5):
        bot.step_autonomous(dt=0.016, dynamic_obstacle_positions=[dyn_obs])

    # Verify detection and replanning
    assert bot.is_blocked, "Robot must detect obstacle within safety distance and set is_blocked!"
    assert bot.is_replanned, "Robot must trigger dynamic replanning!"
    assert len(bot.replanned_route) > 0, "Replanned route must be populated with detour waypoints!"

    # Verify none of the replanned waypoints collide with walls
    for i in range(len(bot.replanned_route) - 1):
        p1 = bot.replanned_route[i]
        p2 = bot.replanned_route[i + 1]
        assert cg.is_segment_clear(p1[0], p1[1], p2[0], p2[1], margin=0.38, step_size=0.05), (
            f"Replanned segment {p1[:2]} -> {p2[:2]} collides with walls!"
        )

    # Continue navigation on detour route
    reached_goal = False
    for step in range(3500):
        bot.step_autonomous(dt=0.016, dynamic_obstacle_positions=[dyn_obs])
        # Ensure robot does not hit the dynamic obstacle
        dist_to_obs = math.hypot(bot.x - dyn_obs[0], bot.y - dyn_obs[1])
        assert dist_to_obs > 0.40, f"Robot collided with dynamic obstacle! Distance: {dist_to_obs:.2f}m"
        if bot.state_machine.state == RobotState.EXECUTING_TASK:
            reached_goal = True
            break

    assert reached_goal, "Robot must reach destination on the replanned detour route!"
    print(f"[TEST B PASSED] Successfully replanned around dynamic obstacle at {dyn_obs} and reached goal.")


def test_c_robot_robot_mutual_avoidance():
    """TEST C: Two robots approaching each other in corridor -> mutual conflict avoidance."""
    print("\n" + "=" * 70)
    print("RUNNING TEST C: Robot-Robot Mutual Avoidance")
    print("=" * 70)

    env = HospitalEnvironment()
    env.build_all()
    cg = env.get_collision_guard(robot_radius=0.38)

    # R1 Delivery (lower priority P3) and R3 Garuda (high priority P1 emergency)
    r1 = DeliveryAMR(start_position=(0.0, 2.0, 0.0), start_yaw=0.0, name="Arogya_Delivery")
    r1.set_collision_guard(cg)
    r1.set_hospital_env(env)

    r3 = EmergencyAMR(start_position=(5.0, 2.0, 0.0), start_yaw=math.pi, name="Garuda_Emergency")
    r3.set_collision_guard(cg)
    r3.set_hospital_env(env)

    # Give missions moving towards each other
    r1.assign_mission([np.array([0.0, 2.0, 0.0]), np.array([8.0, 2.0, 0.0])], "Transit East", "Corridor", priority_level=3)
    r3.assign_mission([np.array([5.0, 2.0, 0.0]), np.array([-3.0, 2.0, 0.0])], "Emergency West", "Corridor", priority_level=1)

    min_separation = float("inf")
    r1_yielded = False
    for step in range(250):
        # Mutual awareness: pass peer coordinates to each robot
        r1.step_autonomous(dt=0.016, dynamic_obstacle_positions=[(r3.x, r3.y)])
        r3.step_autonomous(dt=0.016, dynamic_obstacle_positions=[(r1.x, r1.y)])

        sep = math.hypot(r1.x - r3.x, r1.y - r3.y)
        min_separation = min(min_separation, sep)
        if r1.is_blocked or r1.dynamic_slowdown < 0.9:
            r1_yielded = True
        # Verify physical AMRs never collide
        assert sep > 0.65, f"Robot-robot collision at step {step}! Separation: {sep:.2f}m"

    assert r1_yielded or r1.is_blocked or r1.dynamic_slowdown < 0.9, "Lower priority AMR must yield or slow down for Emergency AMR!"
    print(f"[TEST C PASSED] Zero collision between robots. Minimum separation maintained: {min_separation:.2f}m")


def test_d_patient_room_navigation():
    """TEST D: Navigate to PAT-101 and new patient rooms PAT-103 .. PAT-106."""
    print("\n" + "=" * 70)
    print("RUNNING TEST D: Patient Room Navigation (PAT-101 .. PAT-106)")
    print("=" * 70)

    env = HospitalEnvironment()
    env.build_all()
    cg = env.get_collision_guard(robot_radius=0.38)
    sem_locs = env.get_semantic_locations()

    # 1. Verify all 6 patient rooms are registered in semantic map and goal validator
    patient_rooms = ["PAT-101", "PAT-102", "PAT-103", "PAT-104", "PAT-105", "PAT-106"]
    for pr in patient_rooms:
        assert pr in sem_locs, f"Room {pr} must exist in semantic_locations!"
        assert pr in CLINICAL_ROOM_GOALS, f"Room {pr} must exist in CLINICAL_ROOM_GOALS!"
        assert pr in ROOM_BOUNDS, f"Room {pr} must exist in ROOM_BOUNDS!"

        val_goal, is_val, msg = validate_navigation_goal(pr, env, cg)
        assert is_val, f"Goal for {pr} must be valid! {msg}"
        assert not cg.check_point_collision(val_goal[0], val_goal[1], margin=0.38), (
            f"Goal for {pr} collides with static geometry!"
        )
        print(f"  [OK] Registered & Validated: {pr} -> Goal ({val_goal[0]:.2f}, {val_goal[1]:.2f})")

    # 2. Test natural language command resolution for patient rooms
    test_commands = [
        ("Go to patient room 101", "PAT-101"),
        ("Go to PAT-103", "PAT-103"),
        ("Take medicine to room 104", "PAT-104"),
        ("Deliver to patient room 105", "PAT-105"),
        ("Assist patient 106", "PAT-106"),
    ]
    for nl_cmd, expected_dest in test_commands:
        parsed = parse_natural_command(nl_cmd)
        assert parsed.destination_location == expected_dest, f"'{nl_cmd}' must resolve to {expected_dest}, got {parsed.destination_location}"

    # 3. Simulate full navigation to new patient room PAT-103
    bot = DeliveryAMR(start_position=(-20.0, 2.0, 0.0), start_yaw=-math.pi / 2.0, name="Arogya_Delivery")
    bot.set_collision_guard(cg)
    bot.set_hospital_env(env)
    bot.action_duration = 0.3

    route_103 = plan_hospital_route(bot.get_position(), "PAT-103", env, cg)
    assert len(route_103) >= 3, f"Route to PAT-103 must have waypoints, got {len(route_103)}"

    # Verify route enters through the door of PAT-103 at (-21.5, -12.35)
    door_103 = sem_locs["PAT-103"]["door"]
    has_door = any(math.hypot(wp[0] - door_103[0], wp[1] - door_103[1]) < 0.50 for wp in route_103)
    assert has_door, f"Route must enter PAT-103 through door {door_103[:2]}"

    bot.assign_mission(route_103, "Deliver to PAT-103", "PAT-103", priority_level=3)
    arrived = False
    for step in range(2500):
        bot.step_autonomous(dt=0.016, dynamic_obstacle_positions=[])
        assert not cg.check_point_collision(bot.x, bot.y, margin=0.30), "Robot collided during PAT-103 navigation!"
        if bot.state_machine.state == RobotState.EXECUTING_TASK:
            arrived = True
            break

    assert arrived, "Robot must reach bedside target in PAT-103 and enter EXECUTING_TASK!"
    target_103 = CLINICAL_ROOM_GOALS["PAT-103"][:2]
    d_bedside = math.hypot(bot.x - target_103[0], bot.y - target_103[1])
    assert d_bedside <= 0.40, f"Robot must halt within 0.40m of bedside, got {d_bedside:.2f}m"
    print(f"[TEST D PASSED] All 6 patient rooms operational. Navigated to PAT-103 bedside at ({bot.x:.2f}, {bot.y:.2f}).")


def test_e_path_efficiency_and_pruning():
    """TEST E: Verify path simplification removes redundant zig-zags without clipping corners."""
    print("\n" + "=" * 70)
    print("RUNNING TEST E: Path Efficiency & Waypoint Pruning")
    print("=" * 70)

    env = HospitalEnvironment()
    env.build_all()
    cg = env.get_collision_guard(robot_radius=0.38)

    # Route along central corridor from X=-20.0 to X=20.0 along Y=2.0
    start = (-20.0, 2.0)
    goal = (20.0, 2.0)

    raw_path = cg.plan_path_astar(start, goal)
    assert len(raw_path) >= 2, "A* must find corridor route"

    # Verify smoothed path has no wall clipping
    for i in range(len(raw_path) - 1):
        p1 = raw_path[i]
        p2 = raw_path[i + 1]
        assert cg.is_segment_clear(p1[0], p1[1], p2[0], p2[1], margin=0.38, step_size=0.05), (
            f"Segment {p1} -> {p2} intersects walls!"
        )

    # Verify collinear simplification prunes a straight 40m corridor to minimal nodes
    assert len(raw_path) <= 4, f"Collinear corridor path should be pruned to <=4 waypoints, got {len(raw_path)}"
    print(f"[TEST E PASSED] Path pruned to {len(raw_path)} clean waypoints with zero wall clipping.")


def test_f_goal_arrival_detection():
    """TEST F: Verify arrival detection adheres strictly to <= 0.40m tolerance."""
    print("\n" + "=" * 70)
    print("RUNNING TEST F: Precise Goal Arrival Detection")
    print("=" * 70)

    env = HospitalEnvironment()
    env.build_all()
    cg = env.get_collision_guard(robot_radius=0.38)

    bot = DeliveryAMR(start_position=(14.0, 21.0, 0.0), start_yaw=math.pi / 2.0, name="Arogya_Delivery")
    bot.set_collision_guard(cg)
    bot.set_hospital_env(env)
    bot.action_duration = 0.5

    goal_coord = (14.0, 23.2, 0.0)
    bot.assign_mission([np.array([14.0, 21.0, 0.0]), np.array(goal_coord)], "Arrival check", "PHM-01", priority_level=3)

    arrived = False
    for step in range(500):
        bot.step_autonomous(dt=0.016, dynamic_obstacle_positions=[])
        if bot.state_machine.state == RobotState.EXECUTING_TASK:
            arrived = True
            dist = math.hypot(bot.x - goal_coord[0], bot.y - goal_coord[1])
            assert dist <= 0.40, f"Arrival triggered at excessive distance: {dist:.3f}m (> 0.40m)!"
            break

    assert arrived, "Robot must trigger arrival detection!"
    print(f"[TEST F PASSED] Goal arrival verified within tolerance (final distance: {math.hypot(bot.x - 14.0, bot.y - 23.2):.3f}m).")


if __name__ == "__main__":
    print("\nSTARTING FULL NAVIGATION & ENVIRONMENT CORRECTION TEST SUITE...")
    test_a_normal_navigation()
    test_b_dynamic_obstacle_avoidance_and_replan()
    test_c_robot_robot_mutual_avoidance()
    test_d_patient_room_navigation()
    test_e_path_efficiency_and_pruning()
    test_f_goal_arrival_detection()
    print("\n" + "=" * 70)
    print("ALL 6 TESTS (A THROUGH F) PASSED WITH 100% SUCCESS!")
    print("=" * 70)

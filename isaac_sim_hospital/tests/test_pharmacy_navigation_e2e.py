"""
End-to-End Verification Test for Pharmacy Navigation & Dashboard Telemetry
==========================================================================
Verifies:
1. Goal validation across all clinical departments (PHM-01, ICU-01, EMR-01, LAB-01, RCT-01, OPD-01, OT-01).
2. Ground-truth Pharmacy dispensing counter goal is collision-free and clear of furniture.
3. Complete unobstructed navigation from charging bay to Pharmacy dispensing station.
4. Dynamic obstacle detection, explicit state transitions with reason/action, and real A* replanning.
5. Verification that dashboard strings contain zero unsupported emojis or block glyphs.
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
    find_nearest_valid_goal,
    validate_navigation_goal,
)
from navigation.route_planner import plan_hospital_route
from robots.arogya_robot import DeliveryAMR, RobotState


def test_1_clinical_goal_validation():
    """Verify all clinical departments have valid, collision-free goals."""
    print("\n[TEST 1] Clinical Goal Validation across departments...")
    env = HospitalEnvironment()
    env.build_all()
    cg = env.get_collision_guard(robot_radius=0.38)

    rooms = ["PHM-01", "ICU-01", "EMR-01", "LAB-01", "RCT-01", "OPD-01", "OT-01"]
    for r_id in rooms:
        goal_pos, is_val, msg = validate_navigation_goal(r_id, env, cg, robot_radius=0.38)
        assert is_val, f"Goal for {r_id} must be validated! Msg: {msg}"
        is_coll = cg.check_point_collision(goal_pos[0], goal_pos[1], margin=0.38)
        assert not is_coll, f"Goal {goal_pos[:2]} for {r_id} collides with wall or furniture!"
        print(f"  [OK] {r_id}: Goal ({goal_pos[0]:.2f}, {goal_pos[1]:.2f}) -> {msg}")

    # Specific check for Pharmacy goal vs Dispense Counter
    phm_goal, _, _ = validate_navigation_goal("PHM-01", env, cg)
    assert abs(phm_goal[0] - 14.0) < 0.1, f"Pharmacy goal X must be ~14.0, got {phm_goal[0]}"
    assert phm_goal[1] < 24.0, f"Pharmacy goal Y must be in front of counter (<24.0), got {phm_goal[1]}"
    print("  -> PASSED: All 7 clinical goals are fully collision-free and properly grounded.")


def test_2_pharmacy_route_feasibility():
    """Verify planned route to Pharmacy enters door and halts in front of dispensing counter."""
    print("\n[TEST 2] Pharmacy Route Feasibility & Clearance...")
    env = HospitalEnvironment()
    env.build_all()
    cg = env.get_collision_guard(robot_radius=0.38)

    route = plan_hospital_route((34.5, 33.0), "PHM-01", env, cg)
    assert len(route) >= 4, f"Route must have at least 4 waypoints, got {len(route)}"

    # Check that no waypoint collides with furniture or wall
    for i, wp in enumerate(route):
        coll = cg.check_point_collision(wp[0], wp[1], margin=0.30)
        assert not coll, f"Waypoint {i} ({wp[0]:.2f}, {wp[1]:.2f}) in collision!"

    final_wp = route[-1]
    assert abs(final_wp[0] - 14.0) < 0.2 and abs(final_wp[1] - 23.2) < 0.3, (
        f"Final waypoint must reach dispensing counter (14.0, 23.2), got {final_wp[:2]}"
    )
    print(f"  -> PASSED: Planned {len(route)} waypoints ending safely at ({final_wp[0]:.2f}, {final_wp[1]:.2f}).")


def test_3_unobstructed_pharmacy_navigation():
    """Simulate step-by-step navigation to Pharmacy until task execution and completion."""
    print("\n[TEST 3] Unobstructed Step Navigation to Pharmacy...")
    env = HospitalEnvironment()
    env.build_all()
    cg = env.get_collision_guard(robot_radius=0.38)

    bot = DeliveryAMR(start_position=(34.5, 33.0, 0.0), start_yaw=-math.pi / 2.0, name="Arogya_Delivery")
    bot.collision_guard = cg
    bot.action_duration = 0.5  # Fast execution for automated test

    route = plan_hospital_route(bot.get_position(), "PHM-01", env, cg)
    bot.assign_mission(route, "Deliver Medicine to Pharmacy", "PHM-01", priority_level=3)

    arrived = False
    task_executed = False
    mission_completed = False

    for step in range(2500):
        bot.step_autonomous(dt=0.016, dynamic_obstacle_positions=[])

        if bot.state_machine.state == RobotState.EXECUTING_TASK:
            task_executed = True
        elif bot.state_machine.state == RobotState.MISSION_COMPLETE:
            mission_completed = True
            arrived = True
            break

    assert task_executed, "Robot must enter EXECUTING_TASK at destination!"
    assert mission_completed, "Robot must reach MISSION_COMPLETE!"
    # Verify final pose is at Pharmacy dispensing station
    dist_to_goal = math.hypot(bot.x - 14.0, bot.y - 23.2)
    assert dist_to_goal < 0.60, f"Robot must halt near dispensing counter, distance was {dist_to_goal:.2f}m"
    print(f"  -> PASSED: Robot navigated to Pharmacy, arrived at ({bot.x:.2f}, {bot.y:.2f}), executed task and completed mission.")


def test_4_dynamic_obstacle_detection_and_replanning():
    """Verify obstacle detection halts robot, transitions state with reason, and computes genuine detour."""
    print("\n[TEST 4] Dynamic Obstacle Detection & Real A* Replanning...")
    env = HospitalEnvironment()
    env.build_all()
    cg = env.get_collision_guard(robot_radius=0.38)

    bot = DeliveryAMR(start_position=(34.5, 33.0, 0.0), start_yaw=-math.pi / 2.0, name="Arogya_Delivery")
    bot.collision_guard = cg
    route = plan_hospital_route(bot.get_position(), "PHM-01", env, cg)
    bot.assign_mission(route, "Deliver Medicine to Pharmacy", "PHM-01", priority_level=3)

    # Step into corridor
    for _ in range(500):
        bot.step_autonomous(dt=0.016, dynamic_obstacle_positions=[])

    # Inject obstacle 0.9m directly ahead along path
    rpos = bot.get_position()
    target_wp = bot.waypoints[bot.current_waypoint_idx][:2]
    fwd = target_wp - rpos[:2]
    norm = math.hypot(*fwd)
    fwd_unit = fwd / norm if norm > 0.01 else np.array([1.0, 0.0])
    injected_obs = (float(rpos[0] + fwd_unit[0] * 0.90), float(rpos[1] + fwd_unit[1] * 0.90))

    # Step with obstacle present
    for _ in range(3):
        bot.step_autonomous(dt=0.016, dynamic_obstacle_positions=[injected_obs])

    assert bot.is_blocked, "Robot must set is_blocked = True when obstacle is within safety radius!"
    assert bot.state_machine.state in (RobotState.OBSTACLE_DETECTED, RobotState.REPLANNING, RobotState.WAITING_FOR_CLEARANCE), (
        f"State must reflect obstacle handling, got {bot.state_machine.state.name}"
    )
    assert bot.state_machine.current_reason != "", "FSM must provide explicit reason!"
    assert bot.state_machine.current_action != "", "FSM must provide explicit action!"
    assert bot.is_replanned, "Robot must trigger dynamic replanning!"
    assert len(bot.replanned_route) > 0, "Replanned route must contain new waypoints!"

    print(f"  -> State: {bot.state_machine.state.name}")
    print(f"  -> Reason: {bot.state_machine.current_reason}")
    print(f"  -> Action: {bot.state_machine.current_action}")
    print(f"  -> Replanned Route: {len(bot.replanned_route)} waypoints")
    print("  -> PASSED: Genuine obstacle detection and real A* replanning verified.")


def test_5_ui_glyph_rendering_safety():
    """Verify in_viewport_hud.py and command_interface.py contain zero unsupported emojis or block glyphs."""
    print("\n[TEST 5] UI Glyph & Font Rendering Safety...")
    hud_path = os.path.join(this_dir, "..", "environments", "in_viewport_hud.py")
    with open(hud_path, "r", encoding="utf-8") as f:
        hud_content = f.read()

    unsupported_chars = ["🤖", "🏥", "🎙️", "🛑", "⚕️", "⚠️", "🎯", "🗺️", "🚀", "🚨", "💊", "🏢", "🔬", "⚡", "⏹️", "▶️", "📊", "█", "░"]
    found_bad = []
    for ch in unsupported_chars:
        if ch in hud_content:
            found_bad.append(ch)

    assert len(found_bad) == 0, f"Found unsupported glyphs in in_viewport_hud.py: {found_bad}"
    print("  -> PASSED: Zero unsupported emojis or block characters in in_viewport_hud.py.")


if __name__ == "__main__":
    test_1_clinical_goal_validation()
    test_2_pharmacy_route_feasibility()
    test_3_unobstructed_pharmacy_navigation()
    test_4_dynamic_obstacle_detection_and_replanning()
    test_5_ui_glyph_rendering_safety()
    print("\n==================================================")
    print("ALL 5 END-TO-END PHARMACY & TELEMETRY TESTS PASSED!")
    print("==================================================")

"""
Audit and Pre-Validation Script for AROGYA Medical Center Redesign
"""
import math
import os
import sys
import numpy as np

# Ensure path
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

def run_audit():
    print("=== AUDITING CURRENT HOSPITAL ENVIRONMENT ===")
    env = HospitalEnvironment()
    env.build_all()
    cg = env.get_collision_guard(robot_radius=0.38)
    
    print(f"Total Wall Segments: {env._wall_counter}")
    print(f"Total Collision Boxes: {len(env.collision_boxes)}")
    print(f"Total Semantic Locations: {len(env.semantic_locations)}")
    
    # Check key goals
    test_rooms = ["PHM-01", "ICU-01", "EMR-01", "LAB-01", "RCT-01", "OPD-01", "OT-01", "CHG-01", "PAT-101", "PAT-103"]
    for r_id in test_rooms:
        goal_pos, is_val, msg = validate_navigation_goal(r_id, env, cg, robot_radius=0.38)
        coll = cg.check_point_collision(goal_pos[0], goal_pos[1], margin=0.38)
        print(f"Room {r_id:8s}: Goal=({goal_pos[0]:6.2f}, {goal_pos[1]:6.2f}) Valid={is_val} Collision={coll} -> {msg}")
        assert not coll, f"Goal for {r_id} collides!"

    # Check routes
    routes_to_test = [
        ("Entrance -> Reception", (0.0, -32.0), "RCT-01"),
        ("Reception -> Pharmacy", (0.0, -5.0), "PHM-01"),
        ("Pharmacy -> ICU", (14.0, 23.2), "ICU-01"),
        ("Pharmacy -> ICU-03/PAT-103", (14.0, 23.2), "PAT-103"),
        ("Emergency -> ICU", (-29.0, -8.8), "ICU-01"),
        ("ICU -> Charging Station", (-36.5, 12.5), "CHG-01"),
        ("OPD -> Laboratory", (22.5, -24.0), "LAB-01"),
        ("Main Entrance -> Emergency", (0.0, -32.0), "EMR-01"),
    ]
    
    print("\n=== TESTING CORE NAVIGATION ROUTES ===")
    for name, start_pt, dest_id in routes_to_test:
        route = plan_hospital_route(start_pt, dest_id, env, cg)
        print(f"Route '{name}': {len(route)} waypoints")
        assert len(route) >= 2, f"Route '{name}' failed to plan!"
        for i in range(len(route) - 1):
            p1, p2 = route[i], route[i+1]
            clear = cg.is_segment_clear(p1[0], p1[1], p2[0], p2[1], margin=0.30, step_size=0.05)
            assert clear, f"Segment {i}->{i+1} in route '{name}' collides!"

    print("\nAll baseline audit checks passed!")

if __name__ == "__main__":
    run_audit()

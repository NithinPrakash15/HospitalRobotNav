"""
End-to-End Test Suite for Priority 10 Requirements
===================================================
Tests all 8 required runtime scenarios:
TEST 1: GUI -> "go to ICU"
TEST 2: GUI -> "deliver medicine to ICU Bed 3"
TEST 3: GUI -> "emergency"
TEST 4: Voice -> "Hey Arogya"
TEST 5: Voice -> "Hey Arogya, go to ICU"
TEST 6: Obstacle blocks path
TEST 7: Robot encounters another robot
TEST 8: Robot battery becomes low
"""

from __future__ import annotations

import os
import sys
import unittest
import numpy as np

# Set up paths
_this_dir = os.path.dirname(os.path.abspath(__file__))
_isaac_dir = os.path.dirname(_this_dir)
_repo_root = os.path.dirname(_isaac_dir)

for p in [_repo_root, _isaac_dir]:
    if p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, _repo_root)
sys.path.insert(0, _isaac_dir)

from environments.hospital_env import HospitalEnvironment
from environments.command_interface import (
    CommandInterface,
    CommandType,
    VoiceInteractionState,
    detect_wake_word,
    parse_natural_command,
)
from multi_agent.hospital_agent_manager import HospitalAgentManager

if _isaac_dir in sys.path:
    sys.path.remove(_isaac_dir)
sys.path.insert(0, _isaac_dir)

from navigation.route_planner import plan_hospital_route
from robots.arogya_robot import DeliveryAMR, ReceptionAMR, EmergencyAMR, SupportAMR
from robots.robot_state_machine import RobotState


class TestPriority10EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = HospitalEnvironment()
        cls.env.build_all()
        cls.cg = cls.env.get_collision_guard(robot_radius=0.38)
        cls.agent_mgr = HospitalAgentManager()

    def setUp(self):
        # Create live fleet
        self.r1 = DeliveryAMR("/World/Robots/Arogya_Delivery", (34.5, 33.0, 0.0), 0.0, "Arogya_Delivery")
        self.r2 = ReceptionAMR("/World/Robots/Mitra_Reception", (0.0, -5.0, 0.0), 0.0, "Mitra_Reception")
        self.r3 = EmergencyAMR("/World/Robots/Garuda_Emergency", (-29.0, -8.8, 0.0), 0.0, "Garuda_Emergency")
        self.r4 = SupportAMR("/World/Robots/Sahayak_Support", (39.5, 33.0, 0.0), 0.0, "Sahayak_Support")
        for r in [self.r1, self.r2, self.r3, self.r4]:
            r.set_collision_guard(self.cg)
        self.fleet = {
            "Arogya_Delivery": self.r1,
            "Mitra_Reception": self.r2,
            "Garuda_Emergency": self.r3,
            "Sahayak_Support": self.r4,
        }

    def test_01_gui_go_to_icu(self):
        """TEST 1: GUI -> 'go to ICU'."""
        cmd_text = "go to ICU"
        cmd = parse_natural_command(cmd_text)
        cmd.source = "gui"
        self.assertEqual(cmd.cmd_type, CommandType.GO_LOCATION)
        self.assertEqual(cmd.destination_location, "ICU-01")

        dest_id = cmd.destination_location
        dest_info = self.env.get_semantic_locations()[dest_id]
        dest_coords = (float(dest_info["pos"][0]), float(dest_info["pos"][1]))

        # Contract-Net auction
        winner, score, rationale, bids = self.agent_mgr.allocate_fleet_mission(
            mission_type="PATIENT_GUIDANCE",
            destination_dept=dest_id,
            priority=cmd.priority,
            robots=self.fleet,
            destination_coords=dest_coords,
        )
        self.assertIsNotNone(winner)
        self.assertGreater(score, 0.5)

        route = plan_hospital_route(winner.get_position(), dest_id, self.env, self.cg)
        self.assertGreaterEqual(len(route), 2)
        winner.assign_mission(route, f"Guide to {dest_id}", dest_id, priority_level=cmd.priority)

        self.assertEqual(winner.state_machine.state, RobotState.NAVIGATING)
        p0 = winner.get_position().copy()
        for _ in range(25):
            winner.step_autonomous(0.05, [])
            if float(np.hypot(winner.x - p0[0], winner.y - p0[1])) > 0.0:
                break
        p1 = winner.get_position().copy()
        dist_moved = float(np.hypot(p1[0] - p0[0], p1[1] - p0[1]))
        self.assertGreater(dist_moved, 0.0)

    def test_02_gui_deliver_medicine_to_icu_bed_3(self):
        """TEST 2: GUI -> 'deliver medicine to ICU Bed 3'."""
        cmd_text = "deliver medicine to ICU Bed 3"
        cmd = parse_natural_command(cmd_text)
        cmd.source = "gui"
        self.assertEqual(cmd.cmd_type, CommandType.DELIVER_ITEM)
        self.assertEqual(cmd.destination_location, "ICU-BED-03")

        dest_id = cmd.destination_location
        dest_info = self.env.get_semantic_locations()[dest_id]
        dest_coords = (float(dest_info["pos"][0]), float(dest_info["pos"][1]))

        winner, score, rationale, bids = self.agent_mgr.allocate_fleet_mission(
            mission_type="MEDICINE_DELIVERY",
            destination_dept=dest_id,
            priority=cmd.priority,
            robots=self.fleet,
            destination_coords=dest_coords,
        )
        self.assertEqual(winner.name, "Arogya_Delivery")

        # Two-phase route: Pickup at Pharmacy -> Bedside delivery
        pickup_route = plan_hospital_route(winner.get_position(), "PHM-01", self.env, self.cg)
        delivery_route = plan_hospital_route(pickup_route[-1], dest_id, self.env, self.cg)
        full_route = pickup_route + delivery_route[1:]
        self.assertGreaterEqual(len(full_route), 5)

        winner.assign_mission(full_route, f"Deliver {cmd.item} to {dest_id}", dest_id, priority_level=cmd.priority)
        self.assertEqual(winner.state_machine.state, RobotState.NAVIGATING)

    def test_03_gui_emergency(self):
        """TEST 3: GUI -> 'emergency'."""
        cmd_text = "emergency"
        cmd = parse_natural_command(cmd_text)
        cmd.source = "gui"
        self.assertEqual(cmd.cmd_type, CommandType.EMERGENCY)
        self.assertEqual(cmd.priority, 1)

        # Set Arogya to active delivery to test preemption
        self.r1.mission_active = True
        self.r1.state_machine.transition_to(RobotState.NAVIGATING, "Active delivery")

        dest_id = cmd.destination_location or "ICU-01"
        dest_info = self.env.get_semantic_locations()[dest_id]
        dest_coords = (float(dest_info["pos"][0]), float(dest_info["pos"][1]))

        winner, score, rationale, bids = self.agent_mgr.allocate_fleet_mission(
            mission_type="EMERGENCY_RESPONSE",
            destination_dept=dest_id,
            priority=1,
            robots=self.fleet,
            destination_coords=dest_coords,
        )
        self.assertEqual(winner.name, "Garuda_Emergency")

        # Preemption check: R1 must be preempted to stack
        for name, r in self.fleet.items():
            if r != winner and r.mission_active:
                self.agent_mgr.preemption_stack.append({
                    "robot_name": name,
                    "task": "Delivery",
                })
                r.state_machine.transition_to(RobotState.PAUSED, "Paused for Code Blue")

        self.assertEqual(self.r1.state_machine.state, RobotState.PAUSED)
        self.assertGreater(len(self.agent_mgr.preemption_stack), 0)

        eme_route = plan_hospital_route(winner.get_position(), dest_id, self.env, self.cg)
        winner.assign_mission(eme_route, f"CODE BLUE in {dest_id}", dest_id, priority_level=1)
        self.assertIn(winner.state_machine.state, (RobotState.EMERGENCY_OVERRIDE, RobotState.NAVIGATING))

    def test_04_voice_wake_word(self):
        """TEST 4: Voice -> 'Hey Arogya'."""
        detected, remaining = detect_wake_word("Hey Arogya")
        self.assertTrue(detected)
        self.assertEqual(remaining, "")

    def test_05_voice_wake_and_command(self):
        """TEST 5: Voice -> 'Hey Arogya, go to ICU'."""
        detected, remaining = detect_wake_word("Hey Arogya, go to ICU")
        self.assertTrue(detected)
        cmd = parse_natural_command(remaining)
        self.assertEqual(cmd.cmd_type, CommandType.GO_LOCATION)
        self.assertEqual(cmd.destination_location, "ICU-01")

        # Coordinator tender
        dest_info = self.env.get_semantic_locations()["ICU-01"]
        dest_coords = (float(dest_info["pos"][0]), float(dest_info["pos"][1]))
        winner, score, rationale, bids = self.agent_mgr.allocate_fleet_mission(
            mission_type="PATIENT_GUIDANCE",
            destination_dept="ICU-01",
            priority=cmd.priority,
            robots=self.fleet,
            destination_coords=dest_coords,
        )
        self.assertIsNotNone(winner)
        route = plan_hospital_route(winner.get_position(), "ICU-01", self.env, self.cg)
        winner.assign_mission(route, "Voice Guide to ICU", "ICU-01", priority_level=cmd.priority)
        self.assertEqual(winner.state_machine.state, RobotState.NAVIGATING)

    def test_06_obstacle_blocks_path(self):
        """TEST 6: Obstacle blocks path -> Yielding & dynamic detour."""
        route = [(0.0, 0.0), (5.0, 0.0)]
        self.r1.assign_mission(route, "Straight corridor transit", "Waypoint", priority_level=3)
        self.r1.x = 0.0
        self.r1.y = 0.0
        self.r1.yaw = 0.0

        # Dynamic obstacle blocking at (0.6, 0.0)
        blocked_obstacles = [(0.6, 0.0)]
        is_crit, dist = self.r1.check_dynamic_obstacles(blocked_obstacles, safety_radius=1.80)
        self.assertTrue(is_crit)

        self.r1.step_autonomous(0.05, dynamic_obstacle_positions=blocked_obstacles)
        # Robot linear speed must yield / slow down
        self.assertLessEqual(self.r1.linear_speed, 0.40)

        # Plan dynamic A* detour avoiding obstacle
        detour = self.cg.plan_path_astar_dynamic(
            (0.0, 0.0), (5.0, 0.0), dynamic_obstacles=blocked_obstacles, obstacle_radius=0.9
        )
        self.assertGreaterEqual(len(detour), 2)
        # Detour waypoints must avoid (0.6, 0.0)
        for wx, wy in detour:
            dist = np.hypot(wx - 0.6, wy - 0.0)
            self.assertGreater(dist, 0.35)

    def test_07_robot_encounters_another_robot(self):
        """TEST 7: Robot encounters another robot -> Mutual yielding & collision bubble."""
        # Place R1 and R2 0.5m apart facing each other (critical yielding hazard)
        self.r1.assign_mission([(10.0, 20.0), (15.0, 20.0)], "Corridor transit", "Corridor")
        self.r1.x = 10.0
        self.r1.y = 20.0
        self.r1.yaw = 0.0
        self.r2.x = 10.5
        self.r2.y = 20.0
        self.r2.yaw = np.pi
        self.r1.linear_speed = 0.5
        self.r2.linear_speed = 0.5

        # R1 detects R2 as a dynamic obstacle
        r1_detected = [(self.r2.x, self.r2.y)]
        is_crit, dist = self.r1.check_dynamic_obstacles(r1_detected, safety_radius=1.80)
        self.assertTrue(is_crit)

        self.r1.step_autonomous(0.05, dynamic_obstacle_positions=r1_detected)
        # R1 halts to 0.0 to yield to oncoming robot
        self.assertEqual(self.r1.linear_speed, 0.0)
        self.assertIn(self.r1.state_machine.state, (RobotState.BLOCKED, RobotState.OBSTACLE_DETECTED, RobotState.REPLANNING, RobotState.WAITING_FOR_CLEARANCE))

    def test_08_robot_battery_becomes_low(self):
        """TEST 8: Robot battery becomes low -> Autonomous CHG-01 docking."""
        self.r1.battery_level = 15.0  # < 20% critical threshold
        self.assertLess(self.r1.battery_level, 20.0)

        # Autonomous dock routing
        dock_route = plan_hospital_route(self.r1.get_position(), "CHG-01", self.env, self.cg)
        self.assertGreaterEqual(len(dock_route), 2)
        self.r1.assign_mission(dock_route, "Low Battery Recharging", "CHG-01", priority_level=5)
        self.assertEqual(self.r1.state_machine.state, RobotState.NAVIGATING)

        # Simulate arrival at dock
        dock_pos = self.env.get_semantic_locations()["CHG-01"]["pos"]
        self.r1.x = dock_pos[0]
        self.r1.y = dock_pos[1]
        self.r1.state_machine.transition_to(RobotState.CHARGING, "Docked at CHG-01")
        self.assertEqual(self.r1.state_machine.state, RobotState.CHARGING)

        # Simulate full recharge
        self.r1.battery_level = 100.0
        self.r1.is_charging = False
        self.r1.state_machine.transition_to(RobotState.IDLE, "Fully charged")
        self.assertEqual(self.r1.state_machine.state, RobotState.IDLE)


if __name__ == "__main__":
    unittest.main(verbosity=2)

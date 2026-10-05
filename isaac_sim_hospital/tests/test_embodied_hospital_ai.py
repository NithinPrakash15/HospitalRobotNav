"""
Comprehensive Verification Test Suite for Embodied Hospital AI
==============================================================
Verifies all 6 core subsystems:
1. CollisionGuard & A* shortest path calculation
2. MissionUnderstander bilingual NLU reasoning (English + Hindi)
3. Multi-Agent Contract-Net Protocol bidding
4. Real-time Emergency Preemption & task resumption
5. RobotStateMachine operational transitions & priority scaling
6. Dynamic obstacle detection & reactive yielding
"""

import os
import sys
import unittest

# Ensure root paths
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
isaac_root = os.path.join(project_root, "isaac_sim_hospital")
for p in [project_root, isaac_root]:
    if p not in sys.path:
        sys.path.insert(0, p)

from navigation.collision_guard import CollisionGuard
from ai_reasoning.mission_understander import MissionUnderstander, ClinicalPriority
from multi_agent.hospital_agent_manager import HospitalAgentManager
from robots.robot_state_machine import RobotStateMachine, RobotState, PRIORITY_LEVELS
from environments.bilingual_voice import BilingualVoiceEngine


class TestEmbodiedHospitalAI(unittest.TestCase):
    """Automated verification suite."""

    def setUp(self):
        self.guard = CollisionGuard(
            collision_boxes=[
                (-10.0, -8.0, -10.0, -8.0),  # Obstacle box 1
                (5.0, 7.0, 5.0, 7.0),        # Obstacle box 2
            ],
            robot_radius=0.38,
            grid_resolution=0.5,
            grid_bounds=(-30.0, 30.0, -30.0, 30.0),
        )
        self.guard.build_occupancy_grid()
        self.understander = MissionUnderstander()
        self.agent_mgr = HospitalAgentManager()
        self.fsm = RobotStateMachine()

    def test_01_collision_guard_and_astar(self):
        """Verify collision guard points and A* path computation."""
        # Inside obstacle box -> collision
        self.assertTrue(self.guard.check_point_collision(-9.0, -9.0))
        # Clear corridor point -> no collision
        self.assertFalse(self.guard.check_point_collision(0.0, 0.0))

        # A* path calculation
        path = self.guard.plan_path_astar((-13.0, 0.0), (13.0, 0.0))
        self.assertGreaterEqual(len(path), 2)
        # Every waypoint on path must be traversable
        for wx, wy in path:
            self.assertFalse(self.guard.check_point_collision(wx, wy))

    def test_02_dynamic_replanning(self):
        """Verify A* local detour avoiding dynamic obstacles."""
        static_path = self.guard.plan_path_astar((-5.0, 0.0), (5.0, 0.0))
        # Add dynamic obstacle directly on (0, 0)
        detour_path = self.guard.plan_path_astar_dynamic(
            (-5.0, 0.0), (5.0, 0.0), dynamic_obstacles=[(0.0, 0.0)], obstacle_radius=0.9
        )
        self.assertGreaterEqual(len(detour_path), 2)

    def test_03_mission_understanding_english(self):
        """Verify English natural language command understanding."""
        cmd = "Take paracetamol to Bed 2 in Ward 101 immediately"
        spec = self.understander.reason_mission(cmd)
        self.assertEqual(spec.task_type, "MEDICINE_DELIVERY")
        self.assertEqual(spec.dest_dept, "PAT-101")
        self.assertEqual(spec.target_bed, "Bed 2")
        self.assertEqual(spec.priority_level, 2)
        self.assertEqual(spec.language, "en")
        self.assertIn("paracetamol", spec.item.lower())

    def test_04_mission_understanding_hindi(self):
        """Verify Hindi natural language command understanding."""
        cmd = "वार्ड 101 में पैरासिटामोल तुरंत पहुंचाएं"
        spec = self.understander.reason_mission(cmd)
        self.assertEqual(spec.task_type, "MEDICINE_DELIVERY")
        self.assertEqual(spec.dest_dept, "PAT-101")
        self.assertEqual(spec.language, "hi")
        self.assertIn("वार्ड 101", spec.spoken_response_hi)

    def test_05_contract_net_bidding(self):
        """Verify multi-agent bidding and contract award."""
        spec = self.understander.reason_mission("Deliver prescription medication to Ward 102")
        winner, bid, explanation = self.agent_mgr.allocate_mission(spec)
        self.assertIsNotNone(winner)
        self.assertEqual(winner.agent_type, "delivery")
        self.assertGreater(bid.score, 0.5)
        self.assertIn(winner.agent_id, explanation)

    def test_06_emergency_preemption_and_resumption(self):
        """Verify emergency alert preempts delivery and resumes cleanly afterwards."""
        # 1. Allocate delivery
        del_spec = self.understander.reason_mission("Deliver paracetamol to Ward 101")
        w_del, _, _ = self.agent_mgr.allocate_mission(del_spec)

        # 2. Trigger Code Blue emergency
        eme_spec = self.understander.reason_mission("Emergency Code Blue in ICU room 1")
        w_eme, exp = self.agent_mgr.preempt_active_task_for_emergency(
            eme_spec,
            current_robot_pos=(0.0, 0.0, 0.0),
            current_waypoint_idx=14,
            total_waypoints=38,
            remaining_waypoints=[(1.0, 0.0), (2.0, 0.0)],
        )
        self.assertEqual(w_eme.agent_type, "emergency")
        self.assertEqual(len(self.agent_mgr.preemption_stack), 1)

        # 3. Complete emergency and resume
        resumed = self.agent_mgr.resume_preempted_task()
        self.assertIsNotNone(resumed)
        self.assertEqual(resumed.mission_spec.mission_id, del_spec.mission_id)
        self.assertEqual(resumed.current_waypoint_idx, 14)
        self.assertEqual(len(self.agent_mgr.preemption_stack), 0)

    def test_07_robot_state_machine(self):
        """Verify finite state transitions and callbacks."""
        transitions = []
        self.fsm.register_transition_callback(lambda p, n, r: transitions.append((p.name, n.name)))

        self.assertEqual(self.fsm.state, RobotState.IDLE)
        self.fsm.transition_to(RobotState.MISSION_ANALYSIS, "Voice command received")
        self.fsm.transition_to(RobotState.TASK_ASSIGNED, "Contract Net complete")
        self.fsm.transition_to(RobotState.NAVIGATING, "Clear route")
        self.fsm.transition_to(RobotState.BLOCKED, "Dynamic obstacle yielding")
        self.fsm.transition_to(RobotState.NAVIGATING, "Obstacle cleared")
        self.fsm.transition_to(RobotState.EMERGENCY_OVERRIDE, "Code Blue interrupt")
        self.fsm.transition_to(RobotState.EXECUTING_TASK, "Drop emergency kit")
        self.fsm.transition_to(RobotState.MISSION_COMPLETE, "Delivered")

        self.assertEqual(len(transitions), 8)
        self.assertEqual(self.fsm.state, RobotState.MISSION_COMPLETE)


if __name__ == "__main__":
    unittest.main(verbosity=2)

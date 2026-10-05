"""
Unit tests for robot/, battery, FSM, and mission queue.
"""

import math
import unittest

from robot.robot_state import RobotState, RobotStateMachine
from robot.battery import BatteryModel
from robot.robot import Robot, Mission
from config.robot_config import ROBOT_CONFIG


class TestRobotStateMachine(unittest.TestCase):

    def setUp(self):
        self.fsm = RobotStateMachine(RobotState.IDLE)

    def test_initial_state(self):
        self.assertEqual(self.fsm.state, RobotState.IDLE)

    def test_valid_transition_idle_to_planning(self):
        result = self.fsm.transition(RobotState.PLANNING)
        self.assertTrue(result)
        self.assertEqual(self.fsm.state, RobotState.PLANNING)

    def test_valid_transition_planning_to_moving(self):
        self.fsm.transition(RobotState.PLANNING)
        result = self.fsm.transition(RobotState.MOVING)
        self.assertTrue(result)
        self.assertEqual(self.fsm.state, RobotState.MOVING)

    def test_state_history(self):
        self.fsm.transition(RobotState.PLANNING)
        self.fsm.transition(RobotState.MOVING)
        self.assertIn(RobotState.IDLE, self.fsm.history)
        self.assertIn(RobotState.PLANNING, self.fsm.history)


class TestBatteryModel(unittest.TestCase):

    def setUp(self):
        self.battery = BatteryModel()

    def test_initial_charge(self):
        self.assertAlmostEqual(self.battery.soc, 1.0)

    def test_discharge_moving(self):
        initial = self.battery.total_energy_consumed_wh
        self.battery.discharge_moving(dt=1.0, speed_factor=1.0)
        self.assertGreater(self.battery.total_energy_consumed_wh, initial)

    def test_discharge_reduces_soc(self):
        before = self.battery.soc
        self.battery.discharge_moving(dt=10.0, speed_factor=1.0)
        self.assertLess(self.battery.soc, before)

    def test_charging_increases_soc(self):
        # Discharge significantly so SoC drops well below full
        for _ in range(20):
            self.battery.discharge_moving(dt=100.0, speed_factor=1.0)
        low_soc = self.battery.soc
        # Must call start_charging() before charge_step()
        self.battery.start_charging()
        self.battery.charge_step(dt=200.0)
        self.assertGreater(self.battery.soc, low_soc)



    def test_is_low(self):
        # Full battery should NOT be low
        self.assertFalse(self.battery.is_low())

    def test_reset(self):
        self.battery.discharge_moving(dt=100.0, speed_factor=1.0)
        self.battery.reset()
        self.assertAlmostEqual(self.battery.soc, 1.0)


class TestRobotEntity(unittest.TestCase):

    def setUp(self):
        self.robot = Robot(start_pos=(50, 50))

    def test_initial_position(self):
        self.assertAlmostEqual(self.robot.row, 50.0)
        self.assertAlmostEqual(self.robot.col, 50.0)

    def test_set_position_updates_distance(self):
        self.robot.set_position(51.0, 51.0)
        self.assertGreater(self.robot.total_distance_traveled, 0.0)

    def test_mission_enqueue(self):
        m = Mission.create("Test", "ICU", (10, 10))
        result = self.robot.enqueue_mission(m)
        self.assertTrue(result)
        self.assertEqual(len(self.robot.mission_queue), 1)

    def test_start_next_mission(self):
        m = Mission.create("Test", "ICU", (10, 10))
        self.robot.enqueue_mission(m)
        started = self.robot.start_next_mission()
        self.assertIsNotNone(started)
        self.assertEqual(started.status, "active")

    def test_complete_mission(self):
        m = Mission.create("Test", "ICU", (10, 10))
        self.robot.enqueue_mission(m)
        self.robot.start_next_mission()
        self.robot.complete_current_mission(success=True)
        self.assertEqual(self.robot.total_missions_completed, 1)
        self.assertIsNone(self.robot.current_mission)

    def test_set_path(self):
        path = [(50, 50), (50, 51), (50, 52)]
        self.robot.set_path(path)
        self.assertEqual(len(self.robot.path), 3)
        self.assertTrue(self.robot.has_path())

    def test_advance_waypoint(self):
        path = [(50, 50), (50, 51), (50, 52)]
        self.robot.set_path(path)
        self.robot.advance_waypoint()
        self.assertEqual(self.robot.path_index, 1)

    def test_grid_pos(self):
        self.robot.set_position(49.6, 50.4)
        r, c = self.robot.grid_pos
        self.assertEqual(r, 50)
        self.assertEqual(c, 50)

    def test_robot_id_format(self):
        self.assertTrue(self.robot.robot_id.startswith(ROBOT_CONFIG.ROBOT_ID_PREFIX))

    def test_reset(self):
        self.robot.set_position(30.0, 30.0)
        self.robot.reset((80, 11))
        self.assertAlmostEqual(self.robot.row, 80.0)
        self.assertAlmostEqual(self.robot.col, 11.0)

    def test_stats_dict(self):
        stats = self.robot.get_stats()
        self.assertIn("total_missions", stats)
        self.assertIn("battery_pct", stats)
        self.assertIn("current_speed", stats)


class TestMission(unittest.TestCase):

    def test_mission_factory(self):
        m = Mission.create("Deliver meds", "Pharmacy", (20, 30))
        self.assertIsNotNone(m.mission_id)
        self.assertEqual(m.destination, "Pharmacy")
        self.assertEqual(m.goal_pos, (20, 30))
        self.assertEqual(m.status, "pending")

    def test_mission_unique_ids(self):
        m1 = Mission.create("A", "X")
        m2 = Mission.create("B", "Y")
        self.assertNotEqual(m1.mission_id, m2.mission_id)


if __name__ == "__main__":
    unittest.main()

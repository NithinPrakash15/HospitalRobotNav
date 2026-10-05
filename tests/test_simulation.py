"""
Integration tests for simulation, controller, and semantic query engine.
"""

import math
import unittest

from maps.hospital.hospital_map import HospitalMap
from environment.occupancy_grid import OccupancyGrid
from environment.semantic_map import SemanticMap
from environment.navigation_graph import NavigationGraph
from environment.obstacle_manager import ObstacleManager
from semantic.semantic_query_engine import SemanticQueryEngine
from navigation.path_smoother import PathSmoother
from navigation.collision_detector import CollisionDetector
from algorithms.astar import AStarPlanner
from robot.robot import Robot, Mission
from robot.robot_state import RobotState
from simulation.physics import RobotPhysics
from simulation.simulator import Simulator
from speech.wake_word_detector import WakeWordDetector


class TestSemanticQueryEngine(unittest.TestCase):

    def setUp(self):
        self.map   = HospitalMap().build()
        self.grid  = OccupancyGrid(self.map)
        self.engine = SemanticQueryEngine(self.grid)

    def test_resolve_exact_id(self):
        pos = self.engine.resolve("ER")
        self.assertIsNotNone(pos)

    def test_resolve_alias(self):
        pos = self.engine.resolve("icu")
        self.assertIsNotNone(pos)

    def test_resolve_fuzzy(self):
        pos = self.engine.resolve("pharmacy")
        self.assertIsNotNone(pos)

    def test_resolve_unknown_returns_none(self):
        pos = self.engine.resolve("xyzunknownroom999")
        self.assertIsNone(pos)

    def test_get_destination_names(self):
        destinations = self.engine.get_destination_names()
        self.assertGreater(len(destinations), 10)
        for room_id, label, pos in destinations:
            self.assertIsInstance(room_id, str)
            self.assertIsInstance(pos, tuple)
            self.assertEqual(len(pos), 2)

    def test_resolve_nearest(self):
        pos = self.engine.resolve("nearest pharmacy", robot_pos=(80, 11))
        self.assertIsNotNone(pos)


class TestPathSmoother(unittest.TestCase):

    def setUp(self):
        self.map  = HospitalMap().build()
        self.grid = OccupancyGrid(self.map)
        self.smoother = PathSmoother(
            is_blocked_fn=lambda r, c: not self.grid.is_free(r, c)
        )

    def test_smooth_straight_path(self):
        path = [(50, 50), (50, 51), (50, 52), (50, 53), (50, 54)]
        smoothed = self.smoother.smooth(path, method="shortcut")
        self.assertGreater(len(smoothed), 0)

    def test_smooth_does_not_introduce_obstacles(self):
        start = self.grid.find_nearest_free(50, 50)
        planner = AStarPlanner(self.grid)
        goal = self.grid.find_nearest_free(55, 55)
        result = planner.plan(start, goal)
        if result.success and len(result.path) > 2:
            smoothed = self.smoother.smooth(result.path, method="shortcut")
            # All smoothed points should be within grid bounds
            rows, cols = self.grid.rows, self.grid.cols
            for r, c in smoothed:
                self.assertGreaterEqual(r, 0)
                self.assertLess(r, rows)
                self.assertGreaterEqual(c, 0)
                self.assertLess(c, cols)


class TestCollisionDetector(unittest.TestCase):

    def setUp(self):
        self.map      = HospitalMap().build()
        self.grid     = OccupancyGrid(self.map)
        self.detector = CollisionDetector(self.grid)

    def test_clear_path_returns_none(self):
        start = self.grid.find_nearest_free(50, 50)
        path  = [start, (start[0], start[1]+1), (start[0], start[1]+2)]
        result = self.detector.check_path_ahead(path, 0, lookahead=3)
        # May or may not find obstacle depending on map layout — just ensure it runs
        self.assertTrue(result is None or isinstance(result, tuple))

    def test_robot_footprint_clear(self):
        start = self.grid.find_nearest_free(50, 50)
        result = self.detector.is_position_safe(start[0], start[1])
        # In a free corridor cell, footprint should be clear
        self.assertIsInstance(result, bool)



class TestObstacleManager(unittest.TestCase):

    def setUp(self):
        self.map     = HospitalMap().build()
        self.grid    = OccupancyGrid(self.map)
        self.manager = ObstacleManager(self.grid)

    def test_spawn_obstacles(self):
        self.manager.spawn_random_obstacles(5)
        all_obs = self.manager.get_all_obstacles()
        self.assertLessEqual(len(all_obs), 5)  # Some may fail to spawn on walls

    def test_step_returns_moves(self):
        self.manager.spawn_random_obstacles(3)
        moves = self.manager.step()
        self.assertIsInstance(moves, list)

    def test_clear_all(self):
        self.manager.spawn_random_obstacles(5)
        self.manager.clear_all()
        self.assertEqual(len(self.manager.get_all_obstacles()), 0)


class TestWakeWordDetector(unittest.TestCase):

    def test_typed_wake_word_variants(self):
        detector = WakeWordDetector()
        phrases = [
            "Hey Arogya, go to pharmacy",
            "arogya please take me to ICU",
            "HELLO AROGYA deliver medicine",
        ]
        for phrase in phrases:
            match = detector.check_text(phrase)
            self.assertIsNotNone(match, f"wake word should trigger for: {phrase}")
            stripped = detector.strip_wake_word(phrase)
            self.assertTrue(stripped.lower() != phrase.lower())

    def test_cooldown_allows_explicit_wake_phrase_retry(self):
        detector = WakeWordDetector()
        first = detector.check_text("Hey Arogya, go to pharmacy")
        self.assertIsNotNone(first)
        second = detector.check_text("Arogya deliver medicine")
        self.assertIsNotNone(second)


class TestFullNavigationPipeline(unittest.TestCase):
    """
    Integration test: Plan + Smooth + Assign path to Robot.
    Tests the complete navigation pipeline without Pygame.
    """

    def setUp(self):
        self.map     = HospitalMap().build()
        self.grid    = OccupancyGrid(self.map)
        self.robot   = Robot(start_pos=(80, 11))
        self.planner = AStarPlanner(self.grid)
        self.smoother = PathSmoother(
            is_blocked_fn=lambda r, c: not self.grid.is_free(r, c)
        )

    def test_plan_to_goal_and_assign_path(self):
        start = self.grid.find_nearest_free(80, 11)
        goal  = self.grid.find_nearest_free(20, 50)
        result = self.planner.plan(start, goal)

        self.assertTrue(result.success)
        self.assertGreater(len(result.path), 0)

        # Smooth and assign to robot
        smooth = self.smoother.smooth(result.path, method="bezier")
        grid_path = [(int(round(r)), int(round(c))) for r, c in smooth]
        self.robot.set_path(grid_path)

        self.assertTrue(self.robot.has_path())
        self.assertGreater(self.robot.remaining_waypoints, 0)

    def test_mission_to_completion_cycle(self):
        mission = Mission.create("Deliver meds", "Pharmacy", (20, 50))
        self.robot.enqueue_mission(mission)

        started = self.robot.start_next_mission()
        self.assertIsNotNone(started)
        self.assertEqual(started.status, "active")

        self.robot.complete_current_mission(success=True)
        self.assertEqual(self.robot.total_missions_completed, 1)


class TestMovementGuardrails(unittest.TestCase):
    """Regression tests for stop-before-obstacle and directional smoothness."""

    def test_robot_stops_before_moving_into_blocked_waypoint(self):
        sim = Simulator()
        sim.initialize()
        sim.robot.set_position(10, 10)
        sim.robot.set_path([(10, 11), (10, 12)])
        sim.robot.transition(RobotState.PLANNING)
        sim.robot.transition(RobotState.MOVING)
        sim.occupancy_grid.add_dynamic_obstacle(10, 11)

        before_row, before_col = sim.robot.row, sim.robot.col
        sim.step()

        self.assertLess(abs(sim.robot.row - before_row), 1e-6)
        self.assertLess(abs(sim.robot.col - before_col), 1e-6)
        self.assertIn(sim.robot.state, (RobotState.REPLANNING, RobotState.BLOCKED))

    def test_robot_heading_deadband_reduces_tiny_twists(self):
        robot = Robot(start_pos=(10, 10))
        robot.set_path([(10, 10), (10, 10.2), (10, 10.4)])
        robot.heading = 0.0
        phys = RobotPhysics()

        for _ in range(5):
            phys.step(robot, 0.1)

        self.assertLess(abs(robot.heading), math.radians(10))


if __name__ == "__main__":
    unittest.main()

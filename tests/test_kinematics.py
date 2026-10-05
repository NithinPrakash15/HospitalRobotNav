"""Kinematics unit test (extracted from the retired 2D simulator test-suite)."""
import math
import unittest

from controllers.kinematics import RobotPhysics
from robot.robot import Robot


class TestRobotKinematics(unittest.TestCase):
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

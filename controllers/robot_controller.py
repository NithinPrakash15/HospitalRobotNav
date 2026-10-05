"""
HospitalRobotNav — Robot Controller (Velocity Command Generator)
================================================================
The low-level motion controller that converts planned waypoints into
velocity commands for the differential drive robot.

This is the Layer 8 controller that bridges the high-level path planner
with the physics simulation layer. In ROS2 deployment this maps to the
nav2_controller_server executing a nav2_core::Controller plugin.

Controller Architecture:
    A Pure-Pursuit + PD cascade controller:

    1. Pure-Pursuit:  Compute lookahead point on the path
    2. Heading PD:    Compute angular velocity to track heading error
    3. Speed PD:      Compute linear velocity scaled by heading error
    4. Safety:        Apply collision-based velocity scaling

ROS2 Equivalents:
    nav2_controller_server → nav2_core::Controller
    cmd_vel (geometry_msgs/Twist) published at 20 Hz
    FollowPath action server

Reference:
    Coulter, R.C. (1992). Implementation of the Pure Pursuit Path
    Tracking Algorithm. Carnegie Mellon University Technical Report.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from config.robot_config import PHYSICS_CONFIG
from robot.robot import Robot
from robot.robot_state import RobotState
from navigation.collision_detector import CollisionDetector
from utilities.geometry import angle_difference, normalize_angle
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]


# ─────────────────────────────────────────────────────────────────────────────
# Velocity Command
# ─────────────────────────────────────────────────────────────────────────────

class VelocityCommand:
    """
    A structured velocity command for the robot actuators.

    Equivalent to geometry_msgs/Twist in ROS2.

    Attributes:
        linear_x:  Forward velocity (cells/second).
        angular_z: Rotational velocity (rad/second).
    """

    __slots__ = ("linear_x", "angular_z")

    def __init__(self, linear_x: float = 0.0, angular_z: float = 0.0) -> None:
        self.linear_x  = linear_x
        self.angular_z = angular_z

    @classmethod
    def stop(cls) -> "VelocityCommand":
        """Return a zero-velocity stop command."""
        return cls(0.0, 0.0)

    def __repr__(self) -> str:
        return f"VelCmd(v={self.linear_x:.3f}, w={self.angular_z:.3f})"


# ─────────────────────────────────────────────────────────────────────────────
# Pure-Pursuit Controller
# ─────────────────────────────────────────────────────────────────────────────

class PurePursuitController:
    """
    Pure-Pursuit path tracking controller for the hospital robot.

    Algorithm:
        1. Find the lookahead point: first path waypoint > lookahead_dist ahead.
        2. Compute curvature κ = 2*sin(α) / L  where:
               α = heading error to lookahead point
               L = lookahead distance
        3. Map curvature to angular velocity: ω = v * κ
        4. Scale linear velocity to slow down on curves.

    Parameters:
        lookahead_dist:   Lookahead distance in grid cells.
        max_linear_vel:   Maximum linear velocity (cells/s).
        max_angular_vel:  Maximum angular velocity (rad/s).
        k_v:              Speed-curvature coupling gain.
    """

    def __init__(
        self,
        lookahead_dist:  float = 2.5,
        max_linear_vel:  float = PHYSICS_CONFIG.MAX_LINEAR_VELOCITY,
        max_angular_vel: float = PHYSICS_CONFIG.MAX_ANGULAR_VELOCITY,
        k_v: float = 2.0,
    ) -> None:
        self.lookahead_dist  = lookahead_dist
        self.max_linear_vel  = max_linear_vel
        self.max_angular_vel = max_angular_vel
        self.k_v             = k_v

    def compute(
        self,
        robot: Robot,
        path: List[GridPos],
        path_index: int,
    ) -> VelocityCommand:
        """
        Compute velocity command using Pure-Pursuit.

        Args:
            robot:      Robot with current position and heading.
            path:       Full planned path.
            path_index: Index of next waypoint.

        Returns:
            VelocityCommand with linear_x and angular_z.
        """
        # Nothing to track
        if not path or path_index >= len(path):
            return VelocityCommand.stop()

        # Find lookahead point on path
        lookahead_pt = self._find_lookahead(robot, path, path_index)
        if lookahead_pt is None:
            # Fall back to last waypoint
            lookahead_pt = path[-1]

        # Vector from robot to lookahead
        lr, lc = float(lookahead_pt[0]), float(lookahead_pt[1])
        dr = lr - robot.row
        dc = lc - robot.col
        dist = math.hypot(dr, dc)

        if dist < 0.01:
            return VelocityCommand.stop()

        # Desired heading to lookahead
        desired_heading = math.atan2(-dr, dc)  # row increases downward

        # Heading error α
        alpha = angle_difference(desired_heading, robot.heading)

        # Pure-Pursuit curvature: κ = 2sin(α) / L
        L = max(self.lookahead_dist, dist)
        kappa = 2.0 * math.sin(alpha) / L

        # Angular velocity
        w = PHYSICS_CONFIG.CRUISE_SPEED * kappa
        w = max(-self.max_angular_vel, min(self.max_angular_vel, w))

        # Linear velocity scaled by heading error
        abs_alpha = abs(alpha)
        # Behavior tuning: avoid unnecessary reversing and excessive rotate-while-driving.
        # If heading is very large (facing away), rotate in place until roughly aligned,
        # otherwise drive forward with angular adjustment. Use a small deadzone for heading.
        angle_deadzone = 0.08    # radians (~4.5 degrees)
        large_turn_thresh = math.pi / 2
        align_thresh = 0.35      # radians (~20 degrees)

        if abs_alpha > large_turn_thresh:
            # Too large heading error: prefer rotate-in-place before moving forward
            v = 0.0
            # Command maximal angular velocity in the direction of the error (clamped)
            w = math.copysign(self.max_angular_vel, alpha)
        else:
            # Scale: full speed when aligned, slow on sharp turns
            heading_factor = 1.0 - (abs_alpha / (math.pi / 2))
            v = PHYSICS_CONFIG.CRUISE_SPEED * heading_factor
            v = max(PHYSICS_CONFIG.MIN_LINEAR_VELOCITY, min(self.max_linear_vel, v))

            # Reduce angular command in a small deadzone to prevent tiny oscillations
            if abs_alpha < angle_deadzone:
                w = 0.0
            elif abs_alpha < align_thresh:
                # Gentle steering on modest deviations
                w = PHYSICS_CONFIG.CRUISE_SPEED * kappa
                w = max(-self.max_angular_vel, min(self.max_angular_vel, w))
            else:
                # Moderate turns: be more aggressive on angular velocity
                w = math.copysign(min(self.max_angular_vel, abs(PHYSICS_CONFIG.CRUISE_SPEED * kappa) * 1.2), alpha)

        # Ensure we never command reverse linear velocity from the path tracker
        v = max(0.0, v)

        # Slow near goal
        goal = path[-1]
        dist_to_goal = math.hypot(goal[0] - robot.row, goal[1] - robot.col)
        if dist_to_goal < 3.0:
            v *= max(0.2, dist_to_goal / 3.0)

        return VelocityCommand(linear_x=v, angular_z=w)

    def _find_lookahead(
        self,
        robot: Robot,
        path: List[GridPos],
        path_index: int,
    ) -> Optional[GridPos]:
        """
        Find the lookahead point on the path.

        Searches forward from path_index for the first point
        that is at least `lookahead_dist` cells from the robot.

        Args:
            robot:      Robot with current position.
            path:       Full path.
            path_index: Starting search index.

        Returns:
            (row, col) of lookahead point, or None.
        """
        for i in range(path_index, len(path)):
            r, c = path[i]
            dist = math.hypot(r - robot.row, c - robot.col)
            if dist >= self.lookahead_dist:
                return (r, c)

        # Return last waypoint if no point beyond lookahead found
        return path[-1] if path else None


# ─────────────────────────────────────────────────────────────────────────────
# Robot Controller (Outer Loop)
# ─────────────────────────────────────────────────────────────────────────────

class RobotController:
    """
    High-level robot motion controller.

    Wraps PurePursuitController with:
        - Safety velocity scaling based on obstacle proximity
        - Emergency stop detection
        - Goal arrival detection
        - Velocity smoothing

    Usage (called each simulation frame):
        cmd = controller.update(robot, sim)
        # Apply cmd to robot physics
        robot.velocity    = cmd.linear_x
        robot.angular_vel = cmd.angular_z

    ROS2 Note:
        In deployment, the ControllerServer runs this at 20 Hz.
        The cmd_vel topic (geometry_msgs/Twist) is published to
        the hardware driver node (e.g., diff_drive_controller).
    """

    def __init__(
        self,
        collision_detector: CollisionDetector,
        lookahead_dist: float = 2.5,
    ) -> None:
        self._pursuit     = PurePursuitController(lookahead_dist=lookahead_dist)
        self._detector    = collision_detector
        self._prev_cmd    = VelocityCommand.stop()

        # Smoothing time constant (lower = more responsive, less smooth)
        self._alpha_smooth: float = 0.3

    def update(self, robot: Robot) -> VelocityCommand:
        """
        Compute the next velocity command for the robot.

        Called once per simulation frame. Applies:
            1. Pure-Pursuit path tracking
            2. Obstacle safety scaling
            3. Low-pass velocity smoothing

        Args:
            robot: Robot instance with current state.

        Returns:
            VelocityCommand (linear_x, angular_z).
        """
        state = robot.state

        # Not moving → stop
        if state not in (RobotState.MOVING, RobotState.ARRIVED):
            cmd = VelocityCommand.stop()
            self._prev_cmd = cmd
            return cmd

        # No path assigned → stop
        if not robot.has_path():
            return VelocityCommand.stop()

        # Compute raw Pure-Pursuit command
        cmd = self._pursuit.compute(robot, robot.path, robot.path_index)

        # Safety scaling based on obstacles ahead
        safety_factor = self._compute_safety_factor(robot)
        cmd.linear_x  = cmd.linear_x  * safety_factor
        cmd.angular_z = cmd.angular_z * (0.5 + 0.5 * safety_factor)

        # Low-pass smoothing to prevent jerky commands
        cmd = self._smooth(cmd)
        self._prev_cmd = cmd

        return cmd

    def _compute_safety_factor(self, robot: Robot) -> float:
        """
        Compute a [0, 1] scaling factor based on obstacle proximity.

        0.0 = stop (obstacle immediately ahead)
        1.0 = full speed (path is clear)

        Args:
            robot: Robot with current path.

        Returns:
            Safety scale factor in [0.0, 1.0].
        """
        blocked = self._detector.check_path_ahead(
            robot.path,
            robot.path_index,
            lookahead=4,
        )
        if blocked:
            # Obstacle within 4 cells — scale down
            dist = math.hypot(
                blocked[0] - robot.row,
                blocked[1] - robot.col,
            )
            if dist < 1.0:
                return 0.0      # Emergency stop
            elif dist < 2.0:
                return 0.3      # Very slow
            else:
                return 0.6      # Cautious
        return 1.0              # Clear

    def _smooth(self, cmd: VelocityCommand) -> VelocityCommand:
        """
        Apply exponential moving average smoothing.

        Prevents jerky velocity changes between frames.

        Args:
            cmd: Raw command from Pure-Pursuit.

        Returns:
            Smoothed VelocityCommand.
        """
        a = self._alpha_smooth
        smooth_v = a * cmd.linear_x  + (1 - a) * self._prev_cmd.linear_x
        smooth_w = a * cmd.angular_z + (1 - a) * self._prev_cmd.angular_z

        # Rate-limit linear acceleration per-frame to avoid oscillatory forward/back
        max_dv = 0.2
        dv = smooth_v - self._prev_cmd.linear_x
        if abs(dv) > max_dv:
            smooth_v = self._prev_cmd.linear_x + math.copysign(max_dv, dv)

        # Prevent reversing by clamping to non-negative forward-only speeds
        smooth_v = max(0.0, smooth_v)

        # Small angular deadzone to avoid tiny spin corrections
        if abs(smooth_w) < 0.03:
            smooth_w = 0.0

        return VelocityCommand(linear_x=smooth_v, angular_z=smooth_w)

    def reset(self) -> None:
        """Reset controller state (called on replanning or emergency stop)."""
        self._prev_cmd = VelocityCommand.stop()

"""
HospitalRobotNav — Robot Physics (Kinematics)
================================================
Simulates differential drive robot kinematics for smooth animation.

Physics model:
    Linear velocity:  Controlled by PD controller toward target speed
    Angular velocity: Proportional to heading error
    Position update:  Euler integration at dt
"""

from __future__ import annotations

import math
from typing import Tuple

from config.robot_config import PHYSICS_CONFIG
from robot.robot import Robot
from utilities.geometry import angle_difference, normalize_angle


class RobotPhysics:
    """
    Updates robot position and heading each simulation frame.

    Uses a simplified differential-drive kinematic model:
        x(t+dt) = x(t) + v(t) * cos(θ) * dt
        y(t+dt) = y(t) - v(t) * sin(θ) * dt   (row increases downward)
        θ(t+dt) = θ(t) + ω(t) * dt

    Where ω is controlled to minimize heading error to the next waypoint.
    """

    def __init__(self) -> None:
        # PD gains for speed controller
        self._kp_speed:   float = 3.0
        self._kp_heading: float = 4.0
        # Derivative (velocity-damping) gain for the heading controller.
        # Damping proportional to the *current* angular velocity prevents
        # the robot from swinging past the target heading and circling
        # endlessly (the pure-P controller was marginally stable at best).
        self._kd_heading: float = 1.0

    def step(self, robot: Robot, dt: float) -> None:
        """
        Advance robot physics by one time step.

        Moves robot toward its next waypoint using smooth kinematic control.

        Args:
            robot: Robot instance (mutated in place).
            dt:    Time step in seconds.
        """
        waypoint = robot.get_next_waypoint()
        if waypoint is None:
            # No waypoint — decelerate to stop
            self._decelerate(robot, dt)
            return

        wr, wc = float(waypoint[0]), float(waypoint[1])
        dr = wr - robot.row
        dc = wc - robot.col
        dist = math.hypot(dr, dc)

# ── Check arrival at waypoint ──────────────────────────────────────
        # Use a small, fixed tolerance so smoothed sub-cell waypoints are
        # actually traversed.  The old value (RADIUS_CELLS * 0.8 = 0.56)
        # was larger than the distance between consecutive Bezier sub-cell
        # waypoints (~0.1 cells), so the robot "arrived" at the first one
        # instantly and never made forward progress.
        arrival_tol = 0.25
        if dist < arrival_tol:
            # Skip waypoints that are too close — don't return immediately,
            # keep moving through the path. Advance past any waypoints that
            # are within the tolerance distance of the current position.
            while dist < arrival_tol:
                has_more = robot.advance_waypoint()
                if not has_more:
                    from robot.robot_state import RobotState
                    robot.transition(RobotState.ARRIVED)
                    return
                # Re-check distance to the *next* waypoint
                waypoint = robot.get_next_waypoint()
                if waypoint is None:
                    from robot.robot_state import RobotState
                    robot.transition(RobotState.ARRIVED)
                    return
                wr, wc = float(waypoint[0]), float(waypoint[1])
                dr = wr - robot.row
                dc = wc - robot.col
                dist = math.hypot(dr, dc)
            # Found a waypoint beyond tolerance — keep moving toward it
            # (fall through to the movement code below)

        # ── Desired heading ────────────────────────────────────────────────
        desired_heading = math.atan2(-dr, dc)   # atan2(−Δrow, Δcol)

        # Smooth the target heading by intentionally ignoring tiny angular
        # differences. This prevents the robot from "fighting" its own motion
        # when the path contains close, sub-cell waypoint jitter from smoothing.
        heading_error = angle_difference(desired_heading, robot.heading)
        if abs(heading_error) < math.radians(2.5):
            heading_error = 0.0
            robot.angular_vel = 0.0
            target_speed = PHYSICS_CONFIG.CRUISE_SPEED
        else:
            # PD controller for angular velocity with a deadband to reduce
            # unnecessary twirling around the target heading.
            robot.angular_vel = (self._kp_heading * heading_error
                                 - self._kd_heading * robot.angular_vel)
            robot.angular_vel = max(
                -PHYSICS_CONFIG.MAX_ANGULAR_VELOCITY,
                min(PHYSICS_CONFIG.MAX_ANGULAR_VELOCITY, robot.angular_vel),
            )

            # ── Linear velocity control ────────────────────────────────────────
            # Slow down (and stop if heading error is large) so the robot
            # turns toward the target before driving forward. Driving while
            # facing away from the target makes the robot circle endlessly.
            if abs(heading_error) > math.radians(45):
                target_speed = 0.0
            else:
                heading_factor = max(0.35, 1.0 - abs(heading_error) / math.radians(90))
                target_speed = PHYSICS_CONFIG.CRUISE_SPEED * heading_factor

        # Use the tuned target speed even when the heading is well-aligned and
        # the robot is still moving smoothly, so it doesn't alternately brake and
        # accelerate around small path jitter.

        speed_error   = target_speed - robot.velocity
        robot.velocity += self._kp_speed * speed_error * dt
        robot.velocity  = max(
            0.0,
            min(PHYSICS_CONFIG.MAX_LINEAR_VELOCITY, robot.velocity),
        )

        # ── Integrate heading ──────────────────────────────────────────────
        robot.heading = normalize_angle(robot.heading + robot.angular_vel * dt)

        # ── Integrate position ─────────────────────────────────────────────
        new_row = robot.row + robot.velocity * (-math.sin(robot.heading)) * dt
        new_col = robot.col + robot.velocity * math.cos(robot.heading) * dt

        robot.set_position(new_row, new_col)
        robot.time_moving += dt

    def _decelerate(self, robot: Robot, dt: float) -> None:
        """Smoothly decelerate robot to stop."""
        robot.velocity = max(0.0, robot.velocity - PHYSICS_CONFIG.EMERGENCY_DECEL * dt)
        if robot.velocity < 0.01:
            robot.velocity = 0.0
        robot.time_idle += dt

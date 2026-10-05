"""
HospitalRobotNav — Robot Entity
=================================
The central robot data model representing all physical and operational state.

This class is the single source of truth for robot state. All modules
(controller, renderer, metrics) read from this object.

Physical Model:
    Differential drive robot with:
    - 2D position (row, col) in the grid
    - Continuous heading (radians)
    - Current velocity (cells/second)
    - Safe radius (cells) for collision detection

Mission Model:
    - Priority mission queue (deque)
    - Current task description
    - Mission history

ROS2 Note:
    In deployment, the robot's state would be published as:
    - /odom (nav_msgs/Odometry) — position + velocity
    - /robot_state (custom msg) — FSM state + mission
    - /battery_state (sensor_msgs/BatteryState)
"""

from __future__ import annotations

import math
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, List, Optional, Tuple

from config.robot_config import ROBOT_CONFIG, PHYSICS_CONFIG
from config.robot_config import RobotType
from robot.robot_state import RobotState, RobotStateMachine
from robot.battery import BatteryModel
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]


# ─────────────────────────────────────────────────────────────────────────────
# Mission Dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Mission:
    """
    A single robot mission task.

    Attributes:
        mission_id:   Unique ID.
        description:  Human-readable task description.
        destination:  Target room label (e.g., "ICU").
        goal_pos:     Resolved grid cell (row, col).
        priority:     Lower number = higher priority.
        status:       "pending" | "active" | "complete" | "failed"
    """
    mission_id:  str
    description: str
    destination: str
    goal_pos:    Optional[GridPos] = None
    priority:    int               = 5
    status:      str               = "pending"

    @staticmethod
    def create(description: str, destination: str, goal_pos: Optional[GridPos] = None,
               priority: int = 5) -> "Mission":
        """Factory: create a new Mission with a unique ID."""
        return Mission(
            mission_id=str(uuid.uuid4())[:8].upper(),
            description=description,
            destination=destination,
            goal_pos=goal_pos,
            priority=priority,
        )

    def __repr__(self) -> str:
        return f"Mission({self.mission_id}, dest={self.destination!r}, status={self.status})"


# ─────────────────────────────────────────────────────────────────────────────
# Robot Class
# ─────────────────────────────────────────────────────────────────────────────

class Robot:
    """
    Complete hospital robot model.

    Attributes:
        robot_id:       Unique robot identifier (e.g., "HRN-001").
        robot_type:     RobotType (GENERAL, DELIVERY, etc.).
        position:       Current grid position (row, col) — float for smooth animation.
        heading:        Current heading in radians (0 = east, +CCW).
        velocity:       Current linear speed (cells/second).
        angular_vel:    Current angular velocity (rad/second).
        path:           Current planned path as list of (row, col).
        path_index:     Index of next waypoint in path.
        fsm:            Robot state machine.
        battery:        Battery model.
        current_mission: Active mission (if any).
        mission_queue:  Pending mission deque.
        trail:          Recent position history for trail rendering.
    """

    MAX_TRAIL_LENGTH: int = 200

    def __init__(
        self,
        robot_id: Optional[str] = None,
        robot_type: RobotType = RobotType.GENERAL,
        start_pos: GridPos = (80, 11),  # Default: near charging station
    ) -> None:
        # ── Identity ──────────────────────────────────────────────────────────
        self.robot_id: str       = robot_id or self._generate_id()
        self.robot_type: RobotType = robot_type

        # ── Position & Kinematics ─────────────────────────────────────────────
        self.row: float = float(start_pos[0])
        self.col: float = float(start_pos[1])
        self.heading: float = 0.0          # Radians, east = 0
        self.velocity: float = 0.0         # Cells/second
        self.angular_vel: float = 0.0      # Rad/second
        self.target_velocity: float = 0.0  # Desired speed

        # ── Path & Navigation ─────────────────────────────────────────────────
        self.path: List[GridPos] = []
        self.path_index: int = 0
        self.current_goal: Optional[GridPos] = None

        # ── State Machine ─────────────────────────────────────────────────────
        self.fsm: RobotStateMachine = RobotStateMachine(RobotState.IDLE)

        # ── Battery ───────────────────────────────────────────────────────────
        self.battery: BatteryModel = BatteryModel()

        # ── Mission System ────────────────────────────────────────────────────
        self.current_mission: Optional[Mission] = None
        self.mission_queue: Deque[Mission] = deque(
            maxlen=ROBOT_CONFIG.MAX_MISSION_QUEUE
        )
        self.mission_history: List[Mission] = []
        self.carrying_medicine: Optional[str] = None
        self.carrying_item: Optional[str] = None
        self.escorting_patient: bool = False
        self.current_mission_plan: Optional[Any] = None

        # ── Visualization & Humanoid Animation ────────────────────────────────
        self.trail: List[Tuple[float, float]] = [(self.row, self.col)]
        self.arm_left_angle: float = 0.0
        self.arm_right_angle: float = 0.0
        self.arm_extension: float = 0.0
        self.face_expression: str = "neutral"
        self.blink_timer: float = 0.0
        self.is_blinking: bool = False
        self.lidar_scan_angle: float = 0.0
        self.led_pulse_time: float = 0.0
        self.task_animation: str = "none"
        self.task_animation_time: float = 0.0

        # ── Statistics ────────────────────────────────────────────────────────
        self.total_distance_traveled: float = 0.0
        self.total_missions_completed: int = 0
        self.total_replans: int = 0
        self.time_moving: float = 0.0      # Seconds
        self.time_idle: float = 0.0        # Seconds

        log.info("Robot %s initialized at (%.1f, %.1f)", self.robot_id, self.row, self.col)

    def update_animation(self, dt: float) -> None:
        """Update procedural humanoid animation timers, arm positions, and expressions."""
        self.led_pulse_time += dt
        self.lidar_scan_angle = (self.lidar_scan_angle + dt * 6.28) % (2 * math.pi)

        # Eye blink cycle
        self.blink_timer += dt
        if self.blink_timer > 3.5:
            self.is_blinking = True
            if self.blink_timer > 3.65:
                self.is_blinking = False
                self.blink_timer = 0.0

        # Arm & expression behavior by state
        st = self.state
        if st in (RobotState.COLLECTING, RobotState.DELIVERING):
            self.task_animation_time += dt
            self.arm_extension = min(1.0, self.arm_extension + dt * 2.0)
            self.arm_left_angle = 0.4
            self.arm_right_angle = -0.4
            self.face_expression = "focused"
        elif st == RobotState.INTERACTING:
            self.task_animation_time += dt
            self.arm_right_angle = 0.5 + math.sin(self.task_animation_time * 7.0) * 0.3
            self.arm_left_angle = 0.0
            self.face_expression = "happy"
        elif self.carrying_medicine or self.carrying_item:
            self.arm_extension = max(0.2, self.arm_extension - dt * 2.0)
            self.arm_left_angle = 0.35
            self.arm_right_angle = -0.35
            self.face_expression = "focused"
        elif st == RobotState.MOVING:
            self.task_animation_time += dt
            self.arm_extension = max(0.0, self.arm_extension - dt * 2.0)
            sway = math.sin(self.task_animation_time * 6.0) * 0.15
            self.arm_left_angle = sway
            self.arm_right_angle = -sway
            self.face_expression = "neutral"
        elif st == RobotState.BLOCKED:
            self.face_expression = "alert"
            self.arm_left_angle = 0.3
            self.arm_right_angle = 0.3
        else:
            self.arm_extension = max(0.0, self.arm_extension - dt * 2.0)
            self.arm_left_angle = 0.0
            self.arm_right_angle = 0.0
            self.face_expression = "neutral"

    # ─────────────────────────────────────────────────────────────────────────
    # Position
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def position(self) -> Tuple[float, float]:
        """Current position as (row, col) floats."""
        return (self.row, self.col)

    @property
    def grid_pos(self) -> GridPos:
        """Current grid cell (integer row, col)."""
        return (int(round(self.row)), int(round(self.col)))

    def set_position(self, row: float, col: float) -> None:
        """
        Directly set robot position.

        Updates trail and distance counter.

        Args:
            row: New row (float).
            col: New column (float).
        """
        old_row, old_col = self.row, self.col
        dr = row - old_row
        dc = col - old_col
        dist = math.hypot(dr, dc)

        self.row = row
        self.col = col
        self.total_distance_traveled += dist

        # Update heading if moving
        if dist > 0.01:
            self.heading = math.atan2(-dr, dc)   # Note: row increases downward

        # Update trail
        self.trail.append((row, col))
        if len(self.trail) > self.MAX_TRAIL_LENGTH:
            self.trail.pop(0)

    # ─────────────────────────────────────────────────────────────────────────
    # State
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def state(self) -> RobotState:
        """Current FSM state."""
        return self.fsm.state

    def transition(self, new_state: RobotState) -> bool:
        """Attempt FSM state transition."""
        success = self.fsm.transition(new_state)
        if success:
            log.debug("Robot %s: %s → %s", self.robot_id, self.fsm.history[-2].name if len(self.fsm.history) > 1 else "?", new_state.name)
        return success

    def is_moving(self) -> bool:
        return self.state == RobotState.MOVING

    def is_idle(self) -> bool:
        return self.state == RobotState.IDLE

    def is_planning(self) -> bool:
        return self.state in (RobotState.PLANNING, RobotState.REPLANNING)

    # ─────────────────────────────────────────────────────────────────────────
    # Path Management
    # ─────────────────────────────────────────────────────────────────────────

    def set_path(self, path: List[GridPos]) -> None:
        """
        Assign a new planned path.

        Args:
            path: Ordered list of (row, col) waypoints.
        """
        self.path       = list(path)
        self.path_index = 0
        if path:
            self.current_goal = path[-1]

    def has_path(self) -> bool:
        """Return True if a valid path is assigned."""
        return bool(self.path) and self.path_index < len(self.path)

    def get_next_waypoint(self) -> Optional[GridPos]:
        """Return the next waypoint in the path, or None if complete."""
        if self.path_index < len(self.path):
            return self.path[self.path_index]
        return None

    @property
    def current_waypoint(self) -> Optional[GridPos]:
        """Property alias for get_next_waypoint()."""
        return self.get_next_waypoint()

    def advance_waypoint(self) -> bool:
        """
        Advance to the next waypoint.

        Returns:
            True if more waypoints remain, False if path complete.
        """
        self.path_index += 1
        return self.path_index < len(self.path)

    def clear_path(self) -> None:
        """Clear the current path."""
        self.path       = []
        self.path_index = 0

    @property
    def path_progress(self) -> float:
        """Path completion as fraction [0, 1]."""
        if not self.path:
            return 0.0
        return self.path_index / len(self.path)

    @property
    def remaining_waypoints(self) -> int:
        """Number of waypoints not yet reached."""
        return max(0, len(self.path) - self.path_index)

    # ─────────────────────────────────────────────────────────────────────────
    # Mission System
    # ─────────────────────────────────────────────────────────────────────────

    def enqueue_mission(self, mission: Mission) -> bool:
        """
        Add a mission to the queue.

        Args:
            mission: Mission to enqueue.

        Returns:
            True if enqueued, False if queue is full.
        """
        if len(self.mission_queue) >= ROBOT_CONFIG.MAX_MISSION_QUEUE:
            log.warning("Mission queue full, rejecting: %s", mission)
            return False
        self.mission_queue.append(mission)
        log.info("Mission queued: %s", mission)
        return True

    def start_next_mission(self) -> Optional[Mission]:
        """
        Dequeue and start the next pending mission.

        Returns:
            The Mission if one was available, else None.
        """
        if not self.mission_queue:
            return None
        mission = self.mission_queue.popleft()
        mission.status = "active"
        self.current_mission = mission
        log.info("Mission started: %s", mission)
        return mission

    def complete_current_mission(self, success: bool = True) -> None:
        """
        Mark the current mission as complete or failed.

        Args:
            success: True if mission succeeded, False if failed.
        """
        if self.current_mission:
            self.current_mission.status = "complete" if success else "failed"
            self.mission_history.append(self.current_mission)
            if success:
                self.total_missions_completed += 1
            log.info("Mission %s: %s", self.current_mission.mission_id,
                     self.current_mission.status)
            self.current_mission = None

    # ─────────────────────────────────────────────────────────────────────────
    # Statistics
    # ─────────────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return a dictionary of robot statistics for the analytics panel."""
        return {
            "robot_id":               self.robot_id,
            "state":                  self.state.name,
            "battery_pct":            self.battery.soc_percent,
            "total_distance":         self.total_distance_traveled,
            "total_missions":         self.total_missions_completed,
            "total_replans":          self.total_replans,
            "current_speed":          self.velocity,
            "path_length":            len(self.path),
            "path_progress":          self.path_progress,
            "pending_missions":       len(self.mission_queue),
            "energy_consumed_wh":     self.battery.total_energy_consumed_wh,
            "estimated_range_cells":  self.battery.estimate_remaining_distance(),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _generate_id() -> str:
        """Generate a unique robot ID."""
        import random
        num = random.randint(1, 999)
        return f"{ROBOT_CONFIG.ROBOT_ID_PREFIX}-{num:03d}"

    def reset(self, start_pos: GridPos = (80, 11)) -> None:
        """Reset robot to initial state at start_pos."""
        self.row, self.col = float(start_pos[0]), float(start_pos[1])
        self.heading        = 0.0
        self.velocity       = 0.0
        self.angular_vel    = 0.0
        self.path           = []
        self.path_index     = 0
        self.current_goal   = None
        self.fsm            = RobotStateMachine(RobotState.IDLE)
        self.battery.reset()
        self.current_mission = None
        self.mission_queue.clear()
        self.trail = [(self.row, self.col)]
        self.total_distance_traveled = 0.0
        self.total_missions_completed = 0
        self.total_replans  = 0
        log.info("Robot %s reset to (%d, %d)", self.robot_id, *start_pos)

    def __repr__(self) -> str:
        return (
            f"Robot({self.robot_id}, pos=({self.row:.1f},{self.col:.1f}), "
            f"state={self.state.name}, battery={self.battery.soc_percent:.0f}%)"
        )

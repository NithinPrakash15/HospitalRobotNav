"""
HospitalRobotNav — Collision Detector
========================================
Detects potential collisions between the robot and obstacles.

Supports:
    - Static obstacle collision (wall check at future position)
    - Dynamic obstacle proximity check (distance-based)
    - Forward-looking path safety check
    - Safe zone visualization radius

ROS2 Note:
    Equivalent to the collision monitor in nav2_collision_monitor
    and robot_footprint_checker in nav2_costmap_2d.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from config.robot_config import PHYSICS_CONFIG
from config.hospital_config import HOSPITAL_CONFIG
from environment.occupancy_grid import OccupancyGrid
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]
FloatPos = Tuple[float, float]


class CollisionDetector:
    """
    Detects collisions for the hospital robot.

    Checks:
        1. Wall collision — robot center cell is a wall
        2. Dynamic obstacle — robot too close to a dynamic obstacle
        3. Path safety — any of the next N waypoints is blocked
    """

    def __init__(
        self,
        occupancy_grid: OccupancyGrid,
        safe_distance: float = HOSPITAL_CONFIG.ROBOT_SAFE_DISTANCE,
    ) -> None:
        """
        Args:
            occupancy_grid: Live grid with dynamic obstacles.
            safe_distance:  Minimum distance from obstacle center (cells).
        """
        self._grid = occupancy_grid
        self._safe_dist = safe_distance
        self._robot_radius = PHYSICS_CONFIG.RADIUS_CELLS

    # ─────────────────────────────────────────────────────────────────────────
    # Main Checks
    # ─────────────────────────────────────────────────────────────────────────

    def is_position_safe(self, row: float, col: float, footprint_radius: Optional[float] = None) -> bool:
        """
        Return True if the robot center at (row, col) is collision-free.

        Checks the robot's footprint (circle of radius footprint_radius or RADIUS_CELLS)
        against the occupancy grid.

        Args:
            row: Robot row (float).
            col: Robot column (float).
            footprint_radius: Optional custom footprint radius in cells.

        Returns:
            True if safe.
        """
        r_int = int(round(row))
        c_int = int(round(col))

        # Check center cell
        if not self._grid.is_free(r_int, c_int):
            return False

        rad = self._robot_radius if footprint_radius is None else footprint_radius
        if rad <= 0:
            return True

        # Check footprint (approximate circular check)
        radius = int(math.ceil(rad))
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                if math.hypot(dr, dc) <= rad:
                    if not self._grid.is_free(r_int + dr, c_int + dc):
                        return False

        return True

    def is_near_dynamic_obstacle(
        self,
        row: float,
        col: float,
        obstacle_positions: List[GridPos],
    ) -> bool:
        """
        Return True if robot is within safe_distance of any dynamic obstacle.

        Args:
            row:                Robot row.
            col:                Robot column.
            obstacle_positions: List of (row, col) obstacle positions.

        Returns:
            True if a dynamic obstacle is too close.
        """
        for (or_, oc) in obstacle_positions:
            dist = math.hypot(or_ - row, oc - col)
            if dist <= self._safe_dist:
                return True
        return False

    def check_path_ahead(
        self,
        path: List[GridPos],
        start_index: int,
        lookahead: int = 5,
        obstacle_positions: Optional[List[GridPos]] = None,
    ) -> Optional[GridPos]:
        """
        Check the next `lookahead` waypoints in the path for collisions.

        Dynamic obstacles are treated as soft blockers: if a moving obstacle is
        too close to a future waypoint, the robot should replan before it reaches
        the blocked corridor. This prevents the robot from trying to cut through
        changing human traffic and reduces oscillation near busy areas.
        """
        end = min(start_index + lookahead, len(path))
        for i in range(start_index, end):
            r, c = path[i]
            if not self._grid.is_free(r, c):
                return (r, c)

            if obstacle_positions is not None:
                for or_, oc in obstacle_positions:
                    distance = math.hypot(or_ - r, oc - c)
                    if distance <= 1.4:
                        return (r, c)

        return None

    def get_clearance(self, row: float, col: float) -> float:
        """
        Compute the minimum clearance (cells) from (row, col) to any obstacle.

        Searches expanding rings until an obstacle is found.
        Returns the distance at which the first obstacle is detected.

        Args:
            row: Query row.
            col: Query column.

        Returns:
            Float clearance in cells (0 if on obstacle).
        """
        max_search = 10
        for radius in range(0, max_search + 1):
            for dr in range(-radius, radius + 1):
                for dc in range(-radius, radius + 1):
                    if abs(dr) == radius or abs(dc) == radius:
                        nr = int(round(row)) + dr
                        nc = int(round(col)) + dc
                        if not self._grid.is_free(nr, nc):
                            return math.hypot(dr, dc)
        return float(max_search)

    def is_straight_line_safe(
        self,
        start: GridPos,
        end: GridPos,
        footprint_radius: Optional[float] = None,
    ) -> bool:
        """
        Check if a straight line between start and end is obstacle-free.

        Args:
            start: Source (row, col).
            end:   Target (row, col).
            footprint_radius: Optional custom footprint radius in cells.

        Returns:
            True if no obstacles on the line.
        """
        from utilities.geometry import bresenham_cells
        cells = bresenham_cells(start, end)
        for r, c in cells:
            if footprint_radius is not None and footprint_radius > 0:
                if not self.is_position_safe(r, c, footprint_radius=footprint_radius):
                    return False
            else:
                if not self._grid.is_free(r, c):
                    return False
        return True

    def is_path_clear(
        self,
        path: List[GridPos],
        start_index: int = 0,
        obstacle_positions: Optional[List[GridPos]] = None,
        check_footprint: bool = True,
    ) -> bool:
        """
        Validate whether the remaining path from start_index is clear of all obstacles.

        Args:
            path: List of (row, col) waypoints.
            start_index: Current waypoint index to start checking from.
            obstacle_positions: Dynamic obstacle positions.
            check_footprint: If True, uses circular footprint collision check.

        Returns:
            True if entire remaining path is free.
        """
        return self.get_first_blocked_index(
            path,
            start_index=start_index,
            obstacle_positions=obstacle_positions,
            check_footprint=check_footprint,
        ) is None

    def get_first_blocked_index(
        self,
        path: List[GridPos],
        start_index: int = 0,
        obstacle_positions: Optional[List[GridPos]] = None,
        check_footprint: bool = True,
    ) -> Optional[int]:
        """
        Find index of the first waypoint in path that is blocked.

        Args:
            path: List of (row, col) waypoints.
            start_index: Waypoint index to start checking from.
            obstacle_positions: Dynamic obstacle positions.
            check_footprint: If True, checks footprint collision.

        Returns:
            Index in path of first blocked waypoint, or None if clear.
        """
        for i in range(start_index, len(path)):
            r, c = path[i]
            if check_footprint:
                if not self.is_position_safe(r, c):
                    return i
            else:
                if not self._grid.is_free(r, c):
                    return i

            if obstacle_positions:
                for or_, oc in obstacle_positions:
                    if math.hypot(or_ - r, oc - c) <= 1.4:
                        return i
        return None

"""
HospitalRobotNav — Occupancy Grid
===================================
Wraps the raw hospital map arrays and provides query APIs for planners.

Responsibilities:
    - Maintain binary occupancy (free/wall) as a numpy array
    - Maintain a weighted cost map for planner edge weights
    - Support dynamic obstacle injection and removal
    - Provide neighbor expansion for 4- and 8-connected grids
    - Compute inflation layers (cost gradients near walls)

The OccupancyGrid is the PRIMARY interface for all path planners.
Planners never access the HospitalMap directly.

ROS2 Note:
    This class maps to the nav2_costmap_2d::Costmap2D concept.
    In a ROS2 deployment:
        - Static layer  → nav2_costmap_2d::StaticLayer
        - Obstacle layer → nav2_costmap_2d::ObstacleLayer
        - Inflation layer → nav2_costmap_2d::InflationLayer
"""

from __future__ import annotations

import numpy as np
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from config.hospital_config import COST_CONFIG, HOSPITAL_CONFIG
from maps.hospital.hospital_map import HospitalMap
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]

# 8-directional movement deltas with costs (dr, dc, cost)
_MOVES_8: List[Tuple[int, int, float]] = [
    (-1,  0, 1.0),   # N
    ( 1,  0, 1.0),   # S
    ( 0, -1, 1.0),   # W
    ( 0,  1, 1.0),   # E
    (-1, -1, 1.414), # NW diagonal
    (-1,  1, 1.414), # NE diagonal
    ( 1, -1, 1.414), # SW diagonal
    ( 1,  1, 1.414), # SE diagonal
]

_MOVES_4: List[Tuple[int, int, float]] = [
    (-1,  0, 1.0),
    ( 1,  0, 1.0),
    ( 0, -1, 1.0),
    ( 0,  1, 1.0),
]


class OccupancyGrid:
    """
    Dynamic occupancy grid for path planning.

    Maintains:
        _static_cost   — immutable base cost from hospital map
        _dynamic_cost  — mutable overlay for dynamic obstacles
        _dynamic_cells — set of (row, col) currently occupied dynamically

    The effective cost at (r, c) = max(_static_cost[r,c], _dynamic_cost[r,c])
    """

    def __init__(self, hospital_map: HospitalMap) -> None:
        """
        Initialize from a fully built HospitalMap.

        Args:
            hospital_map: Built HospitalMap instance.
        """
        assert hospital_map._built, "HospitalMap must be built before use."

        self._map = hospital_map
        self.rows  = hospital_map.rows
        self.cols  = hospital_map.cols

        # Static cost layer (from map — never changes)
        self._static_cost: np.ndarray = hospital_map.cost_grid.copy()

        # Dynamic cost overlay (modified at runtime)
        self._dynamic_cost: np.ndarray = np.zeros(
            (self.rows, self.cols), dtype=np.float32
        )

        # Set of cells occupied by dynamic obstacles
        self._dynamic_cells: Set[GridPos] = set()

        # Inflation radius (cells) for obstacle proximity penalty
        self._inflation_radius: float = HOSPITAL_CONFIG.ROBOT_SAFE_DISTANCE

        log.info(
            "OccupancyGrid initialized: %d×%d, inflation_radius=%.1f",
            self.rows, self.cols, self._inflation_radius,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Core Queries
    # ─────────────────────────────────────────────────────────────────────────

    def is_free(self, row: int, col: int) -> bool:
        """
        Return True if cell (row, col) is walkable (not wall, not dynamic obstacle).

        Args:
            row: Grid row.
            col: Grid column.

        Returns:
            True if the cell can be traversed.
        """
        if not self._in_bounds(row, col):
            return False
        if self._static_cost[row, col] >= COST_CONFIG.COST_WALL:
            return False
        if (row, col) in self._dynamic_cells:
            return False
        return True

    def get_cost(self, row: int, col: int) -> float:
        """
        Return the effective traversal cost of cell (row, col).

        Returns:
            Cost in [1.0, ∞). Returns COST_WALL for impassable cells.
        """
        if not self._in_bounds(row, col):
            return COST_CONFIG.COST_WALL
        if (row, col) in self._dynamic_cells:
            return COST_CONFIG.COST_WALL

        base = float(self._static_cost[row, col])
        overlay = float(self._dynamic_cost[row, col])
        return max(base, base + overlay)

    def get_edge_cost(
        self,
        from_pos: GridPos,
        to_pos: GridPos,
    ) -> float:
        """
        Compute the cost of moving from `from_pos` to `to_pos`.

        For diagonal moves, applies the √2 multiplier.
        Returns COST_WALL if destination is not free.

        Args:
            from_pos: Source (row, col).
            to_pos:   Destination (row, col).

        Returns:
            Edge traversal cost.
        """
        if not self.is_free(*to_pos):
            return COST_CONFIG.COST_WALL

        dr = abs(to_pos[0] - from_pos[0])
        dc = abs(to_pos[1] - from_pos[1])
        move_cost = 1.414 if (dr + dc == 2) else 1.0

        return move_cost * self.get_cost(*to_pos)

    # ─────────────────────────────────────────────────────────────────────────
    # Neighbor Expansion (used by all planners)
    # ─────────────────────────────────────────────────────────────────────────

    def get_neighbors_4(self, row: int, col: int) -> List[Tuple[GridPos, float]]:
        """
        Return 4-connected walkable neighbors with edge costs.

        Returns:
            List of ((r, c), cost) tuples.
        """
        result = []
        for dr, dc, move_cost in _MOVES_4:
            nr, nc = row + dr, col + dc
            if self.is_free(nr, nc):
                cost = move_cost * self.get_cost(nr, nc)
                result.append(((nr, nc), cost))
        return result

    def get_neighbors_8(self, row: int, col: int) -> List[Tuple[GridPos, float]]:
        """
        Return 8-connected walkable neighbors with edge costs.

        Diagonal moves are blocked if both cardinal neighbors are walls
        (prevents cutting corners through walls).

        Returns:
            List of ((r, c), cost) tuples.
        """
        result = []
        for dr, dc, move_cost in _MOVES_8:
            nr, nc = row + dr, col + dc
            if not self.is_free(nr, nc):
                continue

            # Corner-cutting check for diagonal moves
            if dr != 0 and dc != 0:
                if (not self.is_free(row + dr, col) or
                        not self.is_free(row, col + dc)):
                    continue   # Block diagonal through wall corner

            cost = move_cost * self.get_cost(nr, nc)
            result.append(((nr, nc), cost))
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Dynamic Obstacle Management
    # ─────────────────────────────────────────────────────────────────────────

    def add_dynamic_obstacle(self, row: int, col: int) -> bool:
        """
        Mark a cell as occupied by a dynamic obstacle.

        Also applies an inflation penalty to surrounding cells.

        Args:
            row: Obstacle row.
            col: Obstacle column.

        Returns:
            True if the obstacle was placed (cell was previously free).
        """
        if not self._in_bounds(row, col):
            return False
        if self._static_cost[row, col] >= COST_CONFIG.COST_WALL:
            return False  # Cannot place on a wall

        self._dynamic_cells.add((row, col))
        self._inflate_around(row, col, add=True)
        log.debug("Dynamic obstacle added at (%d, %d)", row, col)
        return True

    def remove_dynamic_obstacle(self, row: int, col: int) -> bool:
        """
        Remove a dynamic obstacle from a cell.

        Args:
            row: Obstacle row.
            col: Obstacle column.

        Returns:
            True if an obstacle existed at this cell.
        """
        if (row, col) not in self._dynamic_cells:
            return False

        self._dynamic_cells.discard((row, col))
        self._inflate_around(row, col, add=False)
        log.debug("Dynamic obstacle removed from (%d, %d)", row, col)
        return True

    def move_dynamic_obstacle(
        self,
        old_pos: GridPos,
        new_pos: GridPos,
    ) -> bool:
        """
        Atomically move a dynamic obstacle from old_pos to new_pos.

        Args:
            old_pos: Current position (row, col).
            new_pos: Target position (row, col).

        Returns:
            True if the move was successful.
        """
        removed = self.remove_dynamic_obstacle(*old_pos)
        if not removed:
            return False
        return self.add_dynamic_obstacle(*new_pos)

    def get_dynamic_obstacles(self) -> FrozenSet[GridPos]:
        """Return frozen set of all current dynamic obstacle positions."""
        return frozenset(self._dynamic_cells)

    def clear_dynamic_obstacles(self) -> None:
        """Remove all dynamic obstacles and reset inflation overlay."""
        self._dynamic_cells.clear()
        self._dynamic_cost.fill(0.0)
        log.info("All dynamic obstacles cleared.")

    # ─────────────────────────────────────────────────────────────────────────
    # Inflation Layer
    # ─────────────────────────────────────────────────────────────────────────

    def _inflate_around(self, row: int, col: int, add: bool) -> None:
        """
        Add or remove cost inflation around a cell within the inflation radius.

        The inflation cost decays linearly from COST_NEAR_OBSTACLE at radius=0
        to 0 at radius=inflation_radius.

        Args:
            row: Center row.
            col: Center column.
            add: True to add inflation, False to remove it.
        """
        r_int = int(self._inflation_radius) + 1
        for dr in range(-r_int, r_int + 1):
            for dc in range(-r_int, r_int + 1):
                nr, nc = row + dr, col + dc
                if not self._in_bounds(nr, nc):
                    continue
                dist = (dr ** 2 + dc ** 2) ** 0.5
                if dist > self._inflation_radius:
                    continue
                if dist == 0:
                    continue

                fraction = 1.0 - (dist / self._inflation_radius)
                inflation = COST_CONFIG.COST_NEAR_OBSTACLE * fraction

                if add:
                    self._dynamic_cost[nr, nc] += inflation
                else:
                    self._dynamic_cost[nr, nc] = max(
                        0.0, self._dynamic_cost[nr, nc] - inflation
                    )

    # ─────────────────────────────────────────────────────────────────────────
    # Validation
    # ─────────────────────────────────────────────────────────────────────────

    def find_nearest_free(self, row: int, col: int, max_radius: int = 5) -> Optional[GridPos]:
        """
        Find the nearest free cell to (row, col) by BFS-style search.

        Useful for snapping a goal or start position that lands on a wall.

        Args:
            row:        Query row.
            col:        Query column.
            max_radius: Maximum search radius in cells.

        Returns:
            (row, col) of nearest free cell, or None if not found.
        """
        if self.is_free(row, col):
            return (row, col)

        for radius in range(1, max_radius + 1):
            for dr in range(-radius, radius + 1):
                for dc in range(-radius, radius + 1):
                    if abs(dr) == radius or abs(dc) == radius:
                        nr, nc = row + dr, col + dc
                        if self.is_free(nr, nc):
                            return (nr, nc)

        log.warning(
            "No free cell found near (%d, %d) within radius %d",
            row, col, max_radius,
        )
        return None

    def get_random_free_cell(self) -> Optional[GridPos]:
        """Return a random unoccupied free grid cell."""
        import random
        for _ in range(500):
            r = random.randint(2, self.rows - 3)
            c = random.randint(2, self.cols - 3)
            if self.is_free(r, c):
                return (r, c)
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────────────────────

    def _in_bounds(self, row: int, col: int) -> bool:
        """Return True if (row, col) is within grid boundaries."""
        return 0 <= row < self.rows and 0 <= col < self.cols

    @property
    def binary_grid(self) -> np.ndarray:
        """
        Return live binary occupancy (0=free, 1=occupied).
        Includes dynamic obstacles.
        """
        grid = self._map.binary_grid.copy()
        for r, c in self._dynamic_cells:
            grid[r, c] = 1
        return grid

    @property
    def type_grid(self) -> np.ndarray:
        """Return the static type grid from HospitalMap."""
        return self._map.type_grid

    @property
    def room_id_grid(self) -> np.ndarray:
        """Return the room-ID grid from HospitalMap."""
        return self._map.room_id_grid

    @property
    def hospital_map(self) -> HospitalMap:
        """Return the underlying HospitalMap."""
        return self._map

    def __repr__(self) -> str:
        return (
            f"OccupancyGrid({self.rows}×{self.cols}, "
            f"dynamic_obstacles={len(self._dynamic_cells)})"
        )

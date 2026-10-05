"""
HospitalRobotNav — Hybrid A* Path Planning
============================================
Implements Hybrid A* — a continuous-state extension of A* that plans paths
in the robot's continuous configuration space (x, y, θ) while using a
discrete grid for collision checking.

Standard A* vs Hybrid A*:
    A*:       Plans in discrete (row, col) grid cells
    Hybrid A*: Plans in continuous (x, y, heading) configuration space

This makes Hybrid A* directly compatible with ROS2 Nav2 and
produces kinematically feasible paths for a differential drive robot.

State Space:
    Node = (x, y, θ)  where θ = heading in radians
    Grid cell = discretized (x, y, θ) → integer key for hash map

Motion Primitives:
    At each state, the robot can execute:
        - Forward at various steering angles
        - Using a simplified bicycle model

Hybrid A* is used in:
    - Autonomous vehicles (Apollo, Autoware)
    - Hospital robots (direct ROS2 deployment target)
    - Nav2 Smac Planner (HybridA* variant)

Reference:
    Dolgov, D., Thrun, S., Montemerlo, M., Diebel, J. (2008). "Practical Search
    Techniques in Path Planning for Autonomous Driving." AAAI-08 Workshop.
    
    Petereit, J. et al. (2012). "Application of Hybrid A* to an Autonomous
    Mobile Robot for Path Planning in Unstructured Environments." ROBOTIK 2012.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from algorithms.base_planner import BasePlanner
from algorithms.heuristics import HeuristicType, euclidean
from environment.occupancy_grid import OccupancyGrid
from config.robot_config import PHYSICS_CONFIG
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]


# ─────────────────────────────────────────────────────────────────────────────
# Continuous State
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class HybridState:
    """
    Continuous configuration state for Hybrid A*.

    Attributes:
        x:      Continuous column position (cells).
        y:      Continuous row position (cells).
        theta:  Heading angle (radians), discretized for hashing.
    """
    x:     float
    y:     float
    theta: float

    @property
    def grid_pos(self) -> GridPos:
        """Snap continuous position to nearest grid cell (row, col)."""
        return (int(round(self.y)), int(round(self.x)))

    def discretize(self, xy_res: float = 1.0, theta_res: float = 0.5) -> Tuple[int, int, int]:
        """
        Convert to discrete key for hash map.

        Args:
            xy_res:    Resolution for x/y (cells).
            theta_res: Resolution for theta (radians).

        Returns:
            (xi, yi, thetai) integer key.
        """
        xi     = int(round(self.x / xy_res))
        yi     = int(round(self.y / xy_res))
        # Wrap theta to [0, 2π) then discretize
        theta_wrapped = self.theta % (2 * math.pi)
        thetai = int(round(theta_wrapped / theta_res)) % int(round(2 * math.pi / theta_res))
        return (xi, yi, thetai)


# ─────────────────────────────────────────────────────────────────────────────
# Motion Primitives
# ─────────────────────────────────────────────────────────────────────────────

def _generate_motion_primitives(
    step_size: float = 1.0,
    n_angles: int = 7,
    max_steer: float = math.pi / 2,
) -> List[Tuple[float, float, float, float]]:
    """
    Generate kinematically feasible motion primitives for differential drive robot.

    Each primitive: (step, dtheta, cost, steer)
    Includes forward motions, in-place rotations, and reverse motions.
    """
    primitives = []
    # Forward motions with steering angles up to ±pi/2
    steer_angles = [
        -max_steer + i * (2 * max_steer / (n_angles - 1))
        for i in range(n_angles)
    ]
    for steer in steer_angles:
        dtheta = steer
        cost = step_size * (1.0 + 0.3 * abs(steer) / max_steer)
        primitives.append((step_size, dtheta, cost, steer))

    # In-place rotations for differential drive
    for rot in (-math.pi / 2, -math.pi / 4, math.pi / 4, math.pi / 2):
        primitives.append((0.0, rot, 0.4, rot))

    # Reverse motions for tight navigation
    for steer in (0.0, -math.pi / 4, math.pi / 4):
        primitives.append((-step_size, steer, step_size * 1.5, steer))

    return primitives


_MOTION_PRIMITIVES = _generate_motion_primitives()


class HybridAStarPlanner(BasePlanner):
    """
    Hybrid A* planner for kinematically feasible path planning.

    Plans in continuous (x, y, θ) space while checking collisions
    on the discrete occupancy grid. Produces smooth, executable paths
    for the differential-drive hospital robot.

    Configuration:
        - Motion primitives: 7 steering angles from -π/4 to +π/4
        - Step size: 1.0 grid cell per motion
        - Theta discretization: 0.4 rad (~23°) bins

    Limitations:
        - Does not model exact robot footprint (uses point collision)
        - Simplified bicycle model (not full Ackermann)
        - No reverse motion (forward-only primitives)

    Attributes:
        _open_set:       Set of grid cells in frontier (for visualization).
        _closed_set:     Set of expanded grid cells.
        _nodes_expanded: Count.
        _nodes_generated: Count.
        _open_peak:      Peak frontier size.
        _XY_RES:         Spatial discretization (cells).
        _THETA_RES:      Angular discretization (radians).
    """

    _XY_RES:    float = 1.0
    _THETA_RES: float = math.pi / 8   # 22.5° bins

    def __init__(
        self,
        occupancy_grid: OccupancyGrid,
        heuristic_type: HeuristicType = HeuristicType.EUCLIDEAN,
        heuristic_weight: float = 1.0,
        max_iterations: int = BasePlanner.DEFAULT_MAX_ITER,
        use_8_connected: bool = True,
        step_size: float = 1.0,
    ) -> None:
        super().__init__(
            occupancy_grid=occupancy_grid,
            heuristic_type=heuristic_type,
            heuristic_weight=heuristic_weight,
            max_iterations=max_iterations,
            use_8_connected=use_8_connected,
        )
        self._step_size = step_size
        self._motion_primitives = _generate_motion_primitives(step_size)

        self._open_set:        Set[GridPos] = set()
        self._closed_set:      Set[GridPos] = set()
        self._closed_keys:     Set[Tuple]   = set()
        self._nodes_expanded:  int = 0
        self._nodes_generated: int = 0
        self._open_peak:       int = 0

    # ─────────────────────────────────────────────────────────────────────────
    # BasePlanner interface
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "Hybrid A*"

    def reset(self) -> None:
        self._open_set.clear()
        self._closed_set.clear()
        self._closed_keys.clear()
        self._nodes_expanded  = 0
        self._nodes_generated = 0
        self._open_peak       = 0

    def get_open_set(self)        -> Set[GridPos]: return set(self._open_set)
    def get_closed_set(self)      -> Set[GridPos]: return set(self._closed_set)
    def get_nodes_expanded(self)  -> int: return self._nodes_expanded
    def get_nodes_generated(self) -> int: return self._nodes_generated
    def get_open_list_peak(self)  -> int: return self._open_peak

    # ─────────────────────────────────────────────────────────────────────────
    # Core Hybrid A* Implementation
    # ─────────────────────────────────────────────────────────────────────────

    def _plan_impl(self, start: GridPos, goal: GridPos) -> List[GridPos]:
        """
        Execute Hybrid A* from `start` to `goal`.

        Returns grid-cell path (discretized from continuous states).
        """
        # Initial heading: toward goal
        dr = goal[0] - start[0]
        dc = goal[1] - start[1]
        init_theta = math.atan2(-dr, dc)  # Note: row increases downward

        start_state = HybridState(
            x=float(start[1]),
            y=float(start[0]),
            theta=init_theta,
        )
        goal_pos = (float(goal[0]), float(goal[1]))

        # Cost maps: discrete_key → (g_cost, state, parent_key)
        g_cost:    Dict[Tuple, float]              = {}
        came_from: Dict[Tuple, Optional[Tuple]]    = {}
        state_map: Dict[Tuple, HybridState]        = {}

        start_key = start_state.discretize(self._XY_RES, self._THETA_RES)
        g_cost[start_key]    = 0.0
        came_from[start_key] = None
        state_map[start_key] = start_state

        # Heuristic uses Euclidean distance to goal
        h_start = euclidean(start, goal)
        heap: List[Tuple[float, int, Tuple]] = [(h_start, 0, start_key)]
        tie = 0

        self._open_set.add(start)
        self._nodes_generated = 1

        while heap:
            f_curr, _, current_key = heapq.heappop(heap)

            current_state = state_map.get(current_key)
            if current_state is None:
                continue

            grid_pos = current_state.grid_pos

            if current_key in self._closed_keys:
                continue

            self._open_set.discard(grid_pos)
            self._closed_set.add(grid_pos)
            self._closed_keys.add(current_key)
            self._nodes_expanded += 1

            # ── Goal check ─────────────────────────────────────────────────
            gr, gc = goal
            if abs(current_state.y - gr) <= 1.5 and abs(current_state.x - gc) <= 1.5:
                log.debug("Hybrid A* reached goal in %d expansions", self._nodes_expanded)
                return self._reconstruct_hybrid_path(came_from, state_map, start_key, current_key)

            if self._nodes_expanded >= self._max_iter:
                log.warning("Hybrid A* exceeded max iterations")
                return []

            g_curr = g_cost[current_key]

            # ── Apply motion primitives ─────────────────────────────────────
            for step, dtheta, cost, steer in self._motion_primitives:
                theta = current_state.theta
                new_x = current_state.x + step * math.cos(theta)
                new_y = current_state.y - step * math.sin(theta)  # row inverted
                new_theta = (theta + dtheta) % (2 * math.pi)

                new_row = int(round(new_y))
                new_col = int(round(new_x))

                if not self._grid.is_free(new_row, new_col):
                    continue

                new_state = HybridState(new_x, new_y, new_theta)
                new_key   = new_state.discretize(self._XY_RES, self._THETA_RES)

                g_cell = self._grid.get_cost(new_row, new_col)
                g_new  = g_curr + cost * g_cell

                if g_new < g_cost.get(new_key, float("inf")):
                    g_cost[new_key]    = g_new
                    came_from[new_key] = current_key
                    state_map[new_key] = new_state
                    h = euclidean((new_row, new_col), goal)
                    tie += 1
                    heapq.heappush(heap, (g_new + h, tie, new_key))
                    self._open_set.add((new_row, new_col))
                    self._nodes_generated += 1
                    if len(self._open_set) > self._open_peak:
                        self._open_peak = len(self._open_set)

        log.debug("Hybrid A*: no path found")
        return []

    def _reconstruct_hybrid_path(
        self,
        came_from: Dict[Tuple, Optional[Tuple]],
        state_map: Dict[Tuple, "HybridState"],
        start_key: Tuple,
        goal_key: Tuple,
    ) -> List[GridPos]:
        """Reconstruct grid-cell path from continuous state chain."""
        path: List[GridPos] = []
        current = goal_key

        while current is not None:
            state = state_map.get(current)
            if state:
                path.append(state.grid_pos)
            current = came_from.get(current)

        path.reverse()
        # Deduplicate consecutive identical cells
        deduped: List[GridPos] = []
        for cell in path:
            if not deduped or cell != deduped[-1]:
                deduped.append(cell)
        return deduped

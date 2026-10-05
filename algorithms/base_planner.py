"""
HospitalRobotNav — Abstract Base Planner
==========================================
Defines the interface that every path planning algorithm must implement.

Design Pattern: Template Method + Strategy

All planners share:
    - A common `plan()` interface
    - Unified `PlannerResult` output type
    - Built-in performance metrics collection
    - Reset capability for repeated planning
    - Visualization data (open/closed sets)

New planners are added by:
    1. Subclassing BasePlanner
    2. Implementing `_plan_impl()` → List[GridPos]
    3. Registering in PlannerFactory

ROS2 Note:
    In a ROS2 deployment, this interface maps to the nav2_core::GlobalPlanner
    plugin API, with `plan()` equivalent to `createPlan()`.
"""

from __future__ import annotations

import time
import tracemalloc
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Set, Tuple

from environment.occupancy_grid import OccupancyGrid
from algorithms.heuristics import HeuristicFn, HeuristicType, get_heuristic, DEFAULT_HEURISTIC_TYPE
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]


# ─────────────────────────────────────────────────────────────────────────────
# Planner Result
# ─────────────────────────────────────────────────────────────────────────────

class PlannerStatus(Enum):
    """Exit status of a planning attempt."""
    SUCCESS      = auto()   # Valid path found
    NO_PATH      = auto()   # Goal unreachable from start
    TIMEOUT      = auto()   # Exceeded max iteration limit
    INVALID_GOAL = auto()   # Goal cell is a wall or out of bounds
    NOT_RUN      = auto()   # plan() has not been called


@dataclass
class PlannerMetrics:
    """
    Performance metrics for a single planning run.

    Collected automatically by BasePlanner.plan() wrapper.
    """
    planner_name:      str   = ""
    heuristic_name:    str   = ""
    planning_time_ms:  float = 0.0    # Wall-clock planning time
    nodes_expanded:    int   = 0      # Nodes popped from open list
    nodes_generated:   int   = 0      # Nodes added to open list
    path_length:       float = 0.0    # Euclidean path length (cells)
    path_cells:        int   = 0      # Number of cells in path
    memory_kb:         float = 0.0    # Peak memory during planning (KB)
    open_list_peak:    int   = 0      # Maximum open list size
    turns:             int   = 0      # Number of direction changes


@dataclass
class PlannerResult:
    """
    Complete result from a planning run.

    Attributes:
        status:       PlannerStatus enum.
        path:         Ordered list of (row, col) from start to goal.
        open_set:     Final open list cells (for visualization).
        closed_set:   Final closed list cells (for visualization).
        metrics:      Performance metrics.
    """
    status:     PlannerStatus            = PlannerStatus.NOT_RUN
    path:       List[GridPos]            = field(default_factory=list)
    open_set:   Set[GridPos]             = field(default_factory=set)
    closed_set: Set[GridPos]             = field(default_factory=set)
    metrics:    PlannerMetrics           = field(default_factory=PlannerMetrics)

    @property
    def success(self) -> bool:
        """True if planning succeeded and a path was found."""
        return self.status == PlannerStatus.SUCCESS

    @property
    def is_empty(self) -> bool:
        """True if no path exists."""
        return not self.path


# ─────────────────────────────────────────────────────────────────────────────
# Abstract Base Planner
# ─────────────────────────────────────────────────────────────────────────────

class BasePlanner(ABC):
    """
    Abstract base class for all path planners.

    Subclasses MUST implement:
        _plan_impl(start, goal) → List[GridPos]

    Subclasses SHOULD implement:
        reset()
        get_open_set()
        get_closed_set()
        get_nodes_expanded()

    The `plan()` method handles:
        - Input validation
        - Timing and memory measurement
        - Error handling
        - Metrics collection

    Attributes:
        _grid:        OccupancyGrid instance.
        _heuristic:   Heuristic function (for A*-family planners).
        _max_iter:    Maximum node expansions before timeout.
        _result:      Last PlannerResult from plan() call.
    """

    #: Maximum node expansions before timeout (safety guard)
    DEFAULT_MAX_ITER: int = 500_000

    def __init__(
        self,
        occupancy_grid: OccupancyGrid,
        heuristic_type: HeuristicType = DEFAULT_HEURISTIC_TYPE,
        heuristic_weight: float = 1.0,
        max_iterations: int = DEFAULT_MAX_ITER,
        use_8_connected: bool = True,
    ) -> None:
        """
        Initialize the planner.

        Args:
            occupancy_grid:    The grid to plan on.
            heuristic_type:    Which heuristic to use (ignored by Dijkstra).
            heuristic_weight:  Inflation weight for weighted A*.
            max_iterations:    Node expansion limit.
            use_8_connected:   If True, use 8-directional moves; else 4.
        """
        self._grid            = occupancy_grid
        self._heuristic       = get_heuristic(heuristic_type, heuristic_weight)
        self._heuristic_name  = heuristic_type.name
        self._max_iter        = max_iterations
        self._use_8_connected = use_8_connected
        self._result          = PlannerResult()

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def plan(self, start: GridPos, goal: GridPos) -> PlannerResult:
        """
        Plan a path from `start` to `goal`.

        Template method — calls _plan_impl() and wraps with metrics.

        Args:
            start: Starting grid cell (row, col).
            goal:  Goal grid cell (row, col).

        Returns:
            PlannerResult with path, status, and metrics.
        """
        # ── Validation ─────────────────────────────────────────────────────────
        result = self._validate_inputs(start, goal)
        if result is not None:
            self._result = result
            return result

        self.reset()

        # ── Time and memory measurement ────────────────────────────────────────
        tracemalloc.start()
        t_start = time.perf_counter()

        try:
            path = self._plan_impl(start, goal)
        except Exception as exc:
            log.error("%s planning failed with exception: %s", self.name, exc)
            path = []

        t_end  = time.perf_counter()
        _, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # ── Build result ───────────────────────────────────────────────────────
        from utilities.geometry import path_length, count_turns

        metrics = PlannerMetrics(
            planner_name     = self.name,
            heuristic_name   = self._heuristic_name,
            planning_time_ms = (t_end - t_start) * 1000.0,
            nodes_expanded   = self.get_nodes_expanded(),
            nodes_generated  = self.get_nodes_generated(),
            path_length      = path_length(path) if path else 0.0,
            path_cells       = len(path),
            memory_kb        = peak_mem / 1024.0,
            open_list_peak   = self.get_open_list_peak(),
            turns            = count_turns(path) if len(path) >= 3 else 0,
        )

        status = PlannerStatus.SUCCESS if path else PlannerStatus.NO_PATH

        self._result = PlannerResult(
            status     = status,
            path       = path,
            open_set   = self.get_open_set(),
            closed_set = self.get_closed_set(),
            metrics    = metrics,
        )

        log.info(
            "%s: %s | path=%d cells | time=%.1f ms | expanded=%d",
            self.name,
            status.name,
            len(path),
            metrics.planning_time_ms,
            metrics.nodes_expanded,
        )

        return self._result

    # ─────────────────────────────────────────────────────────────────────────
    # Abstract methods (must be implemented by subclasses)
    # ─────────────────────────────────────────────────────────────────────────

    @abstractmethod
    def _plan_impl(self, start: GridPos, goal: GridPos) -> List[GridPos]:
        """
        Core planning logic.

        Args:
            start: Validated start cell.
            goal:  Validated goal cell.

        Returns:
            List of (row, col) cells from start to goal (inclusive),
            or empty list if no path found.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this planner (e.g., "A*")."""
        ...

    # ─────────────────────────────────────────────────────────────────────────
    # Optional overrides (provide visualization data)
    # ─────────────────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset internal planner state for a new planning run."""
        pass

    def get_open_set(self) -> Set[GridPos]:
        """Return the set of cells currently in the open list."""
        return set()

    def get_closed_set(self) -> Set[GridPos]:
        """Return the set of cells in the closed list."""
        return set()

    def get_nodes_expanded(self) -> int:
        """Return number of nodes popped from open list."""
        return 0

    def get_nodes_generated(self) -> int:
        """Return number of nodes added to open list."""
        return 0

    def get_open_list_peak(self) -> int:
        """Return peak size of open list during planning."""
        return 0

    # ─────────────────────────────────────────────────────────────────────────
    # Helper: get neighbors from grid
    # ─────────────────────────────────────────────────────────────────────────

    def _get_neighbors(
        self,
        row: int,
        col: int,
    ) -> List[Tuple[GridPos, float]]:
        """
        Retrieve walkable neighbors with edge costs from the occupancy grid.

        Uses 8-connected or 4-connected movement based on `_use_8_connected`.

        Returns:
            List of ((r, c), cost) tuples.
        """
        if self._use_8_connected:
            return self._grid.get_neighbors_8(row, col)
        return self._grid.get_neighbors_4(row, col)

    # ─────────────────────────────────────────────────────────────────────────
    # Helper: path reconstruction from parent dict
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _reconstruct_path(
        came_from: dict,
        start: GridPos,
        goal: GridPos,
    ) -> List[GridPos]:
        """
        Reconstruct path by back-tracking parent pointers.

        Args:
            came_from: Dict mapping cell → parent cell.
            start:     Start cell.
            goal:      Goal cell.

        Returns:
            Ordered path from start to goal (inclusive).
        """
        path: List[GridPos] = []
        current = goal

        while current != start:
            path.append(current)
            parent = came_from.get(current)
            if parent is None:
                return []   # Broken chain — should not happen
            current = parent

        path.append(start)
        path.reverse()
        return path

    # ─────────────────────────────────────────────────────────────────────────
    # Validation
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_inputs(
        self,
        start: GridPos,
        goal: GridPos,
    ) -> Optional[PlannerResult]:
        """
        Validate start and goal cells.

        Returns:
            PlannerResult with failure status if invalid, else None.
        """
        if not self._grid.is_free(*start):
            # Try to snap to nearest free cell
            snapped = self._grid.find_nearest_free(*start)
            if snapped is None:
                log.error("Start (%d,%d) is blocked with no free neighbor.", *start)
                return PlannerResult(status=PlannerStatus.INVALID_GOAL)
            log.warning("Start snapped from (%d,%d) to (%d,%d)", *start, *snapped)

        if not self._grid.is_free(*goal):
            snapped = self._grid.find_nearest_free(*goal)
            if snapped is None:
                log.error("Goal (%d,%d) is blocked with no free neighbor.", *goal)
                return PlannerResult(status=PlannerStatus.INVALID_GOAL)
            log.warning("Goal snapped from (%d,%d) to (%d,%d)", *goal, *snapped)

        return None

    @property
    def last_result(self) -> PlannerResult:
        """Return the last PlannerResult from the most recent plan() call."""
        return self._result

    def set_heuristic(self, heuristic_type: HeuristicType, weight: float = 1.0) -> None:
        """Change the heuristic at runtime."""
        self._heuristic = get_heuristic(heuristic_type, weight)
        self._heuristic_name = heuristic_type.name
        log.info("%s: heuristic changed to %s (w=%.1f)", self.name, heuristic_type.name, weight)

    def __repr__(self) -> str:
        return f"{self.name}(heuristic={self._heuristic_name}, 8-conn={self._use_8_connected})"

"""
HospitalRobotNav — Planner Factory
=====================================
Factory pattern for creating and switching between path planners at runtime.

Design Pattern: Abstract Factory + Strategy

The PlannerFactory decouples the robot controller from specific planner
implementations. The controller calls plan(start, goal) without knowing
which algorithm is active.

Supported planners:
    A*        — Standard optimal grid planner
    Dijkstra  — Uniform-cost baseline
    Theta*    — Any-angle smoother paths
    Hybrid A* — Kinematically feasible (continuous state)
    D* Lite   — Dynamic replanning

ROS2 Note:
    Maps to nav2_core::GlobalPlanner plugin selection via:
    ros2 param set /planner_server plugin_names "['GridBased']"
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Dict, List, Optional, Type

from algorithms.base_planner import BasePlanner, PlannerResult
from algorithms.astar import AStarPlanner
from algorithms.dijkstra import DijkstraPlanner
from algorithms.theta_star import ThetaStarPlanner
from algorithms.hybrid_astar import HybridAStarPlanner
from algorithms.dstar_lite import DStarLitePlanner
from algorithms.heuristics import HeuristicType
from environment.occupancy_grid import OccupancyGrid
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = tuple


class PlannerType(Enum):
    """Available path planning algorithms."""
    ASTAR        = auto()
    DIJKSTRA     = auto()
    THETA_STAR   = auto()
    HYBRID_ASTAR = auto()
    DSTAR_LITE   = auto()


# Display name for each planner type
PLANNER_NAMES: Dict[PlannerType, str] = {
    PlannerType.ASTAR:        "A*",
    PlannerType.DIJKSTRA:     "Dijkstra",
    PlannerType.THETA_STAR:   "Theta*",
    PlannerType.HYBRID_ASTAR: "Hybrid A*",
    PlannerType.DSTAR_LITE:   "D* Lite",
}

# Planner class registry
_PLANNER_CLASSES: Dict[PlannerType, Type[BasePlanner]] = {
    PlannerType.ASTAR:        AStarPlanner,
    PlannerType.DIJKSTRA:     DijkstraPlanner,
    PlannerType.THETA_STAR:   ThetaStarPlanner,
    PlannerType.HYBRID_ASTAR: HybridAStarPlanner,
    PlannerType.DSTAR_LITE:   DStarLitePlanner,
}


class PlannerFactory:
    """
    Creates and manages path planner instances.

    Maintains one active planner at a time. Allows runtime switching
    between algorithms without modifying the robot controller.

    Usage:
        factory = PlannerFactory(occupancy_grid)
        factory.set_planner(PlannerType.THETA_STAR)
        result = factory.plan(start=(80,11), goal=(18,60))
    """

    def __init__(
        self,
        occupancy_grid: OccupancyGrid,
        default_planner: PlannerType = PlannerType.ASTAR,
        default_heuristic: HeuristicType = HeuristicType.DIAGONAL,
    ) -> None:
        self._grid            = occupancy_grid
        self._planner_type    = default_planner
        self._heuristic_type  = default_heuristic
        self._active_planner: Optional[BasePlanner] = None
        self._planners:       Dict[PlannerType, BasePlanner] = {}

        # Initialize default planner
        self._build_planner(default_planner)
        log.info(
            "PlannerFactory initialized: %s + %s heuristic",
            PLANNER_NAMES[default_planner], default_heuristic.name,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Planner Selection
    # ─────────────────────────────────────────────────────────────────────────

    def set_planner(self, planner_type: PlannerType) -> None:
        """
        Switch the active path planning algorithm.

        Args:
            planner_type: New PlannerType to activate.
        """
        if planner_type not in _PLANNER_CLASSES:
            raise ValueError(f"Unknown planner type: {planner_type}")

        self._planner_type = planner_type
        if planner_type not in self._planners:
            self._build_planner(planner_type)

        self._active_planner = self._planners[planner_type]
        log.info("Planner switched to: %s", PLANNER_NAMES[planner_type])

    def set_heuristic(self, heuristic_type: HeuristicType, weight: float = 1.0) -> None:
        """
        Change the heuristic for all A*-family planners.

        Args:
            heuristic_type: New heuristic to apply.
            weight:         Optional inflation weight.
        """
        self._heuristic_type = heuristic_type
        for planner in self._planners.values():
            planner.set_heuristic(heuristic_type, weight)
        log.info("Heuristic changed to: %s (w=%.1f)", heuristic_type.name, weight)

    # ─────────────────────────────────────────────────────────────────────────
    # Planning
    # ─────────────────────────────────────────────────────────────────────────

    def plan(self, start: GridPos, goal: GridPos) -> PlannerResult:
        """
        Plan a path using the currently active algorithm.

        Args:
            start: Starting grid cell (row, col).
            goal:  Goal grid cell (row, col).

        Returns:
            PlannerResult with path, status, and metrics.
        """
        if self._active_planner is None:
            raise RuntimeError("No active planner set.")
        return self._active_planner.plan(start, goal)

    def replan(self, current_pos: GridPos, goal: GridPos) -> PlannerResult:
        """
        Re-plan from current position to goal.

        For D* Lite, uses incremental repair.
        For other planners, replans from scratch.

        Args:
            current_pos: Current robot position.
            goal:        Original goal.

        Returns:
            New PlannerResult.
        """
        if isinstance(self._active_planner, DStarLitePlanner):
            path = self._active_planner.replan(current_pos)
            # Wrap in PlannerResult
            from algorithms.base_planner import PlannerStatus, PlannerMetrics
            from utilities.geometry import path_length
            status = PlannerStatus.SUCCESS if path else PlannerStatus.NO_PATH
            return PlannerResult(
                status=status,
                path=path,
                metrics=PlannerMetrics(
                    planner_name="D* Lite",
                    path_length=path_length(path),
                    path_cells=len(path),
                ),
            )
        else:
            return self.plan(current_pos, goal)

    def notify_obstacle_change(
        self,
        changed_cells: List[GridPos],
        current_pos: GridPos,
    ) -> None:
        """
        Notify D* Lite of environment changes.

        Only relevant for D* Lite planner. No-op for others.

        Args:
            changed_cells: List of cells whose costs changed.
            current_pos:   Current robot position.
        """
        if isinstance(self._active_planner, DStarLitePlanner):
            self._active_planner.notify_obstacle_change(changed_cells, current_pos)

    # ─────────────────────────────────────────────────────────────────────────
    # Queries
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def active_planner(self) -> Optional[BasePlanner]:
        """Return the currently active planner instance."""
        return self._active_planner

    @property
    def active_planner_type(self) -> PlannerType:
        """Return the active planner type."""
        return self._planner_type

    @property
    def active_planner_name(self) -> str:
        """Return display name of the active planner."""
        return PLANNER_NAMES.get(self._planner_type, "Unknown")

    def get_all_planner_names(self) -> List[str]:
        """Return list of all available planner display names."""
        return list(PLANNER_NAMES.values())

    def get_all_planner_types(self) -> List[PlannerType]:
        """Return list of all PlannerType enum values."""
        return list(PlannerType)

    # ─────────────────────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────────────────────

    def _build_planner(self, planner_type: PlannerType) -> None:
        """Instantiate and cache a planner of given type."""
        cls = _PLANNER_CLASSES[planner_type]
        planner = cls(
            occupancy_grid=self._grid,
            heuristic_type=self._heuristic_type,
        )
        self._planners[planner_type] = planner
        self._active_planner = planner

    def __repr__(self) -> str:
        return (
            f"PlannerFactory(active={self.active_planner_name}, "
            f"heuristic={self._heuristic_type.name})"
        )

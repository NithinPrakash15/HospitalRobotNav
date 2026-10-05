"""
HospitalRobotNav — A* Path Planning Algorithm
===============================================
Complete, from-scratch implementation of the A* search algorithm
with full visualization data export (open list, closed list, expansion order).

A* Algorithm:
    f(n) = g(n) + h(n)
    g(n) = actual cost from start to n
    h(n) = heuristic estimate from n to goal
    f(n) = estimated total cost through n

Properties:
    - Completeness: Yes (finds path if one exists)
    - Optimality:   Yes (with admissible, consistent heuristic)
    - Time:         O(b^d) where b=branching factor, d=solution depth
    - Space:        O(b^d) — stores all generated nodes

Implementation Details:
    - Priority queue: custom binary min-heap (utilities/priority_queue.py)
    - Tie-breaking:   Prefer higher g (deeper) nodes via tie-break counter
    - Open list:      Heap of (f, tie, node)
    - Closed list:    Set of expanded nodes
    - Parent map:     Dict for path reconstruction
    - g_cost map:     Dict for current best costs

Reference:
    Hart, P.E., Nilsson, N.J., Raphael, B. (1968). "A Formal Basis for the
    Heuristic Determination of Minimum Cost Paths." IEEE Transactions on
    Systems Science and Cybernetics, 4(2), 100–107.
"""

from __future__ import annotations

import heapq
from typing import Dict, List, Optional, Set, Tuple

from algorithms.base_planner import BasePlanner, PlannerStatus
from algorithms.heuristics import HeuristicType
from environment.occupancy_grid import OccupancyGrid
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]


class AStarPlanner(BasePlanner):
    """
    A* shortest-path planner for the hospital occupancy grid.

    Supports:
        - 4-connected and 8-connected movement
        - All heuristic types (Manhattan, Euclidean, Diagonal, Chebyshev)
        - Weighted A* (ε-suboptimal for speed)
        - Step-by-step visualization data

    Attributes:
        _open_set:      Cells currently in the open list (for rendering).
        _closed_set:    Cells in the closed list (expanded).
        _nodes_expanded: Count of nodes popped.
        _nodes_generated: Count of nodes pushed.
        _open_peak:     Maximum open list size.
        _expansion_order: Ordered list of expanded nodes (for animation).
    """

    def __init__(
        self,
        occupancy_grid: OccupancyGrid,
        heuristic_type: HeuristicType = HeuristicType.DIAGONAL,
        heuristic_weight: float = 1.0,
        max_iterations: int = BasePlanner.DEFAULT_MAX_ITER,
        use_8_connected: bool = True,
    ) -> None:
        super().__init__(
            occupancy_grid=occupancy_grid,
            heuristic_type=heuristic_type,
            heuristic_weight=heuristic_weight,
            max_iterations=max_iterations,
            use_8_connected=use_8_connected,
        )
        self._open_set:       Set[GridPos] = set()
        self._closed_set:     Set[GridPos] = set()
        self._nodes_expanded: int = 0
        self._nodes_generated: int = 0
        self._open_peak:      int = 0
        self._expansion_order: List[GridPos] = []

    # ─────────────────────────────────────────────────────────────────────────
    # BasePlanner interface
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "A*"

    def reset(self) -> None:
        """Clear all internal state for a fresh planning run."""
        self._open_set.clear()
        self._closed_set.clear()
        self._nodes_expanded  = 0
        self._nodes_generated = 0
        self._open_peak       = 0
        self._expansion_order.clear()

    def get_open_set(self) -> Set[GridPos]:
        return set(self._open_set)

    def get_closed_set(self) -> Set[GridPos]:
        return set(self._closed_set)

    def get_nodes_expanded(self) -> int:
        return self._nodes_expanded

    def get_nodes_generated(self) -> int:
        return self._nodes_generated

    def get_open_list_peak(self) -> int:
        return self._open_peak

    # ─────────────────────────────────────────────────────────────────────────
    # Core A* Implementation
    # ─────────────────────────────────────────────────────────────────────────

    def _plan_impl(self, start: GridPos, goal: GridPos) -> List[GridPos]:
        """
        Execute A* from `start` to `goal`.

        Data structures:
            heap:       [(f, tie_break, node)] — min-heap
            g_cost:     {node: best_g}         — accumulated cost
            came_from:  {node: parent}         — for reconstruction

        Returns:
            Ordered path from start to goal, or [] if none found.
        """
        # ── Initialization ─────────────────────────────────────────────────
        h_start = self._heuristic(start, goal)
        f_start = 0.0 + h_start

        # Heap entry: (f, tie_break, (row, col))
        heap: List[Tuple[float, int, GridPos]] = []
        tie_counter = 0
        heapq.heappush(heap, (f_start, tie_counter, start))

        g_cost:    Dict[GridPos, float] = {start: 0.0}
        came_from: Dict[GridPos, Optional[GridPos]] = {start: None}

        self._open_set.add(start)
        self._nodes_generated = 1

        # ── Main Loop ──────────────────────────────────────────────────────
        while heap:
            f_current, _, current = heapq.heappop(heap)

            # Skip stale entries (lazy deletion)
            if current in self._closed_set:
                continue
            if current not in self._open_set:
                continue

            # ── Expand node ────────────────────────────────────────────────
            self._open_set.discard(current)
            self._closed_set.add(current)
            self._expansion_order.append(current)
            self._nodes_expanded += 1

            # ── Goal check ─────────────────────────────────────────────────
            if current == goal:
                log.debug(
                    "A* reached goal in %d expansions", self._nodes_expanded
                )
                return self._reconstruct_path(came_from, start, goal)

            # ── Timeout check ──────────────────────────────────────────────
            if self._nodes_expanded >= self._max_iter:
                log.warning("A* exceeded max iterations (%d)", self._max_iter)
                return []

            # ── Neighbor expansion ─────────────────────────────────────────
            g_current = g_cost[current]

            for neighbor, edge_cost in self._get_neighbors(*current):
                if neighbor in self._closed_set:
                    continue

                g_new = g_current + edge_cost

                # Accept if better than known cost (or never seen before)
                if g_new < g_cost.get(neighbor, float("inf")):
                    came_from[neighbor] = current
                    g_cost[neighbor]    = g_new
                    h                  = self._heuristic(neighbor, goal)
                    f_new              = g_new + h

                    tie_counter += 1
                    # Tie-break: prefer larger g (closer to goal)
                    # Encode as -g in tie-break slot: lower = better
                    heapq.heappush(heap, (f_new, -g_new, neighbor))

                    self._open_set.add(neighbor)
                    self._nodes_generated += 1

                    # Track open list peak
                    if len(self._open_set) > self._open_peak:
                        self._open_peak = len(self._open_set)

        # Heap exhausted — no path
        log.debug("A* found no path after %d expansions", self._nodes_expanded)
        return []

    # ─────────────────────────────────────────────────────────────────────────
    # Visualization Support
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def expansion_order(self) -> List[GridPos]:
        """
        Return the ordered list of expanded nodes.

        Used by the renderer to animate A* node expansion step-by-step.
        """
        return list(self._expansion_order)

    def get_expansion_frame(self, frame: int) -> Tuple[Set[GridPos], Set[GridPos]]:
        """
        Get open/closed sets at a specific animation frame.

        Args:
            frame: Frame index (number of expansions shown so far).

        Returns:
            (open_set_at_frame, closed_set_at_frame) for rendering.
        """
        closed_at_frame: Set[GridPos] = set(self._expansion_order[:frame])
        return set(), closed_at_frame

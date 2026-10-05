"""
HospitalRobotNav — Dijkstra's Algorithm
=========================================
Complete, from-scratch implementation of Dijkstra's shortest-path algorithm.

Dijkstra's Algorithm:
    A special case of A* where h(n) = 0 (no heuristic).
    Guarantees optimal shortest paths in weighted graphs with non-negative costs.

    f(n) = g(n)   (no heuristic term)
    
Properties:
    - Completeness: Yes
    - Optimality:   Yes (for non-negative edge weights)
    - Time:         O((V + E) log V) with binary heap
    - Space:        O(V)
    - Explores in all directions uniformly (no directional bias)

When to use:
    - When heuristic is unavailable or unreliable
    - As a ground-truth baseline for A* performance comparison
    - When cost map is highly non-uniform (heuristic may mislead A*)
    - For computing all-pairs shortest paths (flood fill mode)

Reference:
    Dijkstra, E.W. (1959). "A note on two problems in connexion with graphs."
    Numerische Mathematik, 1(1), 269–271.
"""

from __future__ import annotations

import heapq
from typing import Dict, List, Optional, Set, Tuple

from algorithms.base_planner import BasePlanner
from algorithms.heuristics import HeuristicType
from environment.occupancy_grid import OccupancyGrid
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]


class DijkstraPlanner(BasePlanner):
    """
    Dijkstra's shortest-path planner.

    Identical to A* but with h(n) = 0, exploring uniformly in all directions.
    Useful as a performance baseline and for uniform-cost planning.

    Attributes:
        _open_set:        Cells in the priority queue (frontier).
        _closed_set:      Expanded cells.
        _nodes_expanded:  Expansion count.
        _nodes_generated: Generation count.
        _open_peak:       Peak frontier size.
    """

    def __init__(
        self,
        occupancy_grid: OccupancyGrid,
        heuristic_type: HeuristicType = HeuristicType.MANHATTAN,  # unused
        heuristic_weight: float = 1.0,
        max_iterations: int = BasePlanner.DEFAULT_MAX_ITER,
        use_8_connected: bool = True,
    ) -> None:
        # Pass heuristic for API consistency but it is NOT used in Dijkstra
        super().__init__(
            occupancy_grid=occupancy_grid,
            heuristic_type=heuristic_type,
            heuristic_weight=heuristic_weight,
            max_iterations=max_iterations,
            use_8_connected=use_8_connected,
        )
        self._open_set:        Set[GridPos] = set()
        self._closed_set:      Set[GridPos] = set()
        self._nodes_expanded:  int = 0
        self._nodes_generated: int = 0
        self._open_peak:       int = 0

    # ─────────────────────────────────────────────────────────────────────────
    # BasePlanner interface
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "Dijkstra"

    def reset(self) -> None:
        self._open_set.clear()
        self._closed_set.clear()
        self._nodes_expanded  = 0
        self._nodes_generated = 0
        self._open_peak       = 0

    def get_open_set(self)   -> Set[GridPos]: return set(self._open_set)
    def get_closed_set(self) -> Set[GridPos]: return set(self._closed_set)
    def get_nodes_expanded(self)  -> int: return self._nodes_expanded
    def get_nodes_generated(self) -> int: return self._nodes_generated
    def get_open_list_peak(self)  -> int: return self._open_peak

    # ─────────────────────────────────────────────────────────────────────────
    # Core Dijkstra Implementation
    # ─────────────────────────────────────────────────────────────────────────

    def _plan_impl(self, start: GridPos, goal: GridPos) -> List[GridPos]:
        """
        Execute Dijkstra's algorithm from `start` to `goal`.

        Data structures:
            heap:       [(g, node)]          — min-heap by accumulated cost
            g_cost:     {node: best_g}       — shortest known distance
            came_from:  {node: parent}       — parent pointers

        Returns:
            Path from start to goal, or [] if unreachable.
        """
        # ── Initialization ─────────────────────────────────────────────────
        heap: List[Tuple[float, GridPos]] = [(0.0, start)]
        g_cost:    Dict[GridPos, float]           = {start: 0.0}
        came_from: Dict[GridPos, Optional[GridPos]] = {start: None}

        self._open_set.add(start)
        self._nodes_generated = 1

        # ── Main Loop ──────────────────────────────────────────────────────
        while heap:
            g_current, current = heapq.heappop(heap)

            # Skip stale entries
            if current in self._closed_set:
                continue

            self._open_set.discard(current)
            self._closed_set.add(current)
            self._nodes_expanded += 1

            # ── Goal check ─────────────────────────────────────────────────
            if current == goal:
                log.debug(
                    "Dijkstra reached goal in %d expansions", self._nodes_expanded
                )
                return self._reconstruct_path(came_from, start, goal)

            # ── Timeout check ──────────────────────────────────────────────
            if self._nodes_expanded >= self._max_iter:
                log.warning("Dijkstra exceeded max iterations")
                return []

            # ── Stale entry check (g_cost already superseded) ──────────────
            if g_current > g_cost.get(current, float("inf")):
                continue

            # ── Neighbor expansion ─────────────────────────────────────────
            for neighbor, edge_cost in self._get_neighbors(*current):
                if neighbor in self._closed_set:
                    continue

                g_new = g_current + edge_cost

                if g_new < g_cost.get(neighbor, float("inf")):
                    came_from[neighbor] = current
                    g_cost[neighbor]    = g_new
                    heapq.heappush(heap, (g_new, neighbor))
                    self._open_set.add(neighbor)
                    self._nodes_generated += 1

                    if len(self._open_set) > self._open_peak:
                        self._open_peak = len(self._open_set)

        log.debug("Dijkstra: no path found after %d expansions", self._nodes_expanded)
        return []

    # ─────────────────────────────────────────────────────────────────────────
    # Flood-fill mode: compute distances from source to ALL reachable cells
    # ─────────────────────────────────────────────────────────────────────────

    def compute_distance_map(self, source: GridPos) -> Dict[GridPos, float]:
        """
        Run Dijkstra from `source` to ALL reachable cells.

        Returns a distance map useful for:
            - Nearest-room queries
            - Battery-aware planning
            - Multi-agent task assignment

        Args:
            source: Starting grid cell.

        Returns:
            Dict mapping (row, col) → shortest distance from source.
        """
        heap: List[Tuple[float, GridPos]] = [(0.0, source)]
        dist: Dict[GridPos, float] = {source: 0.0}
        visited: Set[GridPos] = set()

        while heap:
            d, current = heapq.heappop(heap)
            if current in visited:
                continue
            visited.add(current)

            for neighbor, edge_cost in self._get_neighbors(*current):
                new_d = d + edge_cost
                if new_d < dist.get(neighbor, float("inf")):
                    dist[neighbor] = new_d
                    heapq.heappush(heap, (new_d, neighbor))

        return dist

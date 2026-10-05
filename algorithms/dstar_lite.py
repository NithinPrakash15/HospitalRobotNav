"""
HospitalRobotNav — D* Lite Dynamic Replanning
===============================================
Complete, from-scratch implementation of D* Lite — an incremental
heuristic search algorithm that efficiently re-plans when obstacles
change (dynamic environments).

D* Lite vs A*:
    A*:      Replans from scratch when environment changes
    D* Lite: Incrementally repairs the existing plan → only re-expands
             nodes affected by the change → O(k log n) per update

Why D* Lite for hospital robots:
    Hospital environments have frequent dynamic obstacles:
    - Staff crossing corridors
    - Doors opening/closing
    - Stretchers being moved
    - Other robots

    D* Lite handles these incrementally without full replanning.

Algorithm Overview:
    D* Lite maintains a lookuptable of rhs-values (one-step lookahead costs)
    and g-values (estimated costs to goal). Searches BACKWARD from goal.
    
    Key insight: Plan backward from goal → forward search becomes an
    interpolation problem after environment changes.

Keys:
    k(s) = [min(g(s), rhs(s)) + h(s_start, s); min(g(s), rhs(s))]
    Lexicographically ordered in the priority queue.

Reference:
    Koenig, S. & Likhachev, M. (2002). "D* Lite." AAAI-02, pp. 476–483.
    
    Koenig, S. & Likhachev, M. (2005). "Fast replanning for navigation
    in unknown terrain." IEEE Trans. Robotics, 21(3), 354–363.
"""

from __future__ import annotations

import math
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from algorithms.base_planner import BasePlanner
from algorithms.heuristics import HeuristicType, diagonal
from environment.occupancy_grid import OccupancyGrid
from utilities.priority_queue import IndexedPriorityQueue
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]
DStarKey = Tuple[float, float]   # (k1, k2)

INF = float("inf")


class DStarLitePlanner(BasePlanner):
    """
    D* Lite incremental dynamic replanning algorithm.

    Plans backward from goal to start, then re-plans efficiently
    when dynamic obstacles change the cost map.

    Lifecycle:
        1. initialize(start, goal)    → set up initial backward search
        2. plan(start, goal)          → run initial planning
        3. After obstacle change:
           update_edge(u, v, new_cost) → mark edge changed
           replan(current_pos)         → repair path incrementally

    Attributes:
        _g:    Dict[GridPos, float]  — g-values (cost from node to goal)
        _rhs:  Dict[GridPos, float]  — one-step lookahead values
        _U:    IndexedPriorityQueue  — priority queue of inconsistent nodes
        _start: Current robot position (updated as robot moves)
        _goal:  Goal cell
        _k_m:  Key modifier (accumulated position movement)
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
        # D* Lite state
        self._g:    Dict[GridPos, float] = {}
        self._rhs:  Dict[GridPos, float] = {}
        self._U:    IndexedPriorityQueue = IndexedPriorityQueue()
        self._k_m:  float = 0.0
        self._start: Optional[GridPos] = None
        self._goal:  Optional[GridPos] = None
        self._last_start: Optional[GridPos] = None

        # Visualization
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
        return "D* Lite"

    def reset(self) -> None:
        self._g.clear()
        self._rhs.clear()
        self._U.clear()
        self._k_m          = 0.0
        self._start        = None
        self._goal         = None
        self._last_start   = None
        self._open_set.clear()
        self._closed_set.clear()
        self._nodes_expanded  = 0
        self._nodes_generated = 0
        self._open_peak       = 0

    def get_open_set(self)        -> Set[GridPos]: return set(self._open_set)
    def get_closed_set(self)      -> Set[GridPos]: return set(self._closed_set)
    def get_nodes_expanded(self)  -> int: return self._nodes_expanded
    def get_nodes_generated(self) -> int: return self._nodes_generated
    def get_open_list_peak(self)  -> int: return self._open_peak

    # ─────────────────────────────────────────────────────────────────────────
    # Core D* Lite Implementation
    # ─────────────────────────────────────────────────────────────────────────

    def _plan_impl(self, start: GridPos, goal: GridPos) -> List[GridPos]:
        """
        Run the complete D* Lite initial planning.

        Performs backward search from goal to start.

        Args:
            start: Robot starting position.
            goal:  Destination cell.

        Returns:
            Path from start to goal, or [] if unreachable.
        """
        self._start      = start
        self._goal       = goal
        self._last_start = start

        # D* Lite initialization: rhs(goal) = 0, all others = ∞
        self._rhs[goal] = 0.0
        self._U.push(goal, self._calculate_key(goal))
        self._open_set.add(goal)
        self._nodes_generated = 1

        # Run backward Dijkstra-like search
        self._compute_shortest_path(start)

        if self._g.get(start, INF) == INF:
            log.warning("D* Lite: no path found from %s to %s", start, goal)
            return []

        return self._extract_path(start, goal)

    def _calculate_key(self, s: GridPos) -> float:
        """
        Compute the priority key for node s.

        D* Lite uses lexicographic (k1, k2) keys.
        We store as a single float: k1 + ε*k2 (ε very small).

        k1 = min(g(s), rhs(s)) + h(s_start, s) + k_m
        k2 = min(g(s), rhs(s))

        Args:
            s: Grid cell.

        Returns:
            Float priority (lower = higher priority).
        """
        gs   = self._g.get(s, INF)
        rhs  = self._rhs.get(s, INF)
        min_val = min(gs, rhs)

        if self._start is not None:
            h = self._heuristic(self._start, s)
        else:
            h = 0.0

        k1 = min_val + h + self._k_m
        k2 = min_val
        # Encode as scalar: k1 dominates, k2 breaks ties
        return k1 + 1e-6 * k2

    def _update_vertex(self, u: GridPos) -> None:
        """
        Update vertex u's rhs-value and priority queue status.

        Called after any cost change affecting u.
        """
        if u != self._goal:
            # rhs(u) = min over successors v: c(u,v) + g(v)
            best_rhs = INF
            for (v, cost) in self._get_neighbors(*u):
                g_v = self._g.get(v, INF)
                if g_v + cost < best_rhs:
                    best_rhs = g_v + cost
            self._rhs[u] = best_rhs

        # Remove from U if present
        self._U.remove(u)
        self._open_set.discard(u)

        # Re-insert if locally inconsistent
        if self._g.get(u, INF) != self._rhs.get(u, INF):
            key = self._calculate_key(u)
            self._U.push(u, key)
            self._open_set.add(u)
            self._nodes_generated += 1

    def _compute_shortest_path(self, start: GridPos) -> None:
        """
        Expand nodes until start is locally consistent.

        This is the main D* Lite loop.
        """
        iterations = 0

        while not self._U.is_empty():
            if iterations >= self._max_iter:
                log.warning("D* Lite exceeded max iterations")
                break
            iterations += 1

            # Check if start is consistent
            start_key = self._calculate_key(start)
            try:
                top_key, u = self._U.peek()
            except IndexError:
                break

            g_start   = self._g.get(start, INF)
            rhs_start = self._rhs.get(start, INF)

            if top_key >= start_key and g_start == rhs_start:
                break   # Start is consistent — done

            k_old, u = self._U.pop_min()
            self._open_set.discard(u)
            self._closed_set.add(u)
            self._nodes_expanded += 1

            if len(self._open_set) > self._open_peak:
                self._open_peak = len(self._open_set)

            g_u   = self._g.get(u, INF)
            rhs_u = self._rhs.get(u, INF)
            k_new = self._calculate_key(u)

            if k_old < k_new:
                # Key increased — re-insert with updated key
                self._U.push(u, k_new)
                self._open_set.add(u)
            elif g_u > rhs_u:
                # Overconsistent → make consistent
                self._g[u] = rhs_u
                for (s, cost) in self._get_predecessors(u):
                    self._update_vertex(s)
            else:
                # Underconsistent → set g to ∞ and update
                self._g[u] = INF
                self._update_vertex(u)
                for (s, cost) in self._get_predecessors(u):
                    self._update_vertex(s)

    # ─────────────────────────────────────────────────────────────────────────
    # Dynamic Replanning
    # ─────────────────────────────────────────────────────────────────────────

    def notify_obstacle_change(
        self,
        changed_cells: List[GridPos],
        current_robot_pos: GridPos,
    ) -> None:
        """
        Notify D* Lite that obstacle costs have changed.

        Call this when the OccupancyGrid changes (dynamic obstacle moved).
        Then call replan() to repair the path.

        Args:
            changed_cells:     List of cells whose costs changed.
            current_robot_pos: Current robot position (updates _start).
        """
        if self._start is None or self._goal is None:
            return

        # k_m adjustment: account for robot movement since last plan
        if self._last_start is not None:
            self._k_m += self._heuristic(self._last_start, current_robot_pos)
        self._last_start = current_robot_pos
        self._start      = current_robot_pos

        # Mark affected vertices as inconsistent
        for cell in changed_cells:
            self._update_vertex(cell)
            for (neighbor, _) in self._get_neighbors(*cell):
                self._update_vertex(neighbor)

        log.debug(
            "D* Lite: %d cells changed, replanning from %s",
            len(changed_cells), current_robot_pos,
        )

    def replan(self, current_robot_pos: GridPos) -> List[GridPos]:
        """
        Incrementally repair the path after obstacle changes.

        Args:
            current_robot_pos: Current robot position.

        Returns:
            Updated path, or [] if no path exists.
        """
        if self._goal is None:
            return []

        self._start = current_robot_pos
        self._compute_shortest_path(current_robot_pos)

        if self._g.get(current_robot_pos, INF) == INF:
            log.warning("D* Lite replan: no path found")
            return []

        return self._extract_path(current_robot_pos, self._goal)

    # ─────────────────────────────────────────────────────────────────────────
    # Path Extraction
    # ─────────────────────────────────────────────────────────────────────────

    def _extract_path(self, start: GridPos, goal: GridPos) -> List[GridPos]:
        """
        Extract path by greedy gradient descent on g-values.

        Starting from `start`, at each step move to the neighbor with
        minimum (edge_cost + g(neighbor)).

        Args:
            start: Current position.
            goal:  Destination.

        Returns:
            Ordered path from start to goal.
        """
        path = [start]
        current = start
        visited: Set[GridPos] = {start}

        for _ in range(self._max_iter):
            if current == goal:
                break

            best_next: Optional[GridPos] = None
            best_val = INF

            for (neighbor, edge_cost) in self._get_neighbors(*current):
                g_n = self._g.get(neighbor, INF)
                val = edge_cost + g_n
                if val < best_val:
                    best_val = val
                    best_next = neighbor

            if best_next is None or best_next in visited:
                log.warning("D* Lite path extraction stuck at %s", current)
                break

            path.append(best_next)
            visited.add(best_next)
            current = best_next
        else:
            log.warning("D* Lite path extraction exceeded limit")

        return path

    # ─────────────────────────────────────────────────────────────────────────
    # Helper: Predecessors (backward edges)
    # ─────────────────────────────────────────────────────────────────────────

    def _get_predecessors(self, u: GridPos) -> List[Tuple[GridPos, float]]:
        """
        Return predecessors of u (cells that can reach u in one step).

        For undirected grids, predecessors = successors.

        Args:
            u: Grid cell.

        Returns:
            List of (predecessor, edge_cost) tuples.
        """
        return self._get_neighbors(*u)

"""
HospitalRobotNav — Performance Metrics Collector
==================================================
Collects, stores, and summarizes all performance metrics for the
robot navigation system.

Metrics tracked:
    Planning metrics   (time, nodes, memory)
    Path metrics       (length, turns, smoothness)
    Robot metrics      (speed, distance, energy)
    Mission metrics    (success rate, time-to-complete)
    Planner comparison (across algorithm runs)

IEEE Publication Relevance:
    These metrics directly correspond to the evaluation tables in
    IEEE RA-L / ICRA papers comparing path planning algorithms:
    - Computational efficiency (planning time, nodes expanded)
    - Path quality (length, turns, smoothness)
    - Success rate and robustness
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from algorithms.base_planner import PlannerMetrics
from utilities.logger import get_logger

log = get_logger(__name__)


@dataclass
class RunRecord:
    """One complete navigation run record."""
    run_id:          int
    planner:         str
    heuristic:       str
    start:           tuple
    goal:            tuple
    success:         bool
    planning_ms:     float
    path_length:     float
    path_cells:      int
    nodes_expanded:  int
    nodes_generated: int
    memory_kb:       float
    turns:           int
    travel_dist:     float
    travel_time_s:   float
    energy_wh:       float
    replans:         int
    timestamp:       float = field(default_factory=time.time)

    @property
    def avg_speed(self) -> float:
        """Average speed in cells/second."""
        if self.travel_time_s > 0:
            return self.travel_dist / self.travel_time_s
        return 0.0

    @property
    def efficiency(self) -> float:
        """Path efficiency: optimal (Euclidean) / actual length."""
        from utilities.geometry import euclidean_distance
        if not self.success or self.path_length <= 0:
            return 0.0
        optimal = euclidean_distance(self.start, self.goal)
        return optimal / self.path_length if self.path_length > 0 else 0.0


class PerformanceMetrics:
    """
    Aggregates and reports all system performance metrics.

    Usage:
        metrics = PerformanceMetrics()
        metrics.record_run(planner_result, robot_stats)
        summary = metrics.get_summary()
    """

    def __init__(self) -> None:
        self._runs:           List[RunRecord] = []
        self._run_counter:    int = 0

        # Per-planner aggregates
        self._planner_stats:  Dict[str, List[RunRecord]] = defaultdict(list)

        # Live navigation stats (updated per-frame)
        self.current_speed:   float = 0.0
        self.total_distance:  float = 0.0
        self.session_time_s:  float = 0.0
        self.total_energy_wh: float = 0.0

        self._session_start:  float = time.time()

    # ─────────────────────────────────────────────────────────────────────────
    # Recording
    # ─────────────────────────────────────────────────────────────────────────

    def record_run(
        self,
        planner_metrics: PlannerMetrics,
        start: tuple,
        goal: tuple,
        success: bool,
        travel_dist: float = 0.0,
        travel_time_s: float = 0.0,
        energy_wh: float = 0.0,
        replans: int = 0,
    ) -> RunRecord:
        """
        Record one complete navigation run.

        Args:
            planner_metrics: Metrics from BasePlanner.
            start:           Start position.
            goal:            Goal position.
            success:         True if goal was reached.
            travel_dist:     Actual distance traveled by robot.
            travel_time_s:   Time from start to goal (seconds).
            energy_wh:       Energy consumed (Wh).
            replans:         Number of replanning events.

        Returns:
            RunRecord instance.
        """
        self._run_counter += 1
        record = RunRecord(
            run_id=self._run_counter,
            planner=planner_metrics.planner_name,
            heuristic=planner_metrics.heuristic_name,
            start=start,
            goal=goal,
            success=success,
            planning_ms=planner_metrics.planning_time_ms,
            path_length=planner_metrics.path_length,
            path_cells=planner_metrics.path_cells,
            nodes_expanded=planner_metrics.nodes_expanded,
            nodes_generated=planner_metrics.nodes_generated,
            memory_kb=planner_metrics.memory_kb,
            turns=planner_metrics.turns,
            travel_dist=travel_dist,
            travel_time_s=travel_time_s,
            energy_wh=energy_wh,
            replans=replans,
        )

        self._runs.append(record)
        self._planner_stats[record.planner].append(record)

        log.info(
            "Run #%d [%s]: %s | plan=%.1f ms | path=%.1f cells | nodes=%d",
            record.run_id,
            record.planner,
            "SUCCESS" if success else "FAILED",
            record.planning_ms,
            record.path_length,
            record.nodes_expanded,
        )

        return record

    def update_live(
        self,
        speed: float,
        dt: float,
        dist_this_frame: float,
        energy_this_frame: float,
    ) -> None:
        """
        Update live navigation statistics each simulation frame.

        Args:
            speed:             Current robot speed (cells/s).
            dt:                Frame time step (seconds).
            dist_this_frame:   Distance traveled this frame (cells).
            energy_this_frame: Energy consumed this frame (Wh).
        """
        self.current_speed    = speed
        self.total_distance  += dist_this_frame
        self.total_energy_wh += energy_this_frame
        self.session_time_s  += dt

    # ─────────────────────────────────────────────────────────────────────────
    # Summaries
    # ─────────────────────────────────────────────────────────────────────────

    def get_summary(self) -> Dict:
        """
        Return a comprehensive metrics summary dictionary.

        Used by the analytics panel for UI rendering.
        """
        if not self._runs:
            return self._empty_summary()

        last = self._runs[-1]
        successful = [r for r in self._runs if r.success]
        all_runs = self._runs

        return {
            # Current run
            "last_planner":         last.planner,
            "last_planning_ms":     last.planning_ms,
            "last_path_length":     last.path_length,
            "last_path_cells":      last.path_cells,
            "last_nodes_expanded":  last.nodes_expanded,
            "last_nodes_generated": last.nodes_generated,
            "last_memory_kb":       last.memory_kb,
            "last_turns":           last.turns,
            "last_efficiency":      last.efficiency,
            "last_energy_wh":       last.energy_wh,
            "last_replans":         last.replans,

            # Session totals
            "total_runs":           len(all_runs),
            "success_rate":         len(successful) / len(all_runs) * 100.0,
            "total_distance":       self.total_distance,
            "session_time_s":       self.session_time_s,
            "total_energy_wh":      self.total_energy_wh,
            "current_speed":        self.current_speed,

            # Averages (successful runs)
            "avg_planning_ms":      _safe_avg([r.planning_ms for r in successful]),
            "avg_path_length":      _safe_avg([r.path_length for r in successful]),
            "avg_nodes_expanded":   _safe_avg([r.nodes_expanded for r in successful]),
            "avg_efficiency":       _safe_avg([r.efficiency for r in successful]),
            "avg_turns":            _safe_avg([r.turns for r in successful]),
        }

    def get_planner_comparison(self) -> List[Dict]:
        """
        Return per-planner aggregate statistics for comparison table.

        Useful for generating IEEE-style results tables.
        """
        comparison = []
        for planner_name, runs in self._planner_stats.items():
            successful = [r for r in runs if r.success]
            if not runs:
                continue
            comparison.append({
                "planner":          planner_name,
                "runs":             len(runs),
                "success_rate":     len(successful) / len(runs) * 100.0,
                "avg_planning_ms":  _safe_avg([r.planning_ms for r in successful]),
                "avg_path_length":  _safe_avg([r.path_length for r in successful]),
                "avg_nodes":        _safe_avg([r.nodes_expanded for r in successful]),
                "avg_memory_kb":    _safe_avg([r.memory_kb for r in successful]),
                "avg_efficiency":   _safe_avg([r.efficiency for r in successful]),
                "avg_turns":        _safe_avg([r.turns for r in successful]),
            })
        return sorted(comparison, key=lambda x: x["avg_planning_ms"])

    def get_last_run(self) -> Optional[RunRecord]:
        """Return the most recent run record."""
        return self._runs[-1] if self._runs else None

    def reset_session(self) -> None:
        """Clear all session statistics."""
        self._runs.clear()
        self._planner_stats.clear()
        self._run_counter    = 0
        self.current_speed   = 0.0
        self.total_distance  = 0.0
        self.session_time_s  = 0.0
        self.total_energy_wh = 0.0
        self._session_start  = time.time()
        log.info("Metrics session reset.")

    def _empty_summary(self) -> Dict:
        return {k: 0 for k in [
            "last_planner", "last_planning_ms", "last_path_length",
            "last_path_cells", "last_nodes_expanded", "last_nodes_generated",
            "last_memory_kb", "last_turns", "last_efficiency", "last_energy_wh",
            "last_replans", "total_runs", "success_rate", "total_distance",
            "session_time_s", "total_energy_wh", "current_speed",
            "avg_planning_ms", "avg_path_length", "avg_nodes_expanded",
            "avg_efficiency", "avg_turns",
        ]}


def _safe_avg(values: List[float]) -> float:
    """Compute average of a list, returning 0.0 for empty lists."""
    return sum(values) / len(values) if values else 0.0

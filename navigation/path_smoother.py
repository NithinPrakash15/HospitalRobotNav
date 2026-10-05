"""
HospitalRobotNav — Path Smoother
====================================
Smooths raw grid paths into smoother, more natural-looking trajectories.

Smoothing Techniques:
    1. Shortcut pruning (line-of-sight waypoint reduction)
    2. Bezier curve interpolation (3rd-order cubic Bezier)
    3. Catmull-Rom spline interpolation

For a hospital robot, smooth paths:
    - Reduce mechanical wear (fewer sharp turns)
    - Improve passenger/observer perception
    - Better approximate the actual robot trajectory
    - Feed naturally into velocity controllers

ROS2 Note:
    Equivalent to nav2_smoother_server plugins:
    - nav2_smoother::SimpleSmoother
    - nav2_smoother::SavitzkyGolaySmoother
"""

from __future__ import annotations

import math
from typing import List, Tuple

from utilities.geometry import line_of_sight, euclidean_distance
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]
FloatPos = Tuple[float, float]


class PathSmoother:
    """
    Smooths raw grid paths for natural robot motion.

    Methods:
        shortcut_prune  — Remove redundant intermediate waypoints
        bezier_smooth   — Cubic Bezier spline smoothing
        catmull_rom     — Catmull-Rom spline interpolation
    """

    def __init__(
        self,
        is_blocked_fn,
        clearance_fn: Optional[Any] = None,
        min_clearance: float = 0.0,
    ) -> None:
        """
        Args:
            is_blocked_fn: Callable(row, col) → bool returning True if cell is obstacle.
            clearance_fn:  Optional Callable(row, col) → float returning obstacle clearance in cells.
            min_clearance: Minimum clearance required to accept a shortcut (cells).
        """
        self._is_blocked = is_blocked_fn
        self._clearance_fn = clearance_fn
        self._min_clearance = min_clearance

    def set_clearance_checker(self, clearance_fn: Any, min_clearance: float = 1.0) -> None:
        """Set an obstacle clearance evaluator for safe shortcut pruning."""
        self._clearance_fn = clearance_fn
        self._min_clearance = min_clearance

    def smooth(
        self,
        path: List[GridPos],
        method: str = "shortcut",
        interpolation_steps: int = 5,
        min_clearance: Optional[float] = None,
    ) -> List[FloatPos]:
        """
        Apply path smoothing.

        Args:
            path:               Raw A* path (list of (row, col)).
            method:             "shortcut" | "bezier" | "catmull_rom"
            interpolation_steps: Points between each waypoint.
            min_clearance:      Optional override for minimum clearance.

        Returns:
            Smoothed path as list of (row, col) float positions.
        """
        if len(path) < 2:
            return [(float(r), float(c)) for r, c in path]

        if method == "shortcut":
            pruned = self.shortcut_prune(path, min_clearance=min_clearance)
            return [(float(r), float(c)) for r, c in pruned]
        elif method == "bezier":
            pruned = self.shortcut_prune(path, min_clearance=min_clearance)
            return self.bezier_smooth(pruned, interpolation_steps)
        elif method == "catmull_rom":
            return self.catmull_rom(path, interpolation_steps)
        else:
            return [(float(r), float(c)) for r, c in path]

    # ─────────────────────────────────────────────────────────────────────────
    # Shortcut Pruning
    # ─────────────────────────────────────────────────────────────────────────

    def shortcut_prune(
        self,
        path: List[GridPos],
        min_clearance: Optional[float] = None,
    ) -> List[GridPos]:
        """
        Remove waypoints that are directly visible from earlier waypoints.

        Iterates from the start. For each waypoint s_i, finds the furthest
        s_j (j > i) such that line_of_sight(s_i, s_j) is clear and maintains
        the required safety clearance.
        Skips all intermediate waypoints between i and j.

        This produces minimal paths through the free space without cutting corners.

        Args:
            path: Raw grid path.
            min_clearance: Optional override for minimum clearance.

        Returns:
            Pruned path with fewer redundant waypoints.
        """
        if len(path) < 3:
            return path

        target_clearance = self._min_clearance if min_clearance is None else min_clearance
        pruned = [path[0]]
        i = 0

        while i < len(path) - 1:
            # Find furthest visible waypoint from path[i]
            j = len(path) - 1
            while j > i + 1:
                if line_of_sight(path[i], path[j], self._is_blocked):
                    if target_clearance > 0 and self._clearance_fn is not None:
                        from utilities.geometry import bresenham_cells
                        cells = bresenham_cells(path[i], path[j])
                        if all(self._clearance_fn(r, c) >= target_clearance for r, c in cells):
                            break
                    else:
                        break
                j -= 1
            pruned.append(path[j])
            i = j

        log.debug(
            "Shortcut pruning: %d → %d waypoints", len(path), len(pruned)
        )
        return pruned

    # ─────────────────────────────────────────────────────────────────────────
    # Bezier Curve Smoothing
    # ─────────────────────────────────────────────────────────────────────────

    def bezier_smooth(
        self,
        waypoints: List[GridPos],
        steps: int = 8,
    ) -> List[FloatPos]:
        """
        Smooth path using cubic Bezier curves between waypoint triplets.

        For each consecutive triplet (P0, P1, P2), computes a quadratic
        Bezier curve P(t) = (1-t)²P0 + 2(1-t)tP1 + t²P2, t ∈ [0,1].

        Args:
            waypoints: Pruned waypoint list.
            steps:     Interpolation points per segment.

        Returns:
            Smooth list of (row, col) float positions.
        """
        if len(waypoints) < 3:
            return [(float(r), float(c)) for r, c in waypoints]

        smooth: List[FloatPos] = []

        # Add start point
        smooth.append((float(waypoints[0][0]), float(waypoints[0][1])))

        for i in range(len(waypoints) - 2):
            p0 = (float(waypoints[i][0]),     float(waypoints[i][1]))
            p1 = (float(waypoints[i+1][0]),   float(waypoints[i+1][1]))
            p2 = (float(waypoints[i+2][0]),   float(waypoints[i+2][1]))

            # Midpoints for G1 continuity
            m01 = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
            m12 = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)

            for step in range(steps + 1):
                t = step / steps
                # Quadratic Bezier: m01 → p1 → m12
                row = (1-t)**2 * m01[0] + 2*(1-t)*t * p1[0] + t**2 * m12[0]
                col = (1-t)**2 * m01[1] + 2*(1-t)*t * p1[1] + t**2 * m12[1]
                smooth.append((row, col))

        # Add end point
        last = waypoints[-1]
        smooth.append((float(last[0]), float(last[1])))

        return smooth

    # ─────────────────────────────────────────────────────────────────────────
    # Catmull-Rom Spline
    # ─────────────────────────────────────────────────────────────────────────

    def catmull_rom(
        self,
        path: List[GridPos],
        steps: int = 6,
        alpha: float = 0.5,
    ) -> List[FloatPos]:
        """
        Smooth path using Catmull-Rom splines.

        Centripetal Catmull-Rom produces smooth curves that pass through
        all control points without self-intersections.

        Args:
            path:  Input waypoints.
            steps: Interpolation steps between each pair.
            alpha: 0=uniform, 0.5=centripetal (default), 1=chordal.

        Returns:
            Smooth path as list of (row, col) float positions.
        """
        if len(path) < 4:
            return self.bezier_smooth(path, steps)

        # Extend path with phantom points at each end
        pts = [
            (float(path[0][0]), float(path[0][1])),
        ] + [
            (float(r), float(c)) for r, c in path
        ] + [
            (float(path[-1][0]), float(path[-1][1])),
        ]

        smooth: List[FloatPos] = []

        for i in range(1, len(pts) - 2):
            p0, p1, p2, p3 = pts[i-1], pts[i], pts[i+1], pts[i+2]

            # Centripetal knot parameterization
            t0 = 0.0
            t1 = t0 + (euclidean_distance(p0, p1) ** alpha)
            t2 = t1 + (euclidean_distance(p1, p2) ** alpha)
            t3 = t2 + (euclidean_distance(p2, p3) ** alpha)

            if abs(t1 - t0) < 1e-6 or abs(t2 - t1) < 1e-6 or abs(t3 - t2) < 1e-6:
                smooth.append(p1)
                continue

            for step in range(steps + 1):
                t = t1 + (t2 - t1) * step / steps

                # Barry-Goldman algorithm
                def interp(pa, pb, ta, tb):
                    if abs(tb - ta) < 1e-9:
                        return pa
                    f = (t - ta) / (tb - ta)
                    return (pa[0] + f * (pb[0] - pa[0]),
                            pa[1] + f * (pb[1] - pa[1]))

                a1 = interp(p0, p1, t0, t1)
                a2 = interp(p1, p2, t1, t2)
                a3 = interp(p2, p3, t2, t3)
                b1 = interp(a1, a2, t0, t2)
                b2 = interp(a2, a3, t1, t3)
                c  = interp(b1, b2, t1, t2)
                smooth.append(c)

        smooth.append((float(path[-1][0]), float(path[-1][1])))
        return smooth

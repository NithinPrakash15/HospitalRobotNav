"""
HospitalRobotNav — Geometry Utility Library
============================================
Provides mathematical helper functions for 2D spatial computations
used throughout the navigation and simulation stack.

All coordinate systems use (row, col) grid convention:
    row → Y axis (increases downward)
    col → X axis (increases rightward)

Angle convention:
    0 rad = facing right (+col direction)
    π/2 rad = facing down (+row direction)
    Angles increase counter-clockwise (standard math convention)

ROS2 Note:
    tf2_ros.transformations provides equivalent geometric operations
    for 3D frames in a deployed ROS2 system.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

# Type aliases for clarity
GridPos   = Tuple[int, int]        # (row, col) integer grid cell
FloatPos  = Tuple[float, float]    # (row, col) floating-point position
Vector2D  = Tuple[float, float]    # Generic 2D vector


# ─────────────────────────────────────────────────────────────────────────────
# Distance Metrics
# ─────────────────────────────────────────────────────────────────────────────

def euclidean_distance(a: FloatPos, b: FloatPos) -> float:
    """
    Compute Euclidean (L2) distance between two 2D points.

    Args:
        a: Starting position (row, col).
        b: Ending position (row, col).

    Returns:
        Straight-line distance ≥ 0.
    """
    dr = b[0] - a[0]
    dc = b[1] - a[1]
    return math.hypot(dr, dc)


def manhattan_distance(a: GridPos, b: GridPos) -> int:
    """
    Compute Manhattan (L1) distance between two grid cells.

    Assumes 4-connectivity (no diagonal moves).

    Args:
        a: Starting cell (row, col).
        b: Ending cell (row, col).

    Returns:
        Non-negative integer distance.
    """
    return abs(b[0] - a[0]) + abs(b[1] - a[1])


def chebyshev_distance(a: GridPos, b: GridPos) -> int:
    """
    Compute Chebyshev (L∞) distance between two grid cells.

    Assumes 8-connectivity (diagonal moves cost 1).

    Args:
        a: Starting cell (row, col).
        b: Ending cell (row, col).

    Returns:
        Non-negative integer distance.
    """
    return max(abs(b[0] - a[0]), abs(b[1] - a[1]))


def diagonal_distance(a: GridPos, b: GridPos) -> float:
    """
    Compute octile distance — optimal heuristic for 8-connected grids.

    Combines Chebyshev distance with a correction for diagonal steps:
        D = max(|Δrow|, |Δcol|) + (√2 - 1) × min(|Δrow|, |Δcol|)

    Args:
        a: Starting cell (row, col).
        b: Ending cell (row, col).

    Returns:
        Float distance optimized for 8-connectivity.
    """
    dr = abs(b[0] - a[0])
    dc = abs(b[1] - a[1])
    return max(dr, dc) + (math.sqrt(2) - 1) * min(dr, dc)


# ─────────────────────────────────────────────────────────────────────────────
# Angle & Heading Utilities
# ─────────────────────────────────────────────────────────────────────────────

def angle_between(a: FloatPos, b: FloatPos) -> float:
    """
    Compute the heading angle from point `a` to point `b`.

    Returns angle in radians, measured from +col axis counter-clockwise.
    Result is in range [-π, π].

    Args:
        a: Source position (row, col).
        b: Target position (row, col).
    """
    dc = b[1] - a[1]
    dr = -(b[0] - a[0])   # Negate because row increases downward
    return math.atan2(dr, dc)


def normalize_angle(angle: float) -> float:
    """
    Normalize an angle to the range [-π, π].

    Args:
        angle: Angle in radians (any range).

    Returns:
        Normalized angle in [-π, π].
    """
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle < -math.pi:
        angle += 2 * math.pi
    return angle


def angle_difference(target: float, current: float) -> float:
    """
    Compute the shortest signed angular difference (target - current).

    Args:
        target:  Target heading (radians).
        current: Current heading (radians).

    Returns:
        Signed difference in [-π, π]. Positive = counter-clockwise.
    """
    return normalize_angle(target - current)


def heading_to_vector(heading: float) -> Vector2D:
    """
    Convert a heading angle to a unit direction vector.

    Args:
        heading: Angle in radians from +col axis counter-clockwise.

    Returns:
        (row_component, col_component) unit vector.
    """
    return (-math.sin(heading), math.cos(heading))


# ─────────────────────────────────────────────────────────────────────────────
# Line Segment & Intersection
# ─────────────────────────────────────────────────────────────────────────────

def line_of_sight(
    start: GridPos,
    end: GridPos,
    is_blocked: "callable[[int, int], bool]",
) -> bool:
    """
    Check if there is an unobstructed line of sight from `start` to `end`.

    Uses Bresenham's line algorithm to enumerate grid cells along the ray.

    Args:
        start:      Source grid cell (row, col).
        end:        Target grid cell (row, col).
        is_blocked: Callable(row, col) → bool. Returns True if cell is an obstacle.

    Returns:
        True if no obstacle lies on the line between start and end.
    """
    r0, c0 = start
    r1, c1 = end

    dr = abs(r1 - r0)
    dc = abs(c1 - c0)
    sr = 1 if r1 > r0 else -1
    sc = 1 if c1 > c0 else -1
    err = dr - dc

    while True:
        if (r0, c0) != start and (r0, c0) != end:
            if is_blocked(r0, c0):
                return False

        if r0 == r1 and c0 == c1:
            break

        e2 = 2 * err
        if e2 > -dc:
            err -= dc
            r0 += sr
        if e2 < dr:
            err += dr
            c0 += sc

    return True


def bresenham_cells(
    start: GridPos,
    end: GridPos,
) -> List[GridPos]:
    """
    Enumerate all grid cells on the Bresenham line from `start` to `end`.

    Args:
        start: Source cell (row, col).
        end:   Target cell (row, col).

    Returns:
        List of (row, col) cells along the line, inclusive.
    """
    cells: List[GridPos] = []
    r0, c0 = start
    r1, c1 = end

    dr = abs(r1 - r0)
    dc = abs(c1 - c0)
    sr = 1 if r1 > r0 else -1
    sc = 1 if c1 > c0 else -1
    err = dr - dc

    while True:
        cells.append((r0, c0))
        if r0 == r1 and c0 == c1:
            break
        e2 = 2 * err
        if e2 > -dc:
            err -= dc
            r0 += sr
        if e2 < dr:
            err += dr
            c0 += sc

    return cells


# ─────────────────────────────────────────────────────────────────────────────
# Path Utilities
# ─────────────────────────────────────────────────────────────────────────────

def path_length(path: Sequence[GridPos]) -> float:
    """
    Compute total Euclidean length of a grid path.

    Args:
        path: Ordered sequence of (row, col) cells.

    Returns:
        Total path length in grid cells.
    """
    if len(path) < 2:
        return 0.0
    return sum(
        euclidean_distance(path[i], path[i + 1])
        for i in range(len(path) - 1)
    )


def count_turns(path: Sequence[GridPos], turn_threshold_deg: float = 15.0) -> int:
    """
    Count the number of significant direction changes in a path.

    Args:
        path:               Ordered sequence of (row, col) cells.
        turn_threshold_deg: Minimum angle change (degrees) to count as a turn.

    Returns:
        Integer number of turns.
    """
    if len(path) < 3:
        return 0

    threshold_rad = math.radians(turn_threshold_deg)
    turns = 0
    prev_angle = angle_between(path[0], path[1])

    for i in range(1, len(path) - 1):
        curr_angle = angle_between(path[i], path[i + 1])
        delta = abs(angle_difference(curr_angle, prev_angle))
        if delta > threshold_rad:
            turns += 1
        prev_angle = curr_angle

    return turns


# ─────────────────────────────────────────────────────────────────────────────
# Coordinate Conversion
# ─────────────────────────────────────────────────────────────────────────────

def grid_to_pixel(
    row: float,
    col: float,
    cell_px: int,
    offset_x: int = 0,
    offset_y: int = 0,
) -> Tuple[int, int]:
    """
    Convert grid (row, col) coordinates to screen pixel (x, y) coordinates.

    Args:
        row:      Grid row (float for sub-cell precision).
        col:      Grid column.
        cell_px:  Pixel size of one grid cell.
        offset_x: Viewport X offset (pixels).
        offset_y: Viewport Y offset (pixels).

    Returns:
        (screen_x, screen_y) integer pixel coordinates.
    """
    px = int(col * cell_px + offset_x)
    py = int(row * cell_px + offset_y)
    return px, py


def pixel_to_grid(
    px: int,
    py: int,
    cell_px: int,
    offset_x: int = 0,
    offset_y: int = 0,
) -> GridPos:
    """
    Convert screen pixel (x, y) to grid (row, col) coordinates.

    Args:
        px:       Screen X (pixels).
        py:       Screen Y (pixels).
        cell_px:  Pixel size of one grid cell.
        offset_x: Viewport X offset.
        offset_y: Viewport Y offset.

    Returns:
        (row, col) integer grid cell.
    """
    col = int((px - offset_x) / cell_px)
    row = int((py - offset_y) / cell_px)
    return row, col


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp `value` to the closed interval [lo, hi]."""
    return max(lo, min(hi, value))


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation: a + t*(b-a), t in [0, 1]."""
    return a + t * (b - a)


# ─────────────────────────────────────────────────────────────────────────────
# Angle Utilities
# ─────────────────────────────────────────────────────────────────────────────

def normalize_angle(angle: float) -> float:
    """
    Normalize an angle to (-π, π].

    Args:
        angle: Angle in radians.

    Returns:
        Equivalent angle in (-π, π].
    """
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle <= -math.pi:
        angle += 2.0 * math.pi
    return angle


def angle_difference(target: float, current: float) -> float:
    """
    Compute the signed angular difference from current to target.

    Returns the shortest rotation from current → target in (-π, π].

    Args:
        target:  Desired heading (radians).
        current: Current heading (radians).

    Returns:
        Signed angular difference in (-π, π].
    """
    return normalize_angle(target - current)


# ─────────────────────────────────────────────────────────────────────────────
# Bresenham & LoS
# ─────────────────────────────────────────────────────────────────────────────

def bresenham_cells(
    start: GridPos,
    end: GridPos,
) -> List[GridPos]:
    """
    Return all grid cells on the Bresenham line from start to end.

    Args:
        start: Source (row, col).
        end:   Target (row, col).

    Returns:
        List of (row, col) cells traversed.
    """
    r0, c0 = start
    r1, c1 = end
    cells: List[GridPos] = []

    dr = abs(r1 - r0)
    dc = abs(c1 - c0)
    sr = 1 if r1 > r0 else -1
    sc = 1 if c1 > c0 else -1
    err = dr - dc

    while True:
        cells.append((r0, c0))
        if r0 == r1 and c0 == c1:
            break
        e2 = 2 * err
        if e2 > -dc:
            err -= dc
            r0  += sr
        if e2 < dr:
            err += dr
            c0  += sc

    return cells


def line_of_sight(
    a: GridPos,
    b: GridPos,
    is_blocked_fn,
) -> bool:
    """
    Check line-of-sight between two grid cells using Bresenham's algorithm.

    Args:
        a:             Source cell (row, col).
        b:             Target cell (row, col).
        is_blocked_fn: Callable(row, col) → bool, True if cell is a wall.

    Returns:
        True if the line from a to b is unobstructed.
    """
    for r, c in bresenham_cells(a, b)[1:-1]:   # Exclude endpoints
        if is_blocked_fn(r, c):
            return False
    return True


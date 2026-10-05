"""
HospitalRobotNav — Heuristic Functions
=========================================
Implements all heuristic distance functions used by informed search algorithms.

Heuristics:
    1. Manhattan  — L1 norm, optimal for 4-connected grids, no diagonals
    2. Euclidean  — L2 norm, true straight-line distance, admissible
    3. Diagonal   — Octile distance, optimal for 8-connected grids
    4. Chebyshev  — L∞ norm, for 8-connected with uniform diagonal cost

All heuristics are ADMISSIBLE (never overestimate actual cost) and
CONSISTENT (satisfy triangle inequality), ensuring A* finds optimal paths.

Mathematical Guarantees:
    Admissibility: h(n) ≤ h*(n)  ∀n
    Consistency:   h(n) ≤ c(n,n') + h(n')  ∀ edges (n,n')

    With consistent heuristics, A* never re-expands nodes → optimal O(E log V).

Reference:
    Russell, S. & Norvig, P. "Artificial Intelligence: A Modern Approach",
    4th ed., Pearson, 2021. Chapter 3.5.
"""

from __future__ import annotations

import math
from enum import Enum, auto
from typing import Any, Callable, Tuple

GridPos = Tuple[int, int]
HeuristicFn = Callable[[GridPos, GridPos], float]


class HeuristicType(Enum):
    """Available heuristic types selectable at runtime."""
    MANHATTAN  = auto()
    EUCLIDEAN  = auto()
    DIAGONAL   = auto()
    CHEBYSHEV  = auto()


# ─────────────────────────────────────────────────────────────────────────────
# Individual Heuristic Functions
# ─────────────────────────────────────────────────────────────────────────────

def manhattan(a: GridPos, b: GridPos) -> float:
    """
    Manhattan (L1) distance heuristic.

    Assumes 4-connected movement (no diagonals).
    Admissible and consistent for 4-connected uniform-cost grids.

    h(a, b) = |Δrow| + |Δcol|

    Args:
        a: Source cell (row, col).
        b: Goal cell (row, col).

    Returns:
        Non-negative integer distance as float.
    """
    return float(abs(b[0] - a[0]) + abs(b[1] - a[1]))


def euclidean(a: GridPos, b: GridPos) -> float:
    """
    Euclidean (L2) distance heuristic.

    Straight-line distance — always admissible regardless of grid connectivity.
    Slightly underestimates for grid navigation, making A* optimal.

    h(a, b) = √(Δrow² + Δcol²)

    Args:
        a: Source cell (row, col).
        b: Goal cell (row, col).

    Returns:
        Non-negative float distance.
    """
    dr = b[0] - a[0]
    dc = b[1] - a[1]
    return math.hypot(dr, dc)


def diagonal(a: GridPos, b: GridPos) -> float:
    """
    Diagonal (octile) distance heuristic.

    Optimal admissible heuristic for 8-connected grids with:
        - Cardinal moves cost = 1
        - Diagonal moves cost = √2

    Derivation:
        min_diag = min(|Δrow|, |Δcol|)
        min_card = max(|Δrow|, |Δcol|) - min_diag
        h = min_diag × √2 + min_card × 1
          = max(|Δrow|, |Δcol|) + (√2 - 1) × min(|Δrow|, |Δcol|)

    Args:
        a: Source cell (row, col).
        b: Goal cell (row, col).

    Returns:
        Non-negative float distance (octile metric).
    """
    dr = abs(b[0] - a[0])
    dc = abs(b[1] - a[1])
    return max(dr, dc) + (math.sqrt(2) - 1.0) * min(dr, dc)


def chebyshev(a: GridPos, b: GridPos) -> float:
    """
    Chebyshev (L∞) distance heuristic.

    Optimal for 8-connected grids where diagonal cost = 1 (same as cardinal).

    h(a, b) = max(|Δrow|, |Δcol|)

    Args:
        a: Source cell (row, col).
        b: Goal cell (row, col).

    Returns:
        Non-negative integer distance as float.
    """
    dr = abs(b[0] - a[0])
    dc = abs(b[1] - a[1])
    return float(max(dr, dc))


# ─────────────────────────────────────────────────────────────────────────────
# Weighted Heuristic (for Weighted A*)
# ─────────────────────────────────────────────────────────────────────────────

def weighted_heuristic(
    base_fn: HeuristicFn,
    weight: float,
) -> HeuristicFn:
    """
    Create a weighted heuristic: h_w(a, b) = weight × h(a, b).

    Weighted A* (WA*) trades optimality for speed:
        weight = 1.0  → optimal A* (admissible)
        weight > 1.0  → suboptimal but faster (ε-optimal: cost ≤ weight × optimal)
        weight = ∞    → greedy best-first search

    Args:
        base_fn: Base heuristic function.
        weight:  Inflation factor ≥ 1.0.

    Returns:
        Weighted heuristic callable.
    """
    def _weighted(a: GridPos, b: GridPos) -> float:
        return weight * base_fn(a, b)
    _weighted.__name__ = f"weighted_{base_fn.__name__}(w={weight})"
    return _weighted


# ─────────────────────────────────────────────────────────────────────────────
# Heuristic Factory
# ─────────────────────────────────────────────────────────────────────────────

_HEURISTIC_MAP: dict[HeuristicType, HeuristicFn] = {
    HeuristicType.MANHATTAN: manhattan,
    HeuristicType.EUCLIDEAN: euclidean,
    HeuristicType.DIAGONAL:  diagonal,
    HeuristicType.CHEBYSHEV: chebyshev,
}


def get_heuristic(
    heuristic_type: Any,
    weight: float = 1.0,
) -> HeuristicFn:
    """
    Retrieve a heuristic function by type or name.

    Args:
        heuristic_type: HeuristicType enum value or name string.
        weight:         Optional inflation weight (default 1.0 = optimal).

    Returns:
        Callable heuristic function.

    Raises:
        ValueError: If heuristic_type is unknown.

    Example:
        h = get_heuristic(HeuristicType.DIAGONAL)
        cost = h((0, 0), (10, 10))
    """
    fn = _HEURISTIC_MAP.get(heuristic_type)
    if fn is None:
        # Fallback by name/string match to handle cross-namespace imports
        name = getattr(heuristic_type, "name", str(heuristic_type)).lower()
        if "manhattan" in name:
            fn = manhattan
        elif "euclidean" in name:
            fn = euclidean
        elif "diagonal" in name or "octile" in name:
            fn = diagonal
        elif "chebyshev" in name:
            fn = chebyshev

    if fn is None:
        raise ValueError(f"Unknown heuristic type: {heuristic_type}")
    if weight != 1.0:
        return weighted_heuristic(fn, weight)
    return fn


def get_heuristic_by_name(name: str, weight: float = 1.0) -> HeuristicFn:
    """
    Retrieve a heuristic by string name (case-insensitive).

    Args:
        name:   "manhattan", "euclidean", "diagonal", or "chebyshev".
        weight: Optional inflation weight.

    Returns:
        Callable heuristic function.

    Raises:
        ValueError: If name is not recognized.
    """
    name_map = {
        "manhattan": HeuristicType.MANHATTAN,
        "euclidean": HeuristicType.EUCLIDEAN,
        "diagonal":  HeuristicType.DIAGONAL,
        "chebyshev": HeuristicType.CHEBYSHEV,
        "octile":    HeuristicType.DIAGONAL,   # alias
    }
    h_type = name_map.get(name.lower())
    if h_type is None:
        raise ValueError(
            f"Unknown heuristic name: '{name}'. "
            f"Valid options: {list(name_map.keys())}"
        )
    return get_heuristic(h_type, weight)


# ─────────────────────────────────────────────────────────────────────────────
# Default heuristic used by most planners
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_HEURISTIC: HeuristicFn = diagonal
DEFAULT_HEURISTIC_TYPE: HeuristicType = HeuristicType.DIAGONAL

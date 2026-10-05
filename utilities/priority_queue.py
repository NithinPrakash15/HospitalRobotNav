"""
HospitalRobotNav — Custom Priority Queue (Binary Min-Heap)
===========================================================
Implements a high-performance binary min-heap priority queue used by
all path planners (A*, Dijkstra, Theta*, Hybrid A*, D* Lite).

Design Rationale:
    Python's `heapq` module provides a heap but lacks key operations:
    - O(log n) decrease-key
    - Membership testing O(1)
    - Lazy deletion for D* Lite invalidations

    This module provides:
    1. `PriorityQueue`      — Standard binary min-heap with lazy deletion
    2. `IndexedPriorityQueue` — O(log n) decrease-key (for D* Lite)

Complexity:
    push:        O(log n)
    pop_min:     O(log n)  amortized (includes lazy deletion cleanup)
    peek:        O(1)
    contains:    O(1)
    decrease_key: O(log n)  [IndexedPriorityQueue only]

Reference:
    Cormen, T.H. et al. "Introduction to Algorithms", 4th ed., MIT Press.
    Koenig, S. & Likhachev, M. "D* Lite", AAAI 2002.
"""

from __future__ import annotations

import heapq
from typing import Any, Generic, Iterable, Optional, Tuple, TypeVar

# Generic type variable for stored items
T = TypeVar("T")


# ─────────────────────────────────────────────────────────────────────────────
# Standard Priority Queue with Lazy Deletion
# ─────────────────────────────────────────────────────────────────────────────

class PriorityQueue(Generic[T]):
    """
    Binary min-heap priority queue with lazy deletion.

    Elements are (priority, item) pairs. Duplicate insertions are handled
    via lazy deletion: invalidated entries remain in the heap but are
    silently skipped during `pop_min`.

    The `item` type must be hashable for the membership set.

    Attributes:
        _heap:    Internal heapq list of (priority, counter, item).
        _valid:   Set of currently valid items.
        _counter: Monotone counter to break ties deterministically.
    """

    def __init__(self) -> None:
        self._heap:    list[Tuple[float, int, T]] = []
        self._valid:   set[T] = set()
        self._counter: int = 0

    # ── Core Operations ───────────────────────────────────────────────────────

    def push(self, item: T, priority: float) -> None:
        """
        Insert `item` with given `priority`.

        If `item` already exists, this creates a duplicate entry.
        The old entry will be lazily skipped on pop.

        Args:
            item:     Hashable item to store.
            priority: Float priority (lower = higher priority).
        """
        self._valid.add(item)
        heapq.heappush(self._heap, (priority, self._counter, item))
        self._counter += 1

    def pop_min(self) -> Tuple[float, T]:
        """
        Remove and return the (priority, item) pair with lowest priority.

        Lazily skips invalidated entries.

        Returns:
            (priority, item) tuple.

        Raises:
            IndexError: If the queue is empty.
        """
        while self._heap:
            priority, _, item = heapq.heappop(self._heap)
            if item in self._valid:
                self._valid.discard(item)
                return priority, item
        raise IndexError("pop_min from an empty PriorityQueue")

    def peek(self) -> Tuple[float, T]:
        """
        Return (priority, item) of the minimum element without removing it.

        Raises:
            IndexError: If the queue is empty.
        """
        while self._heap:
            priority, _, item = self._heap[0]
            if item in self._valid:
                return priority, item
            heapq.heappop(self._heap)  # Remove stale entry
        raise IndexError("peek on empty PriorityQueue")

    def remove(self, item: T) -> None:
        """
        Mark `item` as invalid (lazy deletion).

        The item will not be returned by future `pop_min` calls.
        The underlying heap entry remains until popped.

        Args:
            item: Item to invalidate.
        """
        self._valid.discard(item)

    # ── Query Operations ──────────────────────────────────────────────────────

    def contains(self, item: T) -> bool:
        """Return True if `item` is currently valid in the queue."""
        return item in self._valid

    def __contains__(self, item: T) -> bool:
        """Support `in` operator: `if node in open_list:`"""
        return item in self._valid

    def __len__(self) -> int:
        """Return number of valid (non-deleted) items."""
        return len(self._valid)

    def is_empty(self) -> bool:
        """Return True if no valid items remain."""
        return len(self._valid) == 0

    def clear(self) -> None:
        """Remove all items from the queue."""
        self._heap.clear()
        self._valid.clear()
        self._counter = 0

    def __repr__(self) -> str:
        return f"PriorityQueue(size={len(self)})"


# ─────────────────────────────────────────────────────────────────────────────
# Indexed Priority Queue — O(log n) Decrease-Key
# ─────────────────────────────────────────────────────────────────────────────

class IndexedPriorityQueue(Generic[T]):
    """
    Priority queue with O(log n) decrease-key operation.

    Used by D* Lite, which requires efficient key updates during
    dynamic replanning when obstacle costs change.

    Internal representation uses a dictionary mapping item → (priority, index)
    and a standard heapq for ordering.

    Attributes:
        _heap:      List of [priority, counter, item] entries.
        _entry_map: Dict mapping item → list entry in _heap.
        _REMOVED:   Sentinel value for invalidated entries.
        _counter:   Tie breaker counter.
    """

    _REMOVED: Any = object()   # Unique sentinel

    def __init__(self) -> None:
        self._heap:      list[list] = []
        self._entry_map: dict[T, list] = {}
        self._counter:   int = 0

    def push(self, item: T, priority: float) -> None:
        """
        Insert `item` with `priority`, or update if already present.

        If the item exists with a higher priority, performs decrease-key.

        Args:
            item:     Hashable item.
            priority: Float priority (lower = higher priority).
        """
        if item in self._entry_map:
            existing = self._entry_map[item]
            if existing[0] <= priority:
                return   # Existing entry is better; no update needed
            # Mark old entry as removed
            existing[2] = self._REMOVED

        entry = [priority, self._counter, item]
        self._counter += 1
        self._entry_map[item] = entry
        heapq.heappush(self._heap, entry)

    def pop_min(self) -> Tuple[float, T]:
        """
        Remove and return the minimum (priority, item) pair.

        Raises:
            IndexError: If the queue is empty.
        """
        while self._heap:
            entry = heapq.heappop(self._heap)
            priority, _, item = entry[0], entry[1], entry[2]
            if item is not self._REMOVED:
                del self._entry_map[item]
                return priority, item
        raise IndexError("pop_min from empty IndexedPriorityQueue")

    def peek(self) -> Tuple[float, T]:
        """Return minimum (priority, item) without removing."""
        while self._heap:
            entry = self._heap[0]
            priority, _, item = entry[0], entry[1], entry[2]
            if item is not self._REMOVED:
                return priority, item
            heapq.heappop(self._heap)
        raise IndexError("peek on empty IndexedPriorityQueue")

    def remove(self, item: T) -> None:
        """Remove `item` from the queue."""
        if item in self._entry_map:
            self._entry_map[item][2] = self._REMOVED
            del self._entry_map[item]


    def contains(self, item: T) -> bool:
        """Return True if `item` is in the queue."""
        return item in self._entry_map

    def __contains__(self, item: T) -> bool:
        return item in self._entry_map

    def __len__(self) -> int:
        return len(self._entry_map)

    def is_empty(self) -> bool:
        return len(self._entry_map) == 0

    def clear(self) -> None:
        """Reset the queue."""
        self._heap.clear()
        self._entry_map.clear()

    def get_priority(self, item: T) -> Optional[float]:
        """
        Retrieve current priority of `item`.

        Returns:
            Float priority or None if not present.
        """
        entry = self._entry_map.get(item)
        if entry is None or entry[1] is self._REMOVED:
            return None
        return entry[0]

    def __repr__(self) -> str:
        return f"IndexedPriorityQueue(size={len(self)})"

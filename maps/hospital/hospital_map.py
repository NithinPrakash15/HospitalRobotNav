"""
HospitalRobotNav — Hospital Map Generator
==========================================
Procedurally generates the complete 120x120 hospital occupancy grid.

The map encodes:
    0   = free (walkable floor / corridor)
    1   = wall (impassable)
    2   = room floor (walkable, slightly higher cost)
    3   = doorway (navigable transition point)
    4   = corridor (walkable main thoroughfare)

Output grids:
    binary_grid   — 0/1 occupancy (used by planners)
    type_grid     — 0/1/2/3/4 cell type (used by renderer)
    room_id_grid  — room_id string per cell (used by semantic layer)
    cost_grid     — float cost per cell (used by planners)

Design:
    - Wide main corridors (3-5 cells) connect all hospital zones
    - Rooms are carved from solid wall background
    - Each room doorway connects to the nearest corridor
    - A robust flood-fill validation ensures full connectivity

ROS2 Note:
    In a deployed system, this grid would be replaced by a live
    OccupancyGrid message from the SLAM Toolbox:
    /map (nav_msgs/OccupancyGrid)
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
from collections import deque
from typing import Deque, Dict, List, Optional, Set, Tuple

from config.hospital_config import GRID_CONFIG, COST_CONFIG
from maps.hospital.room_definitions import (
    ROOM_DATABASE, ROOMS_BY_ID, RoomDefinition
)
from utilities.logger import get_logger

log = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Cell Type Constants
# ─────────────────────────────────────────────────────────────────────────────
CELL_WALL     = 1
CELL_FREE     = 0
CELL_ROOM     = 2
CELL_DOORWAY  = 3
CELL_CORRIDOR = 4

# Main corridor definitions: (start_row, start_col, end_row, end_col, width)
# Horizontal bands separate zones; vertical bands connect them.
_MAIN_CORRIDORS: List[Tuple[int, int, int, int, int]] = [
    # Horizontal main corridors (zone separators)
    (19, 2, 19, 97, 3),    # H1 — Zone 1 / Zone 2 (rows 19-21)
    (40, 2, 40, 97, 3),    # H2 — Zone 2 / Zone 3 (rows 40-42)
    (61, 2, 61, 97, 3),    # H3 — Zone 3 / Zone 4 (rows 61-63)
    (75, 2, 75, 97, 3),    # H4 — Zone 4 / Zone 5 (rows 75-77)
    (92, 2, 92, 97, 3),    # H5 — Zone 5 / Bottom (rows 92-94)

    # Vertical main corridors (connect horizontal bands)
    (2,  14, 94, 14, 3),   # V1 — Left vertical spine (cols 14-16)
    (2,  50, 94, 50, 3),   # V2 — Center vertical spine (cols 50-52)
    (2,  83, 94, 83, 3),   # V3 — Right vertical spine (cols 83-85)
]


class HospitalMap:
    """
    120x120 hospital occupancy grid generator.

    Attributes:
        rows:         Grid rows (100).
        cols:         Grid columns (100).
        binary_grid:  np.ndarray[uint8] — 1=wall, 0=free.
        type_grid:    np.ndarray[uint8] — cell type codes.
        room_id_grid: np.ndarray[str]   — room_id or "" per cell.
        cost_grid:    np.ndarray[float] — traversal cost per cell.
        rooms:        List of all RoomDefinition objects.
    """

    def __init__(self) -> None:
        self.rows: int = GRID_CONFIG.GRID_ROWS
        self.cols: int = GRID_CONFIG.GRID_COLS

        # Initialize grids
        self.binary_grid  = np.ones((self.rows, self.cols), dtype=np.uint8)
        self.type_grid    = np.full((self.rows, self.cols), CELL_WALL, dtype=np.uint8)
        self.room_id_grid = np.full((self.rows, self.cols), "", dtype=object)
        self.cost_grid    = np.full(
            (self.rows, self.cols), COST_CONFIG.COST_WALL, dtype=np.float32
        )

        self.rooms: List[RoomDefinition] = ROOM_DATABASE
        self._built: bool = False

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def build(self) -> "HospitalMap":
        """
        Generate the complete hospital map.

        Build sequence:
            1. Carve main corridors
            2. Carve rooms
            3. Carve doorways
            4. Build cost grid
            5. Validate connectivity

        Returns:
            self (for method chaining)
        """
        log.info("Building 100x100 hospital map...")

        self._carve_main_corridors()
        self._carve_rooms()
        self._carve_doorways()
        self._build_cost_grid()
        self._validate_connectivity()

        self._built = True
        free_cells = int(np.sum(self.binary_grid == 0))
        wall_cells = int(np.sum(self.binary_grid == 1))
        log.info(
            "Map built: %d rooms, %d free cells, %d wall cells",
            len(self.rooms), free_cells, wall_cells,
        )
        return self

    def is_free(self, row: int, col: int) -> bool:
        """Return True if cell (row, col) is walkable."""
        if not self._in_bounds(row, col):
            return False
        return self.binary_grid[row, col] == 0

    def is_wall(self, row: int, col: int) -> bool:
        """Return True if cell (row, col) is a wall."""
        if not self._in_bounds(row, col):
            return True
        return self.binary_grid[row, col] == 1

    def get_cost(self, row: int, col: int) -> float:
        """Return traversal cost of cell (row, col)."""
        if not self._in_bounds(row, col):
            return COST_CONFIG.COST_WALL
        return float(self.cost_grid[row, col])

    def get_room_id(self, row: int, col: int) -> Optional[str]:
        """Return room_id of the room occupying cell (row, col), or None."""
        if not self._in_bounds(row, col):
            return None
        rid = self.room_id_grid[row, col]
        return rid if rid else None

    def get_room_at(self, row: int, col: int) -> Optional[RoomDefinition]:
        """Return RoomDefinition at (row, col), or None."""
        rid = self.get_room_id(row, col)
        return ROOMS_BY_ID.get(rid) if rid else None

    def get_neighbors_4(self, row: int, col: int) -> List[Tuple[int, int]]:
        """Return 4-connected walkable neighbors of (row, col)."""
        candidates = [
            (row - 1, col), (row + 1, col),
            (row, col - 1), (row, col + 1),
        ]
        return [(r, c) for r, c in candidates if self.is_free(r, c)]

    def get_neighbors_8(self, row: int, col: int) -> List[Tuple[int, int]]:
        """Return 8-connected walkable neighbors of (row, col)."""
        candidates = [
            (row - 1, col - 1), (row - 1, col), (row - 1, col + 1),
            (row,     col - 1),                  (row,     col + 1),
            (row + 1, col - 1), (row + 1, col),  (row + 1, col + 1),
        ]
        return [(r, c) for r, c in candidates if self.is_free(r, c)]

    # ─────────────────────────────────────────────────────────────────────────
    # Build Steps
    # ─────────────────────────────────────────────────────────────────────────

    def _carve_main_corridors(self) -> None:
        """Carve the hospital's main horizontal and vertical corridors."""
        for r0, c0, r1, c1, width in _MAIN_CORRIDORS:
            for w in range(width):
                if r0 == r1:
                    # Horizontal corridor
                    for col in range(c0, c1 + 1):
                        self._set_free(r0 + w, col, CELL_CORRIDOR, COST_CONFIG.COST_CORRIDOR)
                else:
                    # Vertical corridor
                    for row in range(r0, r1 + 1):
                        self._set_free(row, c0 + w, CELL_CORRIDOR, COST_CONFIG.COST_CORRIDOR)

        log.debug("Main corridors carved: %d corridor definitions", len(_MAIN_CORRIDORS))

    def _carve_rooms(self) -> None:
        """Carve interior of each room (1 cell inset from room boundary)."""
        for room in self.rooms:
            # Interior of room (leave 1-cell wall boundary)
            inset = 1
            r_start = room.top_row + inset
            r_end   = room.bottom_row - inset
            c_start = room.left_col + inset
            c_end   = room.right_col - inset

            if r_start > r_end or c_start > c_end:
                log.warning("Room %s too small to carve interior", room.room_id)
                continue

            for row in range(r_start, r_end + 1):
                for col in range(c_start, c_end + 1):
                    self._set_free(row, col, CELL_ROOM, COST_CONFIG.COST_ROOM_FLOOR)
                    self.room_id_grid[row, col] = room.room_id

        log.debug("Rooms carved: %d rooms", len(self.rooms))

    def _carve_doorways(self) -> None:
        """
        Carve doorways at each room's entry point and connect to nearest corridor.
        """
        for room in self.rooms:
            er, ec = room.entry_row, room.entry_col

            # Carve the doorway cell
            self._set_free(er, ec, CELL_DOORWAY, COST_CONFIG.COST_DOORWAY)
            self.room_id_grid[er, ec] = room.room_id

            # Carve a short connecting passage toward the nearest corridor
            self._connect_to_corridor(room)

        log.debug("Doorways carved for %d rooms", len(self.rooms))

    def _connect_to_corridor(self, room: RoomDefinition) -> None:
        """Carve a passage from the room's entry point to the nearest corridor.

        Uses BFS from the entry point through free/wall cells toward the
        nearest corridor cell, caraving a narrow (1-cell) passage. This
        guarantees every room connects to the corridor network.
        """
        er, ec = room.entry_row, room.entry_col

        # If the entry already touches a corridor or free path, done.
        if self._reaches_corridor(er, ec):
            return

        # BFS to find nearest corridor cell
        visited: Set[Tuple[int, int]] = {(er, ec)}
        queue: Deque[Tuple[int, int]] = deque([(er, ec)])
        parent: Dict[Tuple[int, int], Tuple[int, int]] = {}

        found: Optional[Tuple[int, int]] = None
        while queue:
            r, c = queue.popleft()
            # If this cell is a corridor, we've found the connection target
            if self.type_grid[r, c] == CELL_CORRIDOR:
                found = (r, c)
                break

            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if not self._in_bounds(nr, nc):
                    continue
                if (nr, nc) in visited:
                    continue
                # Never carve through another room's interior
                other_room = self.room_id_grid[nr, nc]
                if other_room and other_room != room.room_id:
                    continue
                # Traverse walls or free cells toward a corridor
                if not self.is_free(nr, nc) and self.type_grid[nr, nc] != CELL_CORRIDOR:
                    visited.add((nr, nc))
                    parent[(nr, nc)] = (r, c)
                    queue.append((nr, nc))
                elif self.is_free(nr, nc):
                    visited.add((nr, nc))
                    parent[(nr, nc)] = (r, c)
                    queue.append((nr, nc))

        if found is None:
            log.warning("Room %s entry could not connect to a corridor.", room.room_id)
            return

        # Trace path back from corridor to entry and carve it
        node: Optional[Tuple[int, int]] = found
        count = 0
        while node is not None and node != (er, ec):
            r, c = node
            # Don't overwrite existing corridor cells
            if self.type_grid[r, c] != CELL_CORRIDOR:
                self._set_free(r, c, CELL_FREE, COST_CONFIG.COST_FREE)
            node = parent.get(node)
            count += 1
            # Safety against infinite loops
            if count > 60:
                log.warning("Room %s connection loop exceeded limit.", room.room_id)
                break

    def _reaches_corridor(self, row: int, col: int) -> bool:
        """Return True if (row, col) is adjacent to (or on) a corridor, door, or free path."""
        if self.type_grid[row, col] == CELL_CORRIDOR:
            return True
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = row + dr, col + dc
            if self._in_bounds(nr, nc) and self.type_grid[nr, nc] == CELL_CORRIDOR:
                return True
        return False

    def _build_cost_grid(self) -> None:
        """Finalize the cost grid from type_grid values."""
        cost_map = {
            CELL_WALL:     COST_CONFIG.COST_WALL,
            CELL_FREE:     COST_CONFIG.COST_FREE,
            CELL_ROOM:     COST_CONFIG.COST_ROOM_FLOOR,
            CELL_DOORWAY:  COST_CONFIG.COST_DOORWAY,
            CELL_CORRIDOR: COST_CONFIG.COST_CORRIDOR,
        }
        for r in range(self.rows):
            for c in range(self.cols):
                cell_type = int(self.type_grid[r, c])
                self.cost_grid[r, c] = cost_map.get(cell_type, COST_CONFIG.COST_WALL)

    def _validate_connectivity(self) -> None:
        """
        Validate that all room entries are reachable via flood fill from a
        reference free cell. Logs a warning for any disconnected room.
        """
        # Find a reference free cell
        ref: Optional[Tuple[int, int]] = None
        for r in range(self.rows):
            for c in range(self.cols):
                if self.is_free(r, c):
                    ref = (r, c)
                    break
            if ref:
                break

        if ref is None:
            log.error("Hospital map has NO free cells! Layout is invalid.")
            return

        # Flood fill
        reachable: Set[Tuple[int, int]] = set()
        queue: Deque[Tuple[int, int]] = deque([ref])
        reachable.add(ref)

        while queue:
            r, c = queue.popleft()
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if self._in_bounds(nr, nc) and self.is_free(nr, nc) and (nr, nc) not in reachable:
                    reachable.add((nr, nc))
                    queue.append((nr, nc))

        # Check each room's entry is reachable
        disconnected: List[str] = []
        for room in self.rooms:
            if room.entry_point not in reachable:
                disconnected.append(room.room_id)

        if disconnected:
            log.warning(
                "Map connectivity: %d room(s) DISCONNECTED: %s",
                len(disconnected), ", ".join(disconnected),
            )
        else:
            log.info("Map connectivity: all %d rooms connected.", len(self.rooms))

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _set_free(
        self,
        row: int,
        col: int,
        cell_type: int,
        cost: float,
    ) -> None:
        """Mark a single cell as free with given type and cost."""
        if not self._in_bounds(row, col):
            return
        self.binary_grid[row, col] = 0
        self.type_grid[row, col]   = cell_type
        self.cost_grid[row, col]   = cost

    def _in_bounds(self, row: int, col: int) -> bool:
        """Return True if (row, col) is within grid bounds."""
        return 0 <= row < self.rows and 0 <= col < self.cols

    def __repr__(self) -> str:
        return (
            f"HospitalMap({self.rows}x{self.cols}, "
            f"rooms={len(self.rooms)}, built={self._built})"
        )

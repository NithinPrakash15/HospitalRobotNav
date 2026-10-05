"""
HospitalRobotNav — Semantic Query Engine
=========================================
Natural-language and keyword-based semantic query interface
for destination resolution in a hospital environment.

This module provides the higher-level semantic understanding layer
on top of environment/semantic_map.py. It supports:

    1. Exact match:    "ICU" → ICU-01 room
    2. Fuzzy match:    "intensive" → ICU-01 (substring)
    3. Category match: "emergency" → nearest Emergency room
    4. Alias match:    "ER" → Emergency Room
    5. Nearest query:  "nearest pharmacy" from robot position

ROS2 Note:
    In a production system with LLM integration:
        → Input  (VLM/LLM parsed query): std_msgs/String
        → Output (resolved grid goal):   geometry_msgs/PoseStamped
        → Service: /semantic_map/resolve (std_srvs/srv with custom request)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from maps.hospital.room_definitions import ROOM_DATABASE, RoomCategory
from environment.occupancy_grid import OccupancyGrid
from utilities.geometry import euclidean_distance
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]


# Common shorthand aliases for room names (simulates LLM synonym resolution)
ROOM_ALIASES: Dict[str, str] = {
    "er":           "ER",
    "emergency":    "ER",
    "crash":        "ER",
    "icu":          "ICU-01",
    "intensive":    "ICU-01",
    "ot":           "OT-01",
    "surgery":      "OT-01",
    "operating":    "OT-01",
    "xray":         "RAD-01",
    "radiology":    "RAD-01",
    "mri":          "RAD-01",
    "imaging":      "RAD-01",
    "pharmacy":     "PHM-01",
    "meds":         "PHM-01",
    "lab":          "LAB-01",
    "laboratory":   "LAB-01",
    "reception":    "RCP-01",
    "front desk":   "RCP-01",
    "lobby":        "RCP-01",
    "ward":         "PW-01",
    "nicu":         "NICU-01",
    "nursery":      "NICU-01",
    "cath":         "CATH-01",
    "cafeteria":    "CAF-01",
    "food":         "CAF-01",
    "charge":       "CHG-01",
    "dock":         "CHG-01",
    "charging":     "CHG-01",
}


class SemanticQueryEngine:
    """
    Semantic query engine for hospital navigation.

    Resolves free-text natural language queries into grid positions
    that can be passed directly to the path planner.

    Usage:
        engine = SemanticQueryEngine(occupancy_grid)
        pos = engine.resolve("Take medicine to the ICU")
        if pos:
            robot.navigate_to_pos(*pos)

    Resolution Pipeline:
        1. Preprocess (lowercase, strip)
        2. Check exact room ID match
        3. Check alias table
        4. Check room label substring match
        5. Check room category match
        6. Return None if unresolvable

    Attributes:
        _grid:      OccupancyGrid for position validation.
        _id_index:  room_id → RoomDefinition lookup.
        _label_idx: lowercase_label → RoomDefinition lookup.
    """

    def __init__(self, occupancy_grid: OccupancyGrid) -> None:
        self._grid = occupancy_grid
        self._build_index()

    def _build_index(self) -> None:
        """Build lookup indices over the room database."""
        self._id_index: Dict[str, object]  = {}
        self._label_idx: Dict[str, object] = {}
        self._category_idx: Dict[str, List[object]] = {}

        for room in ROOM_DATABASE:
            self._id_index[room.room_id.upper()] = room
            self._label_idx[room.label.lower()]  = room

            cat_key = room.category.name.lower()
            self._category_idx.setdefault(cat_key, []).append(room)

        log.debug("SemanticQueryEngine indexed %d rooms.", len(ROOM_DATABASE))

    def resolve(
        self,
        query: str,
        robot_pos: Optional[GridPos] = None,
    ) -> Optional[GridPos]:
        """
        Resolve a natural-language query to a grid position.

        Args:
            query:     Free-text destination query.
            robot_pos: Optional current robot position for nearest queries.

        Returns:
            (row, col) grid position, or None if not resolvable.
        """
        q = query.strip().lower()

        # Step 1: "nearest X" prefix stripping
        for prefix in ("nearest ", "closest ", "go to ", "take me to ", "navigate to "):
            if q.startswith(prefix):
                q = q[len(prefix):]
                break

        # Step 2: Alias lookup
        alias = ROOM_ALIASES.get(q)
        if alias:
            room = self._id_index.get(alias.upper())
            if room:
                return self._snap_to_free(room.center_row, room.center_col)

        # Step 3: Exact room ID
        room = self._id_index.get(q.upper())
        if room:
            return self._snap_to_free(room.center_row, room.center_col)

        # Step 4: Exact label
        room = self._label_idx.get(q)
        if room:
            return self._snap_to_free(room.center_row, room.center_col)

        # Step 5: Substring in room label (fuzzy)
        matches = [r for r in ROOM_DATABASE if q in r.label.lower() or q in r.room_id.lower()]
        if matches:
            target = self._pick_nearest(matches, robot_pos) if robot_pos else matches[0]
            return self._snap_to_free(target.center_row, target.center_col)

        # Step 6: Category keyword match
        for cat_key, rooms in self._category_idx.items():
            if q in cat_key:
                target = self._pick_nearest(rooms, robot_pos) if robot_pos else rooms[0]
                return self._snap_to_free(target.center_row, target.center_col)

        log.warning("SemanticQueryEngine: could not resolve query '%s'", query)
        return None

    def resolve_all(self, query: str, robot_pos: Optional[GridPos] = None) -> List[GridPos]:
        """
        Resolve a query to all matching room positions (sorted by distance).

        Useful for "find all pharmacies" style queries.

        Args:
            query:     Destination query.
            robot_pos: Optional robot position for proximity sorting.

        Returns:
            List of (row, col) grid positions.
        """
        q = query.strip().lower()
        matches = [r for r in ROOM_DATABASE
                   if q in r.label.lower() or q in r.room_id.lower()
                   or q in r.category.name.lower()]

        positions = []
        for room in matches:
            pos = self._snap_to_free(room.center_row, room.center_col)
            if pos:
                positions.append(pos)

        if robot_pos and positions:
            positions.sort(key=lambda p: euclidean_distance(p, robot_pos))

        return positions

    def get_destination_names(self) -> List[Tuple[str, str, GridPos]]:
        """
        Return all navigable destinations.

        Returns:
            List of (room_id, label, grid_pos) sorted by room_id.
        """
        results = []
        for room in sorted(ROOM_DATABASE, key=lambda r: r.room_id):
            pos = self._snap_to_free(room.center_row, room.center_col)
            if pos:
                results.append((room.room_id, room.label, pos))
        return results

    def _snap_to_free(self, row: int, col: int) -> Optional[GridPos]:
        """Snap position to nearest free cell."""
        if self._grid.is_free(row, col):
            return (row, col)
        return self._grid.find_nearest_free(row, col)

    def _pick_nearest(self, rooms: list, robot_pos: Optional[GridPos]) -> object:
        """Return the room nearest to robot_pos, or first room if no pos given."""
        if not robot_pos:
            return rooms[0]
        return min(
            rooms,
            key=lambda r: euclidean_distance(
                (r.center_row, r.center_col), robot_pos
            ),
        )

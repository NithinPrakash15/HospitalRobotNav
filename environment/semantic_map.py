"""
HospitalRobotNav — Semantic Map
=================================
Provides semantic understanding of the hospital environment.

The semantic map bridges the gap between:
    Natural language destinations ("Go to ICU")
    ↓
    Room database lookup ("ICU-01")
    ↓
    Navigation graph node
    ↓
    Grid coordinates (row=12, col=60)
    ↓
    A* goal cell

This is the key abstraction enabling language-grounded robot navigation —
a foundational requirement for Vision-Language Model integration.

ROS2 Note:
    In a deployed system, this would interface with:
    - semantic_map_server (custom ROS2 node)
    - or RTAB-Map's database with semantic labels
    - or a ROS2 service: /semantic_map/resolve_destination
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from maps.hospital.room_definitions import (
    ROOM_DATABASE, ROOMS_BY_ID, RoomCategory, RoomPriority,
    lookup_room_by_alias, get_room_entry,
)
from environment.navigation_graph import NavigationGraph
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]


class SemanticMap:
    """
    Semantic layer over the hospital navigation graph.

    Provides:
        - Text-to-destination resolution ("ICU" → grid cell)
        - Category-based room discovery ("find nearest pharmacy")
        - Priority-based emergency routing
        - Room metadata for UI display
        - Foundation for VLM / LLM instruction parsing

    Attributes:
        _graph:     The navigation graph (NetworkX-backed).
        _room_map:  room_id → RoomDefinition.
    """

    def __init__(self, nav_graph: NavigationGraph) -> None:
        """
        Initialize with a built NavigationGraph.

        Args:
            nav_graph: Built NavigationGraph instance.
        """
        assert nav_graph._built, "NavigationGraph must be built first."
        self._graph = nav_graph
        self._room_map = ROOMS_BY_ID

        log.info(
            "SemanticMap initialized with %d rooms.",
            len(self._room_map),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Core: Text → Grid Position
    # ─────────────────────────────────────────────────────────────────────────

    def resolve(self, query: str) -> Optional[GridPos]:
        """
        Resolve a natural language room query to a grid position.

        Resolution order:
            1. Exact room_id match (e.g., "ICU-01")
            2. Alias / label match (e.g., "intensive care unit")
            3. Partial match (e.g., "ICU")
            4. Category name match (e.g., "emergency")

        Args:
            query: Free-form string destination description.

        Returns:
            (row, col) grid position of the room's entry point, or None.

        Example:
            pos = semantic_map.resolve("ICU")
            # Returns (18, 60) — ICU-01 entry point
        """
        query = query.strip()

        # 1. Direct room ID
        if query in self._room_map:
            return get_room_entry(query)

        # 2. Alias/label lookup (case-insensitive)
        room = lookup_room_by_alias(query)
        if room is not None:
            log.info("Resolved '%s' → %s (%s)", query, room.room_id, room.label)
            return room.entry_point

        # 3. Partial string match on label or aliases
        q_lower = query.lower()
        for room in ROOM_DATABASE:
            if q_lower in room.label.lower():
                log.info(
                    "Partial match: '%s' → %s (%s)", query, room.room_id, room.label
                )
                return room.entry_point
            for alias in room.aliases:
                if q_lower in alias.lower():
                    log.info(
                        "Alias partial match: '%s' → %s (%s)",
                        query, room.room_id, room.label,
                    )
                    return room.entry_point

        # 4. Category name match
        for cat in RoomCategory:
            if q_lower in cat.name.lower():
                rooms = [
                    r for r in ROOM_DATABASE if r.category == cat
                ]
                if rooms:
                    best = min(rooms, key=lambda r: r.priority.value)
                    log.info(
                        "Category match: '%s' → %s (%s)",
                        query, best.room_id, best.label,
                    )
                    return best.entry_point

        log.warning("Could not resolve destination: '%s'", query)
        return None

    def resolve_to_room_id(self, query: str) -> Optional[str]:
        """
        Resolve a query to a room_id string (not coordinates).

        Args:
            query: Free-form room name.

        Returns:
            room_id string (e.g., "ICU-01") or None.
        """
        query = query.strip()

        if query in self._room_map:
            return query

        room = lookup_room_by_alias(query)
        if room:
            return room.room_id

        q_lower = query.lower()
        for room in ROOM_DATABASE:
            if q_lower in room.label.lower():
                return room.room_id

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Room Discovery
    # ─────────────────────────────────────────────────────────────────────────

    def find_nearest_room_of_category(
        self,
        category: RoomCategory,
        from_pos: GridPos,
    ) -> Optional[GridPos]:
        """
        Find the nearest room of a given category to a starting position.

        Uses Euclidean distance to entry points for fast lookup.

        Args:
            category: RoomCategory to search for.
            from_pos: Current robot position (row, col).

        Returns:
            Entry point (row, col) of the nearest matching room, or None.
        """
        candidates = [
            r for r in ROOM_DATABASE if r.category == category
        ]
        if not candidates:
            return None

        def dist_to(room):
            er, ec = room.entry_row, room.entry_col
            return ((er - from_pos[0]) ** 2 + (ec - from_pos[1]) ** 2) ** 0.5

        nearest = min(candidates, key=dist_to)
        return nearest.entry_point

    def get_nearest_charging_station(self, from_pos: GridPos) -> Optional[GridPos]:
        """Convenience: find nearest charging station from current position."""
        return self.find_nearest_room_of_category(RoomCategory.ROBOT, from_pos)

    def get_emergency_rooms(self) -> List[GridPos]:
        """Return entry points of all emergency department rooms."""
        return [
            r.entry_point for r in ROOM_DATABASE
            if r.category == RoomCategory.EMERGENCY
        ]

    def get_critical_rooms(self) -> List[GridPos]:
        """Return entry points of all critical-priority rooms."""
        return [
            r.entry_point for r in ROOM_DATABASE
            if r.priority == RoomPriority.CRITICAL
        ]

    # ─────────────────────────────────────────────────────────────────────────
    # Room Information
    # ─────────────────────────────────────────────────────────────────────────

    def get_room_info(self, query: str) -> Optional[Dict]:
        """
        Return a dictionary of room metadata for UI display.

        Args:
            query: Room name or ID.

        Returns:
            Dict with keys: room_id, label, category, priority, description,
            entry_point, center, width, height.
        """
        room_id = self.resolve_to_room_id(query)
        if room_id is None:
            return None

        room = self._room_map[room_id]
        return {
            "room_id":     room.room_id,
            "label":       room.label,
            "category":    room.category.name,
            "priority":    room.priority.name,
            "description": room.description,
            "entry_point": room.entry_point,
            "center":      (room.center_row, room.center_col),
            "width":       room.width,
            "height":      room.height,
            "aliases":     room.aliases,
        }

    def get_all_room_labels(self) -> List[str]:
        """Return sorted list of all room labels (for UI dropdown)."""
        return sorted(r.label for r in ROOM_DATABASE)

    def get_all_room_ids(self) -> List[str]:
        """Return sorted list of all room IDs."""
        return sorted(r.room_id for r in ROOM_DATABASE)

    def get_destination_list(self) -> List[Tuple[str, str, GridPos]]:
        """
        Return a list of (room_id, label, entry_pos) for all rooms.

        Sorted by priority then alphabetically.
        Used to populate the UI navigation panel destination list.
        """
        return sorted(
            [
                (r.room_id, r.label, r.entry_point)
                for r in ROOM_DATABASE
            ],
            key=lambda x: (ROOMS_BY_ID[x[0]].priority.value, x[1]),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Graph-level Navigation
    # ─────────────────────────────────────────────────────────────────────────

    def get_graph_route(
        self,
        source_query: str,
        target_query: str,
    ) -> Optional[List[GridPos]]:
        """
        Compute a high-level graph route between two rooms (by label/ID).

        Returns a list of entry-point grid positions to visit in order.
        This provides a coarse waypoint list for the mission planner.

        Args:
            source_query: Source room name or ID.
            target_query: Target room name or ID.

        Returns:
            Ordered list of (row, col) waypoints, or None if unreachable.
        """
        src_id = self.resolve_to_room_id(source_query)
        tgt_id = self.resolve_to_room_id(target_query)

        if src_id is None or tgt_id is None:
            log.warning(
                "Cannot resolve route: '%s' → '%s'", source_query, target_query
            )
            return None

        node_path = self._graph.get_shortest_path(src_id, tgt_id)
        if node_path is None:
            return None

        waypoints: List[GridPos] = []
        for node_id in node_path:
            pos = self._graph.graph.nodes[node_id].get("pos")
            if pos:
                waypoints.append(tuple(pos))

        return waypoints if waypoints else None

    # ─────────────────────────────────────────────────────────────────────────
    # Spatial Relationship Reasoning & Contextual Topology
    # ─────────────────────────────────────────────────────────────────────────

    def get_opposite_room(self, query: str) -> Optional[Any]:
        """Find the room directly across the corridor from the given room."""
        ref_id = self.resolve_to_room_id(query)
        if not ref_id or ref_id not in self._room_map:
            return None
        ref_room = self._room_map[ref_id]
        ref_r, ref_c = ref_room.center_row, ref_room.center_col

        candidates = []
        for room in ROOM_DATABASE:
            if room.room_id == ref_id:
                continue
            dr = abs(room.center_row - ref_r)
            dc = abs(room.center_col - ref_c)
            # Opposite across horizontal corridor (similar col, moderate dr)
            if dc <= 8 and 8 <= dr <= 24:
                candidates.append((dr + dc, room))
            # Opposite across vertical corridor (similar row, moderate dc)
            elif dr <= 8 and 8 <= dc <= 24:
                candidates.append((dr + dc, room))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]
        return None

    def get_adjacent_rooms(self, query: str) -> List[Any]:
        """Find rooms immediately neighboring the given room along the same corridor side."""
        ref_id = self.resolve_to_room_id(query)
        if not ref_id or ref_id not in self._room_map:
            return []
        ref_room = self._room_map[ref_id]
        ref_r, ref_c = ref_room.center_row, ref_room.center_col

        adjacent = []
        for room in ROOM_DATABASE:
            if room.room_id == ref_id:
                continue
            dist = ((room.center_row - ref_r) ** 2 + (room.center_col - ref_c) ** 2) ** 0.5
            if 4.0 <= dist <= 16.0:
                adjacent.append(room)
        return sorted(adjacent, key=lambda r: ((r.center_row - ref_r) ** 2 + (r.center_col - ref_c) ** 2))

    def get_rooms_between(self, query_a: str, query_b: str) -> List[Any]:
        """Find rooms geometrically between room A and room B."""
        id_a = self.resolve_to_room_id(query_a)
        id_b = self.resolve_to_room_id(query_b)
        if not id_a or not id_b or id_a not in self._room_map or id_b not in self._room_map:
            return []
        room_a = self._room_map[id_a]
        room_b = self._room_map[id_b]

        min_r, max_r = min(room_a.center_row, room_b.center_row), max(room_a.center_row, room_b.center_row)
        min_c, max_c = min(room_a.center_col, room_b.center_col), max(room_a.center_col, room_b.center_col)

        between = []
        for room in ROOM_DATABASE:
            if room.room_id in (id_a, id_b):
                continue
            if min_r - 2 <= room.center_row <= max_r + 2 and min_c - 2 <= room.center_col <= max_c + 2:
                between.append(room)
        return between

    def get_least_congested_room(
        self,
        category_or_label: str,
        obstacle_positions: List[GridPos],
    ) -> Optional[GridPos]:
        """Find the room of a given category/type with the lowest obstacle density around its entry."""
        # Find all matching rooms
        q_lower = category_or_label.lower()
        candidates = []
        for room in ROOM_DATABASE:
            if q_lower in room.label.lower() or q_lower in room.category.name.lower():
                candidates.append(room)

        if not candidates:
            # Fallback to category lookup
            for cat in RoomCategory:
                if q_lower in cat.name.lower():
                    candidates = [r for r in ROOM_DATABASE if r.category == cat]
                    break

        if not candidates:
            return None

        # Score by obstacle congestion within radius of 6 cells
        best_room = None
        min_congestion = 9999
        for room in candidates:
            er, ec = room.entry_point
            congestion = sum(
                1 for (orow, ocol) in obstacle_positions
                if abs(orow - er) <= 6 and abs(ocol - ec) <= 6
            )
            if congestion < min_congestion:
                min_congestion = congestion
                best_room = room

        return best_room.entry_point if best_room else None

    def __repr__(self) -> str:
        return f"SemanticMap(rooms={len(self._room_map)})"


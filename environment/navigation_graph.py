"""
HospitalRobotNav — Navigation Graph
======================================
Builds and maintains the hospital navigation graph using NetworkX.

The navigation graph represents the hospital as a weighted undirected graph:
    - Nodes: rooms (by room_id / nav_node_id) + corridor junction points
    - Edges: connections between rooms via corridors, with traversal costs

This graph layer operates ABOVE the grid planner:
    1. High-level mission planner uses the graph for room-to-room routing
    2. Grid-level planners (A*, D* Lite) handle actual cell-by-cell navigation

Graph Topology:
    Rooms ← corridor edges → Junction nodes ← corridor edges → Rooms

Design:
    Junction nodes (where horizontal and vertical main corridors intersect)
    are derived from the corridor layout in ``hospital_map`` so the graph
    stays in sync with the procedurally generated floor plan.

ROS2 Note:
    Equivalent to the semantic map maintained by the Nav2 behavior tree,
    often implemented as a graph SLAM or semantic SLAM result.

Reference:
    Thrun, S., Burgard, W., Fox, D. "Probabilistic Robotics". MIT Press, 2005.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx

from maps.hospital.hospital_map import _MAIN_CORRIDORS
from maps.hospital.room_definitions import (
    ROOM_DATABASE, ROOMS_BY_ID, RoomDefinition
)
from utilities.geometry import euclidean_distance
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]


class NavigationGraph:
    """
    Weighted undirected navigation graph of the hospital.

    Node attributes:
        label    (str)  : Human-readable name
        pos      (tuple): (row, col) grid position (entry point or junction)
        category (str)  : Room category or "junction"
        room_id  (str)  : Room ID if the node is a room entry

    Edge attributes:
        weight   (float): Cost to traverse this edge
        distance (float): Euclidean distance in grid cells
        edge_type (str) : "corridor" | "room_access" | "elevator"
    """

    def __init__(self) -> None:
        self._graph: nx.Graph = nx.Graph()
        self._built: bool = False
        self._room_nodes: Dict[str, str] = {}   # room_id → graph node id
        self._pos_lookup: Dict[GridPos, str] = {}   # (row,col) → node id

    # ─────────────────────────────────────────────────────────────────────────
    # Build
    # ─────────────────────────────────────────────────────────────────────────

    def build(self) -> "NavigationGraph":
        """
        Construct the full hospital navigation graph.

        1. Add room entry nodes
        2. Add corridor junction nodes (derived from map corridors)
        3. Connect rooms to their nearest corridor junctions
        4. Connect junctions along corridors

        Returns:
            self (for method chaining)
        """
        log.info("Building hospital navigation graph...")

        self._add_room_nodes()
        self._add_corridor_junctions()
        self._connect_rooms_to_corridors()
        self._connect_corridor_junctions()

        self._built = True
        log.info(
            "Navigation graph built: %d nodes, %d edges",
            self._graph.number_of_nodes(),
            self._graph.number_of_edges(),
        )
        return self

    # ─────────────────────────────────────────────────────────────────────────
    # Junction derivation
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _derive_junctions() -> List[Tuple[int, int]]:
        """
        Compute corridor junction positions from the map's main corridors.

        A junction is placed at the intersection of each horizontal and
        vertical corridor band.  Positions use the band centre lines.

        Returns:
            List of (row, col) junction positions.
        """
        h_rows: Set[int] = set()
        v_cols: Set[int] = set()

        for r0, c0, r1, c1, width in _MAIN_CORRIDORS:
            if r0 == r1:
                # Horizontal corridor: centre row = r0 + width // 2
                h_rows.add(r0 + width // 2)
            else:
                v_cols.add(c0 + width // 2)

        # Sort for deterministic ordering
        junctions: List[Tuple[int, int]] = []
        for row in sorted(h_rows):
            for col in sorted(v_cols):
                junctions.append((row, col))
        return junctions

    def _add_room_nodes(self) -> None:
        """Add one node per room at its entry point."""
        for room in ROOM_DATABASE:
            node_id = room.nav_node_id
            self._graph.add_node(
                node_id,
                label=room.label,
                pos=(room.entry_row, room.entry_col),
                category=room.category.name,
                room_id=room.room_id,
                priority=room.priority.value,
            )
            self._room_nodes[room.room_id] = node_id
            self._pos_lookup[(room.entry_row, room.entry_col)] = node_id

        log.debug("Added %d room nodes", len(ROOM_DATABASE))

    def _add_corridor_junctions(self) -> None:
        """Add junction nodes at corridor intersections derived from the map."""
        junction_positions = self._derive_junctions()

        junction_count = 0
        for row, col in junction_positions:
            jid = f"JCT-{row}-{col}"
            self._graph.add_node(
                jid,
                label=f"Junction ({row},{col})",
                pos=(row, col),
                category="junction",
                room_id="",
                priority=3,
            )
            self._pos_lookup[(row, col)] = jid
            junction_count += 1

        log.debug("Added %d corridor junction nodes", junction_count)

    def _connect_rooms_to_corridors(self) -> None:
        """Connect each room node to the nearest corridor junction."""
        junction_nodes = [
            n for n, d in self._graph.nodes(data=True)
            if d.get("category") == "junction"
        ]

        for room in ROOM_DATABASE:
            rnode = room.nav_node_id
            room_pos: GridPos = (room.entry_row, room.entry_col)

            # Find the nearest junction
            best_jct: Optional[str] = None
            best_dist: float = float("inf")

            for jid in junction_nodes:
                jpos = self._graph.nodes[jid]["pos"]
                dist = euclidean_distance(room_pos, jpos)
                if dist < best_dist:
                    best_dist = dist
                    best_jct = jid

            if best_jct is not None:
                self._graph.add_edge(
                    rnode, best_jct,
                    weight=best_dist,
                    distance=best_dist,
                    edge_type="room_access",
                )

    def _connect_corridor_junctions(self) -> None:
        """Connect corridor junctions along horizontal and vertical spines."""
        junction_nodes = {
            n: d for n, d in self._graph.nodes(data=True)
            if d.get("category") == "junction"
        }

        # Group by row (horizontal corridors)
        row_groups: Dict[int, List[str]] = {}
        for nid, data in junction_nodes.items():
            r = data["pos"][0]
            row_groups.setdefault(r, []).append(nid)

        for row, nodes in row_groups.items():
            # Sort by column
            sorted_nodes = sorted(nodes, key=lambda n: junction_nodes[n]["pos"][1])
            for i in range(len(sorted_nodes) - 1):
                a, b = sorted_nodes[i], sorted_nodes[i + 1]
                pa = junction_nodes[a]["pos"]
                pb = junction_nodes[b]["pos"]
                dist = euclidean_distance(pa, pb)
                self._graph.add_edge(
                    a, b, weight=dist, distance=dist, edge_type="corridor"
                )

        # Group by col (vertical corridors)
        col_groups: Dict[int, List[str]] = {}
        for nid, data in junction_nodes.items():
            c = data["pos"][1]
            col_groups.setdefault(c, []).append(nid)

        for col, nodes in col_groups.items():
            sorted_nodes = sorted(nodes, key=lambda n: junction_nodes[n]["pos"][0])
            for i in range(len(sorted_nodes) - 1):
                a, b = sorted_nodes[i], sorted_nodes[i + 1]
                pa = junction_nodes[a]["pos"]
                pb = junction_nodes[b]["pos"]
                dist = euclidean_distance(pa, pb)
                if not self._graph.has_edge(a, b):
                    self._graph.add_edge(
                        a, b, weight=dist, distance=dist, edge_type="corridor"
                    )

    # ─────────────────────────────────────────────────────────────────────────
    # Shortest Path Queries
    # ─────────────────────────────────────────────────────────────────────────

    def get_shortest_path(
        self,
        source_room_id: str,
        target_room_id: str,
    ) -> Optional[List[str]]:
        """
        Compute the shortest node-level path between two rooms using Dijkstra.

        Args:
            source_room_id: Room ID of the start room.
            target_room_id: Room ID of the destination room.

        Returns:
            List of node IDs forming the path, or None if unreachable.
        """
        src = self._room_nodes.get(source_room_id)
        tgt = self._room_nodes.get(target_room_id)

        if src is None or tgt is None:
            log.warning(
                "Unknown room IDs: src=%s, tgt=%s", source_room_id, target_room_id
            )
            return None

        try:
            path = nx.shortest_path(self._graph, src, tgt, weight="weight")
            return path
        except nx.NetworkXNoPath:
            log.warning("No graph path from %s to %s", source_room_id, target_room_id)
            return None

    def get_room_entry_position(self, room_id: str) -> Optional[GridPos]:
        """
        Get the grid entry position (row, col) of a room.

        Args:
            room_id: Room ID string.

        Returns:
            (row, col) of the room's entry node, or None.
        """
        node = self._room_nodes.get(room_id)
        if node is None:
            return None
        return self._graph.nodes[node].get("pos")

    def get_all_room_positions(self) -> Dict[str, GridPos]:
        """Return mapping of room_id → (row, col) entry position."""
        return {
            rid: self._graph.nodes[nid]["pos"]
            for rid, nid in self._room_nodes.items()
            if nid in self._graph
        }

    def get_nearby_rooms(
        self,
        room_id: str,
        max_hops: int = 2,
    ) -> List[str]:
        """
        Find rooms reachable within `max_hops` graph edges.

        Args:
            room_id:  Source room ID.
            max_hops: Maximum number of graph edges to traverse.

        Returns:
            List of reachable room IDs.
        """
        src = self._room_nodes.get(room_id)
        if src is None:
            return []

        reachable = nx.single_source_shortest_path_length(
            self._graph, src, cutoff=max_hops
        )
        results = []
        for nid in reachable:
            room_id_attr = self._graph.nodes[nid].get("room_id", "")
            if room_id_attr and room_id_attr != room_id:
                results.append(room_id_attr)
        return results

    def get_path_graph_distance(
        self,
        source_room_id: str,
        target_room_id: str,
    ) -> Optional[float]:
        """
        Return graph shortest-path weighted distance between two rooms.

        Args:
            source_room_id: Source room ID.
            target_room_id: Target room ID.

        Returns:
            Float distance, or None if unreachable.
        """
        src = self._room_nodes.get(source_room_id)
        tgt = self._room_nodes.get(target_room_id)
        if src is None or tgt is None:
            return None
        try:
            return nx.shortest_path_length(self._graph, src, tgt, weight="weight")
        except nx.NetworkXNoPath:
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Graph Properties
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def graph(self) -> nx.Graph:
        """Direct access to the underlying NetworkX graph."""
        return self._graph

    @property
    def room_nodes(self) -> Dict[str, str]:
        """Mapping of room_id → graph node id."""
        return dict(self._room_nodes)

    def node_count(self) -> int:
        """Total number of graph nodes."""
        return self._graph.number_of_nodes()

    def edge_count(self) -> int:
        """Total number of graph edges."""
        return self._graph.number_of_edges()

    def is_connected(self) -> bool:
        """Return True if the hospital graph is fully connected."""
        return nx.is_connected(self._graph)

    def __repr__(self) -> str:
        return (
            f"NavigationGraph(nodes={self.node_count()}, "
            f"edges={self.edge_count()}, connected={self.is_connected()})"
        )

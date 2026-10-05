"""
HospitalRobotNav — Semantic Map Node (ROS 2)
=============================================
Resolves natural-language destinations to grid coordinates and exposes
room metadata.

Services:
    /semantic_map/resolve_destination  (ResolveDestination)

Topics:
    pub  /semantic_map/rooms  (std_msgs/String)   [JSON summary]
"""

from __future__ import annotations

import json

import rclpy
from rclpy.node import Node

from std_msgs.msg import String, Header
from nav_msgs.msg import OccupancyGrid as RosOccupancyGrid, MapMetaData
from geometry_msgs.msg import Pose, Point, Quaternion
from visualization_msgs.msg import Marker, MarkerArray
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from hospital_robot_nav_msgs.srv import ResolveDestination

from hospital_robot_nav_core.maps.hospital.hospital_map import HospitalMap
from hospital_robot_nav_core.environment.occupancy_grid import OccupancyGrid
from hospital_robot_nav_core.environment.navigation_graph import NavigationGraph
from hospital_robot_nav_core.environment.semantic_map import SemanticMap


class SemanticMapNode(Node):
    """Semantic destination resolution and map publishing service for RViz."""

    def __init__(self) -> None:
        super().__init__("semantic_map_node")

        # ── Build the semantic map and occupancy grid (pure-Python core) ──
        try:
            self._hospital_map = HospitalMap().build()
            self._grid = OccupancyGrid(self._hospital_map)
            self._graph = NavigationGraph().build()
            self._semantic = SemanticMap(self._graph)
            self.get_logger().info(
                f"SemanticMap loaded: {len(self._semantic._room_map)} rooms."
            )
        except Exception as exc:  # pragma: no cover - defensive
            self.get_logger().error(f"Failed to build semantic map: {exc}")
            self._semantic = None
            self._grid = None

        # ── Service / Publishers ───────────────────────────────────────────
        self._srv = self.create_service(
            ResolveDestination,
            "/semantic_map/resolve_destination",
            self._on_resolve,
        )
        self._pub_rooms = self.create_publisher(String, "/semantic_map/rooms", 10)

        # QoS profile with transient local durability so RViz catches the map anytime
        latched_qos = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self._pub_map = self.create_publisher(RosOccupancyGrid, "/map", latched_qos)
        self._pub_markers = self.create_publisher(MarkerArray, "/semantic_map/markers", latched_qos)

        # Publish map & markers immediately and periodically
        self._publish_map_and_markers()
        self._timer = self.create_timer(3.0, self._publish_map_and_markers)

    def _publish_map_and_markers(self) -> None:
        """Publish full 120x120 occupancy grid to /map and 3D room labels to /semantic_map/markers for RViz."""
        if self._grid is None or self._semantic is None:
            return

        now = self.get_clock().now().to_msg()

        # 1. ROS OccupancyGrid (/map)
        msg = RosOccupancyGrid()
        msg.header.stamp = now
        msg.header.frame_id = "map"
        msg.info.resolution = 0.5  # 0.5m per cell
        msg.info.width = self._grid.cols
        msg.info.height = self._grid.rows
        msg.info.origin.position.x = 0.0
        msg.info.origin.position.y = 0.0
        msg.info.origin.position.z = 0.0
        msg.info.origin.orientation.w = 1.0

        # Occupancy grid array: 0=free, 100=occupied
        grid_data = []
        for r in range(self._grid.rows):
            for c in range(self._grid.cols):
                if not self._grid.is_free(r, c):
                    grid_data.append(100)
                else:
                    grid_data.append(0)
        msg.data = grid_data
        self._pub_map.publish(msg)

        # 2. 3D Hospital Room Markers (Floors, Doors, Labels) (/semantic_map/markers)
        CATEGORY_COLORS_RGB = {
            "EMERGENCY": (0.85, 0.15, 0.15),
            "CRITICAL_CARE": (0.75, 0.10, 0.10),
            "SURGICAL": (0.10, 0.40, 0.80),
            "IMAGING": (0.10, 0.50, 0.80),
            "LABORATORY": (0.40, 0.20, 0.80),
            "PATIENT_WARD": (0.25, 0.35, 0.65),
            "OUTPATIENT": (0.30, 0.45, 0.70),
            "PHARMACY": (0.15, 0.70, 0.40),
            "RECEPTION": (0.15, 0.55, 0.30),
            "ADMINISTRATIVE": (0.30, 0.35, 0.45),
            "SUPPORT": (0.35, 0.35, 0.45),
            "UTILITY": (0.35, 0.35, 0.45),
            "STAFF": (0.30, 0.40, 0.50),
            "AMENITY": (0.70, 0.45, 0.10),
            "TRANSPORT": (0.35, 0.35, 0.45),
            "ROBOT": (0.10, 0.80, 0.80),
        }

        marker_array = MarkerArray()
        for idx, (room_id, room) in enumerate(self._semantic._room_map.items()):
            if hasattr(room, "center"):
                center = room.center
            elif hasattr(room, "center_row") and hasattr(room, "center_col"):
                center = (room.center_row, room.center_col)
            else:
                center = (0, 0)

            room_name = getattr(room, "name", getattr(room, "label", room_id))
            cat_name = getattr(room.category, "name", str(room.category)) if hasattr(room, "category") else "GENERIC"
            cat_color = CATEGORY_COLORS_RGB.get(cat_name, (0.3, 0.4, 0.5))

            # 2a. 3D Room Floor Plate (Colored by Department Category)
            floor_m = Marker()
            floor_m.header.stamp = now
            floor_m.header.frame_id = "map"
            floor_m.ns = "hospital_room_floors"
            floor_m.id = idx * 3
            floor_m.type = Marker.CUBE
            floor_m.action = Marker.ADD
            floor_m.pose.position.x = ((room.left_col + room.right_col) / 2.0) * 0.5
            floor_m.pose.position.y = ((room.top_row + room.bottom_row) / 2.0) * 0.5
            floor_m.pose.position.z = 0.02
            floor_m.pose.orientation.w = 1.0
            floor_m.scale.x = float(room.right_col - room.left_col + 1) * 0.5
            floor_m.scale.y = float(room.bottom_row - room.top_row + 1) * 0.5
            floor_m.scale.z = 0.04
            floor_m.color.r = float(cat_color[0])
            floor_m.color.g = float(cat_color[1])
            floor_m.color.b = float(cat_color[2])
            floor_m.color.a = 0.55
            marker_array.markers.append(floor_m)

            # 2b. 3D Doorway Indicator (Gold Entrance Marker)
            if hasattr(room, "entry_row") and hasattr(room, "entry_col"):
                door_m = Marker()
                door_m.header.stamp = now
                door_m.header.frame_id = "map"
                door_m.ns = "hospital_doors"
                door_m.id = idx * 3 + 1
                door_m.type = Marker.CYLINDER
                door_m.action = Marker.ADD
                door_m.pose.position.x = float(room.entry_col) * 0.5
                door_m.pose.position.y = float(room.entry_row) * 0.5
                door_m.pose.position.z = 0.15
                door_m.pose.orientation.w = 1.0
                door_m.scale.x = 0.4
                door_m.scale.y = 0.4
                door_m.scale.z = 0.3
                door_m.color.r = 1.0
                door_m.color.g = 0.85
                door_m.color.b = 0.0
                door_m.color.a = 0.85
                marker_array.markers.append(door_m)

            # 2c. 3D Floating Room Text Label
            text_m = Marker()
            text_m.header.stamp = now
            text_m.header.frame_id = "map"
            text_m.ns = "hospital_room_labels"
            text_m.id = idx * 3 + 2
            text_m.type = Marker.TEXT_VIEW_FACING
            text_m.action = Marker.ADD
            text_m.pose.position.x = float(center[1]) * 0.5
            text_m.pose.position.y = float(center[0]) * 0.5
            text_m.pose.position.z = 0.65
            text_m.pose.orientation.w = 1.0
            text_m.scale.z = 0.65  # Text height in meters
            text_m.color.r = 1.0
            text_m.color.g = 1.0
            text_m.color.b = 1.0
            text_m.color.a = 0.95
            text_m.text = f"{room_name}\n[{room_id}]"
            marker_array.markers.append(text_m)

        # 2d. 3D Hospital Solid Walls (1.2m high extruded walls)
        walls_m = Marker()
        walls_m.header.stamp = now
        walls_m.header.frame_id = "map"
        walls_m.ns = "hospital_3d_walls"
        walls_m.id = 9999
        walls_m.type = Marker.CUBE_LIST
        walls_m.action = Marker.ADD
        walls_m.scale.x = 0.5
        walls_m.scale.y = 0.5
        walls_m.scale.z = 1.2  # 1.2m high walls
        walls_m.color.r = 0.15
        walls_m.color.g = 0.20
        walls_m.color.b = 0.32
        walls_m.color.a = 0.92

        for r in range(self._grid.rows):
            for c in range(self._grid.cols):
                if not self._grid.is_free(r, c):
                    p = Point()
                    p.x = float(c) * 0.5
                    p.y = float(r) * 0.5
                    p.z = 0.6  # Centered at 0.6m height
                    walls_m.points.append(p)
        marker_array.markers.append(walls_m)

        self._pub_markers.publish(marker_array)

        # 3. Room labels JSON
        labels = self._semantic.get_all_room_labels()
        summary_msg = String()
        summary_msg.data = json.dumps({"room_count": len(labels), "labels": labels})
        self._pub_rooms.publish(summary_msg)

    # ── Service callback ───────────────────────────────────────────────────

    def _on_resolve(self, request, response):
        """Resolve a destination query to grid coordinates."""
        if self._semantic is None:
            response.found = False
            return response

        pos = self._semantic.resolve(request.query)
        if pos is None:
            response.found = False
            self.get_logger().debug(f"Unresolved destination: '{request.query}'")
            return response

        response.position.row = int(pos[0])
        response.position.col = int(pos[1])
        response.found = True

        room_id = self._semantic.resolve_to_room_id(request.query)
        if room_id:
            response.room_id = room_id
            info = self._semantic.get_room_info(room_id)
            if info:
                response.label = info.get("label", room_id)

        self.get_logger().info(
            f"Resolved '{request.query}' → ({pos[0]}, {pos[1]}) [{response.room_id}]"
        )
        return response

    # ── Room summary ───────────────────────────────────────────────────────

    def _publish_rooms_summary(self) -> None:
        if self._semantic is None:
            return
        labels = self._semantic.get_all_room_labels()
        msg = String()
        msg.data = json.dumps({"room_count": len(labels), "labels": labels})
        self._pub_rooms.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SemanticMapNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()


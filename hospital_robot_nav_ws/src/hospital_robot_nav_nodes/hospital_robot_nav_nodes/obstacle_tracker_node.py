"""
HospitalRobotNav — Obstacle Tracker Node (ROS 2)
==================================================
Simulates dynamic obstacles (staff, patients, carts) and publishes them
as detection arrays.  In a real deployment, this node would consume
perception data (YOLO + depth camera); here it uses the ObstacleManager.

Topics:
    pub  /obstacles  (DetectionArray)
"""

from __future__ import annotations

import math
import random
import rclpy
from rclpy.node import Node

from visualization_msgs.msg import Marker, MarkerArray
from hospital_robot_nav_msgs.msg import Detection, DetectionArray

from hospital_robot_nav_core.maps.hospital.hospital_map import HospitalMap
from hospital_robot_nav_core.environment.occupancy_grid import OccupancyGrid


# Authentic corridor patrol routes (row, col waypoints) connecting all wings
PATROL_ROUTES = [
    # 1. Doctor (Emergency → Central ICU → Surgery Corridor)
    {
        "role": "Doctor",
        "color": (0.25, 0.65, 1.0),
        "speed": 1.2,
        "waypoints": [(25, 20), (40, 20), (40, 50), (61, 50), (40, 50), (19, 50), (19, 83), (40, 83), (40, 50), (25, 20)],
    },
    # 2. Senior Nurse (Patient Ward Wing → Nursing Station)
    {
        "role": "Nurse",
        "color": (0.20, 0.85, 0.70),
        "speed": 1.4,
        "waypoints": [(61, 14), (61, 50), (61, 83), (75, 83), (92, 83), (75, 83), (61, 83), (61, 50), (61, 14)],
    },
    # 3. Emergency Stretcher (Rapid transit through Central Spine V2)
    {
        "role": "Emergency Stretcher",
        "color": (0.95, 0.20, 0.20),
        "speed": 1.6,
        "waypoints": [(10, 50), (19, 50), (40, 50), (61, 50), (75, 50), (92, 50), (75, 50), (40, 50), (10, 50)],
    },
    # 4. Medicine Delivery Trolley (Pharmacy → Central Wards)
    {
        "role": "Medicine Cart",
        "color": (0.30, 0.80, 0.40),
        "speed": 1.0,
        "waypoints": [(79, 47), (75, 50), (61, 50), (61, 83), (40, 83), (61, 83), (61, 50), (75, 50), (79, 47)],
    },
    # 5. Patient in Wheelchair (OPD Consultation → Radiology / Lab)
    {
        "role": "Wheelchair",
        "color": (1.0, 0.55, 0.20),
        "speed": 0.8,
        "waypoints": [(40, 14), (40, 50), (19, 50), (19, 14), (19, 50), (40, 50), (40, 14)],
    },
    # 6. Cleaning Service Robot (Zone 1 & Zone 2 Corridors)
    {
        "role": "Cleaning Robot",
        "color": (0.80, 0.85, 0.25),
        "speed": 0.9,
        "waypoints": [(19, 14), (19, 50), (19, 83), (40, 83), (40, 50), (40, 14), (19, 14)],
    },
    # 7. Surgeon (OT Prep → Scrub Room → ICU)
    {
        "role": "Surgeon",
        "color": (0.15, 0.75, 0.45),
        "speed": 1.3,
        "waypoints": [(19, 83), (40, 83), (61, 83), (61, 50), (40, 50), (19, 50), (19, 83)],
    },
    # 8. Hospital Visitor (Main Reception → Cafeteria → Waiting Lounge)
    {
        "role": "Visitor",
        "color": (0.80, 0.65, 0.90),
        "speed": 1.0,
        "waypoints": [(92, 14), (92, 50), (75, 50), (61, 50), (75, 50), (92, 50), (92, 14)],
    },
]


class ObstacleTrackerNode(Node):
    """Publishes dynamic obstacle positions as detections and 3D RViz markers with continuous motion."""

    def __init__(self) -> None:
        super().__init__("obstacle_tracker_node")

        # ── Parameters ─────────────────────────────────────────────────────
        self.declare_parameter("publish_rate_hz", 15.0)
        self.declare_parameter("motion_speed_multiplier", 3.0)

        rate = self.get_parameter("publish_rate_hz").value
        self._motion_speed_multiplier = float(
            self.get_parameter("motion_speed_multiplier").value
        )

        # ── Initialize autonomous corridor NPCs ────────────────────────────
        self._agents = []
        for idx, route in enumerate(PATROL_ROUTES):
            start_wp = route["waypoints"][0]
            self._agents.append({
                "id": f"NPC-{idx+1:03d}",
                "role": route["role"],
                "color": route["color"],
                "speed": route["speed"],
                "waypoints": route["waypoints"],
                "wp_idx": 0,
                "pos": [float(start_wp[0]), float(start_wp[1])],
                "heading": 0.0,
            })

        self.get_logger().info(f"ObstacleTracker active: {len(self._agents)} continuous corridor staff/equipment NPCs loaded.")

        # ── Publishers + timer ─────────────────────────────────────────────
        self._pub = self.create_publisher(DetectionArray, "/obstacles", 10)
        self._pub_markers = self.create_publisher(MarkerArray, "/obstacles/markers", 10)
        self._last_time = self.get_clock().now()
        self._timer = self.create_timer(1.0 / max(rate, 1.0), self._publish)

    # ── Continuous Movement & Publish Loop ─────────────────────────────────

    def _publish(self) -> None:
        now_clock = self.get_clock().now()
        dt = (now_clock - self._last_time).nanoseconds / 1e9
        self._last_time = now_clock
        dt = min(max(dt, 0.005), 0.15)

        now_msg = now_clock.to_msg()
        msg = DetectionArray()
        msg.stamp = now_msg
        msg.provider = "obstacle_manager"

        marker_array = MarkerArray()

        for idx, agent in enumerate(self._agents):
            wps = agent["waypoints"]
            target_r, target_c = wps[agent["wp_idx"]]
            curr_r, curr_c = agent["pos"][0], agent["pos"][1]

            dr = float(target_r) - curr_r
            dc = float(target_c) - curr_c
            dist = math.hypot(dr, dc)

            if dist < 0.4:
                # Advance to next corridor waypoint (loops infinitely)
                agent["wp_idx"] = (agent["wp_idx"] + 1) % len(wps)
            else:
                # Move smoothly towards target waypoint
                target_hdg = math.atan2(dc, dr)
                diff = (target_hdg - agent["heading"] + math.pi) % (2 * math.pi) - math.pi
                agent["heading"] += diff * min(1.0, dt * 6.0)

                # Speeds are deliberately scaled for a clear professor-demo
                # movement signal in RViz's large hospital overview.
                step = min(dist, agent["speed"] * self._motion_speed_multiplier * dt)
                agent["pos"][0] += (dr / dist) * step
                agent["pos"][1] += (dc / dist) * step

            r, c = agent["pos"][0], agent["pos"][1]

            # 1. Add Detection
            d = Detection()
            d.label = agent["role"]
            d.confidence = 1.0
            d.bbox_x1 = int(c * 10)
            d.bbox_y1 = int(r * 10)
            d.bbox_x2 = int(c * 10 + 10)
            d.bbox_y2 = int(r * 10 + 10)
            d.center_x = int(c * 10 + 5)
            d.center_y = int(r * 10 + 5)
            msg.detections.append(d)

            # 2. 3D Body Marker
            m_body = Marker()
            m_body.header.stamp = now_msg
            m_body.header.frame_id = "map"
            m_body.ns = "dynamic_obstacles"
            m_body.id = idx * 2
            m_body.type = Marker.CYLINDER
            m_body.action = Marker.ADD
            m_body.pose.position.x = float(c) * 0.5
            m_body.pose.position.y = float(r) * 0.5
            m_body.pose.position.z = 0.55
            m_body.pose.orientation.w = 1.0
            m_body.scale.x = 0.48
            m_body.scale.y = 0.48
            m_body.scale.z = 1.1
            m_body.color.r = float(agent["color"][0])
            m_body.color.g = float(agent["color"][1])
            m_body.color.b = float(agent["color"][2])
            m_body.color.a = 0.95
            marker_array.markers.append(m_body)

            # 3. 3D Floating Role Label
            m_text = Marker()
            m_text.header.stamp = now_msg
            m_text.header.frame_id = "map"
            m_text.ns = "dynamic_obstacle_labels"
            m_text.id = idx * 2 + 1
            m_text.type = Marker.TEXT_VIEW_FACING
            m_text.action = Marker.ADD
            m_text.pose.position.x = float(c) * 0.5
            m_text.pose.position.y = float(r) * 0.5
            m_text.pose.position.z = 1.35
            m_text.pose.orientation.w = 1.0
            m_text.scale.z = 0.45  # Text height
            m_text.color.r = 1.0
            m_text.color.g = 1.0
            m_text.color.b = 1.0
            m_text.color.a = 0.95
            m_text.text = f"{agent['role']}"
            marker_array.markers.append(m_text)

        self._pub.publish(msg)
        self._pub_markers.publish(marker_array)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ObstacleTrackerNode()
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


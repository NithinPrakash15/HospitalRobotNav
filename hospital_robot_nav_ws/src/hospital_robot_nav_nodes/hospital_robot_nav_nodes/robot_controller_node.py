"""
HospitalRobotNav — Robot Controller Node (ROS 2)
===================================================
Publishes odometry and robot state, and accepts velocity commands.

In this simulator-based deployment, the controller integrates the Robot +
RobotPhysics to publish:
    /odom         (nav_msgs/Odometry)
    /robot/state  (std_msgs/String)
    /battery      (sensor_msgs/BatteryState)

It also subscribes to:
    /robot/cmd_vel  (geometry_msgs/Twist)  — sets target velocity
"""

from __future__ import annotations

import math

import rclpy
from rclpy.node import Node

from std_msgs.msg import String
from geometry_msgs.msg import Twist, TransformStamped
from nav_msgs.msg import Odometry, Path
from sensor_msgs.msg import BatteryState
from visualization_msgs.msg import Marker, MarkerArray
from tf2_ros import TransformBroadcaster

from hospital_robot_nav_core.robot.robot import Robot
from hospital_robot_nav_core.robot.robot_state import RobotState
from hospital_robot_nav_core.controllers.kinematics import RobotPhysics


class RobotControllerNode(Node):
    """Publishes robot odometry/state, TF transforms, and follows /plan trajectories."""

    def __init__(self) -> None:
        super().__init__("robot_controller_node")

        # ── Parameters ─────────────────────────────────────────────────────
        self.declare_parameter("publish_rate_hz", 50.0)
        self.declare_parameter("start_row", 80)
        self.declare_parameter("start_col", 11)

        rate = self.get_parameter("publish_rate_hz").value
        start = (
            self.get_parameter("start_row").value,
            self.get_parameter("start_col").value,
        )

        # ── Core robot + physics ───────────────────────────────────────────
        self._robot = Robot(start_pos=start)
        self._physics = RobotPhysics()

        # ── TF Broadcaster ─────────────────────────────────────────────────
        self._tf_broadcaster = TransformBroadcaster(self)

        # ── Subscribers / Publishers ───────────────────────────────────────
        self._sub_cmd_vel = self.create_subscription(
            Twist, "/robot/cmd_vel", self._on_cmd_vel, 10
        )
        self._sub_plan = self.create_subscription(
            Path, "/plan", self._on_plan_path, 10
        )
        self._pub_odom = self.create_publisher(Odometry, "/odom", 10)
        self._pub_state = self.create_publisher(String, "/robot/state", 10)
        self._pub_battery = self.create_publisher(BatteryState, "/battery", 10)
        self._pub_robot_marker = self.create_publisher(Marker, "/robot/marker", 10)
        self._pub_robot_markers = self.create_publisher(MarkerArray, "/robot/markers", 10)

        # ── Timer ──────────────────────────────────────────────────────────
        self._timer = self.create_timer(1.0 / max(rate, 1.0), self._publish_state_all)
        self._last_step = self.get_clock().now()

        self.get_logger().info("RobotControllerNode initialised with path-following.")

    # ── Path & Velocity Callbacks ──────────────────────────────────────────

    def _on_cmd_vel(self, msg: Twist) -> None:
        """Set the robot's target velocity from a Twist command."""
        self._robot.target_velocity = max(0.0, msg.linear.x)

    def _on_plan_path(self, msg: Path) -> None:
        """Receive a planned trajectory from RViz / planner and start navigating."""
        if not msg.poses:
            return
        waypoints = []
        for ps in msg.poses:
            r = int(round(ps.pose.position.y / 0.5))
            c = int(round(ps.pose.position.x / 0.5))
            waypoints.append((r, c))

        if waypoints:
            self._robot.set_path(waypoints)
            self._robot.target_velocity = 1.4  # Target speed in grid cells/s (~0.7 m/s)
            self._robot.transition(RobotState.MOVING)
            self.get_logger().info(f"Received new path with {len(waypoints)} waypoints. Robot moving!")

    # ── Periodic state publish & waypoint navigation ───────────────────────

    def _publish_state_all(self) -> None:
        now = self.get_clock().now()
        dt = (now - self._last_step).nanoseconds / 1e9
        self._last_step = now
        dt = min(max(dt, 1e-4), 0.1)

        # ── Follow waypoints if path is active ─────────────────────────────
        if self._robot.has_path():
            wp = self._robot.get_next_waypoint()
            if wp is not None:
                dr = wp[0] - self._robot.row
                dc = wp[1] - self._robot.col
                dist = math.hypot(dr, dc)

                if dist < 0.4:
                    self._robot.advance_waypoint()
                    if not self._robot.has_path():
                        # Goal reached
                        self._robot.target_velocity = 0.0
                        self._robot.velocity = 0.0
                        self._robot.transition(RobotState.IDLE)
                        self.get_logger().info("Robot reached destination successfully!")
                else:
                    # Steer heading towards waypoint
                    target_hdg = math.atan2(dc, dr)
                    diff = (target_hdg - self._robot.heading + math.pi) % (2 * math.pi) - math.pi
                    self._robot.heading += diff * min(1.0, dt * 5.0)
                    self._robot.target_velocity = 1.4

        # Advance the robot physics
        if self._robot.velocity > 0.0 or self._robot.target_velocity > 0.0:
            self._physics.step(self._robot, dt)

        # ── Odometry ───────────────────────────────────────────────────────
        odom = Odometry()
        odom.header.stamp = now.to_msg()
        odom.header.frame_id = "map"
        odom.child_frame_id = "base_footprint"

        # Grid (row, col) → ROS (x, y): col→x, row→y (inverted direction)
        odom.pose.pose.position.x = float(self._robot.col) * 0.5
        odom.pose.pose.position.y = float(self._robot.row) * 0.5
        odom.pose.pose.orientation.z = math.sin(self._robot.heading / 2.0)
        odom.pose.pose.orientation.w = math.cos(self._robot.heading / 2.0)

        odom.twist.twist.linear.x = float(self._robot.velocity) * 0.5
        odom.twist.twist.angular.z = float(self._robot.angular_vel)
        self._pub_odom.publish(odom)

        # ── TF Transform: map -> base_footprint ─────────────────────────────
        tf_msg = TransformStamped()
        tf_msg.header.stamp = now.to_msg()
        tf_msg.header.frame_id = "map"
        tf_msg.child_frame_id = "base_footprint"
        tf_msg.transform.translation.x = float(self._robot.col) * 0.5
        tf_msg.transform.translation.y = float(self._robot.row) * 0.5
        tf_msg.transform.translation.z = 0.0
        tf_msg.transform.rotation.z = math.sin(self._robot.heading / 2.0)
        tf_msg.transform.rotation.w = math.cos(self._robot.heading / 2.0)
        self._tf_broadcaster.sendTransform(tf_msg)

        # ── 3D Humanoid Robot Multi-Part Markers ───────────────────────────
        m_stamp = now.to_msg()
        m_array = MarkerArray()

        # 1. Base Mobile Chassis (Dark Navy Cylinder)
        m_base = Marker()
        m_base.header.stamp = m_stamp
        m_base.header.frame_id = "base_link"
        m_base.ns = "robot_parts"
        m_base.id = 0
        m_base.type = Marker.CYLINDER
        m_base.action = Marker.ADD
        m_base.pose.position.z = 0.15
        m_base.pose.orientation.w = 1.0
        m_base.scale.x = 0.55
        m_base.scale.y = 0.55
        m_base.scale.z = 0.3
        m_base.color.r = 0.08
        m_base.color.g = 0.12
        m_base.color.b = 0.22
        m_base.color.a = 0.98
        m_array.markers.append(m_base)

        # 2. Sleek Humanoid Torso (Medical White / Cyan)
        m_torso = Marker()
        m_torso.header.stamp = m_stamp
        m_torso.header.frame_id = "base_link"
        m_torso.ns = "robot_parts"
        m_torso.id = 1
        m_torso.type = Marker.CYLINDER
        m_torso.action = Marker.ADD
        m_torso.pose.position.z = 0.65
        m_torso.pose.orientation.w = 1.0
        m_torso.scale.x = 0.42
        m_torso.scale.y = 0.35
        m_torso.scale.z = 0.70
        m_torso.color.r = 0.95
        m_torso.color.g = 0.97
        m_torso.color.b = 1.0
        m_torso.color.a = 0.98
        m_array.markers.append(m_torso)

        # 3. Head & Digital Face Visor (Glossy Black with Cyan glow)
        m_head = Marker()
        m_head.header.stamp = m_stamp
        m_head.header.frame_id = "base_link"
        m_head.ns = "robot_parts"
        m_head.id = 2
        m_head.type = Marker.SPHERE
        m_head.action = Marker.ADD
        m_head.pose.position.z = 1.15
        m_head.pose.orientation.w = 1.0
        m_head.scale.x = 0.32
        m_head.scale.y = 0.32
        m_head.scale.z = 0.32
        m_head.color.r = 0.05
        m_head.color.g = 0.08
        m_head.color.b = 0.15
        m_head.color.a = 1.0
        m_array.markers.append(m_head)

        # 4. Medicine Delivery Tray
        m_tray = Marker()
        m_tray.header.stamp = m_stamp
        m_tray.header.frame_id = "base_link"
        m_tray.ns = "robot_parts"
        m_tray.id = 3
        m_tray.type = Marker.CUBE
        m_tray.action = Marker.ADD
        m_tray.pose.position.x = 0.25
        m_tray.pose.position.z = 0.60
        m_tray.pose.orientation.w = 1.0
        m_tray.scale.x = 0.25
        m_tray.scale.y = 0.38
        m_tray.scale.z = 0.04
        m_tray.color.r = 0.0
        m_tray.color.g = 0.75
        m_tray.color.b = 0.85
        m_tray.color.a = 0.95
        m_array.markers.append(m_tray)

        # 5. Direction Heading Arrow
        m_arrow = Marker()
        m_arrow.header.stamp = m_stamp
        m_arrow.header.frame_id = "base_link"
        m_arrow.ns = "robot_parts"
        m_arrow.id = 4
        m_arrow.type = Marker.ARROW
        m_arrow.action = Marker.ADD
        m_arrow.pose.position.z = 0.05
        m_arrow.pose.orientation.w = 1.0
        m_arrow.scale.x = 0.6
        m_arrow.scale.y = 0.08
        m_arrow.scale.z = 0.08
        m_arrow.color.r = 0.0
        m_arrow.color.g = 0.9
        m_arrow.color.b = 1.0
        m_arrow.color.a = 0.9
        m_array.markers.append(m_arrow)

        # 6. Floating Status Label Badge
        m_label = Marker()
        m_label.header.stamp = m_stamp
        m_label.header.frame_id = "base_link"
        m_label.ns = "robot_parts"
        m_label.id = 5
        m_label.type = Marker.TEXT_VIEW_FACING
        m_label.action = Marker.ADD
        m_label.pose.position.z = 1.45
        m_label.pose.orientation.w = 1.0
        m_label.scale.z = 0.35  # Text height
        m_label.color.r = 0.0
        m_label.color.g = 0.95
        m_label.color.b = 1.0
        m_label.color.a = 0.95
        m_label.text = f"Arogya [{self._robot.state.name}] {self._robot.battery.soc_percent:.0f}%"
        m_array.markers.append(m_label)

        self._pub_robot_markers.publish(m_array)
        self._pub_robot_marker.publish(m_torso)

        # ── Robot state (JSON-ish string) ──────────────────────────────────
        state_msg = String()
        stats = self._robot.get_stats()
        state_msg.data = (
            f"state={self._robot.state.name}, "
            f"pos=({self._robot.row:.1f},{self._robot.col:.1f}), "
            f"battery={stats['battery_pct']:.0f}%, "
            f"missions={stats['total_missions']}"
        )
        self._pub_state.publish(state_msg)

        # ── Battery state ──────────────────────────────────────────────────
        battery = BatteryState()
        battery.header.stamp = now.to_msg()
        battery.voltage = 48.0 * (self._robot.battery.soc_percent / 100.0)
        battery.percentage = self._robot.battery.soc_percent / 100.0
        battery.capacity = 15.0  # Ah
        self._pub_battery.publish(battery)

    # ── Public helper for other nodes ──────────────────────────────────────

    def set_target(self, velocity: float, heading: float) -> None:
        self._robot.target_velocity = max(0.0, velocity)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = RobotControllerNode()
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


"""
ROS 2 Bridge for Isaac Sim Multi-Agent Hospital Fleet
======================================================
Connects the Isaac Sim Embodied AI simulation with the ROS 2 architecture:
- Subscribes to: `/{robot_name}/cmd_vel` (geometry_msgs/Twist)
- Publishes to:  `/{robot_name}/odom` (nav_msgs/Odometry)
                 `/{robot_name}/battery` (sensor_msgs/BatteryState)
                 `/{robot_name}/status` (AgentStatus or std_msgs/String)
                 `/fleet/status` (Fleet heartbeat summary)
                 `/hospital/emergency_broadcast` (Code Blue emergency alert)

Maintains full backward compatibility with the existing ROS 2 workspace in
`hospital_robot_nav_ws/`. If `rclpy` is not present in the current Python
environment, seamlessly falls back to high-fidelity in-memory emulated ROS 2 bus
so simulation runs flawlessly without crashing.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger("IsaacSimROS2Bridge")

# Try importing real ROS 2 rclpy
HAS_RCLPY = False
try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Twist, Point, Quaternion
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import BatteryState
    from std_msgs.msg import String, Header
    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False


class IsaacSimROS2Bridge:
    """
    Bidirectional bridge between Isaac Sim AMR simulation and ROS 2 ecosystem.
    """

    def __init__(self, fleet_robots: Dict[str, Any], publish_rate_hz: float = 10.0) -> None:
        """
        Args:
            fleet_robots: Dictionary mapping robot_name -> HospitalAMR instance.
            publish_rate_hz: Heartbeat frequency for ROS 2 telemetry.
        """
        self.fleet_robots = fleet_robots
        self.publish_rate_hz = publish_rate_hz
        self.last_pub_time = 0.0
        self.pub_interval = 1.0 / publish_rate_hz

        self.has_rclpy = HAS_RCLPY
        self.node = None
        self.publishers: Dict[str, Any] = {}
        self.subscribers: Dict[str, Any] = {}

        # Emulated in-memory ROS 2 topic bus for environments without rclpy
        self.emulated_topic_bus: Dict[str, Any] = {}
        self.cmd_vel_overrides: Dict[str, Tuple[float, float]] = {}

        if self.has_rclpy:
            self._init_real_ros2()
        else:
            self._init_emulated_ros2()

    def _init_real_ros2(self) -> None:
        """Initialize native ROS 2 node, publishers, and subscribers."""
        try:
            if not rclpy.ok():
                rclpy.init()
            self.node = Node("isaac_sim_ros2_bridge")
            log.info("Native ROS 2 initialized: node 'isaac_sim_ros2_bridge' online.")

            for r_name in self.fleet_robots.keys():
                clean_name = r_name.lower().replace(" ", "_")
                # Publishers
                self.publishers[f"{clean_name}/odom"] = self.node.create_publisher(
                    Odometry, f"/{clean_name}/odom", 10
                )
                self.publishers[f"{clean_name}/battery"] = self.node.create_publisher(
                    BatteryState, f"/{clean_name}/battery", 10
                )
                self.publishers[f"{clean_name}/status"] = self.node.create_publisher(
                    String, f"/{clean_name}/status", 10
                )

                # Subscriber to /cmd_vel
                def make_cmd_vel_cb(name: str):
                    def cb(msg: Twist):
                        self.cmd_vel_overrides[name] = (msg.linear.x, msg.angular.z)
                    return cb

                self.subscribers[f"{clean_name}/cmd_vel"] = self.node.create_subscription(
                    Twist, f"/{clean_name}/cmd_vel", make_cmd_vel_cb(r_name), 10
                )

            # Global Fleet Status
            self.publishers["fleet/status"] = self.node.create_publisher(String, "/fleet/status", 10)
            self.publishers["hospital/emergency"] = self.node.create_publisher(
                String, "/hospital/emergency_broadcast", 10
            )
            print("[ROS2 BRIDGE] Connected to ROS 2. Nodes, Publishers, and cmd_vel subscribers active.")

        except Exception as e:
            log.warning("Failed to initialize native ROS 2 node (%s). Falling back to Emulated Bus.", e)
            self.has_rclpy = False
            self._init_emulated_ros2()

    def _init_emulated_ros2(self) -> None:
        """Initialize high-fidelity in-memory ROS 2 topic bus."""
        for r_name in self.fleet_robots.keys():
            clean_name = r_name.lower().replace(" ", "_")
            self.emulated_topic_bus[f"/{clean_name}/odom"] = None
            self.emulated_topic_bus[f"/{clean_name}/battery"] = 100.0
            self.emulated_topic_bus[f"/{clean_name}/status"] = "IDLE"
            self.emulated_topic_bus[f"/{clean_name}/cmd_vel"] = (0.0, 0.0)

        self.emulated_topic_bus["/fleet/status"] = {}
        self.emulated_topic_bus["/hospital/emergency_broadcast"] = "NORMAL"
        log.info("[ROS2 BRIDGE] Running high-fidelity emulated ROS 2 topic bus.")

    def step(self, current_sim_time: float) -> None:
        """
        Step ROS 2 communication: publish telemetry and read incoming control messages.
        """
        if current_sim_time - self.last_pub_time < self.pub_interval:
            return

        self.last_pub_time = current_sim_time
        fleet_summary: Dict[str, Any] = {}

        for r_name, robot in self.fleet_robots.items():
            clean_name = r_name.lower().replace(" ", "_")
            pos = robot.get_position()
            yaw = float(robot.yaw)
            battery = float(robot.battery_level)
            state_str = robot.state_machine.state.name

            # Telemetry record
            telemetry = {
                "name": r_name,
                "role": robot.role,
                "x": round(float(pos[0]), 3),
                "y": round(float(pos[1]), 3),
                "z": round(float(pos[2]), 3),
                "yaw_deg": round(float(np.degrees(yaw)), 1),
                "battery_pct": round(battery, 1),
                "state": state_str,
                "is_blocked": bool(getattr(robot, "is_blocked", False)),
                "current_task": getattr(robot, "current_task_description", "IDLE"),
            }
            fleet_summary[r_name] = telemetry

            if self.has_rclpy and self.node is not None:
                # Publish Odometry
                odom_msg = Odometry()
                odom_msg.header.stamp = self.node.get_clock().now().to_msg()
                odom_msg.header.frame_id = "odom"
                odom_msg.child_frame_id = f"{clean_name}/base_link"
                odom_msg.pose.pose.position.x = float(pos[0])
                odom_msg.pose.pose.position.y = float(pos[1])
                odom_msg.pose.pose.position.z = float(pos[2])
                # Convert yaw to planar quaternion (w, x, y, z)
                odom_msg.pose.pose.orientation.z = float(np.sin(yaw / 2.0))
                odom_msg.pose.pose.orientation.w = float(np.cos(yaw / 2.0))
                self.publishers[f"{clean_name}/odom"].publish(odom_msg)

                # Publish Battery
                bat_msg = BatteryState()
                bat_msg.header.stamp = odom_msg.header.stamp
                bat_msg.percentage = float(battery / 100.0)
                bat_msg.voltage = float(24.0 * (battery / 100.0))
                self.publishers[f"{clean_name}/battery"].publish(bat_msg)

                # Publish Status
                status_msg = String()
                status_msg.data = json.dumps(telemetry)
                self.publishers[f"{clean_name}/status"].publish(status_msg)

            else:
                # Update Emulated Topic Bus
                self.emulated_topic_bus[f"/{clean_name}/odom"] = telemetry
                self.emulated_topic_bus[f"/{clean_name}/battery"] = battery
                self.emulated_topic_bus[f"/{clean_name}/status"] = state_str

        # Publish global Fleet Status
        if self.has_rclpy and self.node is not None:
            fleet_msg = String()
            fleet_msg.data = json.dumps(fleet_summary)
            self.publishers["fleet/status"].publish(fleet_msg)
            # Spin non-blocking
            rclpy.spin_once(self.node, timeout_sec=0.0)
        else:
            self.emulated_topic_bus["/fleet/status"] = fleet_summary

    def send_cmd_vel(self, robot_name: str, linear_x: float, angular_z: float) -> None:
        """Directly inject a /cmd_vel velocity command for an AMR."""
        clean_name = robot_name.lower().replace(" ", "_")
        self.cmd_vel_overrides[robot_name] = (linear_x, angular_z)
        self.emulated_topic_bus[f"/{clean_name}/cmd_vel"] = (linear_x, angular_z)

    def broadcast_emergency(self, reason: str = "Code Blue Trauma") -> None:
        """Broadcast priority emergency preemption over ROS 2 topic."""
        msg_str = f"PRIORITY_1_EMERGENCY: {reason}"
        if self.has_rclpy and self.node is not None and "hospital/emergency" in self.publishers:
            m = String()
            m.data = msg_str
            self.publishers["hospital/emergency"].publish(m)
        self.emulated_topic_bus["/hospital/emergency_broadcast"] = msg_str
        print(f"[ROS2 BRIDGE] 🚨 Broadcasted on /hospital/emergency_broadcast: {msg_str}")

    def get_topic_data(self, topic_name: str) -> Any:
        """Query data from the ROS 2 topic bus."""
        return self.emulated_topic_bus.get(topic_name)

    def shutdown(self) -> None:
        """Cleanly destroy ROS 2 node and context."""
        if self.has_rclpy and self.node is not None:
            try:
                self.node.destroy_node()
                if rclpy.ok():
                    rclpy.shutdown()
            except Exception as e:
                log.warning("ROS 2 shutdown error: %s", e)
        log.info("[ROS2 BRIDGE] Bridge shutdown complete.")

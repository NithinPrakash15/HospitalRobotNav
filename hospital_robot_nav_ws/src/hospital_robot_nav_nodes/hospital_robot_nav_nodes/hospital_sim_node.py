"""
HospitalRobotNav — Hospital Sim Bridge Node (ROS 2)
=====================================================
Optional bridge that keeps the full legacy simulator behaviour available
under ROS 2 by exposing a headless simulation loop on top of the core
``Simulator`` engine.

It publishes a periodic snapshot of the whole simulation state so tools
(visualizers, dashboards) can monitor it over ROS 2.

Topics:
    pub  /sim/state     (std_msgs/String)   [JSON snapshot]
    pub  /sim/robot_pos (GridPos)
"""

from __future__ import annotations

import json

import rclpy
from rclpy.node import Node

from std_msgs.msg import String
from hospital_robot_nav_msgs.msg import GridPos


class HospitalSimNode(Node):
    """Headless bridge around the legacy Simulator engine."""

    def __init__(self) -> None:
        super().__init__("hospital_sim_node")

        # ── Parameters ─────────────────────────────────────────────────────
        self.declare_parameter("publish_rate_hz", 10.0)
        self.declare_parameter("auto_start", True)

        rate = self.get_parameter("publish_rate_hz").value
        auto_start = self.get_parameter("auto_start").value

        # ── Legacy simulator (headless) ────────────────────────────────────
        self._sim = None
        try:
            from hospital_robot_nav_core.simulation.simulator import Simulator
            self._sim = Simulator()
            self._sim.initialize()
            if auto_start:
                self._sim.clock.resume()
            self.get_logger().info("HospitalSimNode: legacy simulator loaded.")
        except Exception as exc:  # pragma: no cover - defensive
            self.get_logger().warning(
                f"Legacy simulator unavailable (pygame may be missing): {exc}"
            )

        # ── Publishers ─────────────────────────────────────────────────────
        self._pub_state = self.create_publisher(String, "/sim/state", 10)
        self._pub_pos = self.create_publisher(GridPos, "/sim/robot_pos", 10)

        # ── Timer ──────────────────────────────────────────────────────────
        self._timer = self.create_timer(1.0 / max(rate, 1.0), self._publish_snapshot)

    def _publish_snapshot(self) -> None:
        if self._sim is None:
            return

        # Advance the sim a few steps per tick
        for _ in range(2):
            self._sim.step()

        robot = self._sim.robot
        pos = GridPos()
        pos.row = int(robot.grid_pos[0])
        pos.col = int(robot.grid_pos[1])
        self._pub_pos.publish(pos)

        snapshot = {
            "robot_pos": list(robot.grid_pos),
            "robot_state": robot.state.name,
            "battery_pct": robot.battery.soc_percent,
            "missions_completed": robot.total_missions_completed,
            "path_cells": len(robot.path),
            "obstacle_count": self._sim.obstacle_manager.get_obstacle_count(),
            "agents": [
                {"id": a.agent_id, "type": a.agent_type, "state": a.state.name}
                for a in self._sim.agent_registry.get_all_agents()
            ],
        }
        msg = String()
        msg.data = json.dumps(snapshot)
        self._pub_state.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = HospitalSimNode()
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


"""
HospitalRobotNav — Planner Node (ROS 2)
=========================================
Exposes global path planning as a service.

Services:
    /planner/plan_path  (PlanPath)  — plans a path between two grid cells

The node loads the hospital map + occupancy grid, builds the PlannerFactory,
and answers path requests using the configured planner algorithm.
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Path, Odometry
from geometry_msgs.msg import PoseStamped, Point, Quaternion
from hospital_robot_nav_msgs.srv import PlanPath

from hospital_robot_nav_core.maps.hospital.hospital_map import HospitalMap
from hospital_robot_nav_core.environment.occupancy_grid import OccupancyGrid
from hospital_robot_nav_core.planning.planner_factory import (
    PlannerFactory,
    PlannerType,
)
from hospital_robot_nav_core.algorithms.heuristics import HeuristicType


class PlannerNode(Node):
    """Global path planning service and RViz path publisher."""

    def __init__(self) -> None:
        super().__init__("planner_node")

        # ── Parameters ─────────────────────────────────────────────────────
        self.declare_parameter("planner", "ASTAR")        # ASTAR | DIJKSTRA | THETA_STAR | HYBRID_ASTAR | DSTAR_LITE
        self.declare_parameter("heuristic", "DIAGONAL")

        planner_name = self.get_parameter("planner").value
        heuristic_name = self.get_parameter("heuristic").value

        # ── Build map + grid + factory ─────────────────────────────────────
        try:
            self._hospital_map = HospitalMap().build()
            self._grid = OccupancyGrid(self._hospital_map)

            self._planner_type = getattr(PlannerType, planner_name.upper(), PlannerType.ASTAR)
            self._heuristic_type = getattr(HeuristicType, heuristic_name.upper(), HeuristicType.DIAGONAL)

            self._factory = PlannerFactory(
                self._grid,
                default_planner=self._planner_type,
                default_heuristic=self._heuristic_type,
            )
            self.get_logger().info(
                f"PlannerNode active: {self._factory.active_planner_name} + {self._heuristic_type.name}"
            )
        except Exception as exc:  # pragma: no cover - defensive
            self.get_logger().error(f"Failed to initialise planner: {exc}")
            self._factory = None

        self._robot_pos = (80, 11)

        # ── Service / Publishers / Subscribers ─────────────────────────────
        self._srv = self.create_service(PlanPath, "/planner/plan_path", self._on_plan)
        self._pub_path = self.create_publisher(Path, "/plan", 10)
        self._sub_odom = self.create_subscription(Odometry, "/odom", self._on_odom, 10)
        self._sub_goal = self.create_subscription(PoseStamped, "/goal_pose", self._on_goal_pose, 10)

    # ── Service callback ───────────────────────────────────────────────────

    def _on_plan(self, request, response):
        """Plan a path from request.start to request.goal."""
        if self._factory is None:
            response.success = False
            response.status = "not_ready"
            return response

        start = (request.start.row, request.start.col)
        goal = (request.goal.row, request.goal.col)

        # Optional runtime planner/heuristic switch
        if request.planner_name:
            try:
                ptype = getattr(PlannerType, request.planner_name.upper())
                self._factory.set_planner(ptype)
            except Exception:
                pass
        if request.heuristic_name:
            try:
                htype = getattr(HeuristicType, request.heuristic_name.upper())
                self._factory.set_heuristic(htype)
            except Exception:
                pass

        result = self._factory.plan(start, goal)

        response.success = bool(result.success)
        response.planner_used = self._factory.active_planner_name
        response.status = result.status.name

        if result.success:
            response.path = [
                self._to_gridpos(r, c) for r, c in result.path
            ]
            response.planning_time_ms = float(result.metrics.planning_time_ms)
            response.nodes_expanded = int(result.metrics.nodes_expanded)
            response.nodes_generated = int(result.metrics.nodes_generated)
            self._publish_path(result.path)

        self.get_logger().info(
            f"Plan {start}→{goal}: {response.status} ({len(response.path)} cells, {response.planning_time_ms:.1f} ms)"
        )
        return response

    def _on_odom(self, msg: Odometry) -> None:
        """Update known robot position from /odom."""
        r = int(round(msg.pose.pose.position.y / 0.5))
        c = int(round(msg.pose.pose.position.x / 0.5))
        self._robot_pos = (r, c)

    def _on_goal_pose(self, msg: PoseStamped) -> None:
        """Plan a path when user clicks '2D Goal Pose' in RViz."""
        if self._factory is None:
            return
        goal_r = int(round(msg.pose.position.y / 0.5))
        goal_c = int(round(msg.pose.position.x / 0.5))
        start = self._robot_pos
        goal = (goal_r, goal_c)

        self.get_logger().info(f"RViz 2D Goal Pose received: {start} → {goal}")
        result = self._factory.plan(start, goal)
        if result.success:
            self._publish_path(result.path)
            self.get_logger().info(f"Published planned path to /plan ({len(result.path)} waypoints)")

    def _publish_path(self, path_cells: list) -> None:
        """Publish a nav_msgs/Path message to /plan."""
        now = self.get_clock().now().to_msg()
        p = Path()
        p.header.stamp = now
        p.header.frame_id = "map"

        for r, c in path_cells:
            pose = PoseStamped()
            pose.header.stamp = now
            pose.header.frame_id = "map"
            pose.pose.position.x = float(c) * 0.5
            pose.pose.position.y = float(r) * 0.5
            pose.pose.position.z = 0.1
            pose.pose.orientation.w = 1.0
            p.poses.append(pose)

        self._pub_path.publish(p)

    @staticmethod
    def _to_gridpos(row: int, col: int):
        from hospital_robot_nav_msgs.msg import GridPos
        g = GridPos()
        g.row = int(row)
        g.col = int(col)
        return g


def main(args=None) -> None:
    rclpy.init(args=args)
    node = PlannerNode()
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


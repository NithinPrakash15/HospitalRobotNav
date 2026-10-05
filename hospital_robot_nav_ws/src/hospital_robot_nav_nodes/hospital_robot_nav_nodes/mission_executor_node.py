"""
HospitalRobotNav — Mission Executor Node (ROS 2)
==================================================
Executes mission plans step-by-step.

Subscribes to validated ``MissionRequest`` messages, generates a
``MissionPlan`` (via the core MissionPlanner), and executes the steps.
Publishes progress on ``/mission/status`` and an action server for
long-running missions.

Topics:
    sub  /mission/request  (MissionRequest)
    pub  /mission/status   (MissionPlan)
    pub  /mission/progress (std_msgs/Float32)

Actions:
    /mission/execute  (ExecuteMission)
"""

from __future__ import annotations

import time

import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer

from std_msgs.msg import Float32
from hospital_robot_nav_msgs.msg import MissionPlan, MissionRequest
from hospital_robot_nav_msgs.action import ExecuteMission

from hospital_robot_nav_core.language.command_resolver import MissionType
from hospital_robot_nav_core.missions.mission_planner import MissionPlanner
from hospital_robot_nav_core.missions.mission_types import TaskType


class MissionExecutorNode(Node):
    """Runs mission plans from NLU requests."""

    def __init__(self) -> None:
        super().__init__("mission_executor_node")

        # ── Subscribers / Publishers ───────────────────────────────────────
        self._sub_request = self.create_subscription(
            MissionRequest, "/mission/request", self._on_request, 10
        )
        self._pub_status = self.create_publisher(
            MissionPlan, "/mission/status", 10
        )
        self._pub_progress = self.create_publisher(
            Float32, "/mission/progress", 10
        )

        # ── Action server ──────────────────────────────────────────────────
        self._action_server = ActionServer(
            self,
            ExecuteMission,
            "/mission/execute",
            execute_callback=self._execute_action,
        )

        # ── Core mission planner ───────────────────────────────────────────
        self._planner = MissionPlanner()

        # ── State ──────────────────────────────────────────────────────────
        self._current_plan: MissionPlan | None = None
        self._mission_id_counter = 0

        self.get_logger().info("MissionExecutorNode initialised.")

    # ── Request subscription ───────────────────────────────────────────────

    def _on_request(self, msg: MissionRequest) -> None:
        """Convert a request message into a mission plan and execute it."""
        if not msg.is_valid:
            self.get_logger().warning(
                f"Invalid mission request: {msg.validation_error}"
            )
            return

        plan = self._build_plan(msg)
        if plan is None:
            return

        self.get_logger().info(
            f"Mission plan ready: {plan.description} ({len(plan.steps)} steps)"
        )
        # Execute the plan synchronously in a timer-safe way
        self._current_plan = plan
        self._execute_plan(plan)

    # ── Plan builder ───────────────────────────────────────────────────────

    def _build_plan(self, msg: MissionRequest) -> MissionPlan | None:
        """Build a core MissionPlan from the request message."""
        try:
            mission_type = MissionType(msg.mission_type)
        except ValueError:
            mission_type = MissionType.NAVIGATE

        request = self._to_core_request(msg, mission_type)
        core_plan = self._planner.plan(request)

        # Convert to ROS 2 message
        plan = MissionPlan()
        plan.plan_id = core_plan.plan_id
        plan.mission_type = core_plan.mission_type
        plan.description = core_plan.description
        plan.priority = core_plan.priority
        plan.eta_total_sec = float(core_plan.eta_total_sec)
        plan.raw_command = core_plan.raw_command
        plan.progress = 0.0
        plan.created_at = self.get_clock().now().to_msg()

        from hospital_robot_nav_msgs.msg import TaskStep
        for step in core_plan.steps:
            ts = TaskStep()
            ts.task_type = step.task_type.value
            ts.step_id = f"{step.task_type.name}_{core_plan.plan_id}"
            ts.description = step.description
            ts.destination = step.destination or ""
            if step.destination_pos:
                ts.destination_pos.row = int(step.destination_pos[0])
                ts.destination_pos.col = int(step.destination_pos[1])
            ts.item = step.item or ""
            ts.duration_sec = float(step.duration_sec)
            ts.status = 0
            plan.steps.append(ts)

        self._current_plan = plan
        return plan

    def _to_core_request(self, msg: MissionRequest, mission_type):
        """Convert a ROS 2 request message into a core MissionRequest."""
        from hospital_robot_nav_core.language.command_resolver import MissionRequest as CoreReq

        req = CoreReq(
            mission_type=mission_type,
            pickup_location=msg.pickup_location,
            delivery_location=msg.delivery_location,
            item=msg.item,
            quantity=int(msg.quantity),
            priority=int(msg.priority),
            priority_label=msg.priority_label,
            patient_name=msg.patient_name,
            raw_text=msg.raw_text,
        )
        if msg.resolved_pickup.row or msg.resolved_pickup.col:
            req.resolved_pickup = (msg.resolved_pickup.row, msg.resolved_pickup.col)
        if msg.resolved_delivery.row or msg.resolved_delivery.col:
            req.resolved_delivery = (msg.resolved_delivery.row, msg.resolved_delivery.col)
        req.is_valid = msg.is_valid
        req.validation_error = msg.validation_error
        return req

    # ── Execution ──────────────────────────────────────────────────────────

    def _execute_plan(self, plan: MissionPlan) -> None:
        """Simulate executing each step with progress publishing."""
        total = len(plan.steps)
        for idx, step in enumerate(plan.steps):
            step.status = 1  # IN_PROGRESS
            self.get_logger().info(
                f"Step {idx + 1}/{total}: {step.description}"
            )
            plan.progress = (idx + 1) / max(total, 1)
            self._pub_status.publish(plan)
            self._pub_progress.publish(Float32(data=float(plan.progress)))
            # Simulate step duration (bounded for demo)
            time.sleep(min(step.duration_sec, 2.0))
            step.status = 2  # COMPLETED

        plan.progress = 1.0
        self._pub_status.publish(plan)
        self._pub_progress.publish(Float32(data=1.0))
        self.get_logger().info(f"Mission complete: {plan.description}")

    # ── Action server callback ─────────────────────────────────────────────

    async def _execute_action(self, goal_handle):
        """Execute a mission via the action server interface."""
        msg = goal_handle.request.mission_request

        # Build plan from request
        plan = self._build_plan(msg)
        if plan is None:
            goal_handle.abort()
            return ExecuteMission.Result(
                success=False, message="Invalid mission request."
            )

        feedback = ExecuteMission.Feedback()
        total = len(plan.steps)
        for idx, step in enumerate(plan.steps):
            feedback.progress = float((idx + 1) / max(total, 1))
            feedback.current_step = step.step_id
            feedback.current_step_description = step.description
            goal_handle.publish_feedback(feedback)
            self._pub_status.publish(plan)
            time.sleep(min(step.duration_sec, 2.0))

        goal_handle.succeed()
        return ExecuteMission.Result(
            success=True,
            mission_id=plan.plan_id,
            message="Mission completed.",
            total_duration_sec=float(plan.eta_total_sec),
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MissionExecutorNode()
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


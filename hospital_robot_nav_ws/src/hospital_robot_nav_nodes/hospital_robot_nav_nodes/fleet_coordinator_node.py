"""
HospitalRobotNav — Fleet Coordinator Node (ROS 2)
====================================================
Implements the Contract-Net task allocation across the agent fleet.

Subscribes to mission requests, broadcasts them to available agents,
collects bids, selects the winner, and assigns the mission.

Topics:
    sub  /mission/request  (MissionRequest)
    pub  /fleet/status     (AgentStatus[])
    pub  /fleet/assignment (std_msgs/String)   [JSON log]
"""

from __future__ import annotations

import json

import rclpy
from rclpy.node import Node

from std_msgs.msg import String
from hospital_robot_nav_msgs.msg import AgentStatus, MissionRequest

from hospital_robot_nav_core.agents.agent_registry import AgentRegistry
from hospital_robot_nav_core.agents.coordinator import AgentCoordinator
from hospital_robot_nav_core.agents.delivery_agent import DeliveryAgent
from hospital_robot_nav_core.agents.reception_agent import ReceptionAgent
from hospital_robot_nav_core.agents.emergency_agent import EmergencyAgent
from hospital_robot_nav_core.agents.navigation_agent import NavigationAgent
from hospital_robot_nav_core.agents.speech_agent import SpeechAgent
from hospital_robot_nav_core.agents.task_allocation_agent import TaskAllocationAgent
from hospital_robot_nav_core.agents.patient_interaction_agent import PatientInteractionAgent
from hospital_robot_nav_core.agents.medicine_management_agent import MedicineManagementAgent
from hospital_robot_nav_core.agents.mission_planning_agent import MissionPlanningAgent
from hospital_robot_nav_core.agents.agent_base import AgentState
from visualization_msgs.msg import Marker, MarkerArray


class FleetCoordinatorNode(Node):
    """Allocates missions to the agent fleet via Contract-Net bidding."""

    def __init__(self) -> None:
        super().__init__("fleet_coordinator_node")

        # ── Parameters ─────────────────────────────────────────────────────
        self.declare_parameter("num_delivery_agents", 1)
        self.declare_parameter("enable_reception", True)
        self.declare_parameter("enable_emergency", True)

        n_delivery = self.get_parameter("num_delivery_agents").value
        enable_reception = self.get_parameter("enable_reception").value
        enable_emergency = self.get_parameter("enable_emergency").value

        # ── Build fleet ────────────────────────────────────────────────────
        self._registry = AgentRegistry()
        for i in range(n_delivery):
            self._registry.register(DeliveryAgent(home_position=(80, 11)))
        if enable_reception:
            self._registry.register(ReceptionAgent())
        if enable_emergency:
            self._registry.register(EmergencyAgent())
        # These are decision-making agents, not additional physical robots.
        # They make the ROS2 fleet's specialist roles observable and publish
        # their live availability through the same heartbeat/status channel.
        self._registry.register(NavigationAgent(home_position=(80, 11)))
        self._registry.register(SpeechAgent(home_position=(2, 50)))
        self._registry.register(TaskAllocationAgent())
        self._registry.register(PatientInteractionAgent())
        self._registry.register(MedicineManagementAgent())
        self._registry.register(MissionPlanningAgent())

        self._coordinator = AgentCoordinator(self._registry)

        # ── Subscriber / Publishers ────────────────────────────────────────
        self._sub_request = self.create_subscription(
            MissionRequest, "/mission/request", self._on_request, 10
        )
        self._pub_fleet = self.create_publisher(
            AgentStatus, "/fleet/status", 10
        )
        self._pub_assignment = self.create_publisher(
            String, "/fleet/assignment", 10
        )
        self._pub_communication = self.create_publisher(
            String, "/agent/communication", 50
        )
        self._pub_markers = self.create_publisher(
            MarkerArray, "/fleet/markers", 10
        )

        # Publish fleet status at 2 Hz
        self._timer = self.create_timer(0.5, self._publish_fleet_status)

        self.get_logger().info(
            f"FleetCoordinatorNode initialised: {self._registry.fleet_size} agents."
        )

    def _publish_message(self, sender, receiver, message_type, priority, payload):
        """Publish a ROS-visible structured inter-agent communication event."""
        out = String()
        out.data = json.dumps({
            "sender": sender,
            "receiver": receiver,
            "message_type": message_type,
            "priority": int(priority),
            "timestamp_ns": self.get_clock().now().nanoseconds,
            "payload": payload,
        })
        self._pub_communication.publish(out)

    # ── Mission allocation ─────────────────────────────────────────────────

    def _on_request(self, msg: MissionRequest) -> None:
        """Broadcast the mission and assign to the winning agent."""
        mission_type = msg.mission_type_name or "NAVIGATE"
        destination = None
        if msg.resolved_delivery.row or msg.resolved_delivery.col:
            destination = (msg.resolved_delivery.row, msg.resolved_delivery.col)

        self.get_logger().info(
            f"Coordinator: broadcasting {mission_type} (pri={msg.priority}) to {self._registry.fleet_size} agents."
        )
        self._publish_message(
            "speech_agent", "coordinator_agent", "MISSION_REQUEST", msg.priority,
            {"mission_type": mission_type, "command": msg.raw_text},
        )
        self._publish_message(
            "coordinator_agent", "task_allocation_agent", "TASK_CREATED", msg.priority,
            {"mission_type": mission_type, "destination": msg.delivery_location},
        )

        winner, bid = self._coordinator.broadcast_mission(
            mission_type=mission_type,
            mission_id=f"ROS2-{self.get_clock().now().nanoseconds % 100000}",
            destination=destination,
            priority=int(msg.priority),
            mission_data={
                "item": msg.item,
                "destination_pos": destination,
                "destination_label": msg.delivery_location,
                "raw_text": msg.raw_text,
            },
        )

        if winner is not None:
            out = String()
            out.data = json.dumps({
                "mission": msg.raw_text,
                "winner": winner.agent_id,
                "bid_score": bid.score if bid else 0.0,
                "eta_s": bid.estimated_eta if bid else 0.0,
            })
            self._pub_assignment.publish(out)
            self._publish_message(
                "coordinator_agent", winner.agent_id, "TASK_ASSIGNED", msg.priority,
                {"mission_type": mission_type, "mission": msg.raw_text},
            )
            self.get_logger().info(
                f"Mission '{msg.raw_text}' → {winner.agent_id}"
            )

    # ── Fleet status ───────────────────────────────────────────────────────

    def _publish_fleet_status(self) -> None:
        markers = MarkerArray()
        for agent in self._registry.get_all_agents():
            status = AgentStatus()
            status.agent_id = agent.agent_id
            status.agent_type = agent.agent_type
            status.state = agent.state.value
            status.position.row = int(agent.position[0])
            status.position.col = int(agent.position[1])
            status.battery_pct = float(agent.battery_pct)
            status.current_mission_id = agent._current_mission_id or ""
            status.capabilities = list(agent.capabilities)
            status.timestamp = self.get_clock().now().to_msg()
            self._pub_fleet.publish(status)

            marker = Marker()
            marker.header.frame_id = "map"
            marker.header.stamp = status.timestamp
            marker.ns = "hospital_agents"
            marker.id = abs(hash(agent.agent_id)) % 2147483647
            marker.type = Marker.CYLINDER
            marker.action = Marker.ADD
            marker.pose.position.x = float(agent.position[1]) * 0.5
            marker.pose.position.y = float(agent.position[0]) * 0.5
            marker.pose.position.z = 0.75
            marker.pose.orientation.w = 1.0
            marker.scale.x = 0.7
            marker.scale.y = 0.7
            marker.scale.z = 1.5
            if agent.state == AgentState.EXECUTING:
                marker.color.r, marker.color.g, marker.color.b = 0.1, 0.9, 0.35
            else:
                marker.color.r, marker.color.g, marker.color.b = 0.15, 0.55, 1.0
            marker.color.a = 0.9
            markers.markers.append(marker)

            label = Marker()
            label.header.frame_id = "map"
            label.header.stamp = status.timestamp
            label.ns = "hospital_agent_labels"
            label.id = marker.id
            label.type = Marker.TEXT_VIEW_FACING
            label.action = Marker.ADD
            label.pose.position.x = marker.pose.position.x
            label.pose.position.y = marker.pose.position.y
            label.pose.position.z = 1.75
            label.pose.orientation.w = 1.0
            label.scale.z = 0.35
            label.color.r = label.color.g = label.color.b = label.color.a = 1.0
            label.text = f"{agent.agent_type}: {agent.state.name}"
            markers.markers.append(label)
        self._pub_markers.publish(markers)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = FleetCoordinatorNode()
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


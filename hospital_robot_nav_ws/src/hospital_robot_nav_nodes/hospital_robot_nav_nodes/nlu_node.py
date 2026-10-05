"""
HospitalRobotNav — NLU Node (ROS 2)
=====================================
Natural-language understanding node.  Subscribes to final speech transcripts
and publishes structured ``MissionRequest`` messages.

Pipeline:
    final transcript ──► IntentParser ──► EntityExtractor ──► CommandResolver
        ──► MissionRequest (validated)

Topics:
    sub  /speech/transcript  (RecognitionResult)
    pub  /mission/request    (MissionRequest)
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node

from hospital_robot_nav_msgs.msg import MissionRequest, RecognitionResult

from hospital_robot_nav_core.language.intent_parser import IntentParser, IntentType
from hospital_robot_nav_core.language.entity_extractor import EntityExtractor
from hospital_robot_nav_core.language.command_resolver import CommandResolver
from hospital_robot_nav_core.language.command_resolver import MissionType


class NLUNode(Node):
    """Converts speech transcript into a structured MissionRequest."""

    def __init__(self) -> None:
        super().__init__("nlu_node")

        # ── Subscribers / Publishers ───────────────────────────────────────
        self._sub_transcript = self.create_subscription(
            RecognitionResult, "/speech/transcript", self._on_transcript, 10
        )
        self._pub_request = self.create_publisher(
            MissionRequest, "/mission/request", 10
        )

        # ── Core NLU components ────────────────────────────────────────────
        self._intent_parser = IntentParser()
        self._entity_extractor = EntityExtractor()
        self._resolver = CommandResolver()

        self.get_logger().info("NLUNode initialised.")

    # ── Callback ───────────────────────────────────────────────────────────

    def _on_transcript(self, msg: RecognitionResult) -> None:
        """Parse a final transcript into a MissionRequest."""
        text = msg.text.strip()
        if not text or not msg.is_final:
            return

        intent = self._intent_parser.parse(text)
        entities = self._entity_extractor.extract(text)

        if not intent.is_valid:
            self.get_logger().debug(
                f"NLU: low-confidence intent {intent.intent.name} ({intent.confidence:.2f}) for '{text}'"
            )
            # Still publish an invalid request so the dialogue node can respond
            request_msg = self._build_msg(intent, entities, text, msg)
            self._pub_request.publish(request_msg)
            return

        request = self._resolver.resolve(intent, entities)
        request_msg = self._build_msg(intent, entities, text, msg, request)
        self._pub_request.publish(request_msg)
        self.get_logger().info(
            f"NLU: '{text}' → {request}"
        )

    # ── Build ROS message ──────────────────────────────────────────────────

    def _build_msg(self, intent, entities, text, transcript_msg, request=None):
        """Convert NLU output into a MissionRequest ROS message."""
        m = MissionRequest()

        # Mission type mapping
        mission_type = MissionType.NAVIGATE
        if request is not None:
            mission_type = request.mission_type
        m.mission_type = mission_type.value
        m.mission_type_name = mission_type.name

        m.item = (request.item if request is not None else
                  (entities.primary_medicine or ""))
        m.raw_text = text
        m.pickup_location = request.pickup_location if request is not None else ""
        m.delivery_location = request.delivery_location if request is not None else ""
        m.priority = request.priority if request is not None else entities.priority
        m.priority_label = (
            request.priority_label if request is not None else entities.priority_label
        )
        m.patient_name = request.patient_name if request is not None else ""
        m.intent_name = intent.intent.name
        m.intent_confidence = float(intent.confidence)
        m.locations = list(entities.locations)
        m.medicines = list(entities.medicines)
        m.room_number = str(entities.room_number) if entities.room_number else ""

        if request is not None:
            if request.resolved_pickup is not None:
                m.resolved_pickup.row, m.resolved_pickup.col = request.resolved_pickup
            if request.resolved_delivery is not None:
                m.resolved_delivery.row, m.resolved_delivery.col = request.resolved_delivery
            m.is_valid = bool(request.is_valid)
            m.validation_error = request.validation_error
        else:
            m.is_valid = bool(intent.is_valid)
            m.validation_error = "" if intent.is_valid else "low_confidence"

        m.stamp = transcript_msg.stamp if transcript_msg is not None else self.get_clock().now().to_msg()
        return m


def main(args=None) -> None:
    rclpy.init(args=args)
    node = NLUNode()
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


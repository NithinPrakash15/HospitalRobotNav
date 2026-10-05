"""
HospitalRobotNav — Dialogue Node (ROS 2)
==========================================
Multi-turn dialogue state machine.  Listens to final transcripts and
wake-word activations, runs the DialogueManager, and emits robot
responses on ``/robot/say``.

Topics:
    sub  /wake_word/active        (std_msgs/Bool)
    sub  /speech/transcript       (RecognitionResult)
    sub  /mission/status          (MissionPlan)          [for progress reporting]
    pub  /robot/say               (std_msgs/String)
    pub  /dialogue/state          (std_msgs/String)
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node

from std_msgs.msg import Bool, String
from hospital_robot_nav_msgs.msg import (
    MissionPlan,
    MissionRequest,
    RecognitionResult,
)

from hospital_robot_nav_core.language.dialogue_manager import DialogueManager


class DialogueNode(Node):
    """Drives the conversational state machine."""

    def __init__(self) -> None:
        super().__init__("dialogue_node")

        # ── Subscribers ────────────────────────────────────────────────────
        self._sub_wake = self.create_subscription(
            Bool, "/wake_word/active", self._on_wake, 10
        )
        self._sub_transcript = self.create_subscription(
            RecognitionResult, "/speech/transcript", self._on_transcript, 10
        )
        self._sub_mission_status = self.create_subscription(
            MissionPlan, "/mission/status", self._on_mission_status, 10
        )

        # ── Publishers ─────────────────────────────────────────────────────
        self._pub_say = self.create_publisher(String, "/robot/say", 10)
        self._pub_state = self.create_publisher(String, "/dialogue/state", 10)
        self._pub_mission_request = self.create_publisher(
            MissionRequest, "/mission/request", 10
        )

        # ── Core dialogue manager ──────────────────────────────────────────
        self._dialogue = DialogueManager()
        # Route robot speech to the /robot/say topic
        self._dialogue.on_robot_speak = self._publish_say

        # ── State tracking ──────────────────────────────────────────────────
        self._last_mission_text = ""

        self.get_logger().info("DialogueNode initialised.")

    # ── Callbacks ──────────────────────────────────────────────────────────

    def _on_wake(self, msg: Bool) -> None:
        """Start a dialogue session when the wake word is heard."""
        if not msg.data:
            return
        greeting = self._dialogue.on_wake_word()
        self._publish_say(greeting)
        self._publish_state(self._dialogue.get_state_display())

    def _on_transcript(self, msg: RecognitionResult) -> None:
        """Feed the final transcript into the dialogue manager."""
        if not msg.is_final or not msg.text.strip():
            return
        response = self._dialogue.on_user_input(msg.text)
        if response:
            self._publish_say(response)
        self._publish_state(self._dialogue.get_state_display())

    def _on_mission_status(self, msg: MissionPlan) -> None:
        """Report mission progress through dialogue."""
        if msg.progress >= 1.0 and self._last_mission_text != msg.description:
            self._last_mission_text = msg.description
            response = self._dialogue.on_mission_complete(msg.description)
            self._publish_say(response)
        self._publish_state(self._dialogue.get_state_display())

    # ── Helpers ────────────────────────────────────────────────────────────

    def _publish_say(self, text: str) -> None:
        if not text:
            return
        out = String()
        out.data = text
        self._pub_say.publish(out)
        self.get_logger().info(f"ROBOT SAYS: {text}")

    def _publish_state(self, state: str) -> None:
        out = String()
        out.data = state
        self._pub_state.publish(out)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DialogueNode()
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


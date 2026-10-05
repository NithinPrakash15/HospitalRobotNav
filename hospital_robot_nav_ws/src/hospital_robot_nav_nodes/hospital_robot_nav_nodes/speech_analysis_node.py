"""
HospitalRobotNav — Speech Analysis Node (ROS 2)
=================================================
Aggregates the full speech pipeline into a single structured
``SpeechAnalysis`` message on ``/robot/speech_analysis``.

It listens to:
    - final transcripts        (ASR output)
    - wake-word activations
    - NLU intent + entities    (from MissionRequest published by NLU node)
    - robot responses          (/robot/say)

and produces one message per user utterance containing the transcript,
STT confidence, NLU intent, extracted entities, dialogue state, and the
robot's response.  This topic is the ideal monitoring/debugging point for
the whole offline speech → NLU → dialogue → TTS chain.

Topics:
    sub  /speech/transcript      (RecognitionResult)
    sub  /wake_word/active       (std_msgs/Bool)
    sub  /mission/request        (MissionRequest)
    sub  /robot/say              (std_msgs/String)
    pub  /robot/speech_analysis  (SpeechAnalysis)
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node

from std_msgs.msg import Bool, String
from hospital_robot_nav_msgs.msg import (
    MissionRequest,
    RecognitionResult,
    SpeechAnalysis,
)


class SpeechAnalysisNode(Node):
    """Aggregates speech pipeline state into a structured topic."""

    def __init__(self) -> None:
        super().__init__("speech_analysis_node")

        # ── Subscribers ────────────────────────────────────────────────────
        self._sub_transcript = self.create_subscription(
            RecognitionResult, "/speech/transcript", self._on_transcript, 10
        )
        self._sub_wake = self.create_subscription(
            Bool, "/wake_word/active", self._on_wake, 10
        )
        self._sub_request = self.create_subscription(
            MissionRequest, "/mission/request", self._on_mission_request, 10
        )
        self._sub_say = self.create_subscription(
            String, "/robot/say", self._on_robot_say, 10
        )

        # ── Publisher ───────────────────────────────────────────────────────
        self._pub = self.create_publisher(
            SpeechAnalysis, "/robot/speech_analysis", 10
        )

        # ── Internal aggregation state ─────────────────────────────────────
        self._transcript = ""
        self._stt_confidence = -1.0
        self._engine = ""
        self._intent_name = ""
        self._intent_confidence = 0.0
        self._locations: list = []
        self._medicines: list = []
        self._room_number = ""
        self._priority_label = ""
        self._dialogue_state = "IDLE"
        self._robot_response = ""
        self._stamp = None

        self.get_logger().info("SpeechAnalysisNode initialised.")

    # ── Subscriber callbacks ───────────────────────────────────────────────

    def _on_transcript(self, msg: RecognitionResult) -> None:
        if not msg.is_final:
            return
        self._transcript = msg.text
        self._stt_confidence = float(msg.confidence)
        self._engine = msg.engine
        self._stamp = msg.stamp
        self._emit()

    def _on_wake(self, msg: Bool) -> None:
        if msg.data:
            self._dialogue_state = "WAKE_DETECTED"
            self._emit()

    def _on_mission_request(self, msg: MissionRequest) -> None:
        self._intent_name = msg.intent_name
        self._intent_confidence = float(msg.intent_confidence)
        self._locations = list(msg.locations)
        self._medicines = list(msg.medicines)
        self._room_number = msg.room_number
        self._priority_label = msg.priority_label
        self._dialogue_state = "NLU_RESOLVED"
        self._emit()

    def _on_robot_say(self, msg: String) -> None:
        self._robot_response = msg.data
        self._dialogue_state = "ROBOT_RESPONDED"
        self._emit()

    # ── Publish aggregate ──────────────────────────────────────────────────

    def _emit(self) -> None:
        """Publish the current aggregated speech analysis state."""
        out = SpeechAnalysis()
        out.transcript = self._transcript
        out.stt_confidence = self._stt_confidence
        out.intent_name = self._intent_name
        out.intent_confidence = self._intent_confidence
        out.entities_locations = self._locations
        out.entities_medicines = self._medicines
        out.entities_room_number = self._room_number
        out.priority_label = self._priority_label
        out.dialogue_state = self._dialogue_state
        out.robot_response = self._robot_response
        out.engine = self._engine
        out.stamp = self._stamp if self._stamp is not None else self.get_clock().now().to_msg()
        self._pub.publish(out)

    # ── Reset after an utterance completes ─────────────────────────────────

    def reset_utterance(self) -> None:
        """Reset aggregation state for the next user utterance."""
        self._transcript = ""
        self._stt_confidence = -1.0
        self._intent_name = ""
        self._intent_confidence = 0.0
        self._locations = []
        self._medicines = []
        self._room_number = ""
        self._priority_label = ""
        self._dialogue_state = "IDLE"
        self._robot_response = ""


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SpeechAnalysisNode()
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


"""
HospitalRobotNav — ASR Node (ROS 2)
=====================================
Speech-to-text node.  Subscribes to raw audio chunks and publishes
recognition results (final + partial).

Uses the offline Vosk engine when available (model path configurable).
Falls back to a simulated text-input engine — a ``std_msgs/String``
subscriber on ``/speech/text_input`` accepts typed commands for testing.

Topics:
    sub  /audio/raw                (hospital_robot_nav_msgs/msg/AudioChunk)
    sub  /speech/text_input        (std_msgs/String)      [fallback mode]
    pub  /speech/transcript        (RecognitionResult)    [final]
    pub  /speech/transcript_partial (RecognitionResult)   [partial]
"""

from __future__ import annotations

import json

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from std_msgs.msg import String
from hospital_robot_nav_msgs.msg import AudioChunk, RecognitionResult

from hospital_robot_nav_core.speech.speech_recognizer import SpeechRecognizer


class ASRNode(Node):
    """Offline speech-to-text node (Vosk or simulated fallback)."""

    def __init__(self) -> None:
        super().__init__("asr_node")

        # ── Parameters ─────────────────────────────────────────────────────
        self.declare_parameter("engine", "vosk")          # vosk | simulated
        self.declare_parameter("vosk_model_path", "")
        self.declare_parameter("emit_partial", True)

        engine = self.get_parameter("engine").value
        self._emit_partial = self.get_parameter("emit_partial").value

        # ── QoS ────────────────────────────────────────────────────────────
        audio_qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE)
        result_qos = QoSProfile(depth=10)

        # ── Subscribers ────────────────────────────────────────────────────
        self._sub_audio = self.create_subscription(
            AudioChunk, "/audio/raw", self._on_audio, audio_qos
        )
        self._sub_text = self.create_subscription(
            String, "/speech/text_input", self._on_text_input, 10
        )

        # ── Publishers ─────────────────────────────────────────────────────
        self._pub_final = self.create_publisher(
            RecognitionResult, "/speech/transcript", result_qos
        )
        self._pub_partial = self.create_publisher(
            RecognitionResult, "/speech/transcript_partial", result_qos
        )

        # ── Core recogniser ────────────────────────────────────────────────
        self._recognizer = SpeechRecognizer()

        # Override model path if provided
        if engine == "vosk":
            model_path = self.get_parameter("vosk_model_path").value
            if model_path:
                from hospital_robot_nav_core.speech.speech_config import SPEECH_CONFIG
                object.__setattr__(
                    SPEECH_CONFIG.recognizer, "VOSK_MODEL_PATH", model_path
                )

        if self._recognizer.initialize():
            self.get_logger().info(
                f"ASR active using engine: {self._recognizer.engine_name}"
            )
        else:
            self.get_logger().error("ASR failed to initialize.")

        self.get_logger().info("ASRNode initialised.")

    # ── Audio callback ─────────────────────────────────────────────────────

    def _on_audio(self, msg: AudioChunk) -> None:
        """Feed an audio chunk to the recogniser."""
        if not self._recognizer.is_ready:
            return

        result = self._recognizer.feed_chunk(msg.data)
        if result is None:
            return

        if result.is_final and not result.is_empty:
            self._publish_result(self._pub_final, result, msg)
        elif self._emit_partial and not result.is_empty:
            self._publish_result(self._pub_partial, result, msg)

    def _on_text_input(self, msg: String) -> None:
        """Accept typed text as a final recognition result."""
        text = msg.data.strip()
        if not text:
            return
        result = self._recognizer.recognize_text(text)
        self._publish_result(self._pub_final, result)

    # ── Publish helper ─────────────────────────────────────────────────────

    def _publish_result(self, publisher, result, audio_msg=None) -> None:
        """Convert a core RecognitionResult into a ROS 2 message."""
        out = RecognitionResult()
        out.text = result.text
        out.is_final = bool(result.is_final)
        out.confidence = float(result.confidence)
        out.engine = str(result.engine)
        out.duration_sec = float(result.duration_s)
        out.word_timings_json = json.dumps(result.word_timings)
        out.stamp = (
            audio_msg.stamp if audio_msg is not None
            else self.get_clock().now().to_msg()
        )
        publisher.publish(out)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ASRNode()
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


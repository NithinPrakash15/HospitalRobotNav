"""
HospitalRobotNav — TTS Node (ROS 2)
=====================================
Text-to-speech node.  Subscribes to ``/robot/say`` and speaks the text
using the offline pyttsx3 engine (or display-only mode).

Topics:
    sub  /robot/say   (std_msgs/String)
    pub  /tts/status  (std_msgs/Bool)
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node

from std_msgs.msg import Bool, String

from hospital_robot_nav_core.speech.tts_engine import TTSEngine
from hospital_robot_nav_core.speech.tts_engine import TTSPriority


class TTSNode(Node):
    """Speaks robot responses via the offline TTS engine."""

    def __init__(self) -> None:
        super().__init__("tts_node")

        # ── Parameters ─────────────────────────────────────────────────────
        self.declare_parameter("engine", "pyttsx3")   # pyttsx3 | disabled
        self.declare_parameter("rate", 160)
        self.declare_parameter("volume", 0.85)

        # ── Subscriber / Publisher ─────────────────────────────────────────
        self._sub_say = self.create_subscription(
            String, "/robot/say", self._on_say, 10
        )
        self._pub_status = self.create_publisher(Bool, "/tts/status", 10)

        # ── Core TTS engine ────────────────────────────────────────────────
        self._tts = TTSEngine()
        if self._tts.initialize():
            self._tts.start()
        self.get_logger().info(
            f"TTSNode initialised (available={self._tts.is_available})."
        )

    def _on_say(self, msg: String) -> None:
        """Speak the incoming text."""
        text = msg.data.strip()
        if not text:
            return
        self._tts.speak(text, priority=TTSPriority.NORMAL, category="ros2_topic")

        status = Bool()
        status.data = self._tts.is_speaking
        self._pub_status.publish(status)

    def destroy_node(self) -> bool:
        self._tts.stop()
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TTSNode()
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


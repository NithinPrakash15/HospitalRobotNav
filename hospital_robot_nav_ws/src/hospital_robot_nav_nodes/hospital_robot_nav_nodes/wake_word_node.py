"""
HospitalRobotNav — Wake Word Node (ROS 2)
===========================================
Detects the configured wake word in streaming partial transcripts and
activates the robot (publishes ``True`` on ``/wake_word/active``).

Topics:
    sub  /speech/transcript_partial (RecognitionResult)
    pub  /wake_word/active          (std_msgs/Bool)
    pub  /wake_word/command         (std_msgs/String)   [wake word stripped]
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from std_msgs.msg import Bool, String
from hospital_robot_nav_msgs.msg import RecognitionResult

from hospital_robot_nav_core.speech.wake_word_detector import WakeWordDetector
from hospital_robot_nav_core.speech.speech_config import SPEECH_CONFIG


class WakeWordNode(Node):
    """Activates the robot when the wake word is spoken."""

    def __init__(self) -> None:
        super().__init__("wake_word_node")

        # ── Parameters ─────────────────────────────────────────────────────
        self.declare_parameter("wake_words", list(SPEECH_CONFIG.wake_word.WAKE_WORDS))
        self.declare_parameter("cooldown_sec", SPEECH_CONFIG.wake_word.COOLDOWN_SEC)

        wake_words = self.get_parameter("wake_words").value
        cooldown = self.get_parameter("cooldown_sec").value

        # ── QoS: audio partials stream fast; use best-effort compatible ────
        partial_qos = QoSProfile(depth=20, reliability=ReliabilityPolicy.BEST_EFFORT)

        # ── Subscribers ────────────────────────────────────────────────────
        self._sub_partial = self.create_subscription(
            RecognitionResult, "/speech/transcript_partial",
            self._on_partial, partial_qos,
        )
        self._sub_final = self.create_subscription(
            RecognitionResult, "/speech/transcript",
            self._on_final, 10,
        )

        # ── Publishers ─────────────────────────────────────────────────────
        self._pub_active = self.create_publisher(Bool, "/wake_word/active", 10)
        self._pub_command = self.create_publisher(String, "/wake_word/command", 10)

        # ── Core detector ───────────────────────────────────────────────────
        self._detector = WakeWordDetector()
        # Override wake words from parameters (frozen dataclass workaround)
        if wake_words:
            object.__setattr__(SPEECH_CONFIG.wake_word, "WAKE_WORDS", tuple(wake_words))
            self._detector = WakeWordDetector()
        if cooldown:
            object.__setattr__(SPEECH_CONFIG.wake_word, "COOLDOWN_SEC", cooldown)
            self._detector = WakeWordDetector()

        self._active = False
        self.get_logger().info(
            f"WakeWordNode initialised — listening for: {SPEECH_CONFIG.wake_word.WAKE_WORDS}"
        )

    # ── Callbacks ──────────────────────────────────────────────────────────

    def _on_partial(self, msg: RecognitionResult) -> None:
        """Check streaming partial transcripts for the wake word."""
        match = self._detector.check_partial(msg.text)
        if match and not self._active:
            self._activate(match.phrase, match.source_text)

    def _on_final(self, msg: RecognitionResult) -> None:
        """Check final transcripts for the wake word and strip it for the command."""
        match = self._detector.check_text(msg.text)
        if not match:
            return

        command = self._detector.strip_wake_word(msg.text)
        self._activate(match.phrase, msg.text)
        if command and command != msg.text:
            cmd_msg = String()
            cmd_msg.data = command
            self._pub_command.publish(cmd_msg)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _activate(self, phrase: str, source: str) -> None:
        """Publish wake-word-active and log the activation."""
        self._active = True
        out = Bool()
        out.data = True
        self._pub_active.publish(out)
        self.get_logger().info(
            f"Wake word activated: '{phrase}' in '{source[:60]}'"
        )

        # Auto-reset after a short window (the NLU/dialogue handles the command)
        self.create_timer(1.0, self._reset_active, oneshot=True)

    def _reset_active(self) -> None:
        self._active = False
        out = Bool()
        out.data = False
        self._pub_active.publish(out)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = WakeWordNode()
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


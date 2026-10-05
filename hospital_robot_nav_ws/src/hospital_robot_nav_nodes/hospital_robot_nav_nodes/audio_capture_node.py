"""
HospitalRobotNav — Audio Capture Node (ROS 2)
===============================================
Publishes microphone audio chunks to ``/audio/raw``.

If no microphone is available (sounddevice missing), the node publishes
silent chunks so the downstream ASR node can still operate in text-input
mode.  The node also publishes an energy level on ``/audio/energy``.

Topics:
    pub  /audio/raw       (hospital_robot_nav_msgs/msg/AudioChunk)
    pub  /audio/energy    (std_msgs/Float32)
"""

from __future__ import annotations

import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from std_msgs.msg import Float32
from hospital_robot_nav_msgs.msg import AudioChunk

# Import core audio capture (graceful if sounddevice is missing)
from hospital_robot_nav_core.speech.audio_capture import AudioCapture
from hospital_robot_nav_core.speech.speech_config import SPEECH_CONFIG


class AudioCaptureNode(Node):
    """Publishes raw microphone chunks as AudioChunk messages."""

    def __init__(self) -> None:
        super().__init__("audio_capture_node")

        # ── Parameters ─────────────────────────────────────────────────────
        self.declare_parameter("sample_rate", SPEECH_CONFIG.audio.SAMPLE_RATE)
        self.declare_parameter("chunk_duration_ms", SPEECH_CONFIG.audio.CHUNK_DURATION_MS)
        self.declare_parameter("publish_rate_hz", 30.0)
        self.declare_parameter("use_microphone", True)

        sample_rate = self.get_parameter("sample_rate").value
        chunk_duration_ms = self.get_parameter("chunk_duration_ms").value
        self._publish_rate = self.get_parameter("publish_rate_hz").value
        self._use_microphone = self.get_parameter("use_microphone").value

        # ── QoS: reliable for audio so no chunks are dropped ──────────────
        audio_qos = QoSProfile(
            depth=50,
            reliability=ReliabilityPolicy.RELIABLE,
        )

        # ── Publishers ─────────────────────────────────────────────────────
        self._pub_audio = self.create_publisher(AudioChunk, "/audio/raw", audio_qos)
        self._pub_energy = self.create_publisher(Float32, "/audio/energy", 10)

        # ── Core audio capture ─────────────────────────────────────────────
        self._capture: AudioCapture | None = None
        self._seq = 0

        if self._use_microphone:
            self._capture = AudioCapture()
            if self._capture.start():
                self.get_logger().info(
                    f"Microphone capture active ({sample_rate} Hz, {chunk_duration_ms} ms chunks)."
                )
            else:
                self.get_logger().warning(
                    "No microphone available — publishing silent chunks "
                    "(text-input mode for ASR)."
                )
                self._capture = None
        else:
            self.get_logger().info("Microphone capture disabled by parameter.")

        # ── Timer to publish chunks at the configured rate ────────────────
        period = 1.0 / max(self._publish_rate, 1.0)
        self._timer = self.create_timer(period, self._publish_chunk)

        self.get_logger().info("AudioCaptureNode initialised.")

    def _publish_chunk(self) -> None:
        """Publish the next audio chunk (real mic or synthetic silence)."""
        msg = AudioChunk()
        msg.stamp = self.get_clock().now().to_msg()
        msg.sequence = self._seq
        self._seq += 1
        msg.sample_rate = SPEECH_CONFIG.audio.SAMPLE_RATE
        msg.channels = SPEECH_CONFIG.audio.CHANNELS
        msg.sample_width_bytes = 2  # int16

        if self._capture is not None:
            chunk = self._capture.read_chunk(timeout=0.05)
            if chunk is not None:
                msg.data = chunk.data
                msg.rms_energy = float(chunk.rms_energy)
                msg.is_speech = bool(chunk.is_speech)
            else:
                msg.data = b""
                msg.rms_energy = 0.0
                msg.is_speech = False
        else:
            # Synthetic silence (1024 int16 samples at 16 kHz)
            msg.data = bytes(SPEECH_CONFIG.audio.CHUNK_SIZE * 2)
            msg.rms_energy = 0.0
            msg.is_speech = False

        self._pub_audio.publish(msg)

        # Energy telemetry
        energy = Float32()
        energy.data = float(msg.rms_energy)
        self._pub_energy.publish(energy)

    def destroy_node(self) -> bool:
        if self._capture is not None:
            self._capture.stop()
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AudioCaptureNode()
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


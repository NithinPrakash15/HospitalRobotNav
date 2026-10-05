"""
HospitalRobotNav — Speech Module
==================================
Wake word detection, offline speech recognition, and text-to-speech
for the hospital assistant robot.

Submodules:
    speech_config:       Audio parameters, wake word list, model paths.
    audio_capture:       Thread-safe microphone stream with VAD.
    wake_word_detector:  Keyword-spotting FSM for activation.
    speech_recognizer:   Vosk offline speech-to-text engine.
    tts_engine:          Offline text-to-speech response system.

Architecture Note:
    The speech pipeline runs on a dedicated thread to avoid blocking the
    Pygame simulation loop.  Recognized text is delivered to the language
    module via the EventBus (HospitalEvent.SPEECH_RECOGNIZED).

ROS2 Deployment Note:
    In a ROS2 deployment each submodule becomes a lifecycle node:
        audio_capture_node       → publishes /audio_raw  (audio_msgs/Audio)
        wake_word_detector_node  → publishes /wake_word  (std_msgs/Bool)
        speech_recognizer_node   → publishes /transcript (std_msgs/String)
        tts_engine_node          → subscribes /robot_say  (std_msgs/String)
"""

def __getattr__(name: str):
    if name in ("SpeechConfig", "SPEECH_CONFIG"):
        from speech.speech_config import SpeechConfig, SPEECH_CONFIG
        return locals()[name]
    if name == "AudioCapture":
        from speech.audio_capture import AudioCapture
        return AudioCapture
    if name == "WakeWordDetector":
        from speech.wake_word_detector import WakeWordDetector
        return WakeWordDetector
    if name == "SpeechRecognizer":
        from speech.speech_recognizer import SpeechRecognizer
        return SpeechRecognizer
    if name == "TTSEngine":
        from speech.tts_engine import TTSEngine
        return TTSEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "SpeechConfig",
    "SPEECH_CONFIG",
    "AudioCapture",
    "WakeWordDetector",
    "SpeechRecognizer",
    "TTSEngine",
]


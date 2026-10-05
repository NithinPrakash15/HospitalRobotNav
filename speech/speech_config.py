"""
HospitalRobotNav — Speech Configuration
==========================================
All configurable parameters for the speech pipeline.

Centralises audio device settings, wake word definitions, response pools,
Vosk model paths, and TTS parameters.  No magic numbers escape this file.

Design:
    Frozen dataclasses ensure configuration is immutable after construction.
    The singleton ``SPEECH_CONFIG`` is the single source of truth used by
    every speech sub-module.

ROS2 Note:
    These values map to ROS2 parameter declarations in the respective
    speech node constructors (rclpy.parameter.Parameter).
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Audio Capture Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AudioConfig:
    """Microphone and audio stream parameters.

    Attributes:
        SAMPLE_RATE:       Recording sample rate in Hz (Vosk requires 16 kHz).
        CHANNELS:          Mono audio for speech recognition.
        CHUNK_DURATION_MS: Duration of each audio chunk in milliseconds.
        CHUNK_SIZE:        Number of samples per chunk (derived).
        DTYPE:             NumPy dtype string for audio samples.
        VAD_ENERGY_THRESHOLD: RMS energy threshold for voice activity.
        VAD_SILENCE_FRAMES:  Consecutive silent chunks to end utterance.
        RING_BUFFER_SEC:   Seconds of audio kept in the ring buffer.
    """
    SAMPLE_RATE: int = 16_000
    CHANNELS: int = 1
    CHUNK_DURATION_MS: int = 30
    DTYPE: str = "int16"
    VAD_ENERGY_THRESHOLD: float = 800.0
    VAD_SILENCE_FRAMES: int = 40          # ~1.2 s of silence at 30 ms chunks
    RING_BUFFER_SEC: float = 30.0
    MAX_UTTERANCE_SEC: float = 15.0       # Safety cap on utterance length

    @property
    def CHUNK_SIZE(self) -> int:
        """Number of samples per audio chunk."""
        return int(self.SAMPLE_RATE * self.CHUNK_DURATION_MS / 1000)

    @property
    def RING_BUFFER_CHUNKS(self) -> int:
        """Maximum chunks stored in the ring buffer."""
        return int(self.RING_BUFFER_SEC * 1000 / self.CHUNK_DURATION_MS)

    @property
    def MAX_UTTERANCE_CHUNKS(self) -> int:
        """Safety limit: max chunks per single utterance."""
        return int(self.MAX_UTTERANCE_SEC * 1000 / self.CHUNK_DURATION_MS)


# ─────────────────────────────────────────────────────────────────────────────
# Wake Word Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class WakeWordConfig:
    """Wake word detection parameters.

    Attributes:
        WAKE_WORDS:             Normalised wake phrases the robot responds to.
        FUZZY_THRESHOLD:        Max Levenshtein distance for fuzzy matching.
        COOLDOWN_SEC:           Minimum seconds between successive activations.
        PARTIAL_WINDOW_WORDS:   Number of trailing words checked in partials.
        GREETING_RESPONSES:     Pool of greeting responses (randomly selected).
    """
    WAKE_WORDS: Tuple[str, ...] = (
        "hey arogya",
        "hi arogya",
        "arogya",
        "hey aroga",
        "hi aroga",
        "hey arogya please",
        "hello arogya",
        "नमस्ते आरोग्य",
        "आरोग्य",
        "ഹായ് അരോഗ്യ",
        "അരോഗ്യ",
    )

    FUZZY_THRESHOLD: int = 2
    COOLDOWN_SEC: float = 3.0
    PARTIAL_WINDOW_WORDS: int = 4

    GREETING_RESPONSES: Tuple[str, ...] = (
        "Hello! I'm Arogya. How may I assist you?",
        "Arogya here. What can I do for you?",
        "Hi! I'm Arogya, your hospital assistant. How can I help?",
        "Yes? I'm Arogya — ready to help.",
        "Arogya listening. Please tell me what you need.",
        "Good day! I'm Arogya. What task shall I perform?",
        "At your service. I'm Arogya — what do you need?",
        "Hello! Arogya is ready for your instructions.",
    )

    def random_greeting(self) -> str:
        """Return a randomly selected greeting response."""
        return random.choice(self.GREETING_RESPONSES)


# ─────────────────────────────────────────────────────────────────────────────
# Speech Recogniser Configuration
# ─────────────────────────────────────────────────────────────────────────────

def _default_vosk_model_candidates() -> Tuple[str, ...]:
    """Return a priority-ordered list of candidate Vosk model locations."""
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    model_dir = os.path.join(project_root, "models")
    env_path = os.environ.get("VOSK_MODEL_PATH")
    env_dir = os.environ.get("VOSK_MODEL_DIR")
    candidates = []
    if env_path:
        candidates.append(env_path)
    if env_dir:
        candidates.append(os.path.join(env_dir, "vosk-model-small-en-us-0.15"))
        candidates.append(os.path.join(env_dir, "vosk-model-small-hi-in-0.4"))
        candidates.append(os.path.join(env_dir, "vosk-model-small-ml-in-0.2"))
    candidates.extend([
        os.path.join(model_dir, "vosk-model-small-en-us-0.15"),
        os.path.join(model_dir, "vosk-model-small-en-us-0.22"),
        os.path.join(model_dir, "vosk-model-small-hi-in-0.4"),
        os.path.join(model_dir, "vosk-model-small-ml-in-0.2"),
    ])
    return tuple(dict.fromkeys(os.path.abspath(p) for p in candidates if p))


@dataclass(frozen=True)
class RecognizerConfig:
    """Vosk / Whisper speech-to-text parameters.

    Attributes:
        ENGINE:             STT engine to use ("vosk" or "whisper").
        VOSK_MODEL_PATH:    Preferred filesystem path to the Vosk model directory.
        VOSK_MODEL_CANDIDATES: Additional common paths to try if the preferred path is absent.
        WHISPER_MODEL_SIZE: Whisper model size if using Whisper ("base", "small").
        MIN_CONFIDENCE:     Minimum confidence to accept a final result.
        PARTIAL_ENABLED:    Whether to emit partial (streaming) transcripts.
        COMMAND_TIMEOUT_SEC: Max seconds to wait for a command after wake word.
    """
    ENGINE: str = "vosk"

    # Vosk model — user must download and place here (or override via env var)
    VOSK_MODEL_PATH: str = field(default_factory=lambda: os.environ.get(
        "VOSK_MODEL_PATH",
        os.path.join(os.path.dirname(__file__), "..", "models", "vosk-model-small-en-us-0.15"),
    ))
    VOSK_MODEL_CANDIDATES: Tuple[str, ...] = field(default_factory=_default_vosk_model_candidates)

    WHISPER_MODEL_SIZE: str = "base"
    # Minimum confidence to accept a final result.  Raised from 0.40 to 0.50
    # so low-confidence phantom detections from background noise are rejected.
    MIN_CONFIDENCE: float = 0.50
    # Minimum transcript length (characters) for a final result to be treated
    # as a real command.  Shorter transcripts are almost always noise.
    MIN_TEXT_LENGTH: int = 3
    PARTIAL_ENABLED: bool = True
    COMMAND_TIMEOUT_SEC: float = 10.0


# ─────────────────────────────────────────────────────────────────────────────
# TTS Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TTSConfig:
    """Text-to-speech engine parameters.

    Attributes:
        ENGINE:    TTS backend ("pyttsx3" or "disabled").
        RATE:      Speech rate in words per minute.
        VOLUME:    Output volume (0.0 – 1.0).
        VOICE_ID:  Platform-specific voice identifier (None = default).
        ASYNC:     If True, TTS runs on a background thread.
    """
    ENGINE: str = "pyttsx3"
    RATE: int = 160
    VOLUME: float = 0.85
    VOICE_ID: str = ""       # Empty string = use platform default
    ASYNC: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# Speech Pipeline State Definitions
# ─────────────────────────────────────────────────────────────────────────────

class SpeechPipelineState:
    """Named constants for the speech pipeline state machine.

    Pipeline flow:
        IDLE ──wake word──► ACTIVATED ──speech──► PROCESSING ──NLU──► RESPONDING ──► IDLE
    """
    IDLE       = "IDLE"          # Listening for wake word only
    ACTIVATED  = "ACTIVATED"     # Wake word detected, listening for command
    PROCESSING = "PROCESSING"    # Command captured, running STT finalisation
    RESPONDING = "RESPONDING"    # Robot is speaking a response via TTS
    ERROR      = "ERROR"         # Recoverable error state
    DISABLED   = "DISABLED"      # Speech pipeline disabled (no mic / no model)


# ─────────────────────────────────────────────────────────────────────────────
# Aggregated Configuration Singleton
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SpeechConfig:
    """Top-level speech configuration aggregating all sub-configs.

    Usage:
        from speech.speech_config import SPEECH_CONFIG
        rate = SPEECH_CONFIG.audio.SAMPLE_RATE
        ww   = SPEECH_CONFIG.wake_word.WAKE_WORDS
    """
    audio: AudioConfig = field(default_factory=AudioConfig)
    wake_word: WakeWordConfig = field(default_factory=WakeWordConfig)
    recognizer: RecognizerConfig = field(default_factory=RecognizerConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)


# Global singleton — import this everywhere
SPEECH_CONFIG = SpeechConfig()

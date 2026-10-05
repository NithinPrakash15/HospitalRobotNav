"""
HospitalRobotNav — Speech Recogniser
=======================================
Offline speech-to-text engine using Vosk for real-time transcription.

Vosk is selected as the primary engine because it:
    - Runs entirely offline (no API key, no cloud dependency)
    - Supports streaming (partial + final results)
    - Has lightweight models (< 50 MB for English)
    - Runs on CPU with low latency

Pipeline:
    AudioCapture (PCM bytes) ──► SpeechRecogniser ──► RecognitionResult
                                                          │
                                    EventBus: SPEECH_RECOGNIZED ──► NLU

Supported Engines:
    1. Vosk (default, recommended)
    2. Whisper (optional, batch-mode only)
    3. Simulated (for testing without models)

ROS2 Deployment Note:
    Maps to a ``speech_recognizer_node`` subscribing to ``/audio_raw``
    and publishing ``/transcript`` (std_msgs/String) and
    ``/transcript_partial`` (std_msgs/String).

Reference:
    Vosk API: https://alphacephei.com/vosk/
    Whisper:  https://github.com/openai/whisper
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from speech.speech_config import SPEECH_CONFIG
from utilities.logger import get_logger

log = get_logger(__name__)

# ── Optional imports with graceful fallback ──────────────────────────────────

_VOSK_AVAILABLE = False
_WHISPER_AVAILABLE = False

try:
    from vosk import Model as VoskModel, KaldiRecognizer
    _VOSK_AVAILABLE = True
except ImportError:
    log.debug("Vosk not installed — Vosk STT engine unavailable.")

try:
    import whisper as whisper_module
    _WHISPER_AVAILABLE = True
except ImportError:
    log.debug("Whisper not installed — Whisper STT engine unavailable.")


# ─────────────────────────────────────────────────────────────────────────────
# Recognition Result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RecognitionResult:
    """Structured result from the speech recogniser.

    Attributes:
        text:        Recognised text (final or partial).
        is_final:    True for final results, False for partial (streaming).
        confidence:  Recognition confidence (0.0 – 1.0), -1 if unavailable.
        engine:      Which STT engine produced this result.
        duration_s:  Duration of the audio segment in seconds.
        timestamp:   Wall-clock time of the result.
        word_timings: Per-word timestamps if available.
    """
    text: str = ""
    is_final: bool = False
    confidence: float = -1.0
    engine: str = "unknown"
    duration_s: float = 0.0
    timestamp: float = field(default_factory=time.monotonic)
    word_timings: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True if the result contains no meaningful text."""
        return len(self.text.strip()) == 0

    def __repr__(self) -> str:
        tag = "FINAL" if self.is_final else "PARTIAL"
        conf = f"{self.confidence:.2f}" if self.confidence >= 0 else "N/A"
        return f"RecResult({tag}, conf={conf}, '{self.text[:50]}')"


# ─────────────────────────────────────────────────────────────────────────────
# Abstract STT Engine
# ─────────────────────────────────────────────────────────────────────────────

class STTEngine:
    """Abstract base for speech-to-text engines.

    Subclasses must implement:
        - ``initialize()``  → load model
        - ``feed_chunk()``  → process a PCM audio chunk (streaming)
        - ``finalize()``    → force final result for current utterance
        - ``reset()``       → clear internal state for next utterance
    """

    def initialize(self) -> bool:
        raise NotImplementedError

    def feed_chunk(self, pcm_bytes: bytes) -> Optional[RecognitionResult]:
        raise NotImplementedError

    def finalize(self) -> Optional[RecognitionResult]:
        raise NotImplementedError

    def reset(self) -> None:
        raise NotImplementedError

    @property
    def is_ready(self) -> bool:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Vosk Engine
# ─────────────────────────────────────────────────────────────────────────────

class VoskEngine(STTEngine):
    """Vosk offline streaming speech-to-text engine.

    Streams PCM chunks and returns partial/final recognition results
    with confidence scores and optional word timings.
    """

    def __init__(self) -> None:
        self._cfg = SPEECH_CONFIG.recognizer
        self._model: Optional[Any] = None    # VoskModel
        self._recognizer: Optional[Any] = None  # KaldiRecognizer
        self._ready = False

    def initialize(self) -> bool:
        """Load the Vosk model from disk.

        Returns:
            True if the model loaded successfully.
        """
        if not _VOSK_AVAILABLE:
            log.error("VoskEngine: Vosk package not installed.")
            return False

        candidate_paths = []
        preferred = self._cfg.VOSK_MODEL_PATH
        if preferred:
            candidate_paths.append(preferred)
        for candidate in self._cfg.VOSK_MODEL_CANDIDATES:
            if candidate and candidate not in candidate_paths:
                candidate_paths.append(candidate)

        model_path = None
        for path in candidate_paths:
            if os.path.isdir(path):
                model_path = path
                break

        if model_path is None:
            log.error(
                "VoskEngine: No model directory found in %s.\n"
                "  Download from https://alphacephei.com/vosk/models\n"
                "  Or set VOSK_MODEL_PATH/VOSK_MODEL_DIR to the speech model folder.",
                candidate_paths,
            )
            return False

        try:
            log.info("VoskEngine: Loading model from '%s'...", model_path)
            self._model = VoskModel(model_path)
            self._recognizer = KaldiRecognizer(self._model, SPEECH_CONFIG.audio.SAMPLE_RATE)
            self._recognizer.SetWords(True)  # Enable word-level timings
            self._ready = True
            log.info("VoskEngine: Model loaded successfully.")
            return True

        except Exception as exc:
            log.error("VoskEngine: Failed to load model — %s", exc)
            return False

    def feed_chunk(self, pcm_bytes: bytes) -> Optional[RecognitionResult]:
        """Feed a PCM audio chunk to Vosk.

        Args:
            pcm_bytes: Raw PCM int16 mono audio bytes.

        Returns:
            RecognitionResult (partial or final), or None if no output.
        """
        if not self._ready or self._recognizer is None:
            return None

        if self._recognizer.AcceptWaveform(pcm_bytes):
            # Final result for this segment
            result_json = self._recognizer.Result()
            return self._parse_result(result_json, is_final=True)
        else:
            # Partial result (streaming)
            if self._cfg.PARTIAL_ENABLED:
                partial_json = self._recognizer.PartialResult()
                return self._parse_partial(partial_json)

        return None

    def finalize(self) -> Optional[RecognitionResult]:
        """Force Vosk to emit its final result for the current audio.

        Call this after the last chunk of an utterance.

        Returns:
            Final RecognitionResult, or None.
        """
        if not self._ready or self._recognizer is None:
            return None

        result_json = self._recognizer.FinalResult()
        return self._parse_result(result_json, is_final=True)

    def reset(self) -> None:
        """Reset the recogniser state for a new utterance."""
        if self._ready and self._model is not None:
            self._recognizer = KaldiRecognizer(self._model, SPEECH_CONFIG.audio.SAMPLE_RATE)
            self._recognizer.SetWords(True)

    @property
    def is_ready(self) -> bool:
        return self._ready

    # ── Internal parsing ─────────────────────────────────────────────────────

    def _parse_result(self, json_str: str, is_final: bool) -> Optional[RecognitionResult]:
        """Parse a Vosk JSON result string into a RecognitionResult."""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return None

        text = data.get("text", "").strip()
        if not text:
            return None

        # Extract word-level timings and confidence
        word_timings: List[Dict[str, Any]] = []
        confidence_sum = 0.0
        confidence_count = 0

        for word_info in data.get("result", []):
            word_timings.append({
                "word": word_info.get("word", ""),
                "start": word_info.get("start", 0.0),
                "end": word_info.get("end", 0.0),
                "confidence": word_info.get("conf", 0.0),
            })
            confidence_sum += word_info.get("conf", 0.0)
            confidence_count += 1

        avg_confidence = (confidence_sum / confidence_count) if confidence_count > 0 else -1.0

        return RecognitionResult(
            text=text,
            is_final=is_final,
            confidence=avg_confidence,
            engine="vosk",
            word_timings=word_timings,
        )

    def _parse_partial(self, json_str: str) -> Optional[RecognitionResult]:
        """Parse a Vosk partial result JSON string."""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return None

        text = data.get("partial", "").strip()
        if not text:
            return None

        return RecognitionResult(
            text=text,
            is_final=False,
            confidence=-1.0,
            engine="vosk",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Simulated Engine (for testing / no-model environments)
# ─────────────────────────────────────────────────────────────────────────────

class SimulatedEngine(STTEngine):
    """Simulated STT engine that converts text input to RecognitionResults.

    Used when neither Vosk nor Whisper is available, or during unit testing.
    Accepts pre-set text via ``set_text()`` and returns it as a final result.
    """

    def __init__(self) -> None:
        self._ready = False
        self._pending_text: Optional[str] = None

    def initialize(self) -> bool:
        self._ready = True
        log.info("SimulatedEngine: Initialised (text-input mode).")
        return True

    def set_text(self, text: str) -> None:
        """Set text to be returned as the next recognition result."""
        self._pending_text = text.strip()

    def feed_chunk(self, pcm_bytes: bytes) -> Optional[RecognitionResult]:
        """Simulated engine ignores audio chunks."""
        return None

    def finalize(self) -> Optional[RecognitionResult]:
        """Return any pending text as a final result."""
        if self._pending_text:
            result = RecognitionResult(
                text=self._pending_text,
                is_final=True,
                confidence=1.0,
                engine="simulated",
            )
            self._pending_text = None
            return result
        return None

    def reset(self) -> None:
        self._pending_text = None

    @property
    def is_ready(self) -> bool:
        return self._ready


# ─────────────────────────────────────────────────────────────────────────────
# Speech Recogniser (Facade)
# ─────────────────────────────────────────────────────────────────────────────

class SpeechRecognizer:
    """High-level speech recognition facade.

    Automatically selects the best available STT engine:
        1. Vosk  (if installed and model exists)
        2. Simulated (text-input fallback)

    Usage::

        recognizer = SpeechRecognizer()
        recognizer.initialize()

        # Streaming mode (from AudioCapture chunks):
        for chunk in audio_chunks:
            result = recognizer.feed_chunk(chunk.data)
            if result and result.is_final:
                handle_command(result.text)

        # Or finalize after an utterance:
        final = recognizer.finalize()

        # Text-input mode:
        recognizer.recognize_text("go to pharmacy")

    Attributes:
        engine_name:       Name of the active STT engine.
        is_ready:          True if an engine is loaded and ready.
        total_recognitions: Count of final results produced.
    """

    def __init__(self) -> None:
        self._cfg = SPEECH_CONFIG.recognizer
        self._engine: Optional[STTEngine] = None
        self.engine_name: str = "none"
        self.is_ready: bool = False
        self.total_recognitions: int = 0

        # Result history (last N)
        self._history: List[RecognitionResult] = []
        self._history_max = 50

    def initialize(self) -> bool:
        """Initialize the best available STT engine.

        Tries engines in priority order: Vosk → Simulated.

        Returns:
            True if an engine was loaded successfully.
        """
        # ── Try Vosk ─────────────────────────────────────────────────────────
        if self._cfg.ENGINE == "vosk" and _VOSK_AVAILABLE:
            engine = VoskEngine()
            if engine.initialize():
                self._engine = engine
                self.engine_name = "vosk"
                self.is_ready = True
                log.info("SpeechRecognizer: Using Vosk engine.")
                return True
            else:
                log.warning("SpeechRecognizer: Vosk init failed — falling back.")

        # ── Fallback: Simulated ──────────────────────────────────────────────
        log.info("SpeechRecognizer: Using simulated engine (text-input mode).")
        engine = SimulatedEngine()
        engine.initialize()
        self._engine = engine
        self.engine_name = "simulated"
        self.is_ready = True
        return True

    def feed_chunk(self, pcm_bytes: bytes) -> Optional[RecognitionResult]:
        """Feed a PCM audio chunk to the active engine.

        Args:
            pcm_bytes: Raw PCM int16 mono audio bytes.

        Returns:
            RecognitionResult (partial or final), or None.
        """
        if not self.is_ready or self._engine is None:
            return None

        result = self._engine.feed_chunk(pcm_bytes)

        if result is not None and result.is_final and not result.is_empty:
            self._record_result(result)

        return result

    def finalize(self) -> Optional[RecognitionResult]:
        """Force the engine to emit a final result.

        Returns:
            Final RecognitionResult, or None.
        """
        if not self.is_ready or self._engine is None:
            return None

        result = self._engine.finalize()

        if result is not None and not result.is_empty:
            self._record_result(result)

        return result

    def recognize_text(self, text: str) -> RecognitionResult:
        """Directly create a RecognitionResult from typed text.

        Bypasses the audio pipeline entirely.  Used for text-input mode
        or testing.

        Args:
            text: User-typed command text.

        Returns:
            A final RecognitionResult with the given text.
        """
        result = RecognitionResult(
            text=text.strip(),
            is_final=True,
            confidence=1.0,
            engine="text_input",
        )
        self._record_result(result)
        return result

    def reset(self) -> None:
        """Reset the engine state for a new utterance."""
        if self._engine is not None:
            self._engine.reset()

    @property
    def last_result(self) -> Optional[RecognitionResult]:
        """The most recent final recognition result."""
        return self._history[-1] if self._history else None

    @property
    def history(self) -> List[RecognitionResult]:
        """Read-only view of result history."""
        return list(self._history)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _record_result(self, result: RecognitionResult) -> None:
        """Record a result in history and update counters."""
        if result.is_final:
            self.total_recognitions += 1
        self._history.append(result)
        if len(self._history) > self._history_max:
            self._history.pop(0)
        log.info("STT [%s]: %s", result.engine, result)

    # ── Diagnostic Methods (used by voice_diagnostic.py) ─────────────────────

    def get_diagnostic_info(self) -> dict:
        """Return diagnostic information about the recognizer state.

        Returns:
            Dict with 'engine', 'model_path', 'ready', 'total_recognitions'.
        """
        info = {
            "engine": self._engine_name,
            "ready": self.is_ready,
            "total_recognitions": self.total_recognitions,
            "model_path": None,
        }
        if hasattr(self._engine, "_cfg"):
            cfg = self._engine._cfg
            info["model_path"] = getattr(cfg, "VOSK_MODEL_PATH", None)
        return info


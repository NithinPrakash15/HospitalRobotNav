"""
HospitalRobotNav — Text-to-Speech Engine
==========================================
Offline text-to-speech system for natural robot vocal responses.

Design:
    The TTS engine runs speech synthesis on a dedicated background thread
    to prevent blocking the Pygame simulation loop.  Callers enqueue
    messages via ``speak()``, and the engine processes them FIFO.

    When TTS hardware/software is unavailable, the engine falls back to
    on-screen text display through the EventBus.

Supported Backends:
    1. **pyttsx3**  — Cross-platform, offline, uses SAPI5 (Windows),
       NSSpeechSynthesizer (macOS), or espeak (Linux).
    2. **disabled** — TTS disabled; messages are only logged and
       published to the EventBus for on-screen display.

ROS2 Deployment Note:
    Maps to a ``tts_engine_node`` subscribing to ``/robot_say``
    (std_msgs/String) and driving hardware speakers or a ROS2 audio
    action server.

Reference:
    pyttsx3 docs: https://pyttsx3.readthedocs.io/
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional

from speech.speech_config import SPEECH_CONFIG
from utilities.logger import get_logger

log = get_logger(__name__)

# Optional import
_PYTTSX3_AVAILABLE = False
try:
    import pyttsx3
    _PYTTSX3_AVAILABLE = True
except (ImportError, RuntimeError):
    log.debug("pyttsx3 not installed — TTS will use display-only mode.")


# ─────────────────────────────────────────────────────────────────────────────
# TTS Message Priority
# ─────────────────────────────────────────────────────────────────────────────

class TTSPriority(Enum):
    """Speech priority levels (lower value = higher priority)."""
    EMERGENCY = 0     # Spoken immediately, interrupts current speech
    HIGH      = 1     # Next in queue after current utterance
    NORMAL    = 2     # Standard FIFO ordering
    LOW       = 3     # Background announcements


# ─────────────────────────────────────────────────────────────────────────────
# TTS Message
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TTSMessage:
    """A queued text-to-speech message.

    Attributes:
        text:      The text to speak.
        priority:  Urgency level for queue ordering.
        timestamp: When the message was enqueued.
        category:  Optional category tag for logging (e.g., "greeting").
    """
    text: str
    priority: TTSPriority = TTSPriority.NORMAL
    timestamp: float = 0.0
    category: str = ""

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.monotonic()

    def __lt__(self, other: "TTSMessage") -> bool:
        """Priority queue comparison: lower priority value comes first."""
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        return self.timestamp < other.timestamp

    def __repr__(self) -> str:
        return f"TTSMsg({self.priority.name}, '{self.text[:40]}')"


# ─────────────────────────────────────────────────────────────────────────────
# TTS Engine
# ─────────────────────────────────────────────────────────────────────────────

class TTSEngine:
    """Asynchronous text-to-speech engine with priority queue.

    Usage::

        tts = TTSEngine()
        tts.initialize()
        tts.start()

        tts.speak("Hello! How may I assist you?")
        tts.speak("EMERGENCY in ICU!", priority=TTSPriority.EMERGENCY)

        tts.stop()

    Attributes:
        is_available:   True if a TTS backend is operational.
        is_speaking:    True if currently synthesising/playing speech.
        total_spoken:   Total number of messages spoken.
        current_text:   Text currently being spoken (or empty string).
    """

    def __init__(self) -> None:
        self._cfg = SPEECH_CONFIG.tts
        self._queue: queue.PriorityQueue[TTSMessage] = queue.PriorityQueue()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._engine: Optional[Any] = None

        # Public state
        self.is_available: bool = False
        self.is_speaking: bool = False
        self.total_spoken: int = 0
        self.current_text: str = ""

        # Callback for on-screen display (set by dashboard)
        self._display_callback: Optional[callable] = None

        # Speech history
        self._history: List[TTSMessage] = []
        self._history_max = 30

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def initialize(self) -> bool:
        """Initialize the TTS backend.

        Returns:
            True if a TTS engine was loaded successfully.
        """
        if self._cfg.ENGINE == "disabled":
            log.info("TTSEngine: Disabled by configuration.")
            self.is_available = False
            return False

        if _PYTTSX3_AVAILABLE and self._cfg.ENGINE == "pyttsx3":
            try:
                self._engine = pyttsx3.init()
                self._engine.setProperty("rate", self._cfg.RATE)
                self._engine.setProperty("volume", self._cfg.VOLUME)

                # Set voice if specified
                if self._cfg.VOICE_ID:
                    self._engine.setProperty("voice", self._cfg.VOICE_ID)

                self.is_available = True
                log.info(
                    "TTSEngine: pyttsx3 initialised (rate=%d, vol=%.2f).",
                    self._cfg.RATE, self._cfg.VOLUME,
                )
                return True

            except Exception as exc:
                log.error("TTSEngine: pyttsx3 init failed — %s", exc)
                self._engine = None

        log.info("TTSEngine: Running in display-only mode (no audio output).")
        self.is_available = False
        return False

    def start(self) -> None:
        """Start the background TTS processing thread."""
        if self._cfg.ASYNC and not self._stop_event.is_set():
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._process_loop,
                name="TTS-Thread",
                daemon=True,
            )
            self._thread.start()
            log.info("TTSEngine: Background thread started.")

    def stop(self) -> None:
        """Stop the TTS thread and release resources."""
        self._stop_event.set()

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3.0)

        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                pass

        log.info(
            "TTSEngine: Stopped. Total messages spoken: %d.",
            self.total_spoken,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def speak(
        self,
        text: str,
        priority: TTSPriority = TTSPriority.NORMAL,
        category: str = "",
    ) -> None:
        """Enqueue a message for speech synthesis.

        In async mode, the message is placed in the priority queue.
        In sync mode, the message is spoken immediately (blocking).

        Args:
            text:     Text to speak.
            priority: Urgency level.
            category: Optional category tag for logging.
        """
        if not text or not text.strip():
            return

        message = TTSMessage(
            text=text.strip(),
            priority=priority,
            category=category,
        )

        # Record history regardless of TTS availability
        self._history.append(message)
        if len(self._history) > self._history_max:
            self._history.pop(0)

        # Notify display callback
        if self._display_callback is not None:
            try:
                self._display_callback(message)
            except Exception as exc:
                log.debug("TTSEngine: Display callback error — %s", exc)

        if self._cfg.ASYNC:
            self._queue.put(message)
            log.debug("TTSEngine: Enqueued %s", message)
        else:
            self._speak_sync(message)

    def speak_greeting(self, greeting: str) -> None:
        """Speak a wake-word greeting response.

        Args:
            greeting: The greeting text to speak.
        """
        self.speak(greeting, priority=TTSPriority.HIGH, category="greeting")

    def speak_confirmation(self, summary: str) -> None:
        """Speak a mission confirmation message.

        Args:
            summary: Task summary to confirm with the user.
        """
        self.speak(
            f"I understood your request. {summary}. Would you like me to begin?",
            priority=TTSPriority.NORMAL,
            category="confirmation",
        )

    def speak_progress(self, destination: str, eta_seconds: float) -> None:
        """Speak a navigation progress update.

        Args:
            destination: Where the robot is heading.
            eta_seconds: Estimated time of arrival in seconds.
        """
        eta_str = f"{eta_seconds:.0f} seconds" if eta_seconds > 0 else "shortly"
        self.speak(
            f"I'm on my way to {destination}. Estimated arrival in {eta_str}.",
            priority=TTSPriority.LOW,
            category="progress",
        )

    def speak_completion(self, task_desc: str) -> None:
        """Speak a mission completion announcement.

        Args:
            task_desc: Description of the completed task.
        """
        self.speak(
            f"Mission complete. {task_desc}.",
            priority=TTSPriority.NORMAL,
            category="completion",
        )

    def speak_error(self, error_desc: str) -> None:
        """Speak an error or failure message.

        Args:
            error_desc: Description of the error.
        """
        self.speak(
            f"I'm sorry. {error_desc}.",
            priority=TTSPriority.HIGH,
            category="error",
        )

    def speak_emergency(self, alert: str) -> None:
        """Speak an emergency alert (highest priority).

        Args:
            alert: Emergency alert text.
        """
        self.speak(alert, priority=TTSPriority.EMERGENCY, category="emergency")

    def cancel_all(self) -> None:
        """Cancel all queued (but not currently playing) messages."""
        cancelled = 0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                cancelled += 1
            except queue.Empty:
                break
        if cancelled > 0:
            log.info("TTSEngine: Cancelled %d queued messages.", cancelled)

    def set_display_callback(self, callback: callable) -> None:
        """Set a callback for on-screen text display.

        The callback receives a TTSMessage whenever the robot speaks.
        Used by the dashboard to show robot dialogue.

        Args:
            callback: Function accepting a TTSMessage.
        """
        self._display_callback = callback

    @property
    def queue_size(self) -> int:
        """Number of messages waiting in the queue."""
        return self._queue.qsize()

    @property
    def history(self) -> List[TTSMessage]:
        """Read-only list of recently spoken messages."""
        return list(self._history)

    @property
    def last_spoken(self) -> Optional[TTSMessage]:
        """The most recently spoken message."""
        return self._history[-1] if self._history else None

    # ─────────────────────────────────────────────────────────────────────────
    # Internal Processing
    # ─────────────────────────────────────────────────────────────────────────

    def _process_loop(self) -> None:
        """Background thread: process TTS queue FIFO with priority."""
        while not self._stop_event.is_set():
            try:
                message = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            self._speak_sync(message)

    def _speak_sync(self, message: TTSMessage) -> None:
        """Synchronously speak a message using the TTS engine.

        Args:
            message: The TTSMessage to speak.
        """
        self.is_speaking = True
        self.current_text = message.text

        log.info("TTS [%s]: '%s'", message.category or "speech", message.text)

        if self.is_available and self._engine is not None:
            try:
                self._engine.say(message.text)
                self._engine.runAndWait()
            except Exception as exc:
                log.error("TTSEngine: Speech synthesis error — %s", exc)
        else:
            # Display-only mode: simulate speech duration
            # ~160 words per minute → ~2.7 words/second
            word_count = len(message.text.split())
            simulated_duration = min(word_count / 2.7, 5.0)
            time.sleep(simulated_duration)

        self.total_spoken += 1
        self.is_speaking = False
        self.current_text = ""


# Type alias for the optional Any import above
from typing import Any

"""
HospitalRobotNav — Wake Word Detector
========================================
Keyword-spotting finite state machine that activates the robot when the
user speaks a designated wake phrase.

Detection Strategy:
    1. **Vosk Partial Results** (primary):
       Vosk streams partial recognition hypotheses in real time.  The
       detector slides a window of the last N words over each partial
       result and checks for a wake word match.

    2. **Fuzzy Matching** (secondary):
       If an exact wake word is not found, the detector computes the
       Levenshtein edit distance between each candidate window and every
       registered wake phrase.  Matches within ``FUZZY_THRESHOLD`` edits
       are accepted.

    3. **Text Input Fallback**:
       When running without a microphone, the detector accepts typed text
       via ``check_text()``.

State Machine:
    LISTENING ──(wake word)──► WAKE_DETECTED ──(auto)──► COMMAND_CAPTURE

Cooldown:
    After a successful activation the detector enters a cooldown period
    to prevent rapid re-triggering from echo or repeated speech.

ROS2 Deployment Note:
    Maps to a ``wake_word_detector_node`` subscribing to ``/transcript``
    and publishing ``/wake_word`` (std_msgs/Bool).
"""

from __future__ import annotations

import re
import time
from enum import Enum, auto
from typing import List, Optional, Tuple

from speech.speech_config import SPEECH_CONFIG
from utilities.logger import get_logger

log = get_logger(__name__)

# Optional fuzzy matching — graceful fallback to exact-only matching
try:
    from Levenshtein import distance as levenshtein_distance
    _FUZZY_AVAILABLE = True
except ImportError:
    _FUZZY_AVAILABLE = False
    log.debug("Levenshtein package not installed — wake word detection uses exact matching only.")


# ─────────────────────────────────────────────────────────────────────────────
# Detector State Machine
# ─────────────────────────────────────────────────────────────────────────────

class DetectorState(Enum):
    """Wake word detector operational states."""
    LISTENING       = auto()   # Passively listening for a wake word
    WAKE_DETECTED   = auto()   # Wake word just detected — transition state
    COMMAND_CAPTURE = auto()   # Actively capturing a user command
    COOLDOWN        = auto()   # Ignoring input after recent activation
    DISABLED        = auto()   # Detector shut down


# ─────────────────────────────────────────────────────────────────────────────
# Wake Word Match Result
# ─────────────────────────────────────────────────────────────────────────────

class WakeWordMatch:
    """Details of a successful wake word match.

    Attributes:
        phrase:      The matched wake phrase (normalised).
        source_text: The raw text that triggered the match.
        edit_dist:   Levenshtein distance (0 = exact match).
        timestamp:   Wall-clock time of the match.
    """

    __slots__ = ("phrase", "source_text", "edit_dist", "timestamp")

    def __init__(
        self,
        phrase: str,
        source_text: str,
        edit_dist: int = 0,
        timestamp: Optional[float] = None,
    ) -> None:
        self.phrase = phrase
        self.source_text = source_text
        self.edit_dist = edit_dist
        self.timestamp = timestamp or time.monotonic()

    def __repr__(self) -> str:
        return (
            f"WakeWordMatch('{self.phrase}', edit_dist={self.edit_dist}, "
            f"src='{self.source_text[:40]}')"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Wake Word Detector
# ─────────────────────────────────────────────────────────────────────────────

class WakeWordDetector:
    """Keyword-spotting engine for robot activation.

    Usage::

        detector = WakeWordDetector()

        # From Vosk partial text (streaming):
        match = detector.check_partial("hey robot how are you")
        if match:
            greeting = detector.get_greeting()
            command_text = "how are you"  # text after wake word stripped

        # From typed text (fallback):
        match = detector.check_text("Hey Arogya, go to pharmacy")
        if match:
            command_text = detector.strip_wake_word("Hey Arogya, go to pharmacy")

    Attributes:
        state:         Current detector state.
        last_match:    Most recent WakeWordMatch (or None).
        activations:   Total number of successful activations.
    """

    def __init__(self) -> None:
        self._cfg = SPEECH_CONFIG.wake_word

        # Pre-compute normalised wake words for fast lookup
        self._wake_words_normalised: List[str] = [
            ww.strip().lower() for ww in self._cfg.WAKE_WORDS
        ]
        self._wake_word_lengths: List[int] = [
            len(ww.split()) for ww in self._wake_words_normalised
        ]

        # State
        self.state: DetectorState = DetectorState.LISTENING
        self.last_match: Optional[WakeWordMatch] = None
        self.activations: int = 0

        # Cooldown tracking
        self._last_activation_time: float = 0.0

        log.info(
            "WakeWordDetector initialised with %d wake phrases: %s",
            len(self._wake_words_normalised),
            self._wake_words_normalised,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def check_partial(self, partial_text: str) -> Optional[WakeWordMatch]:
        """Check a Vosk partial recognition result for a wake word.

        This is called frequently (every ~30 ms) with the latest partial
        hypothesis.  Performance is critical — we limit the search window.

        Args:
            partial_text: Current partial recognition string from Vosk.

        Returns:
            WakeWordMatch if a wake word is found, else None.
        """
        if self.state in (DetectorState.COOLDOWN, DetectorState.DISABLED):
            return None

        if self._in_cooldown() and not self._contains_wake_phrase(partial_text):
            return None

        return self._search(partial_text, limit=self._cfg.PARTIAL_WINDOW_WORDS)

    def check_text(self, text: str) -> Optional[WakeWordMatch]:
        """Check typed text for a wake word (text-input fallback mode).

        Unlike streaming partials, typed commands can be full sentences, so we
        search the entire text instead of just the trailing partial window.

        Args:
            text: User-typed text string.

        Returns:
            WakeWordMatch if a wake word is found, else None.
        """
        if self.state == DetectorState.DISABLED:
            return None

        if self._in_cooldown() and not self._contains_wake_phrase(text):
            return None

        return self._search(text, limit=None)

    def strip_wake_word(self, text: str) -> str:
        """Remove the wake word from the beginning of a text string.

        Useful for extracting the actual command after wake word detection.

        Args:
            text: Full text potentially starting with a wake word.

        Returns:
            Text with the wake word prefix stripped (or unchanged if not found).
        """
        if not text or not text.strip():
            return text

        normalised = text.strip().lower()
        for ww in self._wake_words_normalised:
            if normalised.startswith(ww):
                remainder = text[len(ww):].strip()
                if remainder and remainder[0] in ",.;:!?":
                    remainder = remainder[1:].strip()
                return remainder if remainder else text

            # Also support prefix variants like 'hey arogya, go to pharmacy'
            # where the wake phrase is followed by punctuation without a space.
            if re.search(rf"^(?:.*?\s)?{re.escape(ww)}[\s,;:!?]+", normalised):
                remainder = re.sub(
                    rf"^(?:.*?\s)?{re.escape(ww)}[\s,;:!?]*",
                    "",
                    normalised,
                    count=1,
                )
                return remainder.strip() if remainder.strip() else text

        return text

    def get_greeting(self) -> str:
        """Get a randomised greeting response after wake word detection.

        Returns:
            A greeting string from the configured response pool.
        """
        return self._cfg.random_greeting()

    def reset(self) -> None:
        """Reset the detector to the LISTENING state."""
        self.state = DetectorState.LISTENING
        self.last_match = None
        log.debug("WakeWordDetector reset to LISTENING.")

    def disable(self) -> None:
        """Disable the detector."""
        self.state = DetectorState.DISABLED
        log.info("WakeWordDetector disabled.")

    def enable(self) -> None:
        """Re-enable the detector and return to LISTENING."""
        self.state = DetectorState.LISTENING
        log.info("WakeWordDetector enabled.")

    # ─────────────────────────────────────────────────────────────────────────
    # Internal Detection Logic
    # ─────────────────────────────────────────────────────────────────────────

    def _search(self, text: str, limit: Optional[int] = None) -> Optional[WakeWordMatch]:
        """Search text for a wake word using exact and fuzzy matching.

        Strategy:
            1. Normalise input text.
            2. Generate candidate windows (n-grams of wake word lengths).
            3. For each candidate, try exact match first.
            4. If no exact match, try Levenshtein fuzzy match.

        Args:
            text: Input text to search.
            limit: Optional max number of trailing tokens to consider.  When
                None, the full text is searched (useful for typed commands).

        Returns:
            WakeWordMatch if found, else None.
        """
        if not text or not text.strip():
            return None

        normalised = text.strip().lower()
        words = normalised.split()

        if not words:
            return None

        # Strip leading/trailing punctuation from each word so that
        # "hey robot," or "hey robot!" still triggers an exact match.
        stripped = [w.strip(".,;:!?\"'") for w in words]

        # Streaming partials use a small trailing window. Full typed commands
        # scan the whole sentence to keep wake-word activation reliable.
        if limit is not None and len(stripped) > limit:
            search_words = stripped[-limit:]
        else:
            search_words = stripped

        # Try each wake word length
        for ww_idx, ww in enumerate(self._wake_words_normalised):
            ww_len = self._wake_word_lengths[ww_idx]

            if len(search_words) < ww_len:
                continue

            # Slide a window of ww_len words across the search text
            for i in range(len(search_words) - ww_len + 1):
                candidate = " ".join(search_words[i:i + ww_len])

                # ── Exact match ──────────────────────────────────────────────
                if candidate == ww:
                    return self._activate(ww, text, edit_dist=0)

                # ── Fuzzy match ──────────────────────────────────────────────
                if _FUZZY_AVAILABLE:
                    dist = levenshtein_distance(candidate, ww)
                    if dist <= self._cfg.FUZZY_THRESHOLD:
                        return self._activate(ww, text, edit_dist=dist)

        return None

    def _activate(self, phrase: str, source_text: str, edit_dist: int) -> WakeWordMatch:
        """Record a successful wake word activation.

        Args:
            phrase:      The matched wake phrase.
            source_text: The raw source text.
            edit_dist:   Levenshtein distance of the match.

        Returns:
            The WakeWordMatch object.
        """
        now = time.monotonic()
        match = WakeWordMatch(
            phrase=phrase,
            source_text=source_text,
            edit_dist=edit_dist,
            timestamp=now,
        )

        self.last_match = match
        self.activations += 1
        self._last_activation_time = now
        self.state = DetectorState.COOLDOWN

        match_type = "exact" if edit_dist == 0 else f"fuzzy (dist={edit_dist})"
        log.info(
            "Wake word detected [%s]: '%s' in '%s' (activation #%d)",
            match_type, phrase, source_text[:60], self.activations,
        )

        return match

    def _contains_wake_phrase(self, text: str) -> bool:
        """Return True when the text contains any configured wake phrase."""
        if not text or not text.strip():
            return False
        normalized = text.lower()
        for phrase in self._wake_words_normalised:
            if phrase in normalized:
                return True
        return False

    def _in_cooldown(self) -> bool:
        """Check if the detector is still in the cooldown period."""
        if self._last_activation_time == 0.0:
            return False

        elapsed = time.monotonic() - self._last_activation_time
        if elapsed < self._cfg.COOLDOWN_SEC:
            self.state = DetectorState.COOLDOWN
            return True

        # Cooldown expired — return to listening
        if self.state == DetectorState.COOLDOWN:
            self.state = DetectorState.LISTENING
        return False

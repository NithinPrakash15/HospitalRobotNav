"""
HospitalRobotNav — Speech Display Panel
=========================================
Shows the live speech transcript, dialogue state, wake‑word detection
status, and robot spoken responses in a scrolling glass‑morphism panel.

Subscribes to EventBus events:
    WAKE_WORD_DETECTED  → highlight listening indicator
    SPEECH_RECOGNIZED   → append user transcript line
    DIALOGUE_UPDATE     → update dialogue state badge
    DIALOGUE_RESPONSE   → append robot response line

Architecture Note (ROS2):
    In a deployed system the transcript data arrives via
    /robot/speech_transcript (std_msgs/String) and
    /robot/dialogue_state (std_msgs/String).
"""

from __future__ import annotations

import time
from collections import deque
from typing import Deque, Optional, Tuple

import pygame

from .dashboard_panel import DashboardPanel
from .dashboard_config import (
    FONT_NAME,
    FONT_SIZE_SMALL,
    FONT_SIZE_MEDIUM,
    TEXT_COLOR_PRIMARY,
    TEXT_COLOR_SECONDARY,
    ACCENT_COLOR,
    PANEL_PADDING,
    MAX_LOG_LINES,
)


# ─── Colour shortcuts ────────────────────────────────────────────────────────
_COLOR_USER       = (120, 200, 255)   # Soft cyan for user utterances
_COLOR_ROBOT      = (160, 255, 160)   # Soft green for robot responses
_COLOR_SYSTEM     = (255, 200, 100)   # Amber for system messages
_COLOR_WAKE       = (255, 100, 130)   # Pinkish‑red for wake word indicator
_COLOR_LISTENING  = (100, 255, 180)   # Bright green pulsing dot
_COLOR_IDLE       = (80, 80, 100)     # Dimmed dot


# ─── Transcript entry ────────────────────────────────────────────────────────
class _TranscriptLine:
    """A single line in the transcript log."""

    __slots__ = ("text", "color", "timestamp")

    def __init__(self, text: str, color: Tuple[int, int, int]) -> None:
        self.text = text
        self.color = color
        self.timestamp = time.monotonic()


class SpeechDisplayPanel(DashboardPanel):
    """Pygame panel showing live speech interaction transcript.

    Layout (top → bottom):
        1. Title bar  — "Speech Interaction"
        2. State badge — current dialogue state (IDLE / LISTENING / CONFIRMING …)
        3. Wake‑word indicator — pulsing dot when wake word detected
        4. Scrolling transcript — user utterances (cyan) + robot replies (green)
    """

    # ── construction ─────────────────────────────────────────────────────────

    def __init__(self, height: int, y_offset: int = 0) -> None:
        super().__init__(height, y_offset)
        self.font_small  = pygame.font.SysFont(FONT_NAME, FONT_SIZE_SMALL)
        self.font_medium = pygame.font.SysFont(FONT_NAME, FONT_SIZE_MEDIUM)

        # Transcript buffer (newest at the end)
        self._transcript: Deque[_TranscriptLine] = deque(maxlen=MAX_LOG_LINES)

        # State
        self._dialogue_state: str = "IDLE"
        self._wake_active: bool = False
        self._wake_expire: float = 0.0  # monotonic time wake indicator expires
        self._scroll_offset: int = 0     # for future scroll support

    # ── public API ───────────────────────────────────────────────────────────

    def add_user_utterance(self, text: str) -> None:
        """Append a recognised user utterance to the transcript."""
        self._transcript.append(_TranscriptLine(f"🗣  {text}", _COLOR_USER))

    def add_robot_response(self, text: str) -> None:
        """Append a robot spoken/text response to the transcript."""
        self._transcript.append(_TranscriptLine(f"🤖 {text}", _COLOR_ROBOT))

    def add_system_message(self, text: str) -> None:
        """Append a system‑level message (e.g. 'Wake word detected')."""
        self._transcript.append(_TranscriptLine(f"⚙  {text}", _COLOR_SYSTEM))

    def set_dialogue_state(self, state_name: str) -> None:
        """Update the current dialogue state label."""
        self._dialogue_state = state_name.upper()

    def trigger_wake_indicator(self, duration: float = 2.0) -> None:
        """Flash the wake‑word indicator for *duration* seconds."""
        self._wake_active = True
        self._wake_expire = time.monotonic() + duration

    # ── rendering ────────────────────────────────────────────────────────────

    def render(self, dt: float) -> pygame.Surface:
        surf = super().render(dt)
        y = PANEL_PADDING

        # ── 1. Title ─────────────────────────────────────────────────────────
        title = self.font_medium.render("Speech Interaction", True, TEXT_COLOR_PRIMARY)
        surf.blit(title, (PANEL_PADDING, y))
        y += title.get_height() + 6

        # ── 2. Dialogue state badge ──────────────────────────────────────────
        badge_text = f"State: {self._dialogue_state}"
        badge_surf = self.font_small.render(badge_text, True, ACCENT_COLOR)
        # Draw pill background
        bw = badge_surf.get_width() + 12
        bh = badge_surf.get_height() + 4
        pill = pygame.Surface((bw, bh), pygame.SRCALPHA)
        pygame.draw.rect(pill, (*ACCENT_COLOR, 50), pygame.Rect(0, 0, bw, bh),
                         border_radius=8)
        pill.blit(badge_surf, (6, 2))
        surf.blit(pill, (PANEL_PADDING, y))
        y += bh + 8

        # ── 3. Wake‑word indicator ───────────────────────────────────────────
        now = time.monotonic()
        if self._wake_active and now >= self._wake_expire:
            self._wake_active = False

        dot_color = _COLOR_LISTENING if self._wake_active else _COLOR_IDLE
        # Pulsing radius when active
        radius = 6
        if self._wake_active:
            pulse = abs((now * 4) % 2 - 1)  # 0→1→0 oscillation
            radius = int(6 + 3 * pulse)
        pygame.draw.circle(surf, dot_color, (PANEL_PADDING + 8, y + 8), radius)
        wake_label = "Listening…" if self._wake_active else "Idle — say wake word"
        lbl = self.font_small.render(wake_label, True, TEXT_COLOR_SECONDARY)
        surf.blit(lbl, (PANEL_PADDING + 22, y))
        y += lbl.get_height() + 10

        # ── 4. Separator ─────────────────────────────────────────────────────
        pygame.draw.line(
            surf,
            (*TEXT_COLOR_SECONDARY, 60),
            (PANEL_PADDING, y),
            (self.width - PANEL_PADDING, y),
        )
        y += 6

        # ── 5. Scrolling transcript ──────────────────────────────────────────
        available_height = self.height - y - PANEL_PADDING
        line_h = self.font_small.get_linesize() + 2

        # How many lines fit?
        max_visible = max(1, available_height // line_h)

        # Render the last N lines
        visible_lines = list(self._transcript)[-max_visible:]
        for entry in visible_lines:
            # Truncate long lines
            display_text = entry.text
            if len(display_text) > 40:
                display_text = display_text[:37] + "…"
            txt_surf = self.font_small.render(display_text, True, entry.color)
            surf.blit(txt_surf, (PANEL_PADDING, y))
            y += line_h

        # If transcript is empty, show placeholder
        if not self._transcript:
            placeholder = self.font_small.render(
                "No speech activity yet.", True, _COLOR_IDLE
            )
            surf.blit(placeholder, (PANEL_PADDING, y))

        return surf

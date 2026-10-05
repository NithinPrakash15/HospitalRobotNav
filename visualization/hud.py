"""
HospitalRobotNav — HUD (Head-Up Display) Overlay
==================================================
Renders real-time operational information overlaid on the main viewport.

HUD Elements:
    - Top bar:   FPS counter, simulation speed, sim time
    - Event log: Scrolling event feed (last 8 events)
    - Alerts:    Emergency and warning overlays
    - Status bar: Bottom status strip with current activity
    - Planner badge: Active algorithm name
"""

from __future__ import annotations

import time
from collections import deque
from typing import TYPE_CHECKING, Deque, Tuple

import pygame

from config.settings import COLORS, DISPLAY
from utilities.logger import get_logger

if TYPE_CHECKING:
    from simulation.simulator import Simulator

log = get_logger(__name__)


class HUDEntry:
    """A single HUD event log entry."""

    __slots__ = ("text", "color", "timestamp", "age")

    def __init__(self, text: str, color: Tuple[int, int, int]) -> None:
        self.text      = text
        self.color     = color
        self.timestamp = time.time()
        self.age       = 0.0


class HUD:
    """
    Head-Up Display overlay renderer.

    Draws real-time status information on top of the simulation viewport.

    Usage:
        hud = HUD(screen)
        # Inside render loop:
        hud.update(sim)
        hud.draw()
    """

    MAX_LOG_ENTRIES = 8
    LOG_ENTRY_LIFETIME_S = 8.0
    FADE_START_S = 6.0

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen    = screen
        self._log:     Deque[HUDEntry] = deque(maxlen=self.MAX_LOG_ENTRIES)
        self._alert:   str = ""
        self._alert_color: Tuple[int, int, int] = COLORS.TEXT_DANGER
        self._alert_until: float = 0.0

        pygame.font.init()
        try:
            self._font_large  = pygame.font.SysFont("Segoe UI", 18, bold=True)
            self._font_medium = pygame.font.SysFont("Segoe UI", 13, bold=True)
            self._font_small  = pygame.font.SysFont("Segoe UI", 11)
        except Exception:
            self._font_large  = pygame.font.Font(None, 20)
            self._font_medium = pygame.font.Font(None, 15)
            self._font_small  = pygame.font.Font(None, 13)

        self._fps_clock = pygame.time.Clock()
        self._frame_times: Deque[float] = deque(maxlen=60)
        self._last_frame  = time.time()

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def log_event(
        self,
        text: str,
        color: Tuple[int, int, int] = None,
    ) -> None:
        """
        Add an event to the HUD scrolling event log.

        Args:
            text:  Event description (max 50 chars displayed).
            color: RGB color (default: text secondary).
        """
        color = color or COLORS.TEXT_SECONDARY
        entry = HUDEntry(text[:60], color)
        self._log.append(entry)

    def show_alert(
        self,
        message: str,
        duration_s: float = 3.0,
        color: Tuple[int, int, int] = None,
    ) -> None:
        """
        Show a full-width alert banner on the HUD.

        Args:
            message:    Alert text.
            duration_s: How long to display (seconds).
            color:      Banner color (default: danger red).
        """
        self._alert       = message
        self._alert_color = color or COLORS.TEXT_DANGER
        self._alert_until = time.time() + duration_s

    def update(self, sim: "Simulator") -> None:
        """
        Update HUD state from simulator.

        Should be called once per frame before draw().

        Args:
            sim: Active Simulator instance.
        """
        now = time.time()

        # Update FPS tracking
        dt = now - self._last_frame
        self._last_frame = now
        if dt > 0:
            self._frame_times.append(dt)

        # Age out old log entries
        for entry in list(self._log):
            entry.age = now - entry.timestamp
        # Remove expired entries
        while self._log and self._log[0].age > self.LOG_ENTRY_LIFETIME_S:
            self._log.popleft()

    def draw(self, sim: "Simulator") -> None:
        """
        Render all HUD elements onto the screen.

        Args:
            sim: Active Simulator instance.
        """
        self._draw_topbar(sim)
        self._draw_event_log()
        self._draw_planner_badge(sim)
        self._draw_alert()
        self._draw_statusbar(sim)

    # ─────────────────────────────────────────────────────────────────────────
    # HUD Element Renderers
    # ─────────────────────────────────────────────────────────────────────────

    def _draw_topbar(self, sim: "Simulator") -> None:
        """Draw top HUD bar: FPS, speed, sim time."""
        vp_x = DISPLAY.LEFT_PANEL_WIDTH
        bar_h = 24
        bar_w = DISPLAY.MAP_VIEWPORT_WIDTH

        # Semi-transparent bar background
        surf = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
        surf.fill((10, 12, 20, 180))
        self.screen.blit(surf, (vp_x, 0))

        # FPS
        fps = self._get_fps()
        fps_color = COLORS.TEXT_SUCCESS if fps >= 55 else (
            COLORS.TEXT_WARNING if fps >= 30 else COLORS.TEXT_DANGER
        )
        fps_txt = self._font_small.render(f"FPS: {fps:.0f}", True, fps_color)
        self.screen.blit(fps_txt, (vp_x + 8, 4))

        # Sim time
        sim_t = self._font_small.render(
            f"SIM: {sim.clock.sim_time_s:.1f}s", True, COLORS.TEXT_SECONDARY
        )
        self.screen.blit(sim_t, (vp_x + 80, 4))

        # Speed
        spd_txt = self._font_small.render(
            f"SPEED: {sim.clock.speed:.2g}x", True, COLORS.TEXT_ACCENT
        )
        self.screen.blit(spd_txt, (vp_x + 180, 4))

        # Paused indicator
        if sim.clock.is_paused:
            pause_txt = self._font_medium.render("|| PAUSED", True, COLORS.TEXT_WARNING)
            rect = pause_txt.get_rect(centerx=vp_x + bar_w // 2, y=4)
            self.screen.blit(pause_txt, rect)

        # Step counter
        step_txt = self._font_small.render(
            f"STEP: {sim.clock.sim_step:,}", True, COLORS.TEXT_SECONDARY
        )
        self.screen.blit(step_txt, (vp_x + bar_w - 140, 4))

        # Zoom level
        zoom_txt = self._font_small.render(
            f"ZOOM: {sim.renderer_zoom:.1f}x" if hasattr(sim, "renderer_zoom") else "",
            True, COLORS.TEXT_SECONDARY,
        )
        self.screen.blit(zoom_txt, (vp_x + bar_w - 60, 4))

    def _draw_event_log(self) -> None:
        """Draw scrolling event log in bottom-left of viewport."""
        vp_x = DISPLAY.LEFT_PANEL_WIDTH + 10
        vp_h = DISPLAY.WINDOW_HEIGHT
        line_h = 14
        start_y = vp_h - 30 - len(self._log) * line_h

        for i, entry in enumerate(self._log):
            y = start_y + i * line_h

            # Fade out near expiry
            alpha_frac = 1.0
            if entry.age > self.FADE_START_S:
                alpha_frac = max(0.0, 1.0 - (entry.age - self.FADE_START_S) /
                                 (self.LOG_ENTRY_LIFETIME_S - self.FADE_START_S))

            color = tuple(int(c * alpha_frac) for c in entry.color)
            txt   = self._font_small.render(f"  {entry.text}", True, color)

            # Subtle background
            bg = pygame.Surface((txt.get_width() + 4, line_h), pygame.SRCALPHA)
            bg.fill((10, 12, 20, int(120 * alpha_frac)))
            self.screen.blit(bg, (vp_x - 2, y))
            self.screen.blit(txt, (vp_x, y))

    def _draw_planner_badge(self, sim: "Simulator") -> None:
        """Draw active planner badge in top-right of viewport."""
        vp_x = DISPLAY.LEFT_PANEL_WIDTH
        vp_w = DISPLAY.MAP_VIEWPORT_WIDTH
        planner_name = sim.planner_factory.active_planner_name

        txt  = self._font_medium.render(f"[{planner_name}]", True, COLORS.TEXT_ACCENT)
        rect = txt.get_rect(right=vp_x + vp_w - 10, y=6)

        bg = pygame.Surface((txt.get_width() + 10, 20), pygame.SRCALPHA)
        bg.fill((15, 30, 60, 160))
        self.screen.blit(bg, (rect.x - 5, 4))
        self.screen.blit(txt, rect)

    def _draw_alert(self) -> None:
        """Draw full-width alert banner if active."""
        now = time.time()
        if now > self._alert_until or not self._alert:
            return

        vp_x = DISPLAY.LEFT_PANEL_WIDTH
        vp_w = DISPLAY.MAP_VIEWPORT_WIDTH
        bar_h = 36

        # Blink: visible during first 0.4s of each 0.8s cycle
        t_remaining = self._alert_until - now
        blink_phase = (now * 2) % 1.0
        if t_remaining > 1.0 and blink_phase > 0.5:
            return

        surf = pygame.Surface((vp_w, bar_h), pygame.SRCALPHA)
        surf.fill((*self._alert_color, 200))
        self.screen.blit(surf, (vp_x, DISPLAY.WINDOW_HEIGHT // 2 - bar_h // 2))

        txt = self._font_large.render(self._alert, True, COLORS.TEXT_PRIMARY)
        rect = txt.get_rect(center=(vp_x + vp_w // 2, DISPLAY.WINDOW_HEIGHT // 2))
        self.screen.blit(txt, rect)

    def _draw_statusbar(self, sim: "Simulator") -> None:
        """Draw bottom status bar with robot activity."""
        vp_x  = DISPLAY.LEFT_PANEL_WIDTH
        vp_w  = DISPLAY.MAP_VIEWPORT_WIDTH
        vp_h  = DISPLAY.WINDOW_HEIGHT
        bar_h = 20

        surf = pygame.Surface((vp_w, bar_h), pygame.SRCALPHA)
        surf.fill((10, 12, 20, 180))
        self.screen.blit(surf, (vp_x, vp_h - bar_h))

        robot  = sim.robot
        status = (
            f"Robot: {robot.robot_id}  |  "
            f"State: {robot.state.name}  |  "
            f"Pos: ({robot.row:.1f}, {robot.col:.1f})  |  "
            f"Speed: {robot.velocity:.2f} c/s  |  "
            f"Battery: {robot.battery.soc_percent:.0f}%  |  "
            f"Missions: {robot.total_missions_completed}"
        )
        txt = self._font_small.render(status, True, COLORS.TEXT_SECONDARY)
        self.screen.blit(txt, (vp_x + 6, vp_h - bar_h + 3))

    def draw_text_input(self, current_text: str) -> None:
        """Render the text command input box overlay.

        Called by main.py when the 'T' text-input fallback is active.

        Args:
            current_text: The text currently typed by the user.
        """
        vp_x = DISPLAY.LEFT_PANEL_WIDTH
        vp_w = DISPLAY.MAP_VIEWPORT_WIDTH
        box_h = 40
        box_y = DISPLAY.WINDOW_HEIGHT - 60

        # Semi-transparent input box background
        surf = pygame.Surface((vp_w - 40, box_h), pygame.SRCALPHA)
        surf.fill((20, 30, 50, 220))
        self.screen.blit(surf, (vp_x + 20, box_y))

        # Border
        pygame.draw.rect(
            self.screen, COLORS.BORDER_ACCENT,
            (vp_x + 20, box_y, vp_w - 40, box_h), 2,
        )

        # Blinking cursor
        cursor = "|" if int(time.time() * 2) % 2 == 0 else " "
        display_text = f"> {current_text}{cursor}"

        txt = self._font_medium.render(display_text, True, COLORS.TEXT_ACCENT)
        self.screen.blit(txt, (vp_x + 30, box_y + 10))

        hint = self._font_small.render(
            "Type a command (e.g. 'deliver paracetamol to room 205') — Enter to submit, Esc to cancel",
            True, COLORS.TEXT_SECONDARY,
        )
        self.screen.blit(hint, (vp_x + 30, box_y - 18))

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _get_fps(self) -> float:
        """Compute FPS from recent frame times."""
        if len(self._frame_times) < 2:
            return 0.0
        avg_dt = sum(self._frame_times) / len(self._frame_times)
        return 1.0 / avg_dt if avg_dt > 0 else 0.0

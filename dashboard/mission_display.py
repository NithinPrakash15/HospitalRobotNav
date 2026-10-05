"""
Mission display panel for the dashboard – shows queued missions, progress bars, ETA.
"""

from __future__ import annotations

import pygame
from typing import List, Tuple

from .dashboard_panel import DashboardPanel
from .dashboard_config import (
    FONT_NAME,
    FONT_SIZE_SMALL,
    FONT_SIZE_MEDIUM,
    TEXT_COLOR_PRIMARY,
    TEXT_COLOR_SECONDARY,
    ACCENT_COLOR,
    PANEL_PADDING,
)

# Assuming MissionPlan objects are available via EventBus events.

class MissionDisplayPanel(DashboardPanel):
    """Panel that visualises the mission queue and active mission progress."""

    def __init__(self, height: int, y_offset: int = 0) -> None:
        super().__init__(height, y_offset)
        self.font_small = pygame.font.SysFont(FONT_NAME, FONT_SIZE_SMALL)
        self.font_medium = pygame.font.SysFont(FONT_NAME, FONT_SIZE_MEDIUM)
        self.mission_queue: List[Tuple[str, float]] = []  # (mission_id, eta_sec)
        self.active_mission: str | None = None
        self.active_progress: float = 0.0  # 0‑1

    def set_queue(self, queue: List[Tuple[str, float]]) -> None:
        """Update the mission queue.

        Args:
            queue: List of (mission_id, eta_seconds).
        """
        self.mission_queue = queue

    def set_active(self, mission_id: str, progress: float) -> None:
        self.active_mission = mission_id
        self.active_progress = max(0.0, min(1.0, progress))

    def render(self, dt: float) -> pygame.Surface:
        surf = super().render(dt)
        # Background already drawn
        y = PANEL_PADDING
        # Title
        title_surf = self.font_medium.render("Mission Queue", True, TEXT_COLOR_PRIMARY)
        surf.blit(title_surf, (PANEL_PADDING, y))
        y += title_surf.get_height() + PANEL_PADDING
        # List queued missions
        for idx, (mid, eta) in enumerate(self.mission_queue[:5]):
            line = f"{idx + 1}. {mid} – ETA {int(eta)}s"
            txt = self.font_small.render(line, True, TEXT_COLOR_SECONDARY)
            surf.blit(txt, (PANEL_PADDING, y))
            y += txt.get_height() + 2
        # Active mission progress bar
        if self.active_mission:
            y += PANEL_PADDING
            active_title = self.font_medium.render("Active: " + self.active_mission, True, TEXT_COLOR_PRIMARY)
            surf.blit(active_title, (PANEL_PADDING, y))
            y += active_title.get_height() + 4
            bar_width = self.width - 2 * PANEL_PADDING
            bar_height = 12
            # Draw background bar
            pygame.draw.rect(
                surf,
                (50, 50, 60),
                pygame.Rect(PANEL_PADDING, y, bar_width, bar_height),
                border_radius=6,
            )
            # Draw progress fill
            fill_width = int(bar_width * self.active_progress)
            pygame.draw.rect(
                surf,
                ACCENT_COLOR,
                pygame.Rect(PANEL_PADDING, y, fill_width, bar_height),
                border_radius=6,
            )
            # ETA text
            eta_text = self.font_small.render(
                f"ETA: {int((1 - self.active_progress) * 60)}s", True, TEXT_COLOR_SECONDARY
            )
            surf.blit(eta_text, (PANEL_PADDING, y + bar_height + 2))
        return surf

"""
Dashboard panel base class – provides glassmorphism background, fade‑in/out animations,
and a simple layout system for derived panels.
"""

from __future__ import annotations

import pygame
from typing import Tuple

from .dashboard_config import (
    PANEL_BG_COLOR,
    PANEL_PADDING,
    FADE_IN_DURATION,
    FADE_OUT_DURATION,
)

class DashboardPanel:
    """Base class for all dashboard panels.

    Each panel is drawn onto a surface of size ``(PANEL_WIDTH, height)`` and
    composited onto the main renderer. Sub‑classes implement ``render`` to draw
    their content.
    """

    def __init__(self, height: int, y_offset: int = 0) -> None:
        from .dashboard_config import PANEL_WIDTH
        self.width = PANEL_WIDTH
        self.height = height
        self.y_offset = y_offset
        self.surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.alpha = 0  # Current opacity (0‑255)
        self._fade_in = True
        self._elapsed = 0.0

    def update(self, dt: float) -> None:
        """Update fade animation.

        Args:
            dt: Time step in seconds.
        """
        self._elapsed += dt
        duration = FADE_IN_DURATION if self._fade_in else FADE_OUT_DURATION
        progress = min(self._elapsed / duration, 1.0)
        self.alpha = int(progress * 255)
        if progress >= 1.0:
            # Switch direction when fully visible/invisible
            self._fade_in = not self._fade_in
            self._elapsed = 0.0

    def draw_background(self) -> None:
        """Draw the semi‑transparent glass‑morphism background."""
        # Clear surface
        self.surface.fill((0, 0, 0, 0))
        # Draw rounded rect with blur simulation (simple transparent fill)
        bg_color = (*PANEL_BG_COLOR[:3], self.alpha)
        pygame.draw.rect(
            self.surface,
            bg_color,
            pygame.Rect(0, 0, self.width, self.height),
            border_radius=12,
        )

    def render(self, dt: float) -> pygame.Surface:
        """Public render method – updates animation and returns drawable surface."""
        self.update(dt)
        self.draw_background()
        # Sub‑classes should call ``self.surface.blit`` after this.
        return self.surface

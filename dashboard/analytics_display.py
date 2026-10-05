"""
HospitalRobotNav — Analytics Display Panel
=============================================
Renders real‑time navigation statistics, battery gauge, speed indicator,
visited‑node heatmap, and mission completion metrics in a compact Pygame panel.

Data Sources:
    - Robot battery level, speed, position from Simulator state
    - Path planning metrics from EventBus history
    - Mission completion rate from MissionExecutor

Architecture Note (ROS2):
    Maps to /robot/diagnostics (diagnostic_msgs/DiagnosticArray)
    and /robot/battery_state (sensor_msgs/BatteryState).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

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
)


# ─── Colour constants ────────────────────────────────────────────────────────
_BAR_BG          = (40, 40, 55)
_BATTERY_FULL    = (80, 220, 120)   # Green
_BATTERY_MID     = (240, 200, 60)   # Amber
_BATTERY_LOW     = (240, 80, 80)    # Red
_SPEED_COLOR     = (100, 180, 255)  # Soft blue
_STAT_LABEL      = (160, 160, 180)
_STAT_VALUE      = (220, 220, 235)
_HEATMAP_HOT     = (255, 80, 50)    # Red‑orange
_HEATMAP_COLD    = (30, 30, 60)     # Dark blue‑gray
_SUCCESS_COLOR   = (80, 220, 160)
_FAIL_COLOR      = (240, 80, 80)


@dataclass
class NavigationStats:
    """Snapshot of navigation performance metrics."""

    path_length_cells: int = 0
    planning_time_ms: float = 0.0
    nodes_expanded: int = 0
    replans: int = 0
    collisions_avoided: int = 0
    total_distance_px: float = 0.0
    missions_completed: int = 0
    missions_failed: int = 0


class AnalyticsDisplayPanel(DashboardPanel):
    """Pygame panel showing navigation analytics, battery, speed, and heatmap.

    Layout (top → bottom):
        1. Title — "Analytics"
        2. Battery gauge bar with percentage
        3. Speed indicator bar
        4. Navigation statistics grid (2‑column)
        5. Mission completion ratio bar
        6. Miniature visited‑node heatmap (16×16 cells)
    """

    def __init__(self, height: int, y_offset: int = 0) -> None:
        super().__init__(height, y_offset)
        self.font_small  = pygame.font.SysFont(FONT_NAME, FONT_SIZE_SMALL)
        self.font_medium = pygame.font.SysFont(FONT_NAME, FONT_SIZE_MEDIUM)

        # Inputs — updated externally
        self.battery_pct: float = 100.0          # 0 – 100
        self.speed_pct: float = 0.0              # 0 – 100 of max speed
        self.stats = NavigationStats()

        # Heatmap (16×16 mini grid)
        self._heatmap_size = 16
        self._heatmap: List[List[int]] = [
            [0] * self._heatmap_size for _ in range(self._heatmap_size)
        ]
        self._heatmap_max: int = 1  # avoid division by zero

    # ── Public setters ───────────────────────────────────────────────────────

    def set_battery(self, pct: float) -> None:
        self.battery_pct = max(0.0, min(100.0, pct))

    def set_speed(self, pct: float) -> None:
        self.speed_pct = max(0.0, min(100.0, pct))

    def set_stats(self, stats: NavigationStats) -> None:
        self.stats = stats

    def record_visit(self, grid_row: int, grid_col: int,
                     map_rows: int = 100, map_cols: int = 100) -> None:
        """Record that the robot visited a grid cell (for the heatmap)."""
        hr = int(grid_row / max(1, map_rows) * self._heatmap_size)
        hc = int(grid_col / max(1, map_cols) * self._heatmap_size)
        hr = max(0, min(self._heatmap_size - 1, hr))
        hc = max(0, min(self._heatmap_size - 1, hc))
        self._heatmap[hr][hc] += 1
        self._heatmap_max = max(self._heatmap_max, self._heatmap[hr][hc])

    # ── Rendering helpers ────────────────────────────────────────────────────

    @staticmethod
    def _lerp_color(
        a: Tuple[int, int, int],
        b: Tuple[int, int, int],
        t: float,
    ) -> Tuple[int, int, int]:
        t = max(0.0, min(1.0, t))
        return (
            int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t),
        )

    def _draw_gauge_bar(
        self,
        surf: pygame.Surface,
        x: int, y: int,
        width: int, height: int,
        pct: float,
        fill_color: Tuple[int, int, int],
        label: str,
        value_text: str,
    ) -> int:
        """Draw a labelled horizontal gauge bar. Returns y after the element."""
        # Label
        lbl = self.font_small.render(label, True, _STAT_LABEL)
        surf.blit(lbl, (x, y))
        val = self.font_small.render(value_text, True, _STAT_VALUE)
        surf.blit(val, (x + width - val.get_width(), y))
        y += lbl.get_height() + 2

        # Background bar
        pygame.draw.rect(surf, _BAR_BG,
                         pygame.Rect(x, y, width, height), border_radius=5)
        # Fill bar
        fill_w = int(width * max(0.0, min(1.0, pct / 100.0)))
        if fill_w > 0:
            pygame.draw.rect(surf, fill_color,
                             pygame.Rect(x, y, fill_w, height), border_radius=5)
        return y + height + 8

    def _battery_color(self) -> Tuple[int, int, int]:
        if self.battery_pct > 50:
            return _BATTERY_FULL
        elif self.battery_pct > 20:
            return _BATTERY_MID
        else:
            return _BATTERY_LOW

    # ── Main render ──────────────────────────────────────────────────────────

    def render(self, dt: float) -> pygame.Surface:
        surf = super().render(dt)
        y = PANEL_PADDING
        bar_w = self.width - 2 * PANEL_PADDING

        # ── Title ────────────────────────────────────────────────────────────
        title = self.font_medium.render("Analytics", True, TEXT_COLOR_PRIMARY)
        surf.blit(title, (PANEL_PADDING, y))
        y += title.get_height() + 8

        # ── Battery gauge ────────────────────────────────────────────────────
        y = self._draw_gauge_bar(
            surf, PANEL_PADDING, y, bar_w, 10,
            self.battery_pct, self._battery_color(),
            "Battery", f"{self.battery_pct:.0f}%",
        )

        # ── Speed gauge ──────────────────────────────────────────────────────
        y = self._draw_gauge_bar(
            surf, PANEL_PADDING, y, bar_w, 10,
            self.speed_pct, _SPEED_COLOR,
            "Speed", f"{self.speed_pct:.0f}%",
        )

        # ── Navigation stats (compact 2‑col grid) ───────────────────────────
        stat_items = [
            ("Path Length", f"{self.stats.path_length_cells} cells"),
            ("Plan Time",   f"{self.stats.planning_time_ms:.1f} ms"),
            ("Nodes Exp.",  f"{self.stats.nodes_expanded}"),
            ("Replans",     f"{self.stats.replans}"),
            ("Avoid Coll.", f"{self.stats.collisions_avoided}"),
            ("Distance",    f"{self.stats.total_distance_px:.0f} px"),
        ]

        col_w = bar_w // 2
        for i, (lbl_text, val_text) in enumerate(stat_items):
            col = i % 2
            row_y = y + (i // 2) * (self.font_small.get_linesize() + 4)
            cx = PANEL_PADDING + col * col_w
            lbl = self.font_small.render(lbl_text, True, _STAT_LABEL)
            val = self.font_small.render(val_text, True, _STAT_VALUE)
            surf.blit(lbl, (cx, row_y))
            surf.blit(val, (cx + lbl.get_width() + 4, row_y))

        rows_drawn = math.ceil(len(stat_items) / 2)
        y += rows_drawn * (self.font_small.get_linesize() + 4) + 8

        # ── Mission completion bar ───────────────────────────────────────────
        total_m = self.stats.missions_completed + self.stats.missions_failed
        comp_pct = (
            (self.stats.missions_completed / total_m * 100) if total_m > 0 else 0
        )
        y = self._draw_gauge_bar(
            surf, PANEL_PADDING, y, bar_w, 8,
            comp_pct, _SUCCESS_COLOR,
            "Mission Success",
            f"{self.stats.missions_completed}/{total_m}",
        )

        # ── Heatmap (16×16 miniature) ────────────────────────────────────────
        hm_label = self.font_small.render("Visit Heatmap", True, _STAT_LABEL)
        surf.blit(hm_label, (PANEL_PADDING, y))
        y += hm_label.get_height() + 4

        cell_px = min(
            (bar_w) // self._heatmap_size,
            (self.height - y - PANEL_PADDING) // self._heatmap_size,
            12,
        )
        if cell_px < 2:
            cell_px = 2

        for r in range(self._heatmap_size):
            for c in range(self._heatmap_size):
                intensity = self._heatmap[r][c] / self._heatmap_max
                color = self._lerp_color(_HEATMAP_COLD, _HEATMAP_HOT, intensity)
                rect = pygame.Rect(
                    PANEL_PADDING + c * cell_px,
                    y + r * cell_px,
                    cell_px - 1,
                    cell_px - 1,
                )
                pygame.draw.rect(surf, color, rect)

        return surf

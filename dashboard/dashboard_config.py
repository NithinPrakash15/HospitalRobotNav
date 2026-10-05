"""
Dashboard configuration – colour palette, layout, fonts.
Designed for a premium dark‑mode glassmorphism UI.
"""

from __future__ import annotations

# UI constants – all dimensions are in pixels.
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
PANEL_WIDTH = 320  # Right‑hand side panel width
PANEL_PADDING = 10
FONT_NAME = "Inter"  # Google Font – ensure it is loaded in the renderer.
FONT_SIZE_SMALL = 14
FONT_SIZE_MEDIUM = 18
FONT_SIZE_LARGE = 24

# Colour palette – HSL‑derived, converted to RGB tuples.
# Using a subtle dark‑mode palette with glass‑morphism overlay.
BACKGROUND_COLOR = (10, 10, 15)  # Very dark bluish‑gray
PANEL_BG_COLOR = (25, 25, 35, 180)  # Semi‑transparent dark overlay (RGBA)
ACCENT_COLOR = (70, 130, 180)  # Steel‑blue accent for progress bars
TEXT_COLOR_PRIMARY = (230, 230, 240)  # Light off‑white
TEXT_COLOR_SECONDARY = (180, 180, 190)  # Slightly dimmer

# Animation timings (seconds)
FADE_IN_DURATION = 0.3
FADE_OUT_DURATION = 0.2

# Misc
MAX_LOG_LINES = 200  # Maximum transcript lines kept in memory

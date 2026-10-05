"""
HospitalRobotNav — Configuration Layer
=======================================
Global application settings, constants, and configuration dataclasses.

Design Principles:
    - All magic numbers live here. Never hardcode values in logic modules.
    - Uses Python dataclasses for type-safe, documented configuration.
    - Follows the Single Responsibility Principle: one file per concern.

ROS2 Compatibility Note:
    In a ROS2 deployment, these values would map to ROS2 parameter servers
    (rclpy.parameter.Parameter) declared in respective node constructors.

Author: Hospital Robot Navigation Research Team
Project: Multi-Agent Embodied AI Robot for Autonomous Hospital Assistance
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Display / Window Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DisplayConfig:
    """Window and rendering settings."""

    # Primary window dimensions (pixels)
    WINDOW_WIDTH: int = 1600
    WINDOW_HEIGHT: int = 900
    WINDOW_TITLE: str = "Autonomous Hospital Robot Navigation System"

    # Target frames per second for the simulation loop. 90 FPS provides smoother
    # motion and more responsive navigation feedback while remaining efficient.
    TARGET_FPS: int = 90

    # Sidebar widths (pixels)
    LEFT_PANEL_WIDTH: int = 260
    RIGHT_PANEL_WIDTH: int = 280

    # Map viewport dimensions derived from window
    @property
    def MAP_VIEWPORT_WIDTH(self) -> int:
        return self.WINDOW_WIDTH - self.LEFT_PANEL_WIDTH - self.RIGHT_PANEL_WIDTH

    @property
    def MAP_VIEWPORT_HEIGHT(self) -> int:
        return self.WINDOW_HEIGHT

    # Minimap dimensions (pixels)
    MINIMAP_WIDTH: int = 200
    MINIMAP_HEIGHT: int = 200
    MINIMAP_MARGIN: int = 10


# ─────────────────────────────────────────────────────────────────────────────
# Color Palette — Dark Professional Theme
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ColorConfig:
    """
    Dark-themed color palette.

    Color naming convention: PURPOSE_STATE or ELEMENT_ROLE
    All colors are (R, G, B) tuples, range 0–255.
    """

    # ── Background & Surface ──────────────────────────────────────────────────
    BG_PRIMARY: Tuple[int, int, int]          = (15, 17, 23)      # Deep space black
    BG_SECONDARY: Tuple[int, int, int]        = (22, 25, 35)      # Panel background
    BG_TERTIARY: Tuple[int, int, int]         = (30, 34, 48)      # Card background
    BG_HIGHLIGHT: Tuple[int, int, int]        = (38, 44, 62)      # Hover / selection

    # ── Text ─────────────────────────────────────────────────────────────────
    TEXT_PRIMARY: Tuple[int, int, int]        = (220, 225, 240)   # Main text
    TEXT_SECONDARY: Tuple[int, int, int]      = (140, 150, 175)   # Subtext / labels
    TEXT_ACCENT: Tuple[int, int, int]         = (100, 200, 255)   # Highlighted text
    TEXT_WARNING: Tuple[int, int, int]        = (255, 180, 50)    # Warning text
    TEXT_DANGER: Tuple[int, int, int]         = (255, 80, 80)     # Error text
    TEXT_SUCCESS: Tuple[int, int, int]        = (80, 220, 130)    # Success text

    # ── Borders & Dividers ────────────────────────────────────────────────────
    BORDER_PRIMARY: Tuple[int, int, int]      = (45, 52, 75)
    BORDER_ACCENT: Tuple[int, int, int]       = (60, 120, 200)

    # ── Map Elements ──────────────────────────────────────────────────────────
    MAP_FLOOR: Tuple[int, int, int]           = (28, 32, 44)      # Walkable tile
    MAP_WALL: Tuple[int, int, int]            = (12, 14, 20)      # Wall tile
    MAP_CORRIDOR: Tuple[int, int, int]        = (35, 42, 58)      # Corridor tile
    MAP_GRID_LINE: Tuple[int, int, int]       = (25, 29, 42)      # Faint grid lines

    # ── Room Category Colors ──────────────────────────────────────────────────
    ROOM_EMERGENCY: Tuple[int, int, int]      = (180, 30, 30)     # Red
    ROOM_ICU: Tuple[int, int, int]            = (160, 20, 20)     # Dark red
    ROOM_NICU: Tuple[int, int, int]           = (200, 50, 120)    # Crimson rose
    ROOM_OT: Tuple[int, int, int]             = (20, 80, 160)     # Surgery blue
    ROOM_RECEPTION: Tuple[int, int, int]      = (30, 100, 60)     # Entry green
    ROOM_PHARMACY: Tuple[int, int, int]       = (40, 140, 80)     # Medical green
    ROOM_LAB: Tuple[int, int, int]            = (80, 40, 160)     # Lab purple
    ROOM_MRI: Tuple[int, int, int]            = (20, 100, 160)    # Imaging blue
    ROOM_PATIENT: Tuple[int, int, int]        = (50, 70, 120)     # Patient blue
    ROOM_DOCTOR: Tuple[int, int, int]         = (60, 90, 140)     # Doctor blue
    ROOM_CAFETERIA: Tuple[int, int, int]      = (140, 90, 20)     # Warm amber
    ROOM_CHARGING: Tuple[int, int, int]       = (20, 160, 160)    # Teal
    ROOM_UTILITY: Tuple[int, int, int]        = (70, 70, 90)      # Grey utility
    ROOM_GENERIC: Tuple[int, int, int]        = (45, 55, 80)      # Default

    # ── Robot ─────────────────────────────────────────────────────────────────
    ROBOT_BODY: Tuple[int, int, int]          = (0, 200, 255)     # Cyan blue
    ROBOT_HEADING: Tuple[int, int, int]       = (255, 255, 255)   # White arrow
    ROBOT_TRAIL: Tuple[int, int, int]         = (0, 100, 150)     # Faded cyan
    ROBOT_SAFE_ZONE: Tuple[int, int, int]     = (0, 80, 100)      # Safe radius

    # ── Path & Planning ───────────────────────────────────────────────────────
    PATH_PLANNED: Tuple[int, int, int]        = (0, 220, 120)     # Green path
    PATH_SMOOTHED: Tuple[int, int, int]       = (0, 255, 160)     # Bright smooth
    NODE_OPEN: Tuple[int, int, int]           = (255, 200, 0)     # Open list (amber)
    NODE_CLOSED: Tuple[int, int, int]         = (80, 80, 180)     # Closed list (blue)
    NODE_START: Tuple[int, int, int]          = (0, 255, 100)     # Start node
    NODE_GOAL: Tuple[int, int, int]           = (255, 60, 60)     # Goal node

    # ── Obstacles ────────────────────────────────────────────────────────────
    OBSTACLE_STATIC: Tuple[int, int, int]     = (80, 40, 40)      # Static obstacle
    OBSTACLE_DYNAMIC: Tuple[int, int, int]    = (200, 100, 0)     # Dynamic obstacle

    # ── UI Controls ──────────────────────────────────────────────────────────
    BUTTON_PRIMARY: Tuple[int, int, int]      = (30, 120, 220)    # Primary button
    BUTTON_HOVER: Tuple[int, int, int]        = (50, 150, 255)    # Hover state
    BUTTON_ACTIVE: Tuple[int, int, int]       = (20, 90, 180)     # Pressed state
    BUTTON_DANGER: Tuple[int, int, int]       = (180, 40, 40)     # Danger button
    BUTTON_SUCCESS: Tuple[int, int, int]      = (30, 160, 80)     # Success button
    BUTTON_DISABLED: Tuple[int, int, int]     = (50, 55, 70)      # Disabled button

    # ── Battery ──────────────────────────────────────────────────────────────
    BATTERY_HIGH: Tuple[int, int, int]        = (30, 210, 100)    # > 60 %
    BATTERY_MID: Tuple[int, int, int]         = (255, 180, 0)     # 20–60 %
    BATTERY_LOW: Tuple[int, int, int]         = (255, 60, 60)     # < 20 %

    # ── Minimap ──────────────────────────────────────────────────────────────
    MINIMAP_BG: Tuple[int, int, int]          = (10, 12, 18)
    MINIMAP_BORDER: Tuple[int, int, int]      = (60, 70, 100)
    MINIMAP_ROBOT: Tuple[int, int, int]       = (0, 220, 255)
    MINIMAP_GOAL: Tuple[int, int, int]        = (255, 60, 60)
    MINIMAP_PATH: Tuple[int, int, int]        = (0, 180, 100)


# ─────────────────────────────────────────────────────────────────────────────
# Simulation Timing
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SimulationConfig:
    """Simulation loop and timing parameters."""

    # Simulation time step (seconds per frame at 1× speed)
    BASE_DT: float = 0.016          # ~60 FPS equivalent

    # Speed multipliers available to the user
    SPEED_OPTIONS: Tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
    DEFAULT_SPEED_INDEX: int = 2    # Index into SPEED_OPTIONS (1.0×)

    # Maximum simulation steps before auto-stopping (safety)
    MAX_STEPS: int = 100_000

    # Steps between replanning checks
    REPLAN_CHECK_INTERVAL: int = 10

    # Node expansion animation delay (milliseconds) — for visual A* walkthrough
    NODE_EXPAND_DELAY_MS: int = 5

    # Whether to animate node expansion step-by-step
    ANIMATE_EXPANSION: bool = True

    # Number of nodes expanded per frame during animation
    NODES_PER_FRAME: int = 5

    # Whether to spawn all registered agents as visible physical robots
    # (Useful for debugging multi-robot behavior and UI visibility)
    SPAWN_ALL_AGENTS: bool = True  # Enabled to show multiple robots by default for debugging

    # Force typed text input mode: when True, the simulator will use the
    # TextInputCapture backend and process typed commands instead of opening
    # the microphone. Useful for development or when a mic is unavailable.
    FORCE_TEXT_INPUT: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Application-Wide Settings Singleton
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AppSettings:
    """
    Root configuration object.

    Usage:
        from config.settings import APP_SETTINGS
        width = APP_SETTINGS.display.WINDOW_WIDTH
    """

    display: DisplayConfig = field(default_factory=DisplayConfig)
    colors: ColorConfig = field(default_factory=ColorConfig)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)

    # Debug flags
    DEBUG_MODE: bool = False
    SHOW_GRID: bool = True
    SHOW_ROOM_LABELS: bool = True
    SHOW_OPEN_LIST: bool = True
    SHOW_CLOSED_LIST: bool = True
    SHOW_TRAIL: bool = True
    LOG_LEVEL: str = "INFO"          # DEBUG | INFO | WARNING | ERROR


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton — import this everywhere
# ─────────────────────────────────────────────────────────────────────────────
APP_SETTINGS = AppSettings()
COLORS = APP_SETTINGS.colors
DISPLAY = APP_SETTINGS.display
SIM_CONFIG = APP_SETTINGS.simulation

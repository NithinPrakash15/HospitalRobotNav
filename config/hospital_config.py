"""
HospitalRobotNav — Hospital Layout Configuration
==================================================
Defines spatial parameters for the 100×100 hospital grid.

Each room category gets a priority weighting used in the cost map.
These constants define the "physics" of the hospital environment.

ROS2 Note:
    Maps to: nav2_params.yaml → map_server → yaml_filename
    In ROS2 deployment, the occupancy grid would be loaded from a
    SLAM-generated .pgm/.yaml file rather than being procedurally generated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class GridConfig:
    """Occupancy grid spatial parameters.

    Grid is 120×120 at 0.5 m/cell → 60 m × 60 m physical footprint.
    Matches a 100-bedded UCHC floor plan (≈ 2 550 m² covered area).
    """

    # Grid dimensions (cells) — 60 m × 60 m physical area
    GRID_ROWS: int = 120
    GRID_COLS: int = 120

    # Physical cell size in real-world meters (ROS2 map_server compatible)
    CELL_SIZE_METERS: float = 0.5   # Each cell = 0.5 m × 0.5 m

    # Visual cell size (pixels) at camera zoom level 1.0
    CELL_SIZE_PIXELS: int = 9

    # Main corridor width (cells) — 5 cells = 2.5 m (≈ hospital-grade 3.6 m corridor)
    CORRIDOR_WIDTH: int = 5

    # Minimum room size (cells × cells)
    MIN_ROOM_SIZE: Tuple[int, int] = (6, 6)

    # Wall thickness at room boundaries (cells)
    WALL_THICKNESS: int = 1

    # Outer border thickness (cells)
    BORDER_THICKNESS: int = 2

    # Central courtyard bounds (impassable decorative zone)
    # Robots navigate around it via the V1/V2 spines
    COURTYARD_TOP:    int = 43
    COURTYARD_LEFT:   int = 40
    COURTYARD_BOTTOM: int = 60
    COURTYARD_RIGHT:  int = 65





@dataclass(frozen=True)
class CostConfig:
    """
    Navigation cost weights for the weighted cost map.

    Lower = faster / preferred traversal.
    Used by all planners as edge weights in the graph.
    """

    # Passable terrain costs
    COST_FREE:          float = 1.0     # Open corridor
    COST_CORRIDOR:      float = 1.0     # Standard corridor
    COST_ROOM_FLOOR:    float = 1.2     # Inside a room (slight penalty)
    COST_DOORWAY:       float = 1.5     # Passing through a doorway
    COST_ELEVATOR:      float = 2.0     # Elevator (wait time modeled)
    COST_STAIRS:        float = 3.0     # Stairs (slow for robot)

    # Dynamic cost additions (added on top of base)
    COST_NEAR_HUMAN:    float = 2.0     # Cell near a human (safety buffer)
    COST_NEAR_OBSTACLE: float = 1.5     # Cell near static obstacle

    # Impassable
    COST_WALL:          float = float('inf')
    COST_BLOCKED:       float = float('inf')

    # D* Lite / replanning
    COST_UNKNOWN:       float = 5.0     # Unexplored cell cost


@dataclass(frozen=True)
class HospitalConfig:
    """
    Master hospital configuration object.

    Usage:
        from config.hospital_config import HOSPITAL_CONFIG
        rows = HOSPITAL_CONFIG.grid.GRID_ROWS
    """

    grid: GridConfig = field(default_factory=GridConfig)
    cost: CostConfig = field(default_factory=CostConfig)

    # Map seed for reproducible random elements
    MAP_SEED: int = 42

    # Border wall thickness (outer boundary)
    BORDER_THICKNESS: int = 2

    # Number of randomly placed dynamic obstacles at startup
    INITIAL_DYNAMIC_OBSTACLES: int = 8

    # Dynamic obstacle movement probability per simulation step
    OBSTACLE_MOVE_PROBABILITY: float = 0.02

    # Safe distance robot maintains from obstacles (cells)
    ROBOT_SAFE_DISTANCE: float = 1.5

    # Maximum number of dynamic obstacles allowed simultaneously
    MAX_DYNAMIC_OBSTACLES: int = 20


# Module-level singleton
HOSPITAL_CONFIG = HospitalConfig()
GRID_CONFIG = HOSPITAL_CONFIG.grid
COST_CONFIG = HOSPITAL_CONFIG.cost

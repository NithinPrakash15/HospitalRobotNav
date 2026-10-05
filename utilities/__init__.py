"""HospitalRobotNav — utilities package."""
from utilities.logger import get_logger, initialize_logging
from utilities.geometry import (
    euclidean_distance, manhattan_distance, chebyshev_distance,
    diagonal_distance, angle_between, normalize_angle, angle_difference,
    heading_to_vector, line_of_sight, bresenham_cells, path_length,
    count_turns, grid_to_pixel, pixel_to_grid, clamp, lerp,
)
from utilities.priority_queue import PriorityQueue, IndexedPriorityQueue
from utilities.event_bus import EventBus, HospitalEvent, EventPayload, EVENT_BUS

__all__ = [
    "get_logger", "initialize_logging",
    "euclidean_distance", "manhattan_distance", "chebyshev_distance",
    "diagonal_distance", "angle_between", "normalize_angle",
    "angle_difference", "heading_to_vector", "line_of_sight",
    "bresenham_cells", "path_length", "count_turns",
    "grid_to_pixel", "pixel_to_grid", "clamp", "lerp",
    "PriorityQueue", "IndexedPriorityQueue",
    "EventBus", "HospitalEvent", "EventPayload", "EVENT_BUS",
]

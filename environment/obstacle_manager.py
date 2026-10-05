"""
HospitalRobotNav — Obstacle Manager
======================================
Manages all static and dynamic obstacles in the hospital simulation.

Responsibilities:
    - Maintain a registry of all dynamic obstacles (humans, carts, etc.)
    - Move dynamic obstacles each simulation tick
    - Inject new obstacles on user request or simulated events
    - Notify the occupancy grid of obstacle changes
    - Publish events for replanning triggers

Dynamic obstacle types:
    DOCTOR      — Medical staff, moves room-to-room
    PATIENT     — Slow-moving patient
    STRETCHER   — Being pushed along corridors
    CART        — Medicine/supply cart
    CLEANER     — Cleaning robot (autonomous, predictable)
    VISITOR     — Irregular movement

ROS2 Note:
    In deployment, dynamic obstacles come from:
    - /people_tracker (leg_detector + social_force_model)
    - /tracked_objects (nav2_people_server)
    - YOLO detection + depth camera fusion
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from config.hospital_config import HOSPITAL_CONFIG
from environment.occupancy_grid import OccupancyGrid
from utilities.event_bus import EVENT_BUS, HospitalEvent
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]


class ObstacleType(Enum):
    """Category of dynamic obstacle."""
    DOCTOR     = auto()
    PATIENT    = auto()
    STRETCHER  = auto()
    CART       = auto()
    CLEANER    = auto()
    VISITOR    = auto()
    CUSTOM     = auto()


# Average seconds between movement steps for each obstacle type.
# Using time-based intervals (instead of per-frame probabilities) makes
# obstacle motion visible and FPS-independent — an obstacle with a 2.0 s
# interval moves about once every 2 simulated seconds regardless of how
# fast the render loop runs.
_TYPE_MOVE_INTERVALS: Dict[ObstacleType, float] = {
    ObstacleType.DOCTOR:    3.0,
    ObstacleType.PATIENT:   4.0,
    ObstacleType.STRETCHER: 3.5,
    ObstacleType.CART:      2.5,
    ObstacleType.CLEANER:   1.5,
    ObstacleType.VISITOR:   3.0,
    ObstacleType.CUSTOM:    2.0,
}


@dataclass
class DynamicObstacle:
    """
    Represents one dynamic obstacle in the simulation.

    Attributes:
        obstacle_id:  Unique string ID.
        obs_type:     Obstacle category.
        position:     Current (row, col) grid cell.
        move_prob:    Probability of moving each simulation step.
        speed:        Grid cells per step when moving.
        color:        RGB tuple for rendering.
        label:        Display string.
        path:         Optional predefined movement path.
        path_index:   Current index into path.
    """
    obstacle_id: str
    obs_type:    ObstacleType
    position:    GridPos
    move_prob:   float               = 0.05
    speed:       int                 = 1
    color:       Tuple[int,int,int]  = (200, 100, 0)
    label:       str                 = ""
    path:        List[GridPos]       = field(default_factory=list)
    path_index:  int                 = 0
    move_interval_sec: float         = 2.0

    def __post_init__(self) -> None:
        if not self.label:
            self.label = self.obs_type.name.capitalize()
        if self.move_interval_sec <= 0.0:
            self.move_interval_sec = _TYPE_MOVE_INTERVALS.get(self.obs_type, 2.0)


_TYPE_COLORS: Dict[ObstacleType, Tuple[int, int, int]] = {
    ObstacleType.DOCTOR:    (100, 180, 255),
    ObstacleType.PATIENT:   (200, 160, 80),
    ObstacleType.STRETCHER: (180, 80, 80),
    ObstacleType.CART:      (80, 200, 120),
    ObstacleType.CLEANER:   (120, 80, 200),
    ObstacleType.VISITOR:   (200, 200, 80),
    ObstacleType.CUSTOM:    (200, 100, 0),
}

_TYPE_MOVE_PROBS: Dict[ObstacleType, float] = {
    ObstacleType.DOCTOR:    0.03,
    ObstacleType.PATIENT:   0.01,
    ObstacleType.STRETCHER: 0.02,
    ObstacleType.CART:      0.04,
    ObstacleType.CLEANER:   0.06,
    ObstacleType.VISITOR:   0.02,
    ObstacleType.CUSTOM:    0.05,
}


class ObstacleManager:
    """
    Manages dynamic obstacles and synchronizes with OccupancyGrid.

    Maintains:
        - Registry of DynamicObstacle instances
        - Per-step movement simulation
        - Grid synchronization after each move

    Usage:
        mgr = ObstacleManager(occupancy_grid)
        mgr.spawn_random_obstacles(8)
        mgr.step()  # called each simulation frame
    """

    def __init__(self, occupancy_grid: OccupancyGrid) -> None:
        self._grid = occupancy_grid
        self._obstacles: Dict[str, DynamicObstacle] = {}
        self._id_counter: int = 0
        self._rng = random.Random(HOSPITAL_CONFIG.MAP_SEED + 1)

        # Directions for random movement (4-connected)
        self._directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]

        log.info("ObstacleManager initialized.")

    # ─────────────────────────────────────────────────────────────────────────
    # Spawning
    # ─────────────────────────────────────────────────────────────────────────

    def spawn_obstacle(
        self,
        row: int,
        col: int,
        obs_type: ObstacleType = ObstacleType.CUSTOM,
        label: Optional[str] = None,
    ) -> Optional[str]:
        """
        Spawn a dynamic obstacle at (row, col).

        Args:
            row:      Grid row.
            col:      Grid column.
            obs_type: Obstacle type.
            label:    Optional display label.

        Returns:
            obstacle_id if spawned successfully, else None.
        """
        if not self._grid.is_free(row, col):
            log.warning("Cannot spawn obstacle at (%d,%d): cell not free", row, col)
            return None

        if len(self._obstacles) >= HOSPITAL_CONFIG.MAX_DYNAMIC_OBSTACLES:
            log.warning("Maximum dynamic obstacle count reached.")
            return None

        self._id_counter += 1
        oid = f"OBS-{self._id_counter:04d}"

        obs = DynamicObstacle(
            obstacle_id=oid,
            obs_type=obs_type,
            position=(row, col),
            move_prob=_TYPE_MOVE_PROBS[obs_type],
            move_interval_sec=_TYPE_MOVE_INTERVALS.get(obs_type, 2.0),
            color=_TYPE_COLORS[obs_type],
            label=label or obs_type.name.capitalize(),
        )

        self._obstacles[oid] = obs
        self._grid.add_dynamic_obstacle(row, col)

        EVENT_BUS.publish(
            HospitalEvent.DYNAMIC_OBSTACLE_ADD,
            data={"obstacle_id": oid, "position": (row, col), "type": obs_type.name},
            source="obstacle_manager",
        )

        log.debug("Spawned %s (%s) at (%d,%d)", oid, obs_type.name, row, col)
        return oid

    def spawn_random_obstacles(
        self,
        count: int,
        obs_type: Optional[ObstacleType] = None,
    ) -> List[str]:
        """
        Spawn `count` obstacles at random free locations in corridors.

        Args:
            count:    Number of obstacles to spawn.
            obs_type: Fixed type, or None for random selection.

        Returns:
            List of spawned obstacle IDs.
        """
        rows = self._grid.rows
        cols = self._grid.cols
        spawned = []
        attempts = 0
        max_attempts = count * 50

        while len(spawned) < count and attempts < max_attempts:
            attempts += 1
            r = self._rng.randint(5, rows - 5)
            c = self._rng.randint(5, cols - 5)

            if not self._grid.is_free(r, c):
                continue

            t = obs_type or self._rng.choice(list(ObstacleType))
            oid = self.spawn_obstacle(r, c, t)
            if oid:
                spawned.append(oid)

        log.info("Spawned %d/%d random obstacles.", len(spawned), count)
        return spawned

    # ─────────────────────────────────────────────────────────────────────────
    # Removal
    # ─────────────────────────────────────────────────────────────────────────

    def remove_obstacle(self, obstacle_id: str) -> bool:
        """
        Remove an obstacle by ID.

        Args:
            obstacle_id: The ID of the obstacle to remove.

        Returns:
            True if removed successfully.
        """
        obs = self._obstacles.pop(obstacle_id, None)
        if obs is None:
            return False

        self._grid.remove_dynamic_obstacle(*obs.position)

        EVENT_BUS.publish(
            HospitalEvent.DYNAMIC_OBSTACLE_REMOVE,
            data={"obstacle_id": obstacle_id, "position": obs.position},
            source="obstacle_manager",
        )

        log.debug("Removed obstacle %s", obstacle_id)
        return True

    def clear_all(self) -> None:
        """Remove all dynamic obstacles."""
        for oid in list(self._obstacles.keys()):
            self.remove_obstacle(oid)
        self._grid.clear_dynamic_obstacles()
        log.info("All dynamic obstacles cleared.")

    # ─────────────────────────────────────────────────────────────────────────
    # Per-Step Simulation
    # ─────────────────────────────────────────────────────────────────────────

    def step(self, dt: float = 1.0) -> List[Tuple[GridPos, GridPos]]:
        """
        Advance all dynamic obstacles by one simulation step.

        Movement is **time-based**: each obstacle tracks a movement
        accumulator (``_move_timer``) and attempts to move when its
        accumulated time exceeds its ``move_interval_sec``.  This makes
        obstacle motion visible and FPS-independent — previously the
        per-frame ``move_prob`` (0.01–0.06) meant obstacles only moved
        once every ~20–100 frames, appearing frozen between interactions.

        Args:
            dt: Simulated time elapsed since the last step (seconds).

        Returns:
            List of (old_pos, new_pos) moves that occurred.
        """
        moves: List[Tuple[GridPos, GridPos]] = []
        dt = max(dt, 0.0)

        for oid, obs in list(self._obstacles.items()):
            # Time accumulator — smooth, frame-rate independent motion
            obs._move_timer = getattr(obs, "_move_timer", 0.0) + dt

            interval = obs.move_interval_sec
            # Randomise the interval slightly so obstacles don't move in sync
            jitter = self._rng.uniform(0.6, 1.4)
            if obs._move_timer < interval * jitter:
                continue
            obs._move_timer = 0.0

            new_pos = self._try_move(obs)
            if new_pos is not None:
                old_pos = obs.position
                obs.position = new_pos
                moves.append((old_pos, new_pos))

                EVENT_BUS.publish(
                    HospitalEvent.DYNAMIC_OBSTACLE_MOVE,
                    data={
                        "obstacle_id": oid,
                        "old_pos": old_pos,
                        "new_pos": new_pos,
                    },
                    source="obstacle_manager",
                )

        return moves

    def _try_move(self, obs: DynamicObstacle) -> Optional[GridPos]:
        """
        Attempt to move an obstacle to an adjacent free cell.

        Prefers the path direction if one is set, else random free neighbor.

        Args:
            obs: The obstacle to move.

        Returns:
            New (row, col) position, or None if no valid move.
        """
        row, col = obs.position
        candidates = []

        for dr, dc in self._directions:
            nr, nc = row + dr, col + dc
            # Check if new cell is free and not occupied by another obstacle
            if self._grid.is_free(nr, nc) and (nr, nc) not in self._get_occupied_set():
                candidates.append((nr, nc))

        if not candidates:
            return None

        new_pos = self._rng.choice(candidates)

        # Update grid
        self._grid.move_dynamic_obstacle((row, col), new_pos)
        return new_pos

    def _get_occupied_set(self) -> Set[GridPos]:
        """Return set of all current obstacle positions."""
        return {obs.position for obs in self._obstacles.values()}

    # ─────────────────────────────────────────────────────────────────────────
    # Queries
    # ─────────────────────────────────────────────────────────────────────────

    def get_all_obstacles(self) -> List[DynamicObstacle]:
        """Return list of all active dynamic obstacles."""
        return list(self._obstacles.values())

    def get_obstacle_positions(self) -> List[GridPos]:
        """Return list of all obstacle (row, col) positions."""
        return [obs.position for obs in self._obstacles.values()]

    def get_obstacle_count(self) -> int:
        """Return number of active obstacles."""
        return len(self._obstacles)

    def is_near_obstacle(
        self,
        row: int,
        col: int,
        radius: float = 2.0,
    ) -> bool:
        """
        Return True if any obstacle is within `radius` cells of (row, col).

        Args:
            row:    Query row.
            col:    Query column.
            radius: Check radius in grid cells.

        Returns:
            True if any obstacle is within radius.
        """
        for obs in self._obstacles.values():
            dr = abs(obs.position[0] - row)
            dc = abs(obs.position[1] - col)
            if (dr ** 2 + dc ** 2) ** 0.5 <= radius:
                return True
        return False

    def spawn_event_obstacle(self, event_type: str) -> Optional[str]:
        """
        Spawn a contextually appropriate obstacle for a hospital event.

        Args:
            event_type: String event type (e.g., "emergency", "patient_crossing").

        Returns:
            obstacle_id if spawned, else None.
        """
        event_map = {
            "emergency":       ObstacleType.STRETCHER,
            "patient_crossing": ObstacleType.PATIENT,
            "cleaning":        ObstacleType.CLEANER,
            "supply":          ObstacleType.CART,
            "staff":           ObstacleType.DOCTOR,
        }
        obs_type = event_map.get(event_type.lower(), ObstacleType.CUSTOM)
        spawned = self.spawn_random_obstacles(1, obs_type)
        return spawned[0] if spawned else None

    def __repr__(self) -> str:
        return f"ObstacleManager(count={len(self._obstacles)})"

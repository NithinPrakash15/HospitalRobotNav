"""
HospitalRobotNav — Hospital Entities (NPC System)
====================================================
Realistic embodied simulation of human and mobile equipment agents in hospital corridors.

Features:
    - Distinct clinical & operational roles:
        DOCTOR, NURSE, SURGEON, PATIENT, VISITOR, WHEELCHAIR, STRETCHER, CLEANING_CART, MEDICINE_TROLLEY
    - Multi-modal states: IDLE, WALKING, ATTENDING_PATIENT, TRANSPORTING, YIELDING
    - Smooth continuous trajectory integration with social force avoidance around robots & static walls.
    - Role-specific motion profiles, corridor navigation habits, and procedural animation state.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]
ContinuousPos = Tuple[float, float]


class HospitalEntityRole(Enum):
    DOCTOR = auto()
    NURSE = auto()
    SURGEON = auto()
    PATIENT = auto()
    VISITOR = auto()
    WHEELCHAIR = auto()
    STRETCHER = auto()
    CLEANING_CART = auto()
    MEDICINE_TROLLEY = auto()


class HospitalEntityState(Enum):
    IDLE = auto()
    WALKING = auto()
    ATTENDING_PATIENT = auto()
    TRANSPORTING = auto()
    YIELDING = auto()


# Role color tokens for high-fidelity UI rendering (RGB)
ROLE_COLORS: Dict[HospitalEntityRole, Tuple[int, int, int]] = {
    HospitalEntityRole.DOCTOR:           (70, 160, 245),   # Medical Cyan/Blue
    HospitalEntityRole.NURSE:            (60, 210, 180),   # Teal Scrubs
    HospitalEntityRole.SURGEON:          (40, 180, 120),   # Surgical Green
    HospitalEntityRole.PATIENT:          (240, 180, 90),   # Amber Gown
    HospitalEntityRole.VISITOR:          (200, 160, 220),  # Soft Purple
    HospitalEntityRole.WHEELCHAIR:       (255, 140, 60),   # Safety Orange
    HospitalEntityRole.STRETCHER:        (235, 75, 75),    # Emergency Crimson
    HospitalEntityRole.CLEANING_CART:    (180, 190, 80),   # Olive / Yellow
    HospitalEntityRole.MEDICINE_TROLLEY: (100, 200, 255),  # Pharmacy Sky Blue
}

# Role speeds in grid cells per second
ROLE_SPEEDS: Dict[HospitalEntityRole, float] = {
    HospitalEntityRole.DOCTOR:           1.4,
    HospitalEntityRole.NURSE:            1.6,
    HospitalEntityRole.SURGEON:          1.5,
    HospitalEntityRole.PATIENT:          0.6,
    HospitalEntityRole.VISITOR:          1.0,
    HospitalEntityRole.WHEELCHAIR:       0.9,
    HospitalEntityRole.STRETCHER:        1.8,
    HospitalEntityRole.CLEANING_CART:    0.7,
    HospitalEntityRole.MEDICINE_TROLLEY: 1.1,
}


@dataclass
class HospitalEntity:
    """Represents an intelligent NPC human or equipment entity in the hospital."""
    entity_id: str
    role: HospitalEntityRole
    pos: List[float]               # [row, col] continuous position
    heading: float = 0.0           # Heading angle in radians
    state: HospitalEntityState = HospitalEntityState.IDLE
    speed: float = 1.0
    path: List[GridPos] = field(default_factory=list)
    waypoint_index: int = 0
    assigned_destination: Optional[GridPos] = None
    social_radius: float = 3.0     # Comfort radius in cells
    idle_timer: float = 0.0
    walk_cycle: float = 0.0
    label: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            self.label = f"{self.role.name.capitalize()} {self.entity_id[-3:]}"
        if self.speed <= 0.0:
            self.speed = ROLE_SPEEDS.get(self.role, 1.0)

    @property
    def grid_pos(self) -> GridPos:
        return (int(round(self.pos[0])), int(round(self.pos[1])))

    def update(
        self,
        dt: float,
        occupancy_grid: Any,
        robot_pos: Optional[GridPos] = None,
        all_rooms: Optional[List[Any]] = None,
    ) -> None:
        """Update entity position, path tracking, and social avoidance."""
        self.walk_cycle += dt * 5.0

        # Check social proximity to robot
        if robot_pos:
            dist_to_robot = math.hypot(self.pos[0] - robot_pos[0], self.pos[1] - robot_pos[1])
            if dist_to_robot < self.social_radius:
                # Yield right of way to robot
                self.state = HospitalEntityState.YIELDING
                return

        # Idle countdown
        if self.state == HospitalEntityState.IDLE:
            self.idle_timer -= dt
            if self.idle_timer <= 0:
                self._pick_new_goal(occupancy_grid, all_rooms)
            return

        # Path following
        if not self.path or self.waypoint_index >= len(self.path):
            self.state = HospitalEntityState.IDLE
            self.idle_timer = random.uniform(2.0, 7.0)
            return

        target_r, target_c = self.path[self.waypoint_index]
        dr = target_r - self.pos[0]
        dc = target_c - self.pos[1]
        dist = math.hypot(dr, dc)

        if dist < 0.3:
            self.waypoint_index += 1
            if self.waypoint_index >= len(self.path):
                self.state = HospitalEntityState.IDLE
                self.idle_timer = random.uniform(3.0, 9.0)
            return

        # Move towards current waypoint
        target_heading = math.atan2(dc, dr)
        # Smooth heading interpolation
        angle_diff = (target_heading - self.heading + math.pi) % (2 * math.pi) - math.pi
        self.heading += angle_diff * min(1.0, dt * 6.0)

        step = min(dist, self.speed * dt)
        new_r = self.pos[0] + (dr / dist) * step
        new_c = self.pos[1] + (dc / dist) * step

        # Check collision with static map
        grid_r, grid_c = int(round(new_r)), int(round(new_c))
        if occupancy_grid.is_free(grid_r, grid_c):
            self.pos[0] = new_r
            self.pos[1] = new_c
            self.state = HospitalEntityState.WALKING
        else:
            # Blocked, recalculate goal
            self.state = HospitalEntityState.IDLE
            self.idle_timer = random.uniform(1.0, 3.0)

    def _pick_new_goal(self, occupancy_grid: Any, all_rooms: Optional[List[Any]]) -> None:
        """Select a plausible room destination and compute a simple path."""
        if all_rooms and random.random() < 0.75:
            room = random.choice(all_rooms)
            dest = room.entry_point
        else:
            # Pick a random free corridor cell
            dest = occupancy_grid.get_random_free_cell()

        if dest and dest != self.grid_pos:
            self.assigned_destination = dest
            # Build simple waypoint sequence
            self.path = self._generate_simple_path(self.grid_pos, dest, occupancy_grid)
            self.waypoint_index = 0
            self.state = HospitalEntityState.WALKING if self.path else HospitalEntityState.IDLE

    def _generate_simple_path(self, start: GridPos, goal: GridPos, grid: Any) -> List[GridPos]:
        """Simple Manhattan / L-shaped corridor path generator for NPC entities."""
        path = [start]
        curr_r, curr_c = start
        target_r, target_c = goal

        # Move row first
        step_r = 1 if target_r > curr_r else -1
        while curr_r != target_r:
            next_r = curr_r + step_r
            if grid.is_free(next_r, curr_c):
                curr_r = next_r
                path.append((curr_r, curr_c))
            else:
                break

        # Move col
        step_c = 1 if target_c > curr_c else -1
        while curr_c != target_c:
            next_c = curr_c + step_c
            if grid.is_free(curr_r, next_c):
                curr_c = next_c
                path.append((curr_r, curr_c))
            else:
                break

        return path if len(path) > 1 else []


class HospitalEntityManager:
    """Manager for dynamic hospital NPC entities."""

    def __init__(self, occupancy_grid: Any, semantic_map: Optional[Any] = None) -> None:
        self.occupancy_grid = occupancy_grid
        self.semantic_map = semantic_map
        self.entities: Dict[str, HospitalEntity] = {}
        log.info("HospitalEntityManager initialized.")

    def spawn_default_population(self, count: int = 12) -> None:
        """Populate hospital with doctors, nurses, stretchers, wheelchairs, and patients."""
        roles_distribution = [
            HospitalEntityRole.DOCTOR,
            HospitalEntityRole.NURSE,
            HospitalEntityRole.NURSE,
            HospitalEntityRole.SURGEON,
            HospitalEntityRole.PATIENT,
            HospitalEntityRole.PATIENT,
            HospitalEntityRole.WHEELCHAIR,
            HospitalEntityRole.STRETCHER,
            HospitalEntityRole.CLEANING_CART,
            HospitalEntityRole.MEDICINE_TROLLEY,
            HospitalEntityRole.VISITOR,
            HospitalEntityRole.VISITOR,
        ]

        for i in range(min(count, len(roles_distribution))):
            role = roles_distribution[i]
            prefix = role.name[:3]
            entity_id = f"{prefix}-{i+1:02d}"
            cell = self.occupancy_grid.get_random_free_cell()
            if cell:
                entity = HospitalEntity(
                    entity_id=entity_id,
                    role=role,
                    pos=[float(cell[0]), float(cell[1])],
                    speed=ROLE_SPEEDS.get(role, 1.0),
                )
                self.entities[entity_id] = entity

        log.info("Spawned %d hospital entities in simulation.", len(self.entities))

    def update(self, dt: float, robot_pos: Optional[GridPos] = None) -> None:
        """Tick all entities and sync positions."""
        rooms = None
        if self.semantic_map:
            from maps.hospital.room_definitions import ROOM_DATABASE
            rooms = ROOM_DATABASE

        for entity in self.entities.values():
            entity.update(dt, self.occupancy_grid, robot_pos, rooms)

    def get_all_positions(self) -> List[GridPos]:
        """Return integer grid positions of all entities."""
        return [e.grid_pos for e in self.entities.values()]

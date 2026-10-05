"""
Spatial Relations Engine for AROGYA Multi-Agent Hospital Fleet
==============================================================
Extracts real geometric spatial relationships grounded in the hospital digital twin:
- inside:        PERSON_07 -> located_in -> ICU-01
- blocking:      CART_04   -> blocking   -> CORRIDOR_NORTH
- near:          MITRA     -> near       -> GARUDA
- approaching:   GARUDA    -> approaching-> ICU-03
- ahead/behind:  WHEELCHAIR-> ahead_of   -> AROGYA
- assigned_to:   TASK_MED  -> assigned_to-> AROGYA_DELIVERY
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple


class RelationType(Enum):
    LOCATED_IN    = "located_in"
    BLOCKING      = "blocking"
    NEAR          = "near"
    AHEAD_OF      = "ahead_of"
    BEHIND        = "behind"
    LEFT_OF       = "left_of"
    RIGHT_OF      = "right_of"
    APPROACHING   = "approaching"
    MOVING_TOWARD = "moving_toward"
    ASSIGNED_TO   = "assigned_to"


@dataclass
class SpatialRelation:
    """Verifiable semantic relationship between two entities."""
    subject: str
    relation: RelationType
    object_entity: str
    confidence: float = 1.0
    details: str = ""

    def __str__(self) -> str:
        return f"{self.subject} -> {self.relation.value} -> {self.object_entity}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject": self.subject,
            "relation": self.relation.value,
            "object": self.object_entity,
            "confidence": self.confidence,
            "details": self.details,
            "repr": str(self),
        }


# Hospital Corridor Segments matching 88m x 76m digital twin
HOSPITAL_CORRIDORS = {
    "CORRIDOR_CENTRAL": {"x_min": -44.0, "x_max": 44.0, "y_min": 0.5, "y_max": 3.5},
    "CORRIDOR_NORTH":   {"x_min": -44.0, "x_max": 44.0, "y_min": 18.5, "y_max": 21.5},
    "CORRIDOR_SOUTH":   {"x_min": -44.0, "x_max": 44.0, "y_min": -17.5, "y_max": -14.5},
    "CORRIDOR_WEST":    {"x_min": -21.5, "x_max": -18.5, "y_min": -38.0, "y_max": 38.0},
    "CORRIDOR_MID":     {"x_min": -1.5,  "x_max": 1.5,   "y_min": -38.0, "y_max": 38.0},
    "CORRIDOR_EAST":    {"x_min": 18.5,  "x_max": 21.5,  "y_min": -38.0, "y_max": 38.0},
}


class SpatialRelationsEngine:
    """Derives spatial relations based on actual entity positions and hospital geometry."""

    def __init__(self, room_bounds: Optional[Dict[str, Any]] = None) -> None:
        self.room_bounds = room_bounds or {}
        if not self.room_bounds:
            self._init_default_room_bounds()

    def _init_default_room_bounds(self) -> None:
        """Pre-computed department room boundaries matching hospital_env.py exactly."""
        self.room_bounds = {
            # Patient rooms first (more specific than general department wards)
            "PAT-101": (30.5,  36.5, -37.2, -19.8),
            "PAT-102": (37.5,  43.0, -37.2, -19.8),
            "PAT-103": (-26.0, -21.5, -16.2, -8.5),
            "PAT-104": (-26.0, -21.5,  -7.5,  0.2),
            "PAT-105": (-18.5, -12.5, -16.2, -8.5),
            "PAT-106": (-18.5, -12.5,  -7.5,  0.2),
            "OT-01":   (-43.0, -35.0, 21.8, 37.2),
            "OT-02":   (-34.0, -26.0, 21.8, 37.2),
            "BLB-01":  (-25.0, -17.0, 21.8, 37.2),
            "LAB-01":  (-16.0, -2.0,  21.8, 37.2),
            "RAD-01":  (-1.0,  13.0,  21.8, 37.2),
            "PHM-01":  (8.0,   20.0,  21.8, 37.2),
            "STR-01":  (21.0,  28.5,  21.8, 37.2),
            "CHG-01":  (30.5,  42.0,  21.8, 37.2),
            "EMR-01":  (-43.0, -27.0, -37.2, -21.8),
            "ICU-01":  (-26.0, -10.0, -37.2, -21.8),
            "GW-01":   (-9.0,   5.0,  -37.2, -21.8),
            "PED-01":  (6.0,   18.0,  -37.2, -21.8),
            "OPD-01":  (19.0,  29.0,  -37.2, -21.8),
            "OPD-02":  (30.0,  43.0,  -37.2, -21.8),
            "RCT-01":  (-10.0, 10.0,  -2.0,  10.0),
            "WAT-01":  (-10.0, 10.0, -10.0, -3.0),
        }

    def determine_room(self, x: float, y: float) -> Optional[str]:
        """Find which clinical room an entity is inside."""
        for r_id, (x1, x2, y1, y2) in self.room_bounds.items():
            if min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2):
                return r_id
        return None

    def determine_corridor(self, x: float, y: float) -> Optional[str]:
        """Find which corridor an entity is located in."""
        for c_id, bounds in HOSPITAL_CORRIDORS.items():
            if bounds["x_min"] <= x <= bounds["x_max"] and bounds["y_min"] <= y <= bounds["y_max"]:
                return c_id
        return None

    def extract_relations(
        self,
        observer_robot: Any,
        detected_objects: List[Any],
        fleet_robots: Optional[Dict[str, Any]] = None,
    ) -> List[SpatialRelation]:
        """
        Derive verified spatial relations from observer robot and perceived entities.
        """
        relations: List[SpatialRelation] = []

        rx = float(getattr(observer_robot, "x", getattr(observer_robot, "position", (0, 0))[0]))
        ry = float(getattr(observer_robot, "y", getattr(observer_robot, "position", (0, 0))[1]))
        r_yaw = float(getattr(observer_robot, "yaw", 0.0))
        r_name = str(getattr(observer_robot, "name", "Arogya"))

        # 1. Observer room/corridor relation
        r_room = self.determine_room(rx, ry)
        if r_room:
            relations.append(SpatialRelation(r_name, RelationType.LOCATED_IN, r_room))
        else:
            r_corr = self.determine_corridor(rx, ry)
            if r_corr:
                relations.append(SpatialRelation(r_name, RelationType.LOCATED_IN, r_corr))

        # 2. Check destination approach
        dest_name = getattr(observer_robot, "destination_name", None)
        if dest_name and dest_name in self.room_bounds:
            relations.append(SpatialRelation(r_name, RelationType.APPROACHING, dest_name))

        # 3. Analyze detected objects
        for obj in detected_objects:
            pos = getattr(obj, "position", (0, 0, 0))
            ox, oy = pos[0], pos[1]
            o_id = getattr(obj, "object_id", "OBJECT")
            dist = getattr(obj, "distance", math.hypot(ox - rx, oy - ry))

            # A. Inside Room / Corridor check
            room = self.determine_room(ox, oy)
            if room:
                relations.append(SpatialRelation(o_id, RelationType.LOCATED_IN, room))
            else:
                corridor = self.determine_corridor(ox, oy)
                if corridor:
                    relations.append(SpatialRelation(o_id, RelationType.LOCATED_IN, corridor))
                    # If obstacle is inside corridor and within 2.0m of robot's path, it's blocking
                    if dist < 2.0:
                        relations.append(SpatialRelation(o_id, RelationType.BLOCKING, corridor, details=f"Dist {dist:.1f}m"))

            # B. Relative heading (ahead / behind / left / right)
            dx = ox - rx
            dy = oy - ry
            cos_y = math.cos(-r_yaw)
            sin_y = math.sin(-r_yaw)
            x_rel = dx * cos_y - dy * sin_y  # Forward
            y_rel = dx * sin_y + dy * cos_y  # Left

            if dist < 4.0:
                if x_rel > 0.4 and abs(y_rel) < 1.0:
                    relations.append(SpatialRelation(o_id, RelationType.AHEAD_OF, r_name, details=f"{dist:.1f}m ahead"))
                elif x_rel < -0.4 and abs(y_rel) < 1.0:
                    relations.append(SpatialRelation(o_id, RelationType.BEHIND, r_name))
                elif y_rel > 0.4:
                    relations.append(SpatialRelation(o_id, RelationType.LEFT_OF, r_name))
                elif y_rel < -0.4:
                    relations.append(SpatialRelation(o_id, RelationType.RIGHT_OF, r_name))

            # C. Proximity (Near)
            if dist < 2.5:
                relations.append(SpatialRelation(r_name, RelationType.NEAR, o_id, details=f"{dist:.1f}m"))

        return relations

    def evaluate_all(
        self,
        robot_name: str = "Arogya_Delivery",
        robot_x: float = 0.0,
        robot_y: float = 0.0,
        robot_yaw: float = 0.0,
        detected_objects: Optional[List[Any]] = None,
        planned_waypoints: Optional[List[Tuple[float, float]]] = None,
    ) -> List[SpatialRelation]:
        """Convenience evaluation method matching test and high-level coordinator interface."""
        class _RobotProxy:
            def __init__(self, name: str, x: float, y: float, yaw: float):
                self.name = name
                self.x = x
                self.y = y
                self.yaw = yaw
                self.destination_name = None

        robot = _RobotProxy(robot_name, robot_x, robot_y, robot_yaw)
        rels = self.extract_relations(robot, detected_objects or [])

        # Check if any detected obstacle intersects planned waypoints
        if planned_waypoints and detected_objects:
            for obj in detected_objects:
                pos = getattr(obj, "position", (0, 0, 0))
                ox, oy = pos[0], pos[1]
                o_id = getattr(obj, "object_id", "OBJECT")
                for wx, wy in planned_waypoints:
                    if math.hypot(ox - wx, oy - wy) < 1.0:
                        rels.append(
                            SpatialRelation(
                                subject=robot_name,
                                relation=RelationType.BLOCKING,
                                object_entity=o_id,
                                details=f"Obstacle {o_id} intersects planned waypoint at ({wx:.1f}, {wy:.1f})",
                            )
                        )
                        break

        return rels


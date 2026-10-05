"""
Shared World Model for AROGYA Embodied Multi-Agent Hospital Fleet
==================================================================
Centralized, verifiable knowledge state shared across all AMRs and Coordinator:
- Robot Fleet States: Positions, battery levels, active missions, priority, navigation status
- Detected Objects: Perceived by ANY robot in the fleet (persons, carts, stretchers, peer AMRs)
- Spatial Knowledge: Grounded relations (located_in, blocking, near, approaching)
- Dynamic Hazard Map: Corridors and doorways flagged as blocked by peer robot observations
- Clinical Ward State: Active patient alerts, doctor availability, medication schedules
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from perception.perception_layer import DetectedObject
from perception.spatial_relations import SpatialRelation
from utilities.logger import get_logger

log = get_logger(__name__)


@dataclass
class DynamicHazard:
    """Active hazard or obstruction reported by a fleet robot."""
    hazard_id: str
    source_robot: str
    position: Tuple[float, float]
    zone_name: str
    description: str
    timestamp: float = field(default_factory=time.time)
    clearance_radius: float = 1.20
    is_active: bool = True

    @property
    def obstacle_pos(self) -> Tuple[float, float]:
        return self.position


@dataclass
class WorldEvent:
    """Chronological event record for research replay and timeline display."""
    timestamp_str: str
    source_robot: str
    event_type: str        # PERCEPTION, REASONING, ACTION, HAZARD, COORDINATION
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.timestamp_str}] [{self.source_robot}] {self.summary}"


class SharedWorldModel:
    """
    Authoritative shared world model for the multi-agent hospital fleet.
    Updated continuously by perception layers, robot kinematics, and coordinator decisions.
    """

    def __init__(self) -> None:
        # Fleet robots telemetry (Arogya, Mitra, Garuda, Sahayak)
        self.robots: Dict[str, Dict[str, Any]] = {}

        # Distributed perception: entity_id -> DetectedObject
        self.global_entities: Dict[str, DetectedObject] = {}

        # Spatial relations derived from geometry
        self.active_spatial_relations: List[SpatialRelation] = []

        # Blocked zones and corridor hazards: hazard_id -> DynamicHazard
        self.active_hazards: Dict[str, DynamicHazard] = {}

        # Decaying corridor congestion penalties: cell_id -> dict
        self.congestion_penalties: Dict[str, Dict[str, Any]] = {}

        # Clinical hospital state
        self.clinical_state: Dict[str, Any] = {
            "active_patients": {},
            "emergency_code_blue": False,
            "emergency_room": None,
            "pending_medications": [],
        }

        # Chronological event log (last 100 events)
        self.event_stream: List[WorldEvent] = []

        self._init_default_fleet_slots()

    def _init_default_fleet_slots(self) -> None:
        fleet_names = ["Arogya_Delivery", "Mitra_Reception", "Garuda_Emergency", "Sahayak_Support"]
        for name in fleet_names:
            self.robots[name] = {
                "name": name,
                "position": (0.0, 0.0, 0.0),
                "yaw_deg": 0.0,
                "state": "IDLE",
                "battery": 100.0,
                "is_charging": False,
                "priority": 3,
                "destination": "None",
                "current_task": "Standing by on station",
                "is_blocked": False,
                "is_replanned": False,
                "updated_at": time.time(),
            }

    def record_event(self, source_robot: str, event_type: str, summary: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Append a structured, verifiable event to the real-time timeline."""
        t_str = time.strftime("%H:%M:%S")
        evt = WorldEvent(
            timestamp_str=t_str,
            source_robot=source_robot,
            event_type=event_type,
            summary=summary,
            details=details or {},
        )
        self.event_stream.append(evt)
        if len(self.event_stream) > 100:
            self.event_stream.pop(0)

    def update_robot_telemetry(self, robot_name: str, telemetry: Dict[str, Any]) -> None:
        """Update robot's live kinematics, battery, and navigation state in the world model."""
        if robot_name not in self.robots:
            self.robots[robot_name] = {"name": robot_name}
        self.robots[robot_name].update(telemetry)
        self.robots[robot_name]["updated_at"] = time.time()

    def merge_perceived_entities(self, source_robot: str, entities: List[DetectedObject]) -> None:
        """Merge newly detected objects from a robot's perception layer into the global model."""
        for obj in entities:
            self.global_entities[obj.object_id] = obj

        # Clean out stale entities (> 10s old)
        now = time.time()
        stale_keys = [k for k, v in self.global_entities.items() if now - v.timestamp > 10.0]
        for k in stale_keys:
            del self.global_entities[k]

    def update_spatial_relations(self, relations: List[SpatialRelation]) -> None:
        """Update global list of active spatial relations."""
        self.active_spatial_relations = relations

    def add_congestion_penalty(
        self,
        x: float,
        y: float,
        zone_name: str = "",
        base_penalty: float = 12.0,
        half_life_s: float = 30.0,
        radius: float = 2.5,
    ) -> str:
        """
        Record a localized dynamic congestion penalty with exponential temporal decay.
        """
        cell_id = f"CONG_{int(round(x))}_{int(round(y))}_{zone_name}"
        self.congestion_penalties[cell_id] = {
            "center": (float(x), float(y)),
            "zone_name": zone_name,
            "base_penalty": float(base_penalty),
            "created_at": time.time(),
            "half_life_s": float(half_life_s),
            "radius": float(radius),
        }
        return cell_id

    def get_congestion_penalty_at(self, x: float, y: float) -> float:
        """
        Calculate total dynamic congestion penalty at coordinates (x, y)
        taking into account temporal decay and distance falloff.
        Automatically prunes expired penalties (< 0.05).
        """
        now = time.time()
        total_penalty = 0.0
        expired_keys = []

        for cid, data in list(self.congestion_penalties.items()):
            dt = max(0.0, now - data["created_at"])
            decay_factor = 0.5 ** (dt / data["half_life_s"])
            current_base = data["base_penalty"] * decay_factor

            if current_base < 0.05:
                expired_keys.append(cid)
                continue

            cx, cy = data["center"]
            dist_sq = (x - cx) ** 2 + (y - cy) ** 2
            r_sq = data["radius"] ** 2

            if dist_sq <= r_sq:
                spatial_weight = 1.0 - (dist_sq / r_sq)
                total_penalty += current_base * spatial_weight

        for k in expired_keys:
            self.congestion_penalties.pop(k, None)

        return float(total_penalty)

    def get_dynamic_obstacles_with_congestion(
        self,
        min_penalty_threshold: float = 2.0,
    ) -> List[Tuple[float, float]]:
        """
        Return coordinates of active hazards and significant congestion hotspots
        for dynamic path planning and A* inflation.
        """
        now = time.time()
        coords = []
        # 1. Active physical hazards
        for h in self.active_hazards.values():
            if h.is_active:
                coords.append((float(h.position[0]), float(h.position[1])))

        # 2. Significant congestion centers
        for data in self.congestion_penalties.values():
            dt = max(0.0, now - data["created_at"])
            decay_factor = 0.5 ** (dt / data["half_life_s"])
            current_val = data["base_penalty"] * decay_factor
            if current_val >= min_penalty_threshold:
                coords.append((float(data["center"][0]), float(data["center"][1])))

        return coords

    def report_hazard(
        self,
        source_robot: str,
        position: Tuple[float, float],
        zone_name: str,
        description: str,
        clearance_radius: float = 1.20,
    ) -> DynamicHazard:
        """
        Record a dynamic obstruction reported by an observing robot.
        Immediately available for all peer robots to check against their active routes.
        """
        h_id = f"HAZARD_{zone_name}_{int(time.time() * 10) % 10000}"
        hazard = DynamicHazard(
            hazard_id=h_id,
            source_robot=source_robot,
            position=position,
            zone_name=zone_name,
            description=description,
            clearance_radius=clearance_radius,
            is_active=True,
        )
        self.active_hazards[h_id] = hazard

        # Automatically register a decaying congestion penalty around the hazard
        self.add_congestion_penalty(
            x=position[0],
            y=position[1],
            zone_name=zone_name,
            base_penalty=15.0,
            half_life_s=45.0,
            radius=clearance_radius + 1.0,
        )

        self.record_event(
            source_robot=source_robot,
            event_type="HAZARD",
            summary=f"Reported {description} at ({position[0]:.1f}, {position[1]:.1f}) in {zone_name}",
            details={"hazard_id": h_id, "pos": position, "zone": zone_name},
        )
        return hazard

    register_hazard = report_hazard

    def clear_hazard(self, hazard_id: str) -> None:
        """Deactivate a resolved hazard."""
        if hazard_id in self.active_hazards:
            self.active_hazards[hazard_id].is_active = False
            del self.active_hazards[hazard_id]

    def is_route_conflicted(self, waypoints: List[Any], margin: float = 0.80) -> Tuple[bool, Optional[DynamicHazard]]:
        """
        Check if any active dynamic hazard intersects a robot's planned waypoints.
        Enables proactive detour replanning for peer robots!
        """
        if not waypoints or not self.active_hazards:
            return False, None

        for h in self.active_hazards.values():
            if not h.is_active:
                continue
            hx, hy = h.position
            threshold = h.clearance_radius + margin
            for wp in waypoints:
                wx = float(wp[0]) if hasattr(wp, "__getitem__") else float(getattr(wp, "x", 0))
                wy = float(wp[1]) if hasattr(wp, "__getitem__") else float(getattr(wp, "y", 0))
                if (wx - hx) ** 2 + (wy - hy) ** 2 < threshold ** 2:
                    return True, h
        return False, None

    def get_fleet_summary(self) -> Dict[str, Any]:
        """Return full structured summary for the Perception-Reasoning Twin UI."""
        return {
            "robots": self.robots,
            "active_hazards_count": len([h for h in self.active_hazards.values() if h.is_active]),
            "global_entities_count": len(self.global_entities),
            "spatial_relations_count": len(self.active_spatial_relations),
            "emergency_code_blue": self.clinical_state.get("emergency_code_blue", False),
            "recent_events": [str(e) for e in self.event_stream[-6:]],
        }


# Singleton shared world model instance
SHARED_WORLD_MODEL = SharedWorldModel()

"""
Distributed Multi-Robot Perception & Observation Sharing Bridge
===============================================================
Implements real backend observation propagation between fleet AMRs:
1. Robot A perceives an obstacle blocking a corridor or doorway.
2. Observation is published to the Shared World Model.
3. Peer robots (B, C, D) evaluate whether their active route intersects the blockage.
4. If an active route is affected, the peer robot proactively replans a detour
   BEFORE reaching the bottleneck!
5. Real structured events:
   - PERCEPTION_EVENT
   - OBSERVATION_SHARED
   - PATH_CONFLICT
   - REPLAN_REQUEST
   - REPLAN_COMPLETE
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Tuple

from utilities.event_bus import EVENT_BUS, HospitalEvent
from utilities.logger import get_logger
from world_model.shared_world_model import SHARED_WORLD_MODEL, DynamicHazard

log = get_logger(__name__)


class ObservationSharingBridge:
    """
    Coordinates distributed perception sharing and proactive multi-robot replanning.
    """

    def __init__(self, fleet_robots: Optional[Dict[str, Any]] = None) -> None:
        self.fleet_robots = fleet_robots or {}
        self._last_shared_hazard_times: Dict[str, float] = {}

    def set_fleet_robots(self, fleet_robots: Dict[str, Any]) -> None:
        self.fleet_robots = fleet_robots

    def share_observation(
        self,
        source_robot_name: str,
        obstacle_position: Tuple[float, float],
        zone_name: str,
        description: str = "Dynamic Obstacle",
    ) -> Optional[DynamicHazard]:
        """
        Robot A publishes an observation to the shared world model and alerts peer robots.
        """
        now = time.time()
        # Cooldown per zone (avoid flooding identical hazard events)
        last_t = self._last_shared_hazard_times.get(zone_name, 0.0)
        if now - last_t < 3.0:
            return None
        self._last_shared_hazard_times[zone_name] = now

        # 1. Register in Shared World Model
        hazard = SHARED_WORLD_MODEL.report_hazard(
            source_robot=source_robot_name,
            position=obstacle_position,
            zone_name=zone_name,
            description=description,
        )

        # 2. Publish to EventBus
        EVENT_BUS.publish(
            HospitalEvent.OBSTACLE_DETECTED,
            data={
                "source_robot": source_robot_name,
                "position": obstacle_position,
                "zone": zone_name,
                "hazard_id": hazard.hazard_id,
            },
            source=source_robot_name,
        )

        SHARED_WORLD_MODEL.record_event(
            source_robot=source_robot_name,
            event_type="OBSERVATION_SHARED",
            summary=f"Published hazard '{description}' at ({obstacle_position[0]:.1f}, {obstacle_position[1]:.1f}) in {zone_name}",
        )

        # 3. Check all peer robots in fleet for route conflicts
        for p_name, peer in self.fleet_robots.items():
            if p_name == source_robot_name:
                continue

            # Only evaluate robots with active routes
            if not getattr(peer, "mission_active", False) or not getattr(peer, "waypoints", []):
                continue

            # Check if peer's upcoming waypoints intersect the reported hazard
            is_conflicted, h = SHARED_WORLD_MODEL.is_route_conflicted(peer.waypoints)
            if is_conflicted and h is not None:
                SHARED_WORLD_MODEL.record_event(
                    source_robot=p_name,
                    event_type="PATH_CONFLICT",
                    summary=f"Active trajectory conflicts with {h.hazard_id} reported by {source_robot_name}",
                    details={"peer": p_name, "hazard": h.hazard_id},
                )

                # Trigger proactive detour replanning on peer robot!
                SHARED_WORLD_MODEL.record_event(
                    source_robot=p_name,
                    event_type="REPLAN_REQUEST",
                    summary=f"Triggering proactive detour around {h.zone_name}",
                )

                if hasattr(peer, "_replan_detour"):
                    replan_success = peer._replan_detour(
                        dynamic_obstacles=[h.position],
                        reason=f"Proactive peer replan: avoided hazard in {h.zone_name} reported by {source_robot_name}",
                    )
                    if replan_success:
                        SHARED_WORLD_MODEL.record_event(
                            source_robot=p_name,
                            event_type="REPLAN_COMPLETE",
                            summary=f"Successfully generated collision-free detour ({len(peer.waypoints)} waypoints)",
                        )
                    else:
                        SHARED_WORLD_MODEL.record_event(
                            source_robot=p_name,
                            event_type="REPLAN_WAIT",
                            summary=f"No alternative corridor found; holding station cautiously",
                        )

        return hazard

    def check_mutual_robot_conflict(self, robot_a: Any, robot_b: Any) -> Optional[Tuple[str, str]]:
        """
        Evaluate if two robots approach in a narrow corridor and decide right-of-way.
        Returns: (yielding_robot_name, passing_robot_name) or None.
        """
        ax, ay = float(robot_a.x), float(robot_a.y)
        bx, by = float(robot_b.x), float(robot_b.y)
        dist = math.hypot(ax - bx, ay - by)

        # Conflict threshold in corridor
        if dist > 3.8:
            return None

        # Right-of-way determination by Priority Level (Level 1 Emergency > Level 2 > Level 3)
        prio_a = getattr(robot_a, "priority_level", 3)
        prio_b = getattr(robot_b, "priority_level", 3)

        if prio_a < prio_b:  # Lower number = higher priority
            return robot_b.name, robot_a.name
        elif prio_b < prio_a:
            return robot_a.name, robot_b.name
        else:
            # Equal priority: robot closer to its destination has right-of-way
            rem_a = robot_a.get_remaining_distance() if hasattr(robot_a, "get_remaining_distance") else 10.0
            rem_b = robot_b.get_remaining_distance() if hasattr(robot_b, "get_remaining_distance") else 10.0
            if rem_a <= rem_b:
                return robot_b.name, robot_a.name
            else:
                return robot_a.name, robot_b.name


# Singleton observation sharing bridge
OBSERVATION_SHARING = ObservationSharingBridge()

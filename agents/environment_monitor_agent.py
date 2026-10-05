"""
HospitalRobotNav — Environment Monitor Agent
=============================================
Safety agent continuously assessing corridor traffic congestion, doorway clearances,
spills/hazards, fire door states, and elevator availability across hospital zones.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from utilities.logger import get_logger
from .agent_base import AgentBid, AgentState, HospitalAgent
from . import agent_config as cfg

log = get_logger(__name__)

GridPos = Tuple[int, int]


class EnvironmentMonitorAgent(HospitalAgent):
    """Hospital facility safety and traffic congestion monitoring agent."""

    def __init__(self, home_position: GridPos = (50, 50)) -> None:
        super().__init__(
            agent_type="env_monitor",
            capabilities=frozenset({
                cfg.CAPABILITY_MONITOR,
                cfg.CAPABILITY_EMERGENCY,
                cfg.CAPABILITY_NAVIGATE,
            }),
            home_position=home_position,
        )
        self.monitored_zones_count: int = 5
        self.hazards_detected_count: int = 0

    def evaluate_mission(
        self,
        mission_type: str,
        destination: Optional[GridPos],
        priority: int,
    ) -> Optional[AgentBid]:
        if not self.is_available:
            return None

        type_weights = {
            "CORRIDOR_MONITORING": 0.98,
            "HAZARD_INSPECTION": 0.95,
            "FIRE_ALARM_CHECK": 0.92,
            "FACILITY_PATROL": 0.90,
        }
        if mission_type not in type_weights:
            return None

        base_score = type_weights[mission_type]
        dist = self.distance_to(destination) if destination else 0.0
        dist_factor = max(0.2, 1.0 - (dist / 120.0))
        final_score = base_score * 0.5 + dist_factor * 0.3 + (self.battery_pct / 100.0) * 0.2

        return AgentBid(
            agent_id=self.agent_id,
            score=round(final_score, 3),
            estimated_eta=round(dist * 0.7 + 3.0, 1),
            battery_pct=self.battery_pct,
            distance=round(dist, 1),
            rationale=f"EnvironmentMonitorAgent ready (zones={self.monitored_zones_count}, dist={dist:.1f})",
        )

    def accept_mission(self, mission_id: str, mission_data: Dict[str, Any]) -> bool:
        if not self.is_available:
            return False
        self._current_mission_id = mission_id
        self.set_state(AgentState.EXECUTING)
        log.info("EnvironmentMonitorAgent %s accepted mission %s", self.agent_id, mission_id)
        return True

    def abort_mission(self, reason: str = "") -> None:
        log.warning("EnvironmentMonitorAgent %s aborted mission %s: %s", self.agent_id, self._current_mission_id, reason)
        self._current_mission_id = None
        self.set_state(AgentState.IDLE)

    def execute_step(self, dt: float) -> None:
        if self.state == AgentState.EXECUTING:
            self._battery_pct = max(5.0, self._battery_pct - dt * 0.02)

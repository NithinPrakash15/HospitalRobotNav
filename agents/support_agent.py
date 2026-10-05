"""
HospitalRobotNav — Support Agent
=================================
Specialized hospital agent for equipment transport, supply restock,
sanitization/UV-C procedures, and auxiliary task execution (Sahayak).

Capabilities:
    - Sterile equipment transport and cart restock
    - Supply replenishment across wards and departments
    - UV-C sanitization sweeps
    - Heavy payload logistics and backup assistance

Architecture Note (ROS2):
    ros2 run hospital_robot support_agent --ros-args -p agent_id:=SUP-001
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from utilities.logger import get_logger
from .agent_base import AgentBid, AgentState, HospitalAgent
from . import agent_config as cfg

log = get_logger(__name__)

GridPos = Tuple[int, int]

_SUPPORT_MISSIONS = frozenset({
    "EQUIPMENT_TRANSPORT",
    "RESTOCK_CART",
    "SUPPLY_DELIVERY",
    "SANITIZATION_SWEEP",
    "UVC_DISINFECTION",
    "SUPPORT_ASSIST",
    "MEDICINE_DELIVERY",  # Secondary capability
})


class SupportAgent(HospitalAgent):
    """Agent specialised in equipment transport, supply restock, and auxiliary hospital assistance.

    Wraps a Support AMR (Sahayak) entity and evaluates missions based on
    proximity to target room, battery level, and equipment restock capacity.
    """

    def __init__(
        self,
        home_position: GridPos = (40, 33),
        storage_position: GridPos = (40, 30),
    ) -> None:
        super().__init__(
            agent_type="support",
            capabilities=frozenset({
                cfg.CAPABILITY_TRANSPORT,
                cfg.CAPABILITY_FETCH,
                cfg.CAPABILITY_MONITOR,
                cfg.CAPABILITY_HEALTH,
            }),
            home_position=home_position,
        )
        self._storage_pos = storage_position
        self._equipped_tool: Optional[str] = "Restock Platform & UV-C Emitter"

    # ── Contract-Net ─────────────────────────────────────────────────────────

    def evaluate_mission(
        self,
        mission_type: str,
        destination: Optional[GridPos],
        priority: int,
    ) -> Optional[AgentBid]:
        """Bid on equipment transport, restock, and auxiliary support missions."""
        if not self.is_available:
            return None

        if mission_type not in _SUPPORT_MISSIONS:
            return None

        if self._battery_pct < 15.0:
            log.debug("SupportAgent %s declining — battery too low (%.0f%%)",
                      self.agent_id, self._battery_pct)
            return None

        if destination:
            dist = self.grid_distance(destination)
        else:
            dist = self.grid_distance(self._storage_pos)

        score = self.compute_bid_score(dist, priority)

        # Specialty boost for equipment/restock/sanitization
        if mission_type in ("EQUIPMENT_TRANSPORT", "RESTOCK_CART", "SANITIZATION_SWEEP"):
            score = min(1.0, score + 0.15)
        elif mission_type == "MEDICINE_DELIVERY":
            # Backup delivery: lower score than primary delivery agent
            score *= 0.75

        eta = dist / max(cfg.DEFAULT_AGENT_SPEED, 0.1)

        bid = AgentBid(
            agent_id=self.agent_id,
            score=score,
            estimated_eta=eta,
            battery_pct=self._battery_pct,
            distance=dist,
            rationale=f"Support agent at dist={dist:.0f}, bat={self._battery_pct:.0f}%",
        )
        log.info("[SupportAgent] Bid on %s: score=%.3f, dist=%.1f cells",
                 mission_type, score, dist)
        return bid

    def accept_mission(self, mission_id: str, mission_data: Dict[str, Any]) -> bool:
        """Accept an equipment transport or support mission and begin execution."""
        if not self.is_available:
            log.warning("SupportAgent %s cannot accept — state=%s",
                        self.agent_id, self._state.name)
            return False

        self._current_mission_id = mission_id
        dest = mission_data.get("destination_pos")
        self.set_state(AgentState.EXECUTING)
        log.info("SupportAgent %s accepted mission %s — destination %s",
                 self.agent_id, mission_id, dest)
        return True

    def abort_mission(self, reason: str = "") -> None:
        """Abort current support mission and return to idle."""
        log.warning("SupportAgent %s aborting mission %s: %s",
                    self.agent_id, self._current_mission_id, reason)
        self._current_mission_id = None
        self.set_state(AgentState.IDLE)

    def execute_task(self, task: Dict[str, Any]) -> None:
        """Execute assigned equipment transport or support mission."""
        self.set_state(AgentState.EXECUTING)
        dest = task.get("destination")
        t_type = task.get("type", "SUPPORT_ASSIST")
        log.info("[SupportAgent %s] Executing %s to %s", self.agent_id, t_type, dest)

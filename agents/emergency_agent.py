"""
HospitalRobotNav — Emergency Agent
=====================================
High-priority agent that responds to emergency events.

Capabilities:
    - Immediate response to Code Blue / fire / urgent nurse calls
    - Can preempt other agents' missions
    - Always maintains minimum battery reserve for emergencies

Design Decision:
    The emergency agent bids with maximum score on priority-1 missions
    and declines all non-emergency tasks. This guarantees that the
    coordinator always has a dedicated responder.

Architecture Note (ROS2):
    ros2 run hospital_robot emergency_agent
    Subscribes to /hospital/emergency with QoS RELIABLE + TRANSIENT_LOCAL
    to never miss an alert.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from utilities.event_bus import EVENT_BUS, HospitalEvent
from utilities.logger import get_logger
from .agent_base import AgentBid, AgentState, HospitalAgent
from . import agent_config as cfg

log = get_logger(__name__)

GridPos = Tuple[int, int]

_EMERGENCY_MISSIONS = frozenset({
    "EMERGENCY_RESPONSE",
    "CALL_NURSE",
})

# Minimum battery to remain on standby
_MIN_STANDBY_BATTERY = 25.0


class EmergencyAgent(HospitalAgent):
    """Agent that handles emergency events with highest priority.

    Always ready — only discharges below the standby reserve when
    actively responding to an emergency. Can preempt other agents
    by sending an ABORT via the EventBus.
    """

    def __init__(
        self,
        home_position: GridPos = (50, 50),
    ) -> None:
        super().__init__(
            agent_type="emergency",
            capabilities=frozenset({
                cfg.CAPABILITY_EMERGENCY,
            }),
            home_position=home_position,
        )
        self._emergency_active: bool = False
        self._emergency_location: Optional[GridPos] = None

        # Subscribe to emergency alerts for immediate response
        EVENT_BUS.subscribe(HospitalEvent.EMERGENCY_ALERT, self._on_emergency_alert)

    # ── Emergency listener ───────────────────────────────────────────────────

    def _on_emergency_alert(self, payload) -> None:
        """React to hospital emergency broadcasts."""
        room = payload.data.get("room", "unknown")
        code = payload.data.get("code", "RED")
        log.warning("Emergency agent %s received alert — room=%s, code=%s",
                     self.agent_id, room, code)
        self._emergency_active = True

    # ── Contract-Net ─────────────────────────────────────────────────────────

    def evaluate_mission(
        self,
        mission_type: str,
        destination: Optional[GridPos],
        priority: int,
    ) -> Optional[AgentBid]:
        """Only bid on emergency / nurse-call missions."""
        if mission_type not in _EMERGENCY_MISSIONS:
            return None  # We only handle emergencies

        if self._state == AgentState.EXECUTING and not self._emergency_active:
            return None  # Already responding to another emergency

        if self._battery_pct < _MIN_STANDBY_BATTERY * 0.5:
            return None  # Critical battery — cannot respond

        dist = self.grid_distance(destination) if destination else 0.0

        # Emergency agents always bid high
        score = 0.95 if priority <= cfg.PRIORITY_HIGH else 0.80
        eta = dist / max(cfg.DEFAULT_AGENT_SPEED * 1.5, 0.1)  # Rush speed

        return AgentBid(
            agent_id=self.agent_id,
            score=score,
            estimated_eta=eta,
            battery_pct=self._battery_pct,
            distance=dist,
            rationale=f"Emergency agent — priority response, dist={dist:.0f}",
        )

    def accept_mission(self, mission_id: str, mission_data: Dict[str, Any]) -> bool:
        """Accept and immediately start emergency response."""
        self._current_mission_id = mission_id
        self._emergency_location = mission_data.get("destination_pos")
        self._emergency_active = True
        self.set_state(AgentState.EXECUTING)

        log.info("EMERGENCY Agent %s responding to mission %s",
                 self.agent_id, mission_id)
        return True

    def abort_mission(self, reason: str = "") -> None:
        """Abort emergency response (only if another agent takes over)."""
        log.warning("Emergency agent %s aborting mission %s: %s",
                    self.agent_id, self._current_mission_id, reason)
        self._emergency_active = False
        self._emergency_location = None
        self._current_mission_id = None
        self.set_state(AgentState.IDLE)

    # ── Emergency lifecycle ──────────────────────────────────────────────────

    def resolve_emergency(self) -> None:
        """Mark the current emergency as resolved."""
        self._emergency_active = False
        self._emergency_location = None
        log.info("Emergency agent %s — emergency resolved", self.agent_id)

    @property
    def is_on_standby(self) -> bool:
        """True if agent is idle and has sufficient battery for response."""
        return (self._state == AgentState.IDLE
                and self._battery_pct >= _MIN_STANDBY_BATTERY)

    def __repr__(self) -> str:
        active = ", EMERGENCY" if self._emergency_active else ""
        return (f"EmergencyAgent({self.agent_id}, {self._state.name}"
                f"{active})")

"""
HospitalRobotNav — Reception Agent
=====================================
Specialised hospital agent for patient guidance and visitor escort tasks.

Capabilities:
    - Guide patients from reception to their assigned room / department
    - Escort visitors through the hospital
    - Provide wayfinding information at reception desk

The agent is typically stationed at the hospital reception area and
roams when escorting a person, returning to reception when done.

Architecture Note (ROS2):
    ros2 run hospital_robot reception_agent --ros-args -p home:=reception
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from utilities.logger import get_logger
from .agent_base import AgentBid, AgentState, HospitalAgent
from . import agent_config as cfg

log = get_logger(__name__)

GridPos = Tuple[int, int]

_RECEPTION_MISSIONS = frozenset({
    "GUIDE_PATIENT",
    "ESCORT_VISITOR",
})


class ReceptionAgent(HospitalAgent):
    """Agent specialised in patient guidance and visitor escort.

    Stationed near the reception desk by default and accompanies
    people to their destination, then returns to reception.
    """

    def __init__(
        self,
        home_position: GridPos = (2, 50),
        reception_position: GridPos = (2, 50),
    ) -> None:
        super().__init__(
            agent_type="reception",
            capabilities=frozenset({
                cfg.CAPABILITY_GUIDE,
                cfg.CAPABILITY_ESCORT,
            }),
            home_position=home_position,
        )
        self._reception_pos = reception_position
        self._escorting_person: Optional[str] = None
        self._escort_destination: Optional[GridPos] = None

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def is_escorting(self) -> bool:
        return self._escorting_person is not None

    # ── Contract-Net ─────────────────────────────────────────────────────────

    def evaluate_mission(
        self,
        mission_type: str,
        destination: Optional[GridPos],
        priority: int,
    ) -> Optional[AgentBid]:
        """Bid on guide / escort missions."""
        if not self.is_available:
            return None

        if mission_type not in _RECEPTION_MISSIONS:
            return None

        if self._battery_pct < 10.0:
            return None

        dist = self.grid_distance(destination) if destination else 0.0
        score = self.compute_bid_score(dist, priority)

        # Bonus: if near reception (our home), we respond faster
        dist_to_reception = self.grid_distance(self._reception_pos)
        if dist_to_reception < 10:
            score = min(1.0, score + 0.1)

        eta = dist / max(cfg.DEFAULT_AGENT_SPEED, 0.1)

        return AgentBid(
            agent_id=self.agent_id,
            score=score,
            estimated_eta=eta,
            battery_pct=self._battery_pct,
            distance=dist,
            rationale=f"Reception agent at dist={dist:.0f}",
        )

    def accept_mission(self, mission_id: str, mission_data: Dict[str, Any]) -> bool:
        if not self.is_available:
            return False

        self._current_mission_id = mission_id
        self._escorting_person = mission_data.get("person_name", "Patient")
        dest = mission_data.get("destination_pos")
        if dest:
            self._escort_destination = tuple(dest)  # type: ignore[arg-type]
        self.set_state(AgentState.EXECUTING)

        log.info("Agent %s accepted escort — guiding '%s'",
                 self.agent_id, self._escorting_person)
        return True

    def abort_mission(self, reason: str = "") -> None:
        log.warning("Agent %s aborting escort of '%s': %s",
                    self.agent_id, self._escorting_person, reason)
        self._escorting_person = None
        self._escort_destination = None
        self._current_mission_id = None
        self.set_state(AgentState.IDLE)

    # ── Escort lifecycle ─────────────────────────────────────────────────────

    def begin_escort(self, person_name: str, destination: GridPos) -> None:
        self._escorting_person = person_name
        self._escort_destination = destination
        log.info("Agent %s escorting '%s' to %s",
                 self.agent_id, person_name, destination)

    def end_escort(self) -> Optional[str]:
        person = self._escorting_person
        self._escorting_person = None
        self._escort_destination = None
        if person:
            log.info("Agent %s completed escort of '%s'", self.agent_id, person)
        return person

    def __repr__(self) -> str:
        escort = f", escorting='{self._escorting_person}'" if self.is_escorting else ""
        return (f"ReceptionAgent({self.agent_id}, {self._state.name}"
                f"{escort})")

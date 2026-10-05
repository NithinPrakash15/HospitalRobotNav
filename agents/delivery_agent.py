"""
HospitalRobotNav — Delivery Agent
====================================
Specialised hospital agent for medicine, report, and sample delivery tasks.

Capabilities:
    - Medicine collection from pharmacy → delivery to patient room
    - Lab report transport (lab → doctor office)
    - Lab sample transport (ward → laboratory)
    - Wheelchair fetching

The agent bids aggressively on delivery-type missions and factors in
proximity to the pharmacy and current payload capacity.

Architecture Note (ROS2):
    ros2 run hospital_robot delivery_agent --ros-args -p agent_id:=DEL-001
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

from utilities.logger import get_logger
from .agent_base import AgentBid, AgentState, HospitalAgent
from . import agent_config as cfg

log = get_logger(__name__)

GridPos = Tuple[int, int]

# Delivery-related mission types this agent can handle
_DELIVERY_MISSIONS = frozenset({
    "MEDICINE_DELIVERY",
    "DELIVER_REPORT",
    "TRANSPORT_SAMPLE",
    "FETCH_WHEELCHAIR",
})


class DeliveryAgent(HospitalAgent):
    """Agent specialised in pick-up and delivery operations.

    Wraps a ``Robot`` entity and evaluates delivery missions based on
    proximity to the pharmacy / source location, battery level, and
    whether the agent is already carrying a payload.
    """

    def __init__(
        self,
        home_position: GridPos = (5, 5),
        pharmacy_position: GridPos = (50, 10),
    ) -> None:
        super().__init__(
            agent_type="delivery",
            capabilities=frozenset({
                cfg.CAPABILITY_DELIVER,
                cfg.CAPABILITY_TRANSPORT,
                cfg.CAPABILITY_FETCH,
            }),
            home_position=home_position,
        )
        self._pharmacy_pos = pharmacy_position
        self._carrying_item: Optional[str] = None
        self._carrying_destination: Optional[GridPos] = None

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def is_carrying(self) -> bool:
        return self._carrying_item is not None

    # ── Contract-Net ─────────────────────────────────────────────────────────

    def evaluate_mission(
        self,
        mission_type: str,
        destination: Optional[GridPos],
        priority: int,
    ) -> Optional[AgentBid]:
        """Bid on delivery-type missions only."""
        if not self.is_available:
            return None

        if mission_type not in _DELIVERY_MISSIONS:
            return None  # Not our specialty

        if self._battery_pct < 15.0:
            log.debug("Agent %s declining — battery too low (%.0f%%)",
                      self.agent_id, self._battery_pct)
            return None

        # Compute distance to destination (or to pharmacy first)
        if destination:
            dist = self.grid_distance(destination)
        else:
            dist = self.grid_distance(self._pharmacy_pos)

        score = self.compute_bid_score(dist, priority)

        # Bonus: if already carrying an item for the same dest, bid higher
        if self.is_carrying and destination == self._carrying_destination:
            score = min(1.0, score + 0.15)

        # Penalty: if currently carrying something else
        if self.is_carrying and destination != self._carrying_destination:
            score *= 0.6

        eta = dist / max(cfg.DEFAULT_AGENT_SPEED, 0.1)

        bid = AgentBid(
            agent_id=self.agent_id,
            score=score,
            estimated_eta=eta,
            battery_pct=self._battery_pct,
            distance=dist,
            rationale=f"Delivery agent at dist={dist:.0f}, bat={self._battery_pct:.0f}%",
        )
        log.debug("Agent %s bid %.3f for %s", self.agent_id, score, mission_type)
        return bid

    def accept_mission(self, mission_id: str, mission_data: Dict[str, Any]) -> bool:
        """Accept a delivery mission and start execution."""
        if not self.is_available:
            log.warning("Agent %s cannot accept — state=%s",
                        self.agent_id, self._state.name)
            return False

        self._current_mission_id = mission_id
        self._carrying_item = mission_data.get("item")
        dest = mission_data.get("destination_pos")
        if dest:
            self._carrying_destination = tuple(dest)  # type: ignore[arg-type]
        self.set_state(AgentState.EXECUTING)

        log.info("Agent %s accepted mission %s — delivering '%s'",
                 self.agent_id, mission_id,
                 self._carrying_item or "item")
        return True

    def abort_mission(self, reason: str = "") -> None:
        """Abort current delivery and return to idle."""
        log.warning("Agent %s aborting mission %s: %s",
                    self.agent_id, self._current_mission_id, reason)
        self._carrying_item = None
        self._carrying_destination = None
        self._current_mission_id = None
        self.set_state(AgentState.IDLE)

    # ── Delivery lifecycle ───────────────────────────────────────────────────

    def pickup_item(self, item_name: str, destination: GridPos) -> None:
        """Record that the agent picked up an item."""
        self._carrying_item = item_name
        self._carrying_destination = destination
        log.info("Agent %s picked up '%s'", self.agent_id, item_name)

    def deliver_item(self) -> Optional[str]:
        """Deliver the carried item. Returns the item name or None."""
        item = self._carrying_item
        self._carrying_item = None
        self._carrying_destination = None
        if item:
            log.info("Agent %s delivered '%s'", self.agent_id, item)
        return item

    def __repr__(self) -> str:
        carrying = f", carrying='{self._carrying_item}'" if self.is_carrying else ""
        return (f"DeliveryAgent({self.agent_id}, {self._state.name}"
                f"{carrying})")

"""
HospitalRobotNav — Task Allocation Agent
=========================================
Contract-Net Protocol auctioneer and multi-robot task scheduler. Manages priority
queues, preemption rules, load balancing, and SLA deadlines.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from utilities.logger import get_logger
from .agent_base import AgentBid, AgentState, HospitalAgent
from . import agent_config as cfg

log = get_logger(__name__)

GridPos = Tuple[int, int]


class TaskAllocationAgent(HospitalAgent):
    """Dynamic task allocation and fleet scheduling agent."""

    def __init__(self, home_position: GridPos = (50, 50)) -> None:
        super().__init__(
            agent_type="task_allocator",
            capabilities=frozenset({
                cfg.CAPABILITY_ALLOCATE,
                cfg.CAPABILITY_PLAN,
                cfg.CAPABILITY_EMERGENCY,
            }),
            home_position=home_position,
        )
        self.total_auctions_conducted: int = 0
        self.total_preemptions_triggered: int = 0

    def evaluate_mission(
        self,
        mission_type: str,
        destination: Optional[GridPos],
        priority: int,
    ) -> Optional[AgentBid]:
        if not self.is_available:
            return None

        if mission_type not in ("TASK_ALLOCATION", "FLEET_AUCTION", "LOAD_BALANCE"):
            return None

        base_score = 0.90 if priority <= 2 else 0.70
        return AgentBid(
            agent_id=self.agent_id,
            score=round(base_score, 3),
            estimated_eta=1.0,
            battery_pct=self.battery_pct,
            distance=0.0,
            rationale=f"TaskAllocationAgent ready (Pri={priority})",
        )

    def accept_mission(self, mission_id: str, mission_data: Dict[str, Any]) -> bool:
        if not self.is_available:
            return False
        self._current_mission_id = mission_id
        self.set_state(AgentState.EXECUTING)
        log.info("TaskAllocationAgent %s accepted mission %s", self.agent_id, mission_id)
        return True

    def abort_mission(self, reason: str = "") -> None:
        log.warning("TaskAllocationAgent %s aborted mission %s: %s", self.agent_id, self._current_mission_id, reason)
        self._current_mission_id = None
        self.set_state(AgentState.IDLE)

    def execute_step(self, dt: float) -> None:
        if self.state == AgentState.EXECUTING:
            self._battery_pct = max(5.0, self._battery_pct - dt * 0.02)

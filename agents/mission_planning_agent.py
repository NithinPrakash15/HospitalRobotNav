"""
HospitalRobotNav — Mission Planning Agent
==========================================
HTN (Hierarchical Task Network) decomposition agent breaking down natural language
goals into sequential atomic TaskSteps (NAVIGATE, COLLECT, DELIVER, INTERACT, ESCORT).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from utilities.logger import get_logger
from .agent_base import AgentBid, AgentState, HospitalAgent
from . import agent_config as cfg

log = get_logger(__name__)

GridPos = Tuple[int, int]


class MissionPlanningAgent(HospitalAgent):
    """Hierarchical mission decomposition and task sequence planning agent."""

    def __init__(self, home_position: GridPos = (50, 50)) -> None:
        super().__init__(
            agent_type="mission_planner",
            capabilities=frozenset({
                cfg.CAPABILITY_PLAN,
                cfg.CAPABILITY_ALLOCATE,
                cfg.CAPABILITY_DELIVER,
            }),
            home_position=home_position,
        )
        self.plans_synthesized_count: int = 0

    def evaluate_mission(
        self,
        mission_type: str,
        destination: Optional[GridPos],
        priority: int,
    ) -> Optional[AgentBid]:
        if not self.is_available:
            return None

        if mission_type not in ("MISSION_PLANNING", "TASK_DECOMPOSITION", "PLAN_SYNTHESIS"):
            return None

        base_score = 0.95 if priority <= 2 else 0.85
        return AgentBid(
            agent_id=self.agent_id,
            score=round(base_score, 3),
            estimated_eta=1.5,
            battery_pct=self.battery_pct,
            distance=0.0,
            rationale=f"MissionPlanningAgent ready (synthesized={self.plans_synthesized_count})",
        )

    def accept_mission(self, mission_id: str, mission_data: Dict[str, Any]) -> bool:
        if not self.is_available:
            return False
        self._current_mission_id = mission_id
        self.plans_synthesized_count += 1
        self.set_state(AgentState.EXECUTING)
        log.info("MissionPlanningAgent %s accepted mission %s", self.agent_id, mission_id)
        return True

    def abort_mission(self, reason: str = "") -> None:
        log.warning("MissionPlanningAgent %s aborted mission %s: %s", self.agent_id, self._current_mission_id, reason)
        self._current_mission_id = None
        self.set_state(AgentState.IDLE)

    def execute_step(self, dt: float) -> None:
        if self.state == AgentState.EXECUTING:
            self._battery_pct = max(5.0, self._battery_pct - dt * 0.02)

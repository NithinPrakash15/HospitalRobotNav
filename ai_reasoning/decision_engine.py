"""
Explainable Reasoning & Decision Engine for AROGYA Hospital Fleet
==================================================================
Translates cognitive events into verifiable 5-tuple reasoning records:
- SITUATION:   What is happening?
- CONSTRAINTS: What limits the decision?
- OPTIONS:     What actions are possible?
- DECISION:    What did the system select?
- ACTION:      What does the robot actually do?

Integrated with:
- Contract-Net task allocation in HospitalAgentManager
- Dynamic obstacle avoidance in HospitalAMR
- Proactive detour replanning from shared observations
- Emergency Code Blue preemption
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from world_model.shared_world_model import SHARED_WORLD_MODEL
from utilities.logger import get_logger

log = get_logger(__name__)


@dataclass
class ExplainableDecision:
    """Verifiable 5-tuple cognitive reasoning decision record."""
    robot_name: str
    mission_description: str
    situation: str
    constraints: str
    options: List[str]
    decision: str
    action: str
    timestamp: float = field(default_factory=time.time)

    def format_summary(self) -> str:
        return f"[{self.robot_name}] Decision: {self.decision} -> {self.action}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "robot": self.robot_name,
            "mission": self.mission_description,
            "situation": self.situation,
            "constraints": self.constraints,
            "options": self.options,
            "decision": self.decision,
            "action": self.action,
            "timestamp_str": time.strftime("%H:%M:%S", time.localtime(self.timestamp)),
        }


class DecisionEngine:
    """
    Reasoning engine generating explainable decisions for fleet AMRs.
    Maintains active decision state for the Perception-Reasoning Twin UI.
    """

    def __init__(self) -> None:
        self.active_decisions: Dict[str, ExplainableDecision] = {}
        self.decision_history: List[ExplainableDecision] = []
        self._init_default_decisions()

    def _init_default_decisions(self) -> None:
        for r_name in ["Arogya_Delivery", "Mitra_Reception", "Garuda_Emergency", "Sahayak_Support"]:
            self.active_decisions[r_name] = ExplainableDecision(
                robot_name=r_name,
                mission_description="Standby on base station",
                situation="Robot idle at designated station; all subsystems nominal",
                constraints="Standing by for clinical voice or coordinator task dispatch",
                options=["STANDBY", "CHARGE", "ROUTINE_INSPECTION"],
                decision="STANDBY",
                action="Awaiting clinical assignment with sensors active",
            )

    def reason_obstacle_avoidance(
        self,
        robot_name: str,
        mission_desc: str,
        obstacle_dist: float,
        is_blocked: bool,
        replan_succeeded: bool,
        corridor_width: float = 2.0,
    ) -> ExplainableDecision:
        """Formulate explainable reasoning when an obstacle enters safety envelope."""
        if replan_succeeded:
            sit = f"Dynamic obstacle detected {obstacle_dist:.2f}m ahead in active path"
            con = f"Corridor width is {corridor_width:.1f}m; safety margin must be >= 0.38m; goal must be preserved"
            opts = ["STOP", "WAIT", "SLOW_DOWN", "REPLAN_DETOUR"]
            dec = "REPLAN_DETOUR"
            act = "Compute dynamic collision-free detour waypoints around obstruction"
        elif is_blocked:
            sit = f"Corridor bottleneck completely obstructed ({obstacle_dist:.2f}m ahead)"
            con = "No alternate collision-free corridor bypass currently available without wall clipping"
            opts = ["STOP_AND_WAIT", "BACKTRACK", "EMERGENCY_HALT"]
            dec = "STOP_AND_WAIT"
            act = "Yield station and wait for dynamic obstacle to clear passage"
        else:
            sit = f"Obstacle detected in caution zone ({obstacle_dist:.2f}m)"
            con = "Obstacle velocity is dynamic; path trajectory currently clear"
            opts = ["MAINTAIN_SPEED", "CAUTIOUS_SLOWDOWN", "REPLAN"]
            dec = "CAUTIOUS_SLOWDOWN"
            act = f"Reduce speed factor smoothly to ensure safe stopping distance"

        decision = ExplainableDecision(
            robot_name=robot_name,
            mission_description=mission_desc,
            situation=sit,
            constraints=con,
            options=opts,
            decision=dec,
            action=act,
        )
        self.active_decisions[robot_name] = decision
        self.decision_history.append(decision)
        if len(self.decision_history) > 60:
            self.decision_history.pop(0)

        SHARED_WORLD_MODEL.record_event(
            source_robot=robot_name,
            event_type="REASONING",
            summary=f"Decision: {dec} -> {act[:35]}",
            details=decision.to_dict(),
        )
        return decision

    def reason_task_allocation(
        self,
        mission_type: str = "MEDICINE_DELIVERY",
        destination: str = "PAT-101",
        candidates: Optional[Dict[str, Any]] = None,
        winner_robot_name: str = "Arogya_Delivery",
        winning_reason: str = "Optimal bid",
        **kwargs: Any,
    ) -> ExplainableDecision:
        """Formulate explainable decision for Contract-Net task award."""
        if "mission_desc" in kwargs:
            mission_type = kwargs["mission_desc"]
        if "winning_agent_id" in kwargs:
            winner_robot_name = kwargs["winning_agent_id"]
        if "all_bids" in kwargs:
            bids = kwargs["all_bids"]
            if isinstance(bids, list):
                candidates = {b.get("agent_id", f"A_{i}"): b for i, b in enumerate(bids)}
            elif isinstance(bids, dict):
                candidates = bids
        if "winning_bid_score" in kwargs:
            winning_score = kwargs["winning_bid_score"]
            winning_reason = f"optimal bid score: {winning_score:.2f}"

        candidates = candidates or {}
        candidate_summary = ", ".join([
            f"{k} (Score: {v.get('score', 0.0):.2f})" if "score" in v else
            f"{k} (Batt: {v.get('battery', 100):.0f}%, Dist: {v.get('dist', 0):.1f}m)"
            for k, v in candidates.items()
        ]) if candidates else "Multiple candidates evaluated"

        sit = f"New clinical task '{mission_type}' directed to {destination}. Selected {winner_robot_name} with {winning_reason}."
        con = f"Candidate capabilities, battery levels, proximity, and priority constraints ({candidate_summary})"
        opts = list(candidates.keys()) if candidates else ["ALLOCATE", "DEFER", "REJECT"]
        dec = "AWARD_MISSION"
        act = f"Dispatch {winner_robot_name} to execute {mission_type}: {winning_reason}"

        decision = ExplainableDecision(
            robot_name=winner_robot_name,
            mission_description=f"{mission_type} -> {destination}",
            situation=sit,
            constraints=con,
            options=opts,
            decision=dec,
            action=act,
        )
        self.active_decisions[winner_robot_name] = decision
        self.decision_history.append(decision)

        SHARED_WORLD_MODEL.record_event(
            source_robot="COORDINATOR",
            event_type="COORDINATION",
            summary=f"Task '{mission_type}' awarded to {winner_robot_name} ({winning_reason})",
            details=decision.to_dict(),
        )
        return decision

    def reason_emergency_preemption(
        self,
        emergency_robot_name: str = "Garuda_Emergency",
        preempted_robot_name: str = "Arogya_Delivery",
        emergency_dept: str = "ICU-01",
        preempted_task_desc: str = "Routine transport",
        **kwargs: Any,
    ) -> ExplainableDecision:
        """Formulate explainable decision for Code Blue Emergency Preemption."""
        p_id = kwargs.get("emergency_patient_id", "")
        if "emergency_room" in kwargs:
            emergency_dept = kwargs["emergency_room"]
        if "preempted_robot" in kwargs:
            preempted_robot_name = kwargs["preempted_robot"]
        if "dispatched_robot" in kwargs:
            emergency_robot_name = kwargs["dispatched_robot"]

        sit_patient = f" for patient {p_id}" if p_id else ""
        sit = f"CRITICAL CODE BLUE EMERGENCY declared{sit_patient} in {emergency_dept}!"
        con = "Medical priority hierarchy dictates Level 1 Emergency preempts routine deliveries"
        opts = ["DISPATCH_IDLE_AMR", "PREEMPT_ACTIVE_MISSION", "DEFER_EMERGENCY"]
        dec = "PREEMPT_AND_DISPATCH"
        act = f"Preempt {preempted_robot_name}'s routine mission '{preempted_task_desc}'; dispatch Emergency AMR {emergency_robot_name} with priority override"

        decision = ExplainableDecision(
            robot_name=emergency_robot_name,
            mission_description=f"CODE BLUE in {emergency_dept}",
            situation=sit,
            constraints=con,
            options=opts,
            decision=dec,
            action=act,
        )
        self.active_decisions[emergency_robot_name] = decision
        self.decision_history.append(decision)

        SHARED_WORLD_MODEL.record_event(
            source_robot="COORDINATOR",
            event_type="EMERGENCY",
            summary=f"CODE BLUE PREEMPTION: Dispatched {emergency_robot_name} to {emergency_dept}",
            details=decision.to_dict(),
        )
        return decision

    def get_decision_for_robot(self, robot_name: str) -> Optional[ExplainableDecision]:
        """Retrieve active explainable decision for the selected robot."""
        # Exact match or prefix match (e.g. "Arogya" matches "Arogya_Delivery")
        for k, d in self.active_decisions.items():
            if k.lower().startswith(robot_name.lower().split("_")[0]):
                return d
        return None


# Singleton decision engine instance
DECISION_ENGINE = DecisionEngine()

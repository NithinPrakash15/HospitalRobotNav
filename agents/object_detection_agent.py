"""
HospitalRobotNav — Object Detection Agent
==========================================
Specialized neural perception agent simulating YOLO-based medicine vial detection,
stretcher/wheelchair recognition, obstacle categorization, and bounding box localization.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from utilities.logger import get_logger
from .agent_base import AgentBid, AgentState, HospitalAgent
from . import agent_config as cfg

log = get_logger(__name__)

GridPos = Tuple[int, int]


class ObjectDetectionAgent(HospitalAgent):
    """Neural object detection and medical supply visual inspection agent."""

    def __init__(self, home_position: GridPos = (50, 50)) -> None:
        super().__init__(
            agent_type="object_detector",
            capabilities=frozenset({
                cfg.CAPABILITY_DETECT,
                cfg.CAPABILITY_VISION,
                cfg.CAPABILITY_MEDICINE,
            }),
            home_position=home_position,
        )
        self.confidence_threshold: float = 0.75
        self.total_detections: int = 0

    def evaluate_mission(
        self,
        mission_type: str,
        destination: Optional[GridPos],
        priority: int,
    ) -> Optional[AgentBid]:
        if not self.is_available:
            return None

        type_weights = {
            "OBJECT_DETECTION": 0.96,
            "MEDICINE_VERIFICATION": 0.94,
            "OBSTACLE_CLASSIFICATION": 0.90,
            "INVENTORY_SCAN": 0.88,
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
            estimated_eta=round(dist * 0.7 + 2.0, 1),
            battery_pct=self.battery_pct,
            distance=round(dist, 1),
            rationale=f"ObjectDetectionAgent ready (conf={self.confidence_threshold:.2f}, dist={dist:.1f})",
        )

    def accept_mission(self, mission_id: str, mission_data: Dict[str, Any]) -> bool:
        if not self.is_available:
            return False
        self._current_mission_id = mission_id
        self.set_state(AgentState.EXECUTING)
        log.info("ObjectDetectionAgent %s accepted mission %s", self.agent_id, mission_id)
        return True

    def abort_mission(self, reason: str = "") -> None:
        log.warning("ObjectDetectionAgent %s aborted mission %s: %s", self.agent_id, self._current_mission_id, reason)
        self._current_mission_id = None
        self.set_state(AgentState.IDLE)

    def execute_step(self, dt: float) -> None:
        if self.state == AgentState.EXECUTING:
            self._battery_pct = max(5.0, self._battery_pct - dt * 0.04)

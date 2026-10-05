"""
HospitalRobotNav — Vision & Perception Agent
=============================================
Specialized computer vision agent simulating visual landmark identification,
RGB-D depth sensing, QR/barcode validation, and visual SLAM spatial anchoring.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from utilities.logger import get_logger
from .agent_base import AgentBid, AgentState, HospitalAgent
from . import agent_config as cfg

log = get_logger(__name__)

GridPos = Tuple[int, int]


class VisionAgent(HospitalAgent):
    """Computer vision, scene understanding, and visual grounding agent."""

    def __init__(self, home_position: GridPos = (50, 50)) -> None:
        super().__init__(
            agent_type="vision",
            capabilities=frozenset({
                cfg.CAPABILITY_VISION,
                cfg.CAPABILITY_DETECT,
                cfg.CAPABILITY_MONITOR,
            }),
            home_position=home_position,
        )
        self.camera_fps: float = 30.0
        self.fov_degrees: float = 90.0
        self.objects_detected_count: int = 0

    def evaluate_mission(
        self,
        mission_type: str,
        destination: Optional[GridPos],
        priority: int,
    ) -> Optional[AgentBid]:
        if not self.is_available:
            return None

        type_weights = {
            "SCENE_INSPECTION": 0.95,
            "PATIENT_STATUS_CHECK": 0.88,
            "OBJECT_DETECTION": 0.92,
            "CORRIDOR_MONITORING": 0.85,
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
            rationale=f"VisionAgent ready (FOV {self.fov_degrees}°, dist={dist:.1f})",
        )

    def accept_mission(self, mission_id: str, mission_data: Dict[str, Any]) -> bool:
        if not self.is_available:
            return False
        self._current_mission_id = mission_id
        self.set_state(AgentState.EXECUTING)
        log.info("VisionAgent %s accepted mission %s", self.agent_id, mission_id)
        return True

    def abort_mission(self, reason: str = "") -> None:
        log.warning("VisionAgent %s aborted mission %s: %s", self.agent_id, self._current_mission_id, reason)
        self._current_mission_id = None
        self.set_state(AgentState.IDLE)

    def execute_step(self, dt: float) -> None:
        if self.state == AgentState.EXECUTING:
            self._battery_pct = max(5.0, self._battery_pct - dt * 0.04)

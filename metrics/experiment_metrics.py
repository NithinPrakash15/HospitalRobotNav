"""
Research Experiment Mode & Digital Twin Metrics Recorder for AROGYA
===================================================================
Tracks, records, and replays research-grade metrics across multi-agent clinical missions:
- Path efficiency and trajectory optimization ratio
- Replanning counts and dynamic obstacle avoidance incidents
- Human-aware yielding durations and social clearance metrics
- Battery consumption and energy efficiency profiles
- Verifiable explainable decision counts
- State-space replay buffer (LIVE, PAUSE, REPLAY modes) for digital twin visualization
- Export to structured JSON / CSV for IEEE RA-L / ICRA / IROS publication tables
"""

from __future__ import annotations

import csv
import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from utilities.logger import get_logger

log = get_logger(__name__)


class ExperimentMode(Enum):
    LIVE    = "LIVE"
    PAUSE   = "PAUSE"
    REPLAY  = "REPLAY"


@dataclass
class MissionMetricsRecord:
    """Individual mission performance and research metrics record."""
    mission_id: str
    robot_name: str
    mission_type: str
    priority: int
    start_time: float = field(default_factory=time.time)
    completion_time: Optional[float] = None
    duration_seconds: float = 0.0
    planned_path_length_m: float = 0.0
    actual_travel_dist_m: float = 0.0
    path_efficiency_ratio: float = 1.0
    replan_count: int = 0
    obstacles_encountered: int = 0
    human_encounters: int = 0
    time_spent_yielding_s: float = 0.0
    battery_consumed_pct: float = 0.0
    initial_battery_pct: float = 100.0
    final_battery_pct: float = 100.0
    avg_speed_mps: float = 0.0
    max_speed_mps: float = 0.0
    success: bool = False
    status_label: str = "IN_PROGRESS"  # COMPLETED, PREEMPTED, FAILED
    explainable_decisions_count: int = 0

    def finalize(self, success: bool, status_label: str = "COMPLETED") -> None:
        """Finalize metrics upon mission completion."""
        now = time.time()
        self.completion_time = now
        self.duration_seconds = max(0.001, now - self.start_time)
        self.success = success
        self.status_label = status_label
        self.battery_consumed_pct = max(0.0, self.initial_battery_pct - self.final_battery_pct)

        if self.actual_travel_dist_m > 0 and self.planned_path_length_m > 0:
            self.path_efficiency_ratio = round(self.planned_path_length_m / self.actual_travel_dist_m, 3)
        else:
            self.path_efficiency_ratio = 1.0


@dataclass
class ReplaySnapshot:
    """Chronological digital twin state snapshot."""
    timestamp: float
    frame_idx: int
    robot_states: Dict[str, Dict[str, Any]]
    obstacle_positions: List[Tuple[float, float]]
    active_events: List[str]


class ExperimentMetricsRecorder:
    """
    Central recorder for research experiments, benchmarking, and digital twin replay.
    Supports LIVE capture, PAUSE inspection, and chronologically-indexed REPLAY.
    """

    def __init__(self) -> None:
        self.mode: ExperimentMode = ExperimentMode.LIVE
        self.records: Dict[str, MissionMetricsRecord] = {}
        self.active_missions: Dict[str, str] = {}  # robot_name -> mission_id
        self._last_robot_pos: Dict[str, Tuple[float, float]] = {}
        self._speed_samples: Dict[str, List[float]] = {}
        self.replay_buffer: List[ReplaySnapshot] = []
        self._max_replay_frames: int = 3600  # ~2 minutes at 30Hz

    def set_mode(self, mode: ExperimentMode | str) -> None:
        """Switch operational mode between LIVE, PAUSE, and REPLAY."""
        if isinstance(mode, str):
            mode = ExperimentMode(mode.upper())
        self.mode = mode
        log.info("[ExperimentMetrics] Operational mode set to: %s", self.mode.value)

    def start_mission(
        self,
        mission_id: str,
        robot_name: str,
        mission_type: str = "MEDICINE_DELIVERY",
        priority: int = 3,
        planned_path_length_m: float = 0.0,
        initial_battery_pct: float = 100.0,
    ) -> MissionMetricsRecord:
        """Register the start of an autonomous clinical mission."""
        record = MissionMetricsRecord(
            mission_id=mission_id,
            robot_name=robot_name,
            mission_type=mission_type,
            priority=priority,
            planned_path_length_m=planned_path_length_m,
            initial_battery_pct=initial_battery_pct,
            final_battery_pct=initial_battery_pct,
        )
        self.records[mission_id] = record
        self.active_missions[robot_name] = mission_id
        self._speed_samples[robot_name] = []
        log.info(
            "[ExperimentMetrics] Mission started: %s (Robot: %s, Type: %s, Planned Dist: %.2fm)",
            mission_id, robot_name, mission_type, planned_path_length_m
        )
        return record

    def record_step(
        self,
        robot_name: str,
        x: float,
        y: float,
        speed: float,
        battery: float,
        is_yielding: bool = False,
        dt: float = 0.016,
    ) -> None:
        """Record a discrete motion step for an AMR."""
        if self.mode != ExperimentMode.LIVE:
            return

        m_id = self.active_missions.get(robot_name)
        if not m_id or m_id not in self.records:
            return

        rec = self.records[m_id]
        rec.final_battery_pct = battery

        # Odometer distance tracking
        if robot_name in self._last_robot_pos:
            px, py = self._last_robot_pos[robot_name]
            delta_d = float(math.hypot(x - px, y - py))
            # Filter out gross teleports / level resets (> 25.0m per step)
            if delta_d < 25.0:
                rec.actual_travel_dist_m += delta_d

        self._last_robot_pos[robot_name] = (x, y)

        # Speed metrics
        if speed > rec.max_speed_mps:
            rec.max_speed_mps = round(speed, 3)

        if robot_name in self._speed_samples:
            self._speed_samples[robot_name].append(speed)
            rec.avg_speed_mps = round(sum(self._speed_samples[robot_name]) / len(self._speed_samples[robot_name]), 3)

        # Yielding duration
        if is_yielding:
            rec.time_spent_yielding_s += dt

    def record_replan(self, robot_name: str) -> None:
        """Increment dynamic replanning encounter for the active mission."""
        m_id = self.active_missions.get(robot_name)
        if m_id and m_id in self.records:
            self.records[m_id].replan_count += 1

    def record_obstacle(self, robot_name: str, is_human: bool = False) -> None:
        """Increment obstacle or human encounter counter."""
        m_id = self.active_missions.get(robot_name)
        if m_id and m_id in self.records:
            self.records[m_id].obstacles_encountered += 1
            if is_human:
                self.records[m_id].human_encounters += 1

    def record_explainable_decision(self, robot_name: str) -> None:
        """Increment cognitive decisions formulated for the active mission."""
        m_id = self.active_missions.get(robot_name)
        if m_id and m_id in self.records:
            self.records[m_id].explainable_decisions_count += 1

    def complete_mission(self, mission_id: str, success: bool = True, status: str = "COMPLETED") -> Optional[MissionMetricsRecord]:
        """Finalize and archive a completed mission."""
        if mission_id not in self.records:
            return None

        rec = self.records[mission_id]
        rec.finalize(success=success, status_label=status)

        # Remove from active missions map
        if rec.robot_name in self.active_missions and self.active_missions[rec.robot_name] == mission_id:
            del self.active_missions[rec.robot_name]

        log.info(
            "[ExperimentMetrics] Mission %s completed: Success=%s, Time=%.2fs, Dist=%.2fm (Eff: %.2f), Replans=%d",
            mission_id, success, rec.duration_seconds, rec.actual_travel_dist_m, rec.path_efficiency_ratio, rec.replan_count
        )
        return rec

    def record_snapshot(
        self,
        robot_states: Dict[str, Dict[str, Any]],
        obstacle_positions: List[Tuple[float, float]],
        active_events: List[str],
    ) -> None:
        """Capture digital twin snapshot frame for replay."""
        if self.mode != ExperimentMode.LIVE:
            return

        frame = ReplaySnapshot(
            timestamp=time.time(),
            frame_idx=len(self.replay_buffer),
            robot_states={k: dict(v) for k, v in robot_states.items()},
            obstacle_positions=list(obstacle_positions),
            active_events=list(active_events),
        )
        self.replay_buffer.append(frame)
        if len(self.replay_buffer) > self._max_replay_frames:
            self.replay_buffer.pop(0)

    def get_replay_frame(self, frame_idx: int) -> Optional[ReplaySnapshot]:
        """Fetch historical frame from the replay buffer."""
        if 0 <= frame_idx < len(self.replay_buffer):
            return self.replay_buffer[frame_idx]
        return None

    def export_summary_json(self, output_path: str) -> bool:
        """Export all captured metrics to a structured JSON file."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            summary_data = {
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_missions": len(self.records),
                "successful_missions": sum(1 for r in self.records.values() if r.success),
                "missions": [asdict(r) for r in self.records.values()],
            }
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(summary_data, f, indent=2)
            log.info("[ExperimentMetrics] Metrics exported to JSON: %s", output_path)
            return True
        except Exception as e:
            log.error("[ExperimentMetrics] JSON export failed: %s", e)
            return False

    def export_csv(self, output_path: str) -> bool:
        """Export tabular evaluation metrics to CSV for IEEE paper benchmarks."""
        if not self.records:
            return False
        try:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            fields = list(asdict(next(iter(self.records.values()))).keys())
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                for r in self.records.values():
                    writer.writerow(asdict(r))
            log.info("[ExperimentMetrics] Metrics exported to CSV: %s", output_path)
            return True
        except Exception as e:
            log.error("[ExperimentMetrics] CSV export failed: %s", e)
            return False


# Singleton metrics recorder instance
EXPERIMENT_METRICS = ExperimentMetricsRecorder()

"""
Performance Profiler & Real-Time Thread Diagnostic for AROGYA Simulation
========================================================================
Lightweight, low-overhead performance monitor tracking:
- Effective Simulation FPS & Frame Times
- Physics & Rendering Step duration (world.step)
- Multi-Agent Autonomous Navigation duration (step_autonomous)
- Sensor Raycasting & Processing duration (LiDAR + Camera)
- In-Viewport HUD (omni.ui) render/update duration
- ROS 2 Bridge telemetry duration
- Memory and Bottleneck Detection

Sampled periodically (e.g. 1 Hz) to prevent overhead.
"""

from __future__ import annotations

import time
import logging
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

try:
    from utilities.logger import get_logger
    log = get_logger(__name__)
except Exception:
    log = logging.getLogger(__name__)


class PerformanceProfiler:
    """Non-intrusive timing profiler identifying main-thread bottlenecks."""

    def __init__(self, sample_interval_s: float = 2.0, slow_frame_threshold_ms: float = 40.0) -> None:
        self.sample_interval_s = sample_interval_s
        self.slow_frame_threshold_ms = slow_frame_threshold_ms
        self._section_times: Dict[str, List[float]] = {}
        self._frame_start_time = time.perf_counter()
        self._last_sample_time = time.perf_counter()
        self._frame_count = 0
        self._total_frames = 0
        self.fps = 60.0
        self.avg_frame_time_ms = 16.6
        self.last_report_str = "Profiler initialized"

    @contextmanager
    def profile(self, section_name: str) -> Generator[None, None, None]:
        """Context manager measuring execution time of a code block."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            dt_ms = (time.perf_counter() - t0) * 1000.0
            if section_name not in self._section_times:
                self._section_times[section_name] = []
            self._section_times[section_name].append(dt_ms)

    def tick(self) -> Optional[str]:
        """Called at the end of each simulation step to update metrics."""
        now = time.perf_counter()
        self._frame_count += 1
        self._total_frames += 1

        elapsed = now - self._last_sample_time
        if elapsed >= self.sample_interval_s:
            self.fps = round(self._frame_count / elapsed, 1)
            self.avg_frame_time_ms = round((elapsed / self._frame_count) * 1000.0, 2)

            # Summarize section breakdowns
            breakdowns = []
            for sec, times in self._section_times.items():
                if times:
                    avg_t = sum(times) / len(times)
                    max_t = max(times)
                    pct = (avg_t / max(0.001, self.avg_frame_time_ms)) * 100.0
                    breakdowns.append(f"{sec}: {avg_t:.1f}ms ({pct:.0f}%, max {max_t:.1f}ms)")
                times.clear()

            report = (
                f"[PERF] FPS: {self.fps} | Frame: {self.avg_frame_time_ms:.1f}ms | "
                + " | ".join(breakdowns)
            )
            self.last_report_str = report
            self._frame_count = 0
            self._last_sample_time = now

            if self.fps < 25.0:
                log.warning("[PERF WARNING] Main thread FPS dropped to %.1f: %s", self.fps, report)
            return report

        return None

    def get_diagnostics_dict(self) -> Dict[str, Any]:
        """Return structured diagnostics dictionary."""
        return {
            "fps": self.fps,
            "avg_frame_time_ms": self.avg_frame_time_ms,
            "total_frames": self._total_frames,
            "last_report": self.last_report_str,
        }


# Singleton instance
PERFORMANCE_PROFILER = PerformanceProfiler()

__all__ = ["PerformanceProfiler", "PERFORMANCE_PROFILER"]

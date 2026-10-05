"""
HospitalRobotNav — Simulation Clock
======================================
Manages simulation time, speed control, and frame timing.
"""

from __future__ import annotations

import time
from config.settings import SIM_CONFIG


class SimClock:
    """
    Simulation time manager with variable speed control.

    Tracks:
        wall_time_s  — Real wall-clock seconds since simulation start
        sim_time_s   — Simulated time (scaled by speed multiplier)
        sim_step     — Number of simulation steps executed
        dt           — Current time step in seconds
    """

    def __init__(self) -> None:
        self._speed_options = list(SIM_CONFIG.SPEED_OPTIONS)
        self._speed_index   = SIM_CONFIG.DEFAULT_SPEED_INDEX
        self._start_wall    = time.perf_counter()
        self._last_tick     = time.perf_counter()
        self._sim_time_s    = 0.0
        self._wall_time_s   = 0.0
        self._sim_step      = 0
        self._paused        = False
        self._pause_start   = 0.0
        self._total_paused  = 0.0

    def tick(self) -> float:
        """
        Advance the clock by one wall-clock frame.

        Returns:
            dt — simulation time step for this frame (seconds).
        """
        now = time.perf_counter()
        wall_dt = now - self._last_tick
        self._last_tick = now
        self._wall_time_s = now - self._start_wall - self._total_paused

        if self._paused:
            return 0.0

        speed = self._speed_options[self._speed_index]
        # Fixed simulation timestep — deterministic and FPS-independent.
        # Previously used `wall_dt * speed`, which starved the physics
        # integrator when the render loop ran faster than the target FPS
        # (per-frame robot displacement became effectively zero, so the
        # robot appeared frozen unless an event forced a step).
        dt = self.base_dt * speed
        self._sim_time_s += dt
        self._sim_step   += 1
        return dt

    # ── Speed Control ─────────────────────────────────────────────────────────

    def speed_up(self) -> float:
        """Increase simulation speed. Returns new speed multiplier."""
        self._speed_index = min(len(self._speed_options) - 1, self._speed_index + 1)
        return self.speed

    def speed_down(self) -> float:
        """Decrease simulation speed. Returns new speed multiplier."""
        self._speed_index = max(0, self._speed_index - 1)
        return self.speed

    def set_speed_index(self, index: int) -> None:
        """Set speed by index into SPEED_OPTIONS."""
        self._speed_index = max(0, min(len(self._speed_options) - 1, index))

    @property
    def speed(self) -> float:
        """Current speed multiplier."""
        return self._speed_options[self._speed_index]

    @property
    def speed_index(self) -> int:
        """Index of current speed in SPEED_OPTIONS."""
        return self._speed_index

    # ── Pause / Resume ────────────────────────────────────────────────────────

    def pause(self) -> None:
        """Pause simulation."""
        if not self._paused:
            self._paused = True
            self._pause_start = time.perf_counter()

    def resume(self) -> None:
        """Resume simulation."""
        if self._paused:
            self._total_paused += time.perf_counter() - self._pause_start
            self._paused = False

    @property
    def is_paused(self) -> bool:
        """True if simulation is paused."""
        return self._paused

    # ── Time Queries ──────────────────────────────────────────────────────────

    @property
    def sim_time_s(self) -> float:
        """Simulated time in seconds."""
        return self._sim_time_s

    @property
    def wall_time_s(self) -> float:
        """Real elapsed wall-clock seconds."""
        return self._wall_time_s

    @property
    def sim_step(self) -> int:
        """Total simulation steps executed."""
        return self._sim_step

    @property
    def base_dt(self) -> float:
        """Base time step (1× speed)."""
        return SIM_CONFIG.BASE_DT

    def reset(self) -> None:
        """Reset clock to zero."""
        now = time.perf_counter()
        self._start_wall   = now
        self._last_tick    = now
        self._sim_time_s   = 0.0
        self._wall_time_s  = 0.0
        self._sim_step     = 0
        self._paused       = False
        self._total_paused = 0.0

    def __repr__(self) -> str:
        return (
            f"SimClock(sim={self._sim_time_s:.1f}s, "
            f"speed={self.speed}×, step={self._sim_step})"
        )

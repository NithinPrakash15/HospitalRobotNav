"""
HospitalRobotNav — Battery Model
==================================
Simulates the hospital robot's battery lifecycle.

Models:
    - Discharge during movement (speed-dependent)
    - Discharge while idle (standby draw)
    - Charging (constant-current / constant-voltage approximation)
    - State-of-charge (SoC) as a percentage
    - Low and critical battery events

Energy Estimation:
    Energy consumed per step = Power × Δt
    where Power depends on robot state (moving vs idle)

    This model approximates a LiFePO4 battery pack similar to those
    used in commercial hospital robots (TUG, Fetch Freight).

ROS2 Note:
    In deployment, battery state would come from:
    /battery_state (sensor_msgs/BatteryState)
    Published by the hardware battery driver.
"""

from __future__ import annotations

from config.robot_config import BATTERY_CONFIG
from utilities.event_bus import EVENT_BUS, HospitalEvent
from utilities.logger import get_logger

log = get_logger(__name__)


class BatteryModel:
    """
    Simulates the hospital robot battery.

    Tracks:
        - Current charge in Watt-hours (Wh)
        - State-of-charge (SoC) as 0.0–1.0 fraction
        - Cumulative energy consumed
        - Charging state

    Usage:
        battery = BatteryModel()
        battery.discharge_moving(dt=0.016)   # One frame of movement
        if battery.is_low():
            robot.return_to_dock()
    """

    def __init__(self) -> None:
        self._capacity_wh:  float = BATTERY_CONFIG.MAX_CAPACITY_WH
        self._charge_wh:    float = BATTERY_CONFIG.MAX_CAPACITY_WH * BATTERY_CONFIG.INITIAL_CHARGE
        self._total_energy_consumed_wh: float = 0.0
        self._is_charging:  bool = False
        self._low_event_fired:      bool = False
        self._critical_event_fired: bool = False

    # ─────────────────────────────────────────────────────────────────────────
    # Discharge
    # ─────────────────────────────────────────────────────────────────────────

    def discharge_moving(self, dt: float, speed_factor: float = 1.0) -> float:
        """
        Discharge battery for one simulation time step during movement.

        Energy consumed = Moving_Power × dt × speed_factor (seconds)

        Args:
            dt:           Simulation time step in seconds.
            speed_factor: Speed multiplier (0.0–1.0+). Higher = more power.

        Returns:
            Energy consumed this step (Wh).
        """
        power_w = BATTERY_CONFIG.MOVING_POWER_W * max(0.0, speed_factor)
        return self._consume(power_w, dt)

    def discharge_idle(self, dt: float) -> float:
        """
        Discharge battery for one simulation step while idle.

        Args:
            dt: Simulation time step in seconds.

        Returns:
            Energy consumed this step (Wh).
        """
        return self._consume(BATTERY_CONFIG.IDLE_POWER_W, dt)

    # ─────────────────────────────────────────────────────────────────────────
    # Charging
    # ─────────────────────────────────────────────────────────────────────────

    def start_charging(self) -> None:
        """Start charging the battery."""
        self._is_charging = True
        log.info("Battery: charging started (SoC=%.1f%%)", self.soc_percent)

    def stop_charging(self) -> None:
        """Stop charging."""
        self._is_charging = False
        log.info("Battery: charging stopped (SoC=%.1f%%)", self.soc_percent)

    def charge_step(self, dt: float) -> bool:
        """
        Advance charging by one time step.

        Args:
            dt: Simulation time step in seconds.

        Returns:
            True if battery is fully charged.
        """
        if not self._is_charging:
            return False

        charge_per_step = (BATTERY_CONFIG.CHARGING_POWER_W / 3600.0) * dt
        self._charge_wh = min(self._capacity_wh, self._charge_wh + charge_per_step)

        if self.soc >= BATTERY_CONFIG.RESUME_THRESHOLD:
            self._is_charging = False
            self._low_event_fired      = False
            self._critical_event_fired = False
            log.info("Battery: fully charged (%.1f%%)", self.soc_percent)
            EVENT_BUS.publish(
                HospitalEvent.ROBOT_CHARGED,
                data={"soc": self.soc},
                source="battery_model",
            )
            return True

        return False

    # ─────────────────────────────────────────────────────────────────────────
    # State Queries
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def soc(self) -> float:
        """State of charge as fraction [0.0, 1.0]."""
        return max(0.0, min(1.0, self._charge_wh / self._capacity_wh))

    @property
    def soc_percent(self) -> float:
        """State of charge as percentage [0, 100]."""
        return self.soc * 100.0

    @property
    def charge_wh(self) -> float:
        """Current charge in Watt-hours."""
        return self._charge_wh

    @property
    def is_charging(self) -> bool:
        """True if battery is currently charging."""
        return self._is_charging

    @property
    def total_energy_consumed_wh(self) -> float:
        """Total cumulative energy consumed since initialization (Wh)."""
        return self._total_energy_consumed_wh

    def is_low(self) -> bool:
        """Return True if SoC is below the low-battery threshold."""
        return self.soc <= BATTERY_CONFIG.LOW_BATTERY_THRESHOLD

    def is_critical(self) -> bool:
        """Return True if SoC is below the critical threshold."""
        return self.soc <= BATTERY_CONFIG.CRITICAL_BATTERY_THRESHOLD

    def is_depleted(self) -> bool:
        """Return True if battery is completely empty."""
        return self._charge_wh <= 0.0

    def estimate_remaining_distance(self) -> float:
        """
        Estimate remaining navigable distance in grid cells.

        Assumes cruising speed and cell-size for approximation.

        Returns:
            Float distance in grid cells.
        """
        from config.hospital_config import GRID_CONFIG
        from config.robot_config import PHYSICS_CONFIG

        # Energy remaining (Wh)
        remaining_wh = self._charge_wh

        # Power at cruise speed (W)
        power_w = BATTERY_CONFIG.MOVING_POWER_W

        # Time remaining (hours)
        time_h = remaining_wh / max(power_w, 1.0)

        # Distance = speed (m/s) × time (s)
        speed_mps = PHYSICS_CONFIG.CRUISE_SPEED
        time_s    = time_h * 3600.0
        dist_m    = speed_mps * time_s

        # Convert meters to cells
        dist_cells = dist_m / GRID_CONFIG.CELL_SIZE_METERS
        return dist_cells

    def reset(self) -> None:
        """Reset battery to full charge."""
        self._charge_wh = self._capacity_wh
        self._total_energy_consumed_wh = 0.0
        self._is_charging  = False
        self._low_event_fired      = False
        self._critical_event_fired = False
        log.info("Battery: reset to full charge.")

    # ─────────────────────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────────────────────

    def _consume(self, power_w: float, dt: float) -> float:
        """
        Consume energy from battery.

        Args:
            power_w: Power consumption (Watts).
            dt:      Time step (seconds).

        Returns:
            Actual energy consumed (Wh), may be less than requested if empty.
        """
        energy_wh = (power_w / 3600.0) * dt   # Watts × seconds → Wh
        actual    = min(energy_wh, max(0.0, self._charge_wh))
        self._charge_wh             -= actual
        self._total_energy_consumed_wh += actual

        # Fire events
        if self.is_critical() and not self._critical_event_fired:
            self._critical_event_fired = True
            EVENT_BUS.publish(
                HospitalEvent.BATTERY_CRITICAL,
                data={"soc": self.soc},
                source="battery_model",
            )
            log.warning("BATTERY CRITICAL: %.1f%%", self.soc_percent)

        elif self.is_low() and not self._low_event_fired:
            self._low_event_fired = True
            EVENT_BUS.publish(
                HospitalEvent.BATTERY_LOW,
                data={"soc": self.soc},
                source="battery_model",
            )
            log.warning("Battery low: %.1f%%", self.soc_percent)

        return actual

    def __repr__(self) -> str:
        state = "CHARGING" if self._is_charging else "DISCHARGING"
        return f"BatteryModel(SoC={self.soc_percent:.1f}%, {state})"

"""
HospitalRobotNav & Isaac Sim Hospital — Robot State Machine & Priority Policy
=============================================================================
Defines the autonomous operational state machine and priority scheduling
for the Arogya medical AMR.

States:
    IDLE               : Standby on charging pad or corridor waypoint
    MISSION_ANALYSIS   : Natural language & vision-language comprehension
    TASK_ASSIGNED      : Multi-agent contract awarded to winning agent
    PLANNING           : A* path computation with obstacle inflation
    NAVIGATING         : Smooth corridor pure-pursuit trajectory following
    EXECUTING_TASK     : Clinical action (dispense medication, vitals, handoff)
    BLOCKED            : Yielding to dynamic humanoids in forward safety envelope
    EMERGENCY_OVERRIDE : Code Blue emergency preemption mode
    MISSION_COMPLETE   : Destination verified, returning report to coordinator

Priority Levels (1 to 5):
    1: CRITICAL_EMERGENCY  (Interrupts all active tasks immediately)
    2: URGENT_MEDICINE     (High-priority stat delivery)
    3: SCHEDULED_DELIVERY  (Standard clinical delivery queue)
    4: VISITOR_ESCORT      (Low-priority escort and guidance)
    5: RETURN_TO_DOCK      (Background battery maintenance)
"""

from __future__ import annotations

import os
import sys
import logging
import time
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

# Ensure repository root is on sys.path
_this_dir = os.path.dirname(os.path.abspath(__file__))
_isaac_dir = os.path.dirname(_this_dir)
_repo_dir = os.path.dirname(_isaac_dir)
for _p in [_repo_dir, _isaac_dir]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from utilities.logger import get_logger
    log = get_logger(__name__)
except ImportError:
    log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Robot State Enum
# ─────────────────────────────────────────────────────────────────────────────

class RobotState(Enum):
    """Operational states of the Arogya hospital AMR."""
    IDLE                   = auto()
    AVAILABLE              = IDLE
    ASSIGNED               = auto()
    TASK_ASSIGNED          = ASSIGNED
    MISSION_ANALYSIS       = auto()
    PLANNING               = auto()
    NAVIGATING             = auto()
    STUCK_DETECTED         = auto()
    LOCAL_RECOVERY         = auto()
    OBSTACLE_DETECTED      = auto()
    AVOIDING_OBSTACLE      = auto()
    AVOIDING               = AVOIDING_OBSTACLE
    REPLANNING             = auto()
    WAITING_FOR_CLEARANCE  = auto()
    EXECUTING_TASK         = auto()
    MISSION_COMPLETE       = auto()
    NAVIGATION_FAILED      = auto()
    BLOCKED                = auto()
    MISSION_BLOCKED        = BLOCKED
    EMERGENCY_OVERRIDE     = auto()
    RETURNING              = auto()
    RETURNING_TO_DOCK      = RETURNING
    DOCKING                = auto()
    CHARGING               = auto()
    PAUSED                 = auto()



# ─────────────────────────────────────────────────────────────────────────────
# Priority Hierarchy Definition
# ─────────────────────────────────────────────────────────────────────────────

PRIORITY_LEVELS: Dict[int, Dict[str, Any]] = {
    1: {"name": "CRITICAL_EMERGENCY", "speed_multiplier": 1.25, "preemptable": False},
    2: {"name": "URGENT_MEDICINE",    "speed_multiplier": 1.10, "preemptable": True},
    3: {"name": "SCHEDULED_DELIVERY", "speed_multiplier": 1.00, "preemptable": True},
    4: {"name": "VISITOR_ESCORT",     "speed_multiplier": 0.85, "preemptable": True},
    5: {"name": "RETURN_TO_DOCK",     "speed_multiplier": 0.80, "preemptable": True},
}


# ─────────────────────────────────────────────────────────────────────────────
# Robot State Machine
# ─────────────────────────────────────────────────────────────────────────────

class RobotStateMachine:
    """
    Finite State Machine managing AMR lifecycle and operational transitions.
    """

    def __init__(self, initial_state: RobotState = RobotState.IDLE) -> None:
        self.current_state: RobotState = initial_state
        self.previous_state: Optional[RobotState] = None
        self.current_reason: str = "Initialization"
        self.current_action: str = "Standby"
        self.state_enter_time: float = time.monotonic()
        self.history: List[Tuple[float, RobotState, str]] = [
            (self.state_enter_time, initial_state, "Initialization")
        ]
        self._on_transition_callbacks: List[Callable[[RobotState, RobotState, str], None]] = []

    def register_transition_callback(
        self, callback: Callable[[RobotState, RobotState, str], None]
    ) -> None:
        """Register a callback function to be invoked on every state change."""
        self._on_transition_callbacks.append(callback)

    def transition_to(self, new_state: RobotState, reason: str = "", action: str = "") -> bool:
        """
        Transition robot to a new operational state with explicit reason and action.
        
        Args:
            new_state: Target RobotState.
            reason: Contextual description of the transition trigger.
            action: Concrete operational action being taken (e.g. 'Replanning', 'Tracking').
            
        Returns:
            True if transition occurred, False if already in that state.
        """
        if new_state == self.current_state:
            if reason:
                self.current_reason = reason
            if action:
                self.current_action = action
            return False

        now = time.monotonic()
        prev = self.current_state
        self.previous_state = prev
        self.current_state = new_state
        self.current_reason = reason or "Normal operation"
        self.current_action = action or ("Navigating" if new_state == RobotState.NAVIGATING else "Standby")
        self.state_enter_time = now

        log_msg = f"[FSM] {prev.name} -> {new_state.name} | Reason: {self.current_reason} | Action: {self.current_action}"
        if new_state == RobotState.EMERGENCY_OVERRIDE:
            log.warning(log_msg)
        else:
            log.info(log_msg)

        self.history.append((now, new_state, reason))

        # Notify callbacks (e.g. voice engine, UI HUD)
        for cb in self._on_transition_callbacks:
            try:
                cb(prev, new_state, reason)
            except Exception as e:
                log.error("[FSM] Error in transition callback: %s", e)

        return True

    @property
    def state(self) -> RobotState:
        """Return the current RobotState."""
        return self.current_state

    @property
    def state_name(self) -> str:
        """Return human-readable state string."""
        return self.current_state.name

    def time_in_state(self) -> float:
        """Return elapsed duration in seconds since current state entry."""
        return time.monotonic() - self.state_enter_time

    def is_idle(self) -> bool:
        return self.current_state == RobotState.IDLE

    def is_navigating(self) -> bool:
        return self.current_state in (RobotState.NAVIGATING, RobotState.EMERGENCY_OVERRIDE)

    def is_emergency(self) -> bool:
        return self.current_state == RobotState.EMERGENCY_OVERRIDE

    def is_blocked(self) -> bool:
        return self.current_state == RobotState.BLOCKED

    def is_executing(self) -> bool:
        return self.current_state == RobotState.EXECUTING_TASK

    def is_charging(self) -> bool:
        return self.current_state == RobotState.CHARGING

    def is_paused(self) -> bool:
        return self.current_state == RobotState.PAUSED

    def is_complete(self) -> bool:
        return self.current_state == RobotState.MISSION_COMPLETE

"""
HospitalRobotNav — Robot Finite State Machine
===============================================
Defines all possible robot states and valid state transitions.

The robot operates as a Finite State Machine (FSM):

    ┌─────────┐    goal assigned    ┌──────────┐
    │  IDLE   │ ─────────────────► │ PLANNING │
    └─────────┘                    └──────────┘
         ▲                              │ path found
         │ mission complete             ▼
    ┌─────────┐    executing path  ┌──────────┐
    │COMPLETE │ ◄──────────────── │  MOVING  │
    └─────────┘                    └──────────┘
                                        │ obstacle!
                                        ▼
    ┌──────────┐   new path found  ┌────────────┐
    │  MOVING  │ ◄──────────────── │ REPLANNING │
    └──────────┘                   └────────────┘
         │ battery low
         ▼
    ┌──────────┐   charged         ┌────────────┐
    │  DOCKED  │ ◄──────────────── │  CHARGING  │
    └──────────┘                   └────────────┘

ROS2 Note:
    This FSM maps to the Nav2 Behavior Tree structure:
        IDLE → NavigateToPose BT action
        REPLANNING → ClearCostmapService + replanning
        CHARGING → return-to-dock behavior tree
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Dict, FrozenSet, Optional


class RobotState(Enum):
    """
    All valid robot operational states.

    Each state drives a different behavior set in the simulation loop.
    """
    # ── Idle / Ready ──────────────────────────────────────────────────────────
    IDLE        = auto()   # Waiting for mission assignment

    # ── Navigation states ─────────────────────────────────────────────────────
    PLANNING    = auto()   # Running path planner
    MOVING      = auto()   # Executing planned path
    REPLANNING  = auto()   # Re-planning due to obstacle change

    # ── Terminal / Pause states ───────────────────────────────────────────────
    PAUSED      = auto()   # User paused simulation
    WAITING     = auto()   # Waiting for corridor to clear
    BLOCKED     = auto()   # Path completely blocked, cannot replan

    # ── Task completion & Interactive states ──────────────────────────────────
    ARRIVED     = auto()   # Reached current waypoint
    COMPLETE    = auto()   # Mission fully complete
    COLLECTING  = auto()   # Collecting medicine/item
    DELIVERING  = auto()   # Delivering medicine/item
    INTERACTING = auto()   # Interacting with patient/nurse
    ESCORTING   = auto()   # Guiding/escorting patient or visitor

    # ── Power management ─────────────────────────────────────────────────────
    RETURNING   = auto()   # Returning to charging station
    DOCKED      = auto()   # At charging station
    CHARGING    = auto()   # Battery charging in progress

    # ── Error states ──────────────────────────────────────────────────────────
    ERROR       = auto()   # System error requiring operator attention


# ─────────────────────────────────────────────────────────────────────────────
# Valid State Transitions (transition guard)
# ─────────────────────────────────────────────────────────────────────────────

# Maps each state to the set of states it can legally transition to
_VALID_TRANSITIONS: Dict[RobotState, FrozenSet[RobotState]] = {
    RobotState.IDLE:       frozenset({
        RobotState.PLANNING,
        RobotState.RETURNING,
        RobotState.DOCKED,
        RobotState.CHARGING,
        RobotState.COLLECTING,
        RobotState.DELIVERING,
        RobotState.INTERACTING,
        RobotState.ESCORTING,
    }),
    RobotState.PLANNING:   frozenset({
        RobotState.MOVING,
        RobotState.BLOCKED,
        RobotState.IDLE,
        RobotState.ERROR,
    }),
    RobotState.MOVING:     frozenset({
        RobotState.ARRIVED,
        RobotState.COMPLETE,
        RobotState.REPLANNING,
        RobotState.WAITING,
        RobotState.BLOCKED,
        RobotState.PAUSED,
        RobotState.RETURNING,
        RobotState.ERROR,
        RobotState.COLLECTING,
        RobotState.DELIVERING,
        RobotState.INTERACTING,
        RobotState.ESCORTING,
    }),
    RobotState.REPLANNING: frozenset({
        RobotState.MOVING,
        RobotState.BLOCKED,
        RobotState.IDLE,
        RobotState.ERROR,
    }),
    RobotState.PAUSED:     frozenset({
        RobotState.MOVING,
        RobotState.PLANNING,
        RobotState.IDLE,
    }),
    RobotState.WAITING:    frozenset({
        RobotState.MOVING,
        RobotState.REPLANNING,
        RobotState.BLOCKED,
    }),
    RobotState.BLOCKED:    frozenset({
        RobotState.IDLE,
        RobotState.REPLANNING,
        RobotState.ERROR,
    }),
    RobotState.ARRIVED:    frozenset({
        RobotState.MOVING,
        RobotState.COMPLETE,
        RobotState.PLANNING,
        RobotState.IDLE,
        RobotState.COLLECTING,
        RobotState.DELIVERING,
        RobotState.INTERACTING,
        RobotState.ESCORTING,
    }),
    RobotState.COLLECTING: frozenset({
        RobotState.MOVING,
        RobotState.PLANNING,
        RobotState.IDLE,
        RobotState.COMPLETE,
    }),
    RobotState.DELIVERING: frozenset({
        RobotState.MOVING,
        RobotState.PLANNING,
        RobotState.IDLE,
        RobotState.COMPLETE,
    }),
    RobotState.INTERACTING: frozenset({
        RobotState.MOVING,
        RobotState.PLANNING,
        RobotState.IDLE,
        RobotState.COMPLETE,
    }),
    RobotState.ESCORTING: frozenset({
        RobotState.MOVING,
        RobotState.PLANNING,
        RobotState.IDLE,
        RobotState.COMPLETE,
    }),
    RobotState.COMPLETE:   frozenset({
        RobotState.IDLE,
        RobotState.RETURNING,
    }),
    RobotState.RETURNING:  frozenset({
        RobotState.MOVING,
        RobotState.DOCKED,
        RobotState.PLANNING,
    }),
    RobotState.DOCKED:     frozenset({
        RobotState.CHARGING,
        RobotState.IDLE,
    }),
    RobotState.CHARGING:   frozenset({
        RobotState.DOCKED,
        RobotState.IDLE,
    }),
    RobotState.ERROR:      frozenset({
        RobotState.IDLE,
    }),
}


class RobotStateMachine:
    """
    Guards and tracks valid robot state transitions.

    Usage:
        fsm = RobotStateMachine(initial_state=RobotState.IDLE)
        fsm.transition(RobotState.PLANNING)   # OK
        fsm.transition(RobotState.CHARGING)   # Raises ValueError
    """

    def __init__(self, initial_state: RobotState = RobotState.IDLE) -> None:
        self._state   = initial_state
        self._history = [initial_state]

    @property
    def state(self) -> RobotState:
        """Current robot state."""
        return self._state

    @property
    def history(self):
        """Full state transition history."""
        return list(self._history)

    def can_transition(self, new_state: RobotState) -> bool:
        """Return True if transitioning to new_state is valid."""
        return new_state in _VALID_TRANSITIONS.get(self._state, frozenset())

    def transition(self, new_state: RobotState, strict: bool = False) -> bool:
        """
        Attempt to transition to new_state.

        Args:
            new_state: Target state.
            strict:    If True, raise ValueError on invalid transition.

        Returns:
            True if transition occurred, False otherwise.

        Raises:
            ValueError: If strict=True and transition is invalid.
        """
        if new_state == self._state:
            return True   # No-op

        if not self.can_transition(new_state):
            msg = (
                f"Invalid FSM transition: {self._state.name} → {new_state.name}"
            )
            if strict:
                raise ValueError(msg)
            return False

        self._state = new_state
        self._history.append(new_state)
        return True

    def force_transition(self, new_state: RobotState) -> None:
        """
        Force a state transition regardless of validity.

        Use only for emergency overrides (e.g., system reset).

        Args:
            new_state: Target state to force.
        """
        self._state = new_state
        self._history.append(new_state)

    def is_navigating(self) -> bool:
        """Return True if robot is actively moving or planning."""
        return self._state in (
            RobotState.MOVING,
            RobotState.PLANNING,
            RobotState.REPLANNING,
            RobotState.RETURNING,
        )

    def is_stuck(self) -> bool:
        """Return True if robot is in a non-moving problem state."""
        return self._state in (RobotState.BLOCKED, RobotState.ERROR, RobotState.WAITING)

    def is_available(self) -> bool:
        """Return True if robot can accept a new mission."""
        return self._state in (
            RobotState.IDLE,
            RobotState.COMPLETE,
            RobotState.DOCKED,
        )

    def __repr__(self) -> str:
        return f"RobotFSM(state={self._state.name})"

"""
HospitalRobotNav — Mission Types & Data Structures
=====================================================
Core data structures for the mission planning and execution system.

Defines:
    - TaskType:   Atomic task categories (navigate, collect, deliver, wait, etc.).
    - TaskStep:   A single executable step in a mission plan.
    - MissionPlan: An ordered sequence of TaskSteps with metadata.

These structures are the lingua franca between the MissionPlanner
(which generates plans) and the MissionExecutor (which runs them).
"""

from __future__ import annotations

import uuid
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

GridPos = Tuple[int, int]


# ─────────────────────────────────────────────────────────────────────────────
# Task Types
# ─────────────────────────────────────────────────────────────────────────────

class TaskType(Enum):
    """Atomic task categories for mission steps."""
    NAVIGATE        = auto()   # Move to a grid position
    COLLECT         = auto()   # Pick up an item at current location
    DELIVER         = auto()   # Drop off an item at current location
    WAIT            = auto()   # Wait at current location for a duration
    INTERACT        = auto()   # Interact with a person (speak, alert)
    ESCORT          = auto()   # Lead a person to a destination
    ALERT           = auto()   # Trigger an alert (nurse call, emergency)
    RETURN_TO_DOCK  = auto()   # Navigate back to charging dock
    CHARGE          = auto()   # Charge at dock


class TaskStatus(Enum):
    """Execution status of a single task step."""
    PENDING     = auto()
    IN_PROGRESS = auto()
    COMPLETED   = auto()
    FAILED      = auto()
    SKIPPED     = auto()


# ─────────────────────────────────────────────────────────────────────────────
# Task Step
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TaskStep:
    """A single executable step in a mission plan.

    Attributes:
        step_id:      Unique step identifier.
        task_type:    What kind of action to perform.
        description:  Human-readable description.
        destination:  Target location name (for NAVIGATE steps).
        destination_pos: Resolved grid coordinates (row, col).
        item:         Item to collect/deliver (for COLLECT/DELIVER).
        duration_sec: Expected duration in seconds (for WAIT steps).
        status:       Current execution status.
        started_at:   Timestamp when step execution began.
        completed_at: Timestamp when step completed.
        metadata:     Arbitrary extra data for specialised steps.
    """
    step_id: str = ""
    task_type: TaskType = TaskType.NAVIGATE
    description: str = ""
    destination: str = ""
    destination_pos: Optional[GridPos] = None
    item: str = ""
    duration_sec: float = 0.0
    status: TaskStatus = TaskStatus.PENDING
    started_at: float = 0.0
    completed_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.step_id:
            self.step_id = str(uuid.uuid4())[:8].upper()

    def start(self) -> None:
        """Mark step as in progress."""
        self.status = TaskStatus.IN_PROGRESS
        self.started_at = time.monotonic()

    def complete(self) -> None:
        """Mark step as completed."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = time.monotonic()

    def fail(self) -> None:
        """Mark step as failed."""
        self.status = TaskStatus.FAILED
        self.completed_at = time.monotonic()

    @property
    def elapsed_sec(self) -> float:
        """Seconds elapsed since step started (0 if not started)."""
        if self.started_at == 0.0:
            return 0.0
        end = self.completed_at if self.completed_at > 0 else time.monotonic()
        return end - self.started_at

    @property
    def is_complete(self) -> bool:
        return self.status == TaskStatus.COMPLETED

    @property
    def is_active(self) -> bool:
        return self.status == TaskStatus.IN_PROGRESS

    @property
    def is_pending(self) -> bool:
        return self.status == TaskStatus.PENDING

    def __repr__(self) -> str:
        return (
            f"TaskStep({self.step_id}, {self.task_type.name}, "
            f"'{self.description[:30]}', {self.status.name})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Mission Plan
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MissionPlan:
    """An ordered sequence of TaskSteps forming a complete mission.

    Attributes:
        plan_id:      Unique plan identifier.
        mission_type: High-level mission category string.
        description:  Human-readable mission description.
        steps:        Ordered list of TaskSteps.
        priority:     Mission priority (1=critical, 5=low).
        created_at:   Timestamp when plan was generated.
        eta_total_sec: Estimated total execution time in seconds.
        raw_command:  The original spoken command.
    """
    plan_id: str = ""
    mission_type: str = ""
    description: str = ""
    steps: List[TaskStep] = field(default_factory=list)
    priority: int = 4
    created_at: float = field(default_factory=time.monotonic)
    eta_total_sec: float = 0.0
    raw_command: str = ""

    def __post_init__(self) -> None:
        if not self.plan_id:
            self.plan_id = f"MSN-{str(uuid.uuid4())[:6].upper()}"

    # ── Progress tracking ────────────────────────────────────────────────────

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.is_complete)

    @property
    def progress_fraction(self) -> float:
        """Fraction of steps completed (0.0 – 1.0)."""
        if self.total_steps == 0:
            return 0.0
        return self.completed_steps / self.total_steps

    @property
    def progress_percent(self) -> int:
        """Integer percentage of steps completed."""
        return int(self.progress_fraction * 100)

    @property
    def current_step(self) -> Optional[TaskStep]:
        """The currently active step, or the next pending step."""
        for step in self.steps:
            if step.is_active:
                return step
        for step in self.steps:
            if step.is_pending:
                return step
        return None

    @property
    def current_step_index(self) -> int:
        """0-based index of the current step."""
        for i, step in enumerate(self.steps):
            if step.is_active or step.is_pending:
                return i
        return self.total_steps

    @property
    def is_complete(self) -> bool:
        """True if all steps are completed."""
        return all(s.is_complete for s in self.steps)

    @property
    def has_failed(self) -> bool:
        """True if any step has failed."""
        return any(s.status == TaskStatus.FAILED for s in self.steps)

    @property
    def elapsed_sec(self) -> float:
        """Total elapsed seconds since mission started."""
        if not self.steps:
            return 0.0
        started = [s.started_at for s in self.steps if s.started_at > 0]
        if not started:
            return 0.0
        return time.monotonic() - min(started)

    def get_summary(self) -> str:
        """Generate a human-readable mission summary."""
        lines = [f"Mission {self.plan_id}: {self.description}"]
        for i, step in enumerate(self.steps, 1):
            icon = "✓" if step.is_complete else "→" if step.is_active else "○"
            lines.append(f"  {icon} Step {i}: {step.description}")
        lines.append(f"  Progress: {self.progress_percent}%")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"MissionPlan({self.plan_id}, {self.mission_type}, "
            f"{self.completed_steps}/{self.total_steps} steps, "
            f"pri={self.priority})"
        )

"""
HospitalRobotNav — Mission Executor
======================================
Executes MissionPlans step-by-step, coordinating with the robot controller,
medicine manager, and dialogue manager.

Responsibilities:
    - Step through a MissionPlan's TaskSteps in order.
    - For NAVIGATE steps: issue navigation goals to the simulator.
    - For COLLECT/DELIVER: trigger medicine animation states.
    - For INTERACT: speak via TTS and wait.
    - For ESCORT: navigate at reduced speed with patient following.
    - Handle timeouts, retries, and failure recovery.
    - Publish progress events via the EventBus.

Integration Points:
    - Reads robot position from the Robot entity.
    - Calls simulator.navigate_to() for path planning.
    - Calls MedicineManager for pickup/dropoff.
    - Calls DialogueManager for speech output.
    - Publishes HospitalEvents for dashboard and HUD.

ROS2 Deployment Note:
    Maps to a ``mission_executor_node`` with a BehaviorTree (BT)
    action server using Nav2's ``NavigateToPose`` and custom BT nodes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from missions.mission_types import (
    TaskType, TaskStep, TaskStatus, MissionPlan,
)
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]


# ─────────────────────────────────────────────────────────────────────────────
# Executor State
# ─────────────────────────────────────────────────────────────────────────────

class ExecutorState:
    """Named constants for the executor state machine."""
    IDLE          = "IDLE"           # No active mission
    EXECUTING     = "EXECUTING"      # Running a mission plan
    STEP_NAVIGATE = "STEP_NAVIGATE"  # Current step: navigation
    STEP_COLLECT  = "STEP_COLLECT"   # Current step: item collection
    STEP_DELIVER  = "STEP_DELIVER"   # Current step: item delivery
    STEP_INTERACT = "STEP_INTERACT"  # Current step: person interaction
    STEP_ESCORT   = "STEP_ESCORT"    # Current step: escorting person
    STEP_ALERT    = "STEP_ALERT"     # Current step: triggering alert
    STEP_WAIT     = "STEP_WAIT"      # Current step: waiting
    PAUSED        = "PAUSED"         # Mission paused
    COMPLETE      = "COMPLETE"       # Mission completed
    FAILED        = "FAILED"         # Mission failed


# ─────────────────────────────────────────────────────────────────────────────
# Executor Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ExecutorConfig:
    """Mission executor parameters."""
    STEP_TIMEOUT_SEC: float = 120.0    # Max seconds per step
    NAVIGATE_TIMEOUT_SEC: float = 60.0 # Max seconds for navigation
    COLLECT_DURATION_SEC: float = 5.0  # Default collection time
    DELIVER_DURATION_SEC: float = 3.0  # Default delivery time
    INTERACT_DURATION_SEC: float = 3.0 # Default interaction time
    MAX_RETRIES: int = 2               # Max retries per step
    RETRY_DELAY_SEC: float = 2.0       # Delay between retries


EXECUTOR_CONFIG = ExecutorConfig()


# ─────────────────────────────────────────────────────────────────────────────
# Mission Executor
# ─────────────────────────────────────────────────────────────────────────────

class MissionExecutor:
    """Executes MissionPlans step-by-step.

    Usage::

        executor = MissionExecutor()

        # Set callbacks for integration
        executor.on_navigate = lambda dest, pos: simulator.navigate_to(dest)
        executor.on_collect = lambda item: medicine_manager.collect(item)
        executor.on_deliver = lambda item: medicine_manager.deliver(item)
        executor.on_speak = lambda text: tts.speak(text)
        executor.on_step_complete = lambda step: dashboard.update_step(step)
        executor.on_mission_complete = lambda plan: dialogue.on_mission_complete(plan)

        # Submit a mission
        executor.submit(mission_plan)

        # Call update() every frame
        executor.update(dt)

    The executor does NOT drive navigation itself — it issues goals and
    monitors the robot's state to detect arrival/failure.

    Attributes:
        state:          Current executor state.
        active_plan:    The currently executing MissionPlan (or None).
        mission_queue:  Queue of pending MissionPlans.
        completed:      List of completed MissionPlans.
    """

    def __init__(
        self,
        simulator: Optional[Any] = None,
        robot: Optional[Any] = None,
        medicine_manager: Optional[Any] = None,
    ) -> None:
        self._simulator = simulator
        self._robot = robot
        self._medicine_manager = medicine_manager
        self._cfg = EXECUTOR_CONFIG

        # State
        self.state: str = ExecutorState.IDLE
        self.active_plan: Optional[MissionPlan] = None
        self.mission_queue: List[MissionPlan] = []
        self.completed: List[MissionPlan] = []

        # Current step tracking
        self._current_step: Optional[TaskStep] = None
        self._step_start_time: float = 0.0
        self._step_timer: float = 0.0
        self._retry_count: int = 0
        self._waiting_for_arrival: bool = False

        # Callbacks (set by the simulation integrator)
        self.on_navigate: Optional[Callable[[str, Optional[GridPos]], None]] = None
        self.on_collect: Optional[Callable[[str], None]] = None
        self.on_deliver: Optional[Callable[[str], None]] = None
        self.on_speak: Optional[Callable[[str], None]] = None
        self.on_alert: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self.on_step_complete: Optional[Callable[[TaskStep], None]] = None
        self.on_mission_complete: Optional[Callable[[MissionPlan], None]] = None
        self.on_mission_failed: Optional[Callable[[MissionPlan, str], None]] = None

        # Statistics
        self.total_missions_completed: int = 0
        self.total_missions_failed: int = 0
        self.total_steps_executed: int = 0

        log.info("MissionExecutor initialised.")

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def submit(self, plan: MissionPlan) -> None:
        """Submit a mission plan for execution.

        If a mission is already active, the new plan is queued.
        Higher priority plans are inserted before lower priority ones.

        Args:
            plan: The MissionPlan to execute.
        """
        if self.active_plan is None:
            self._start_mission(plan)
        else:
            # Priority queue insertion
            inserted = False
            for i, queued in enumerate(self.mission_queue):
                if plan.priority < queued.priority:
                    self.mission_queue.insert(i, plan)
                    inserted = True
                    break
            if not inserted:
                self.mission_queue.append(plan)

            log.info(
                "MissionExecutor: Queued %s (queue size: %d).",
                plan.plan_id, len(self.mission_queue),
            )

    def update(self, dt: float) -> None:
        """Update the executor state (called every simulation frame).

        Args:
            dt: Elapsed time in seconds since last frame.
        """
        if self.state == ExecutorState.IDLE:
            self._check_queue()
            return

        if self.active_plan is None or self._current_step is None:
            return

        # Update step timer
        self._step_timer += dt

        # Check step timeout
        if self._step_timer > self._cfg.STEP_TIMEOUT_SEC:
            log.warning(
                "MissionExecutor: Step timeout — %s",
                self._current_step.description,
            )
            self._handle_step_failure("Step timed out")
            return

        # State-specific update
        if self.state == ExecutorState.STEP_NAVIGATE:
            self._update_navigate(dt)
        elif self.state == ExecutorState.STEP_COLLECT:
            self._update_timed_step(dt)
        elif self.state == ExecutorState.STEP_DELIVER:
            self._update_timed_step(dt)
        elif self.state == ExecutorState.STEP_INTERACT:
            self._update_timed_step(dt)
        elif self.state == ExecutorState.STEP_WAIT:
            self._update_timed_step(dt)
        elif self.state == ExecutorState.STEP_ESCORT:
            self._update_navigate(dt)  # Escort uses navigation
        elif self.state == ExecutorState.STEP_ALERT:
            self._update_timed_step(dt)

    def notify_arrival(self) -> None:
        """Called by the simulator when the robot reaches its navigation goal.

        This unblocks NAVIGATE and ESCORT steps that are waiting for arrival.
        """
        if self._waiting_for_arrival:
            self._waiting_for_arrival = False
            log.info("MissionExecutor: Robot arrived at destination.")
            self._complete_current_step()

    def cancel(self) -> None:
        """Cancel the active mission."""
        if self.active_plan:
            log.info("MissionExecutor: Mission %s cancelled.", self.active_plan.plan_id)
            self.active_plan = None
            self._current_step = None
            self.state = ExecutorState.IDLE

    def pause(self) -> None:
        """Pause mission execution."""
        if self.state not in (ExecutorState.IDLE, ExecutorState.PAUSED):
            self._saved_state = self.state
            self.state = ExecutorState.PAUSED
            log.info("MissionExecutor: Paused.")

    def resume(self) -> None:
        """Resume mission execution."""
        if self.state == ExecutorState.PAUSED:
            self.state = getattr(self, "_saved_state", ExecutorState.EXECUTING)
            log.info("MissionExecutor: Resumed.")

    @property
    def is_busy(self) -> bool:
        """True if a mission is active or queued."""
        return self.active_plan is not None or len(self.mission_queue) > 0

    @property
    def queue_size(self) -> int:
        return len(self.mission_queue)

    @property
    def current_step_description(self) -> str:
        """Human-readable description of the current step."""
        if self._current_step:
            return self._current_step.description
        return "No active step"

    @property
    def progress_percent(self) -> int:
        """Overall mission progress percentage."""
        if self.active_plan:
            return self.active_plan.progress_percent
        return 0

    # ─────────────────────────────────────────────────────────────────────────
    # Internal: Mission Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def _start_mission(self, plan: MissionPlan) -> None:
        """Begin executing a mission plan."""
        self.active_plan = plan
        self.state = ExecutorState.EXECUTING

        log.info(
            "MissionExecutor: Starting %s — '%s' (%d steps).",
            plan.plan_id, plan.description, plan.total_steps,
        )

        self._advance_to_next_step()

    def _advance_to_next_step(self) -> None:
        """Move to the next pending step in the active plan."""
        if self.active_plan is None:
            return

        step = self.active_plan.current_step
        if step is None:
            # All steps complete
            self._complete_mission()
            return

        self._current_step = step
        self._step_timer = 0.0
        self._retry_count = 0
        self._waiting_for_arrival = False
        step.start()

        log.info(
            "MissionExecutor: Step %d/%d — %s [%s]",
            self.active_plan.current_step_index + 1,
            self.active_plan.total_steps,
            step.description,
            step.task_type.name,
        )

        # Dispatch step execution
        self._dispatch_step(step)

    def _dispatch_step(self, step: TaskStep) -> None:
        """Dispatch step execution based on task type."""

        if step.task_type == TaskType.NAVIGATE:
            self.state = ExecutorState.STEP_NAVIGATE
            self._waiting_for_arrival = True
            if self.on_navigate:
                self.on_navigate(step.destination, step.destination_pos)

        elif step.task_type == TaskType.RETURN_TO_DOCK:
            self.state = ExecutorState.STEP_NAVIGATE
            self._waiting_for_arrival = True
            if self.on_navigate:
                self.on_navigate("Charging Dock", step.destination_pos)

        elif step.task_type == TaskType.COLLECT:
            self.state = ExecutorState.STEP_COLLECT
            if step.duration_sec <= 0:
                step.duration_sec = self._cfg.COLLECT_DURATION_SEC
            if self.on_collect:
                self.on_collect(step.item)
            speech = step.metadata.get("speech", "")
            if speech and self.on_speak:
                self.on_speak(speech)

        elif step.task_type == TaskType.DELIVER:
            self.state = ExecutorState.STEP_DELIVER
            if step.duration_sec <= 0:
                step.duration_sec = self._cfg.DELIVER_DURATION_SEC
            if self.on_deliver:
                self.on_deliver(step.item)
            speech = step.metadata.get("speech", "")
            if speech and self.on_speak:
                self.on_speak(speech)

        elif step.task_type == TaskType.INTERACT:
            self.state = ExecutorState.STEP_INTERACT
            if step.duration_sec <= 0:
                step.duration_sec = self._cfg.INTERACT_DURATION_SEC
            speech = step.metadata.get("speech", "")
            if speech and self.on_speak:
                self.on_speak(speech)

        elif step.task_type == TaskType.ESCORT:
            self.state = ExecutorState.STEP_ESCORT
            self._waiting_for_arrival = True
            if self.on_navigate:
                self.on_navigate(step.destination, step.destination_pos)

        elif step.task_type == TaskType.ALERT:
            self.state = ExecutorState.STEP_ALERT
            if step.duration_sec <= 0:
                step.duration_sec = 2.0
            if self.on_alert:
                self.on_alert(
                    step.metadata.get("alert_type", "general"),
                    step.metadata,
                )
            speech = step.metadata.get("speech", "")
            if speech and self.on_speak:
                self.on_speak(speech)

        elif step.task_type == TaskType.WAIT:
            self.state = ExecutorState.STEP_WAIT

        elif step.task_type == TaskType.CHARGE:
            self.state = ExecutorState.STEP_WAIT
            if step.duration_sec <= 0:
                step.duration_sec = 30.0

    def _complete_current_step(self) -> None:
        """Mark the current step as completed and advance."""
        if self._current_step:
            self._current_step.complete()
            self.total_steps_executed += 1

            log.info(
                "MissionExecutor: Step completed — %s (%.1f s).",
                self._current_step.description,
                self._current_step.elapsed_sec,
            )

            if self.on_step_complete:
                try:
                    self.on_step_complete(self._current_step)
                except Exception as exc:
                    log.debug("MissionExecutor: Step callback error — %s", exc)

        self._advance_to_next_step()

    def _complete_mission(self) -> None:
        """Mark the active mission as complete."""
        plan = self.active_plan
        if plan is None:
            return

        self.total_missions_completed += 1
        self.completed.append(plan)

        log.info(
            "MissionExecutor: Mission %s COMPLETE (%.1f s, %d steps).",
            plan.plan_id, plan.elapsed_sec, plan.total_steps,
        )

        if self.on_mission_complete:
            try:
                self.on_mission_complete(plan)
            except Exception as exc:
                log.debug("MissionExecutor: Mission complete callback error — %s", exc)

        self.active_plan = None
        self._current_step = None
        self.state = ExecutorState.IDLE
        self._check_queue()

    def _handle_step_failure(self, reason: str) -> None:
        """Handle a failed step with retry logic."""
        if self._current_step is None:
            return

        self._retry_count += 1

        if self._retry_count <= self._cfg.MAX_RETRIES:
            log.warning(
                "MissionExecutor: Retrying step (attempt %d/%d) — %s",
                self._retry_count, self._cfg.MAX_RETRIES, reason,
            )
            self._step_timer = 0.0
            self._dispatch_step(self._current_step)
        else:
            self._current_step.fail()
            log.error(
                "MissionExecutor: Step FAILED after %d retries — %s",
                self._cfg.MAX_RETRIES, reason,
            )

            self.total_missions_failed += 1

            if self.on_mission_failed and self.active_plan:
                try:
                    self.on_mission_failed(self.active_plan, reason)
                except Exception as exc:
                    log.debug("MissionExecutor: Failure callback error — %s", exc)

            self.active_plan = None
            self._current_step = None
            self.state = ExecutorState.IDLE
            self._check_queue()

    def _check_queue(self) -> None:
        """Start the next queued mission if available."""
        if self.mission_queue and self.active_plan is None:
            next_plan = self.mission_queue.pop(0)
            self._start_mission(next_plan)

    # ─────────────────────────────────────────────────────────────────────────
    # Step Update Methods
    # ─────────────────────────────────────────────────────────────────────────

    def _update_navigate(self, dt: float) -> None:
        """Update for NAVIGATE / ESCORT steps — just wait for arrival callback."""
        # Navigation timeout (separate from general step timeout)
        if self._step_timer > self._cfg.NAVIGATE_TIMEOUT_SEC:
            self._handle_step_failure("Navigation timed out")

    def _update_timed_step(self, dt: float) -> None:
        """Update for timed steps (COLLECT, DELIVER, INTERACT, WAIT, ALERT)."""
        if self._current_step and self._step_timer >= self._current_step.duration_sec:
            self._complete_current_step()

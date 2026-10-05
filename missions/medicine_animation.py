"""
HospitalRobotNav — Medicine Animation
========================================
Visual state machine for medicine pickup and delivery sequences.

Animation States:
    IDLE ──► APPROACHING ──► ALIGNING ──► ARM_EXTENDING ──► GRABBING
                                                              │
    COMPLETE ◄── DELIVERING ◄── CARRYING ◄── ARM_RETRACTING ◄┘

Each state has:
    - A visual representation (robot color, arm position, medicine sprite).
    - A minimum duration before auto-advancing.
    - Draw methods called by the Renderer.

This module provides the visual layer only — it does NOT control robot
movement.  The MissionExecutor drives state transitions; this module
draws the corresponding animation frames.

Design:
    The animation state machine is updated each frame via ``update(dt)``.
    The Renderer queries ``draw_robot_extras()`` and ``draw_medicine()``
    each frame to overlay animation sprites on the robot body.
"""

from __future__ import annotations

import math
import time
from enum import Enum, auto
from typing import Optional, Tuple

from utilities.logger import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Animation States
# ─────────────────────────────────────────────────────────────────────────────

class AnimationState(Enum):
    """Medicine animation state machine states."""
    IDLE            = auto()   # No animation active
    APPROACHING     = auto()   # Robot moving towards counter
    ALIGNING        = auto()   # Robot aligning with counter/shelf
    ARM_EXTENDING   = auto()   # Arm extending towards medicine
    GRABBING        = auto()   # Gripping the medicine box
    ARM_RETRACTING  = auto()   # Arm retracting with medicine
    CARRYING        = auto()   # Carrying medicine (main transit state)
    DELIVERING      = auto()   # At destination, placing medicine
    DETACHING       = auto()   # Medicine separating from robot
    COMPLETE        = auto()   # Animation complete


# ─────────────────────────────────────────────────────────────────────────────
# Animation Timings (seconds per state)
# ─────────────────────────────────────────────────────────────────────────────

_STATE_DURATION = {
    AnimationState.APPROACHING:     0.5,
    AnimationState.ALIGNING:        0.8,
    AnimationState.ARM_EXTENDING:   1.0,
    AnimationState.GRABBING:        0.5,
    AnimationState.ARM_RETRACTING:  0.8,
    AnimationState.CARRYING:        0.0,   # No auto-advance (stays until delivery)
    AnimationState.DELIVERING:      0.8,
    AnimationState.DETACHING:       0.6,
    AnimationState.COMPLETE:        0.3,
}

# State → next state transition map
_STATE_TRANSITIONS = {
    AnimationState.APPROACHING:    AnimationState.ALIGNING,
    AnimationState.ALIGNING:       AnimationState.ARM_EXTENDING,
    AnimationState.ARM_EXTENDING:  AnimationState.GRABBING,
    AnimationState.GRABBING:       AnimationState.ARM_RETRACTING,
    AnimationState.ARM_RETRACTING: AnimationState.CARRYING,
    # CARRYING → DELIVERING triggered externally by MissionExecutor
    AnimationState.DELIVERING:     AnimationState.DETACHING,
    AnimationState.DETACHING:      AnimationState.COMPLETE,
    AnimationState.COMPLETE:       AnimationState.IDLE,
}


# ─────────────────────────────────────────────────────────────────────────────
# Medicine Animation Controller
# ─────────────────────────────────────────────────────────────────────────────

class MedicineAnimation:
    """Visual animation controller for medicine collection and delivery.

    Usage::

        anim = MedicineAnimation()

        # When robot reaches pharmacy:
        anim.start_collection("Paracetamol")

        # Each frame:
        anim.update(dt)

        # When robot reaches destination:
        anim.start_delivery()

        # Query visual state for rendering:
        arm_progress = anim.arm_extension      # 0.0 – 1.0
        has_box = anim.show_medicine_box        # True/False
        box_alpha = anim.medicine_box_alpha     # 0 – 255

    Attributes:
        state:          Current animation state.
        medicine_name:  Name of the medicine being animated.
        arm_extension:  Normalised arm extension (0.0=retracted, 1.0=extended).
        show_medicine_box: Whether to render the medicine box sprite.
        medicine_box_alpha: Opacity of the medicine box (0–255).
    """

    def __init__(self) -> None:
        self.state: AnimationState = AnimationState.IDLE
        self.medicine_name: str = ""

        # Visual properties
        self.arm_extension: float = 0.0       # 0.0 = retracted, 1.0 = fully extended
        self.show_medicine_box: bool = False
        self.medicine_box_alpha: int = 255
        self.robot_glow_intensity: float = 0.0  # 0.0–1.0 glow during collection

        # Internal timing
        self._state_timer: float = 0.0
        self._state_duration: float = 0.0
        self._total_elapsed: float = 0.0

        log.info("MedicineAnimation initialised.")

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def start_collection(self, medicine_name: str) -> None:
        """Begin the medicine collection animation sequence.

        Args:
            medicine_name: Name of the medicine being collected.
        """
        self.medicine_name = medicine_name
        self._transition_to(AnimationState.APPROACHING)
        log.info("MedicineAnimation: Collection started for '%s'.", medicine_name)

    def start_delivery(self) -> None:
        """Begin the medicine delivery animation sequence.

        Should be called when the robot arrives at the delivery destination.
        """
        if self.state == AnimationState.CARRYING:
            self._transition_to(AnimationState.DELIVERING)
            log.info("MedicineAnimation: Delivery started for '%s'.", self.medicine_name)
        else:
            log.warning("MedicineAnimation: Cannot start delivery — state is %s.", self.state.name)

    def cancel(self) -> None:
        """Cancel the current animation and return to IDLE."""
        self.state = AnimationState.IDLE
        self._reset_visuals()
        log.info("MedicineAnimation: Cancelled.")

    def update(self, dt: float) -> None:
        """Update animation state each frame.

        Args:
            dt: Elapsed time in seconds since last frame.
        """
        if self.state == AnimationState.IDLE:
            return

        self._state_timer += dt
        self._total_elapsed += dt

        # Update visual properties based on current state
        self._update_visuals()

        # Auto-advance if duration exceeded (except CARRYING, which waits)
        if self.state != AnimationState.CARRYING:
            if self._state_timer >= self._state_duration:
                next_state = _STATE_TRANSITIONS.get(self.state)
                if next_state:
                    self._transition_to(next_state)

    @property
    def is_active(self) -> bool:
        """True if an animation is currently running."""
        return self.state != AnimationState.IDLE

    @property
    def is_collecting(self) -> bool:
        """True if in the collection phase (before CARRYING)."""
        return self.state in (
            AnimationState.APPROACHING,
            AnimationState.ALIGNING,
            AnimationState.ARM_EXTENDING,
            AnimationState.GRABBING,
            AnimationState.ARM_RETRACTING,
        )

    @property
    def is_carrying(self) -> bool:
        """True if the robot is carrying medicine."""
        return self.state == AnimationState.CARRYING

    @property
    def is_delivering(self) -> bool:
        """True if in the delivery phase."""
        return self.state in (
            AnimationState.DELIVERING,
            AnimationState.DETACHING,
        )

    @property
    def progress(self) -> float:
        """Current state progress (0.0–1.0)."""
        if self._state_duration <= 0:
            return 1.0
        return min(self._state_timer / self._state_duration, 1.0)

    @property
    def state_display(self) -> str:
        """Human-readable state for dashboard display."""
        name = self.state.name.replace("_", " ").title()
        if self.medicine_name and self.state != AnimationState.IDLE:
            return f"{name}: {self.medicine_name}"
        return name

    # ─────────────────────────────────────────────────────────────────────────
    # Visual Property Updates
    # ─────────────────────────────────────────────────────────────────────────

    def _update_visuals(self) -> None:
        """Update visual properties based on current animation state."""
        progress = self.progress

        if self.state == AnimationState.APPROACHING:
            self.arm_extension = 0.0
            self.show_medicine_box = False
            self.robot_glow_intensity = progress * 0.3

        elif self.state == AnimationState.ALIGNING:
            self.arm_extension = 0.0
            self.show_medicine_box = False
            self.robot_glow_intensity = 0.3 + progress * 0.2

        elif self.state == AnimationState.ARM_EXTENDING:
            # Arm smoothly extends (eased)
            self.arm_extension = self._ease_in_out(progress)
            self.show_medicine_box = False
            self.robot_glow_intensity = 0.5

        elif self.state == AnimationState.GRABBING:
            self.arm_extension = 1.0
            self.show_medicine_box = True
            self.medicine_box_alpha = int(progress * 255)
            self.robot_glow_intensity = 0.7

        elif self.state == AnimationState.ARM_RETRACTING:
            # Arm smoothly retracts
            self.arm_extension = 1.0 - self._ease_in_out(progress)
            self.show_medicine_box = True
            self.medicine_box_alpha = 255
            self.robot_glow_intensity = 0.5 - progress * 0.3

        elif self.state == AnimationState.CARRYING:
            self.arm_extension = 0.0
            self.show_medicine_box = True
            self.medicine_box_alpha = 255
            self.robot_glow_intensity = 0.1
            # Subtle bobbing effect
            bob = math.sin(self._total_elapsed * 2.0) * 0.05
            self.robot_glow_intensity = 0.1 + abs(bob)

        elif self.state == AnimationState.DELIVERING:
            self.arm_extension = self._ease_in_out(progress) * 0.7
            self.show_medicine_box = True
            self.medicine_box_alpha = 255
            self.robot_glow_intensity = progress * 0.5

        elif self.state == AnimationState.DETACHING:
            self.arm_extension = 0.7 * (1.0 - progress)
            self.show_medicine_box = True
            self.medicine_box_alpha = int(255 * (1.0 - progress))
            self.robot_glow_intensity = 0.5 * (1.0 - progress)

        elif self.state == AnimationState.COMPLETE:
            self._reset_visuals()

    def _reset_visuals(self) -> None:
        """Reset all visual properties to defaults."""
        self.arm_extension = 0.0
        self.show_medicine_box = False
        self.medicine_box_alpha = 255
        self.robot_glow_intensity = 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # State Machine
    # ─────────────────────────────────────────────────────────────────────────

    def _transition_to(self, new_state: AnimationState) -> None:
        """Transition to a new animation state."""
        old = self.state
        self.state = new_state
        self._state_timer = 0.0
        self._state_duration = _STATE_DURATION.get(new_state, 0.5)

        if new_state == AnimationState.IDLE:
            self._reset_visuals()
            self._total_elapsed = 0.0

        log.debug("MedicineAnimation: %s → %s", old.name, new_state.name)

    # ─────────────────────────────────────────────────────────────────────────
    # Easing Functions
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _ease_in_out(t: float) -> float:
        """Smooth ease-in-out interpolation (cubic).

        Args:
            t: Progress value (0.0–1.0).

        Returns:
            Eased value (0.0–1.0).
        """
        t = max(0.0, min(1.0, t))
        if t < 0.5:
            return 4.0 * t * t * t
        return 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0

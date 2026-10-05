"""
HospitalRobotNav — Patient Assistance Manager
=================================================
Implements all 8 patient assistance mission types with specialised
behaviour logic for each.

Supported Mission Types:
    1. Medicine Delivery     — Full pickup → navigate → deliver pipeline.
    2. Guide Patient         — Lead patient sprite to destination.
    3. Call Nurse             — Navigate to nurse station, trigger alert, return.
    4. Emergency Response     — High-priority preemptive navigation.
    5. Deliver Reports        — Navigate to lab, collect, deliver to doctor.
    6. Transport Lab Samples  — Bidirectional lab ↔ ward transport.
    7. Bring Wheelchair       — Fetch from storage, deliver to room.
    8. Escort Visitors        — Guide visitor sprite through hospital.

Design:
    Each mission type has a dedicated handler that:
        - Validates the request.
        - Configures specialised parameters (speed, priority).
        - Provides mission-specific dialogue templates.
        - Hooks into the MissionExecutor callbacks.

    The PatientAssistanceManager is the domain expert — it knows
    what a "medicine delivery" actually entails in a hospital context.
    The MissionPlanner handles the generic step decomposition.

ROS2 Deployment Note:
    In production, each mission type would have a dedicated BT
    (Behavior Tree) XML configuration for Nav2 BT Navigator.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from language.command_resolver import MissionRequest, MissionType
from missions.mission_types import TaskType, TaskStep, MissionPlan
from utilities.logger import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Patient Interaction Model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PatientInteraction:
    """Record of a single patient interaction.

    Attributes:
        interaction_id:  Unique identifier.
        patient_ref:     Patient reference string.
        mission_type:    Type of assistance provided.
        location:        Where the interaction occurred.
        timestamp:       When the interaction started.
        duration_sec:    Duration of the interaction.
        outcome:         Result ("success", "cancelled", "failed").
        notes:           Additional notes.
    """
    interaction_id: str = ""
    patient_ref: str = ""
    mission_type: str = ""
    location: str = ""
    timestamp: float = field(default_factory=time.monotonic)
    duration_sec: float = 0.0
    outcome: str = "pending"
    notes: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Mission Type Configurations
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MissionTypeConfig:
    """Configuration for a specific mission type.

    Attributes:
        name:               Display name.
        default_priority:   Default priority if not specified.
        speed_multiplier:   Robot speed modifier (1.0 = normal).
        requires_return:    Whether to return to dock after completion.
        max_duration_sec:   Maximum allowed duration.
        announce_start:     Speech template for mission start.
        announce_complete:  Speech template for mission completion.
    """
    name: str = ""
    default_priority: int = 4
    speed_multiplier: float = 1.0
    requires_return: bool = True
    max_duration_sec: float = 300.0
    announce_start: str = ""
    announce_complete: str = ""


# Per-mission-type configurations
_MISSION_CONFIGS: Dict[MissionType, MissionTypeConfig] = {

    MissionType.MEDICINE_DELIVERY: MissionTypeConfig(
        name="Medicine Delivery",
        default_priority=3,
        speed_multiplier=1.0,
        requires_return=True,
        max_duration_sec=180.0,
        announce_start="Starting medicine delivery. Heading to the pharmacy.",
        announce_complete="Medicine has been successfully delivered.",
    ),

    MissionType.GUIDE_PATIENT: MissionTypeConfig(
        name="Patient Guidance",
        default_priority=3,
        speed_multiplier=0.7,    # Slower pace for patient comfort
        requires_return=True,
        max_duration_sec=240.0,
        announce_start="I'll guide you to your destination. Please follow me.",
        announce_complete="We've arrived. I hope you have a speedy recovery!",
    ),

    MissionType.CALL_NURSE: MissionTypeConfig(
        name="Nurse Call",
        default_priority=2,
        speed_multiplier=1.2,    # Slightly faster for urgency
        requires_return=True,
        max_duration_sec=120.0,
        announce_start="Calling a nurse. I'll fetch help right away.",
        announce_complete="A nurse has been notified and is on the way.",
    ),

    MissionType.EMERGENCY_RESPONSE: MissionTypeConfig(
        name="Emergency Response",
        default_priority=1,      # Highest priority
        speed_multiplier=1.5,    # Maximum safe speed
        requires_return=False,   # Stay at emergency site
        max_duration_sec=60.0,
        announce_start="EMERGENCY! Responding immediately!",
        announce_complete="Emergency response complete. Standing by.",
    ),

    MissionType.DELIVER_REPORT: MissionTypeConfig(
        name="Report Delivery",
        default_priority=3,
        speed_multiplier=1.0,
        requires_return=True,
        max_duration_sec=180.0,
        announce_start="Heading to collect the lab report.",
        announce_complete="Report has been delivered successfully.",
    ),

    MissionType.TRANSPORT_SAMPLE: MissionTypeConfig(
        name="Sample Transport",
        default_priority=2,      # Time-sensitive
        speed_multiplier=0.9,    # Careful handling
        requires_return=True,
        max_duration_sec=180.0,
        announce_start="Starting sample transport. Handling with care.",
        announce_complete="Sample has been delivered to the laboratory.",
    ),

    MissionType.FETCH_WHEELCHAIR: MissionTypeConfig(
        name="Wheelchair Delivery",
        default_priority=3,
        speed_multiplier=0.8,    # Slower with large item
        requires_return=True,
        max_duration_sec=180.0,
        announce_start="Fetching a wheelchair. I'll be right back.",
        announce_complete="Wheelchair delivered. Please let me know if you need more help.",
    ),

    MissionType.ESCORT_VISITOR: MissionTypeConfig(
        name="Visitor Escort",
        default_priority=4,
        speed_multiplier=0.7,    # Comfortable pace for visitors
        requires_return=True,
        max_duration_sec=240.0,
        announce_start="Welcome! I'll escort you to your destination.",
        announce_complete="Here we are. I hope you have a pleasant visit!",
    ),

    MissionType.NAVIGATE: MissionTypeConfig(
        name="Navigation",
        default_priority=4,
        speed_multiplier=1.0,
        requires_return=False,
        max_duration_sec=120.0,
        announce_start="Navigating to the destination.",
        announce_complete="Arrived at the destination.",
    ),

    MissionType.RETURN_TO_DOCK: MissionTypeConfig(
        name="Return to Dock",
        default_priority=5,
        speed_multiplier=0.8,
        requires_return=False,
        max_duration_sec=120.0,
        announce_start="Returning to the charging dock.",
        announce_complete="Docked at the charging station.",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Patient Assistance Manager
# ─────────────────────────────────────────────────────────────────────────────

class PatientAssistanceManager:
    """Domain expert for patient assistance mission types.

    Provides:
        - Mission type validation and configuration.
        - Specialised pre/post-mission logic.
        - Patient interaction history tracking.
        - Speech templates per mission type.
        - Speed multiplier and priority overrides.

    Usage::

        pam = PatientAssistanceManager()

        # Get config for a mission type
        config = pam.get_config(MissionType.MEDICINE_DELIVERY)

        # Validate a mission request
        is_valid, error = pam.validate(request)

        # Record an interaction
        pam.record_interaction(patient="P-123", mission_type="MEDICINE_DELIVERY")

    Attributes:
        interactions:    List of recorded patient interactions.
        active_escorts:  Count of currently active escort missions.
    """

    def __init__(self) -> None:
        self.interactions: List[PatientInteraction] = []
        self.active_escorts: int = 0
        self._interaction_counter: int = 0

        # Statistics per mission type
        self.stats: Dict[str, Dict[str, int]] = {
            mt.name: {"started": 0, "completed": 0, "failed": 0}
            for mt in MissionType
        }

        log.info("PatientAssistanceManager initialised.")

    def get_config(self, mission_type: MissionType) -> MissionTypeConfig:
        """Get the configuration for a mission type.

        Args:
            mission_type: The mission type to look up.

        Returns:
            MissionTypeConfig with parameters and templates.
        """
        return _MISSION_CONFIGS.get(mission_type, MissionTypeConfig(name=mission_type.name))

    def validate(self, request: MissionRequest) -> Tuple[bool, str]:
        """Validate a mission request for feasibility.

        Checks:
            - Mission type is supported.
            - Required fields are present.
            - Robot is not already at capacity (for escorts).

        Args:
            request: The mission request to validate.

        Returns:
            Tuple of (is_valid, error_message).
        """
        config = _MISSION_CONFIGS.get(request.mission_type)
        if config is None:
            return False, f"Unsupported mission type: {request.mission_type.name}"

        # Check escort capacity (max 1 escort at a time)
        if request.mission_type in (MissionType.GUIDE_PATIENT, MissionType.ESCORT_VISITOR):
            if self.active_escorts >= 1:
                return False, "Already escorting someone. Please wait."

        # Check for required delivery location
        if request.mission_type != MissionType.RETURN_TO_DOCK:
            if not request.delivery_location:
                return False, "No destination specified."

        return True, ""

    def on_mission_start(self, request: MissionRequest) -> None:
        """Called when a mission starts.

        Args:
            request: The starting mission request.
        """
        mt_name = request.mission_type.name
        self.stats[mt_name]["started"] += 1

        if request.mission_type in (MissionType.GUIDE_PATIENT, MissionType.ESCORT_VISITOR):
            self.active_escorts += 1

        self.record_interaction(
            patient_ref=request.patient_name or "unknown",
            mission_type=mt_name,
            location=request.delivery_location,
        )

        log.info("PatientAssistance: Mission started — %s", mt_name)

    def on_mission_complete(self, request: MissionRequest) -> None:
        """Called when a mission completes successfully.

        Args:
            request: The completed mission request.
        """
        mt_name = request.mission_type.name
        self.stats[mt_name]["completed"] += 1

        if request.mission_type in (MissionType.GUIDE_PATIENT, MissionType.ESCORT_VISITOR):
            self.active_escorts = max(0, self.active_escorts - 1)

        # Update the latest interaction outcome
        if self.interactions:
            self.interactions[-1].outcome = "success"

        log.info("PatientAssistance: Mission completed — %s", mt_name)

    def on_mission_failed(self, request: MissionRequest, reason: str) -> None:
        """Called when a mission fails.

        Args:
            request: The failed mission request.
            reason: Failure reason.
        """
        mt_name = request.mission_type.name
        self.stats[mt_name]["failed"] += 1

        if request.mission_type in (MissionType.GUIDE_PATIENT, MissionType.ESCORT_VISITOR):
            self.active_escorts = max(0, self.active_escorts - 1)

        if self.interactions:
            self.interactions[-1].outcome = "failed"
            self.interactions[-1].notes = reason

        log.warning("PatientAssistance: Mission failed — %s: %s", mt_name, reason)

    def record_interaction(
        self,
        patient_ref: str = "",
        mission_type: str = "",
        location: str = "",
    ) -> PatientInteraction:
        """Record a patient interaction in the audit trail.

        Args:
            patient_ref: Patient identifier.
            mission_type: Type of assistance.
            location: Where the interaction occurred.

        Returns:
            The recorded PatientInteraction.
        """
        self._interaction_counter += 1
        interaction = PatientInteraction(
            interaction_id=f"INT-{self._interaction_counter:04d}",
            patient_ref=patient_ref,
            mission_type=mission_type,
            location=location,
        )
        self.interactions.append(interaction)

        # Keep history bounded
        if len(self.interactions) > 500:
            self.interactions = self.interactions[-250:]

        return interaction

    def get_start_announcement(self, mission_type: MissionType) -> str:
        """Get the start announcement for a mission type.

        Args:
            mission_type: The mission type.

        Returns:
            Announcement text.
        """
        config = self.get_config(mission_type)
        return config.announce_start

    def get_completion_announcement(self, mission_type: MissionType) -> str:
        """Get the completion announcement for a mission type.

        Args:
            mission_type: The mission type.

        Returns:
            Announcement text.
        """
        config = self.get_config(mission_type)
        return config.announce_complete

    def get_speed_multiplier(self, mission_type: MissionType) -> float:
        """Get the speed multiplier for a mission type.

        Args:
            mission_type: The mission type.

        Returns:
            Speed multiplier (1.0 = normal).
        """
        config = self.get_config(mission_type)
        return config.speed_multiplier

    def get_statistics_summary(self) -> Dict[str, Dict[str, int]]:
        """Get a summary of all mission type statistics.

        Returns:
            Dict mapping mission type names to started/completed/failed counts.
        """
        return dict(self.stats)

    @property
    def total_interactions(self) -> int:
        """Total number of recorded patient interactions."""
        return len(self.interactions)

    @property
    def total_completed(self) -> int:
        """Total completed missions across all types."""
        return sum(v["completed"] for v in self.stats.values())

    @property
    def success_rate(self) -> float:
        """Overall mission success rate (0.0–1.0)."""
        total = sum(v["completed"] + v["failed"] for v in self.stats.values())
        if total == 0:
            return 1.0
        completed = sum(v["completed"] for v in self.stats.values())
        return completed / total

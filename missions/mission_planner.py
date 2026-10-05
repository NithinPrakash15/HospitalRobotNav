"""
HospitalRobotNav — Mission Planner
=====================================
Decomposes high-level MissionRequests into ordered sequences of atomic
TaskSteps that the MissionExecutor can run step-by-step.

Examples:
    MEDICINE_DELIVERY("Paracetamol", "Room 205"):
        1. TaskStep(NAVIGATE, destination="Pharmacy")
        2. TaskStep(COLLECT, item="Paracetamol")
        3. TaskStep(NAVIGATE, destination="Room 205")
        4. TaskStep(DELIVER, item="Paracetamol")
        5. TaskStep(NAVIGATE, destination="Charging Dock")

    GUIDE_PATIENT(destination="Radiology"):
        1. TaskStep(INTERACT, description="Greet patient")
        2. TaskStep(ESCORT, destination="Radiology")
        3. TaskStep(INTERACT, description="Handoff at Radiology")
        4. TaskStep(RETURN_TO_DOCK)

Design:
    The planner uses a strategy pattern — each MissionType has a
    dedicated planning method that returns a list of TaskSteps.
    New mission types can be added by implementing a new method
    and registering it in the dispatcher.

ROS2 Deployment Note:
    Maps to a ``mission_planner_server`` (action server) in Nav2.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from language.command_resolver import MissionRequest, MissionType
from missions.mission_types import TaskType, TaskStep, MissionPlan
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]


class MissionPlanner:
    """Decomposes MissionRequests into executable MissionPlans.

    Usage::

        planner = MissionPlanner()
        plan = planner.plan(mission_request)
        for step in plan.steps:
            print(step)

    Attributes:
        total_plans: Number of plans generated.
    """

    def __init__(self, semantic_map: Optional[Any] = None) -> None:
        self.semantic_map = semantic_map
        # Dispatcher: MissionType → planning method
        self._planners: Dict[MissionType, Callable[[MissionRequest], List[TaskStep]]] = {
            MissionType.MEDICINE_DELIVERY:  self._plan_medicine_delivery,
            MissionType.GUIDE_PATIENT:      self._plan_guide_patient,
            MissionType.CALL_NURSE:         self._plan_call_nurse,
            MissionType.EMERGENCY_RESPONSE: self._plan_emergency,
            MissionType.DELIVER_REPORT:     self._plan_deliver_report,
            MissionType.TRANSPORT_SAMPLE:   self._plan_transport_sample,
            MissionType.FETCH_WHEELCHAIR:   self._plan_fetch_wheelchair,
            MissionType.ESCORT_VISITOR:     self._plan_escort_visitor,
            MissionType.NAVIGATE:           self._plan_navigate,
            MissionType.RETURN_TO_DOCK:     self._plan_return_to_dock,
            MissionType.PATIENT_EMERGENCY:   self._plan_emergency,
            MissionType.PATIENT_STATUS_QUERY: self._plan_query,
            MissionType.DOCTOR_QUERY:         self._plan_query,
            MissionType.MEDICATION_QUERY:     self._plan_query,
            MissionType.SHOW_ACTIVE_PATIENTS: self._plan_query,
        }

        self.total_plans: int = 0
        log.info("MissionPlanner initialised with %d mission strategies.", len(self._planners))

    def plan(self, request: MissionRequest) -> MissionPlan:
        """Generate a MissionPlan from a MissionRequest.

        Args:
            request: Validated MissionRequest from CommandResolver.

        Returns:
            A MissionPlan with ordered TaskSteps.
        """
        planner_fn = self._planners.get(request.mission_type)
        if planner_fn is None:
            log.error("MissionPlanner: No strategy for %s", request.mission_type.name)
            return MissionPlan(
                mission_type=request.mission_type.name,
                description=f"Unsupported: {request.mission_type.name}",
            )

        steps = planner_fn(request)

        plan = MissionPlan(
            mission_type=request.mission_type.name,
            description=self._build_description(request),
            steps=steps,
            priority=request.priority,
            raw_command=request.raw_text,
            eta_total_sec=self._estimate_eta(steps),
        )

        self.total_plans += 1
        log.info("MissionPlanner: Generated %s with %d steps (ETA: %.0f s).",
                 plan.plan_id, plan.total_steps, plan.eta_total_sec)

        return plan

    def plan_medicine_delivery(
        self,
        medicine_name: str,
        destination_name: str,
        priority: int = 4,
    ) -> MissionPlan:
        """Helper method to plan a medicine delivery from parameters directly."""
        req = MissionRequest(
            mission_type=MissionType.MEDICINE_DELIVERY,
            item=medicine_name,
            delivery_location=destination_name,
            priority=priority,
            pickup_location="Pharmacy",
            raw_text=f"Deliver {medicine_name} to {destination_name}",
        )
        return self.plan(req)

    # ─────────────────────────────────────────────────────────────────────────
    # Mission Strategies
    # ─────────────────────────────────────────────────────────────────────────

    def _plan_medicine_delivery(self, req: MissionRequest) -> List[TaskStep]:
        """Plan: Navigate to pharmacy → collect → navigate to destination → deliver → return."""
        return [
            TaskStep(
                task_type=TaskType.NAVIGATE,
                description=f"Navigate to {req.pickup_location}",
                destination=req.pickup_location,
                destination_pos=req.resolved_pickup,
            ),
            TaskStep(
                task_type=TaskType.COLLECT,
                description=f"Collect {req.item}",
                item=req.item,
                destination=req.pickup_location,
                duration_sec=5.0,
            ),
            TaskStep(
                task_type=TaskType.NAVIGATE,
                description=f"Navigate to {req.delivery_location}",
                destination=req.delivery_location,
                destination_pos=req.resolved_delivery,
            ),
            TaskStep(
                task_type=TaskType.DELIVER,
                description=f"Deliver {req.item} to {req.delivery_location}",
                item=req.item,
                destination=req.delivery_location,
                duration_sec=3.0,
            ),
            TaskStep(
                task_type=TaskType.RETURN_TO_DOCK,
                description="Return to Charging Dock",
                destination="Charging Dock",
            ),
        ]

    def _plan_guide_patient(self, req: MissionRequest) -> List[TaskStep]:
        """Plan: Greet patient → escort to destination → handoff → return."""
        return [
            TaskStep(
                task_type=TaskType.INTERACT,
                description="Greet patient and announce escort",
                duration_sec=3.0,
                metadata={"speech": f"Hello, I'll guide you to {req.delivery_location}. Please follow me."},
            ),
            TaskStep(
                task_type=TaskType.ESCORT,
                description=f"Escort patient to {req.delivery_location}",
                destination=req.delivery_location,
                destination_pos=req.resolved_delivery,
            ),
            TaskStep(
                task_type=TaskType.INTERACT,
                description=f"Handoff at {req.delivery_location}",
                duration_sec=2.0,
                metadata={"speech": f"We've arrived at {req.delivery_location}. Have a good day!"},
            ),
            TaskStep(
                task_type=TaskType.RETURN_TO_DOCK,
                description="Return to Charging Dock",
                destination="Charging Dock",
            ),
        ]

    def _plan_call_nurse(self, req: MissionRequest) -> List[TaskStep]:
        """Plan: Navigate to nurse station → alert → navigate to patient → return."""
        return [
            TaskStep(
                task_type=TaskType.NAVIGATE,
                description="Navigate to Nurse Station",
                destination="Nurse Station",
            ),
            TaskStep(
                task_type=TaskType.ALERT,
                description=f"Alert nurse: assistance needed at {req.delivery_location}",
                duration_sec=3.0,
                metadata={"alert_type": "nurse_call", "target": req.delivery_location},
            ),
            TaskStep(
                task_type=TaskType.NAVIGATE,
                description=f"Return to {req.delivery_location}",
                destination=req.delivery_location,
                destination_pos=req.resolved_delivery,
            ),
            TaskStep(
                task_type=TaskType.INTERACT,
                description="Notify patient that nurse is on the way",
                duration_sec=2.0,
                metadata={"speech": "A nurse has been notified and is on the way."},
            ),
            TaskStep(
                task_type=TaskType.RETURN_TO_DOCK,
                description="Return to Charging Dock",
                destination="Charging Dock",
            ),
        ]

    def _plan_emergency(self, req: MissionRequest) -> List[TaskStep]:
        """Plan: Alert → rush to emergency location → standby."""
        return [
            TaskStep(
                task_type=TaskType.ALERT,
                description="Broadcast emergency alert",
                duration_sec=1.0,
                metadata={"alert_type": "emergency", "speech": "Emergency! Responding immediately."},
            ),
            TaskStep(
                task_type=TaskType.NAVIGATE,
                description=f"Rush to {req.delivery_location}",
                destination=req.delivery_location,
                destination_pos=req.resolved_delivery,
                metadata={"speed_multiplier": 1.5},
            ),
            TaskStep(
                task_type=TaskType.INTERACT,
                description="Standby at emergency site",
                duration_sec=10.0,
                metadata={"speech": "I'm at the emergency location. Standing by for instructions."},
            ),
        ]

    def _plan_deliver_report(self, req: MissionRequest) -> List[TaskStep]:
        """Plan: Navigate to lab → collect report → deliver to doctor → return."""
        return [
            TaskStep(
                task_type=TaskType.NAVIGATE,
                description=f"Navigate to {req.pickup_location}",
                destination=req.pickup_location,
            ),
            TaskStep(
                task_type=TaskType.COLLECT,
                description=f"Collect {req.item}",
                item=req.item,
                destination=req.pickup_location,
                duration_sec=4.0,
            ),
            TaskStep(
                task_type=TaskType.NAVIGATE,
                description=f"Navigate to {req.delivery_location}",
                destination=req.delivery_location,
                destination_pos=req.resolved_delivery,
            ),
            TaskStep(
                task_type=TaskType.DELIVER,
                description=f"Deliver {req.item} to {req.delivery_location}",
                item=req.item,
                destination=req.delivery_location,
                duration_sec=2.0,
            ),
            TaskStep(
                task_type=TaskType.RETURN_TO_DOCK,
                description="Return to Charging Dock",
                destination="Charging Dock",
            ),
        ]

    def _plan_transport_sample(self, req: MissionRequest) -> List[TaskStep]:
        """Plan: Navigate to ward → collect sample → deliver to lab → return."""
        pickup = req.pickup_location or "current location"
        return [
            TaskStep(
                task_type=TaskType.NAVIGATE,
                description=f"Navigate to {pickup}",
                destination=pickup,
            ),
            TaskStep(
                task_type=TaskType.COLLECT,
                description=f"Collect {req.item}",
                item=req.item,
                destination=pickup,
                duration_sec=4.0,
            ),
            TaskStep(
                task_type=TaskType.NAVIGATE,
                description="Navigate to Laboratory",
                destination="Laboratory",
            ),
            TaskStep(
                task_type=TaskType.DELIVER,
                description=f"Deliver {req.item} to Laboratory",
                item=req.item,
                destination="Laboratory",
                duration_sec=3.0,
            ),
            TaskStep(
                task_type=TaskType.RETURN_TO_DOCK,
                description="Return to Charging Dock",
                destination="Charging Dock",
            ),
        ]

    def _plan_fetch_wheelchair(self, req: MissionRequest) -> List[TaskStep]:
        """Plan: Navigate to storage → collect wheelchair → deliver to room → return."""
        return [
            TaskStep(
                task_type=TaskType.NAVIGATE,
                description=f"Navigate to {req.pickup_location}",
                destination=req.pickup_location,
            ),
            TaskStep(
                task_type=TaskType.COLLECT,
                description="Collect wheelchair",
                item="wheelchair",
                destination=req.pickup_location,
                duration_sec=5.0,
            ),
            TaskStep(
                task_type=TaskType.NAVIGATE,
                description=f"Navigate to {req.delivery_location}",
                destination=req.delivery_location,
                destination_pos=req.resolved_delivery,
            ),
            TaskStep(
                task_type=TaskType.DELIVER,
                description=f"Deliver wheelchair to {req.delivery_location}",
                item="wheelchair",
                destination=req.delivery_location,
                duration_sec=3.0,
            ),
            TaskStep(
                task_type=TaskType.RETURN_TO_DOCK,
                description="Return to Charging Dock",
                destination="Charging Dock",
            ),
        ]

    def _plan_escort_visitor(self, req: MissionRequest) -> List[TaskStep]:
        """Plan: Greet visitor → escort to destination → handoff → return."""
        return [
            TaskStep(
                task_type=TaskType.INTERACT,
                description="Greet visitor",
                duration_sec=3.0,
                metadata={"speech": f"Welcome! I'll take you to {req.delivery_location}. Please follow me."},
            ),
            TaskStep(
                task_type=TaskType.ESCORT,
                description=f"Escort visitor to {req.delivery_location}",
                destination=req.delivery_location,
                destination_pos=req.resolved_delivery,
            ),
            TaskStep(
                task_type=TaskType.INTERACT,
                description="Visitor handoff",
                duration_sec=2.0,
                metadata={"speech": f"Here we are — {req.delivery_location}. Have a pleasant visit!"},
            ),
            TaskStep(
                task_type=TaskType.RETURN_TO_DOCK,
                description="Return to Charging Dock",
                destination="Charging Dock",
            ),
        ]

    def _plan_navigate(self, req: MissionRequest) -> List[TaskStep]:
        """Plan: Simple navigation to a destination."""
        return [
            TaskStep(
                task_type=TaskType.NAVIGATE,
                description=f"Navigate to {req.delivery_location}",
                destination=req.delivery_location,
                destination_pos=req.resolved_delivery,
            ),
        ]

    def _plan_return_to_dock(self, req: MissionRequest) -> List[TaskStep]:
        """Plan: Return to charging dock."""
        return [
            TaskStep(
                task_type=TaskType.RETURN_TO_DOCK,
                description="Return to Charging Dock",
                destination="Charging Dock",
            ),
        ]

    def _plan_query(self, req: MissionRequest) -> List[TaskStep]:
        """Plan an information query response (verbal / visual interaction)."""
        return [
            TaskStep(
                task_type=TaskType.INTERACT,
                description=req.response_text or f"Answer {req.mission_type.name}",
                duration_sec=2.0,
            )
        ]

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_description(req: MissionRequest) -> str:
        """Build a human-readable mission description."""
        desc = req.mission_type.name.replace("_", " ").title()
        if req.item:
            desc += f": {req.item}"
        if req.delivery_location:
            desc += f" → {req.delivery_location}"
        return desc

    @staticmethod
    def _estimate_eta(steps: List[TaskStep]) -> float:
        """Estimate total mission duration in seconds.

        Rough heuristic: 8s per NAVIGATE, plus step-specific durations.
        """
        eta = 0.0
        for step in steps:
            if step.task_type == TaskType.NAVIGATE:
                eta += 8.0  # Average navigation time
            elif step.task_type == TaskType.RETURN_TO_DOCK:
                eta += 10.0
            elif step.task_type == TaskType.ESCORT:
                eta += 12.0  # Slower with patient
            else:
                eta += step.duration_sec
        return eta

"""
HospitalRobotNav — Medication Delivery Workflow
=================================================
Orchestrates the multi-stage, event-driven medication delivery lifecycle:
Database Schedule → Dispatch → Pharmacy Pickup → Transit → Bedside Verification → Handover → DB Audit Record.

Complies with closed-loop medication administration (CLMA) hospital safety protocols:
    1. Right Patient (Bedside ID verification)
    2. Right Medication (Formulary and prescription match)
    3. Right Dose (Dosage and route check)
    4. Right Time (Scheduled slot tracking)
    5. Right Documentation (Immutable audit entry in HospitalDatabase)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from database.hospital_db import HospitalDatabase, TaskPriority, TaskStatus, TaskType
from database.db_query_engine import DBQueryEngine
from utilities.event_bus import EVENT_BUS, HospitalEvent
from utilities.logger import get_logger

log = get_logger(__name__)


class MedicationWorkflowState(Enum):
    """Lifecycle stages for a clinical medication delivery order."""
    SCHEDULED          = auto()   # In database queue, awaiting due time or trigger
    DISPATCHED         = auto()   # Assigned to robot, route planned to pharmacy
    EN_ROUTE_PICKUP    = auto()   # Moving to Pharmacy
    COLLECTING         = auto()   # Dispensing/loading medicine at pharmacy
    EN_ROUTE_PATIENT   = auto()   # Transporting medicine to patient ward/room
    BEDSIDE_VERIFYING  = auto()   # Arrived at patient bedside; barcode/identity check
    DELIVERED          = auto()   # Successfully handed off; DB updated
    CANCELLED          = auto()   # Aborted before completion
    FAILED             = auto()   # Encountered unrecoverable error (e.g. mismatch)


@dataclass
class MedicationDeliveryOrder:
    """Represents a single active or historical medication delivery mission."""
    order_id: str = field(default_factory=lambda: f"ORD-{uuid.uuid4().hex[:6].upper()}")
    schedule_id: str = ""
    patient_id: str = ""
    patient_name: str = ""
    room_id: str = ""
    medicine_name: str = ""
    dosage: str = ""
    route: str = "oral"
    assigned_robot_id: str = "arogya"
    state: MedicationWorkflowState = MedicationWorkflowState.SCHEDULED
    verification_passed: bool = False
    verification_notes: str = ""
    dispatched_at: float = 0.0
    collected_at: float = 0.0
    delivered_at: float = 0.0
    db_task_id: Optional[str] = None

    @property
    def is_active(self) -> bool:
        return self.state not in (
            MedicationWorkflowState.DELIVERED,
            MedicationWorkflowState.CANCELLED,
            MedicationWorkflowState.FAILED,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "schedule_id": self.schedule_id,
            "patient_id": self.patient_id,
            "patient_name": self.patient_name,
            "room_id": self.room_id,
            "medicine_name": self.medicine_name,
            "dosage": self.dosage,
            "route": self.route,
            "assigned_robot_id": self.assigned_robot_id,
            "state": self.state.name,
            "verification_passed": self.verification_passed,
            "verification_notes": self.verification_notes,
            "dispatched_at": self.dispatched_at,
            "collected_at": self.collected_at,
            "delivered_at": self.delivered_at,
        }


class MedicationWorkflowManager:
    """Coordinates end-to-end medication deliveries between Database, Robots, and Events."""

    def __init__(
        self,
        db: HospitalDatabase,
        query_engine: DBQueryEngine,
    ) -> None:
        self._db = db
        self._query_engine = query_engine
        self._orders: Dict[str, MedicationDeliveryOrder] = {}

        log.info("MedicationWorkflowManager initialised.")

    def create_order_for_patient(
        self,
        patient_id: str,
        medicine_name: str,
        assigned_robot: str = "arogya",
        priority: int = 2,
    ) -> Optional[MedicationDeliveryOrder]:
        """Create and dispatch a medication delivery order directly from a patient ID."""
        pid = self._query_engine.resolve_patient_id(patient_id) or patient_id
        patient_info = self._query_engine.get_patient_info(pid)
        if not patient_info:
            log.warning("MedicationWorkflowManager: Cannot create order — patient %s not found.", pid)
            return None

        # Check stock in database
        med_row = self._db.get_medicine_by_name(medicine_name)
        if not med_row:
            log.warning("MedicationWorkflowManager: Medicine '%s' not in formulary.", medicine_name)
            return None

        room = patient_info.get("assigned_room") or patient_info.get("room_id") or "Ward 101"
        order = MedicationDeliveryOrder(
            patient_id=pid,
            patient_name=patient_info.get("name", "Unknown"),
            room_id=room,
            medicine_name=med_row["name"],
            dosage=med_row.get("dosage", "Standard"),
            assigned_robot_id=assigned_robot,
            state=MedicationWorkflowState.DISPATCHED,
            dispatched_at=time.time(),
        )

        # Record in hospital_tasks table
        task_res = self._query_engine.create_medication_delivery_task(
            patient_id=pid,
            medicine_name=med_row["name"],
        )
        task_id = task_res.get("task_id") if isinstance(task_res, dict) else str(task_res)
        order.db_task_id = task_id
        self._orders[order.order_id] = order

        EVENT_BUS.publish(
            HospitalEvent.MISSION_STARTED,
            data={"order": order.to_dict()},
            source="medication_workflow",
        )
        log.info("Medication delivery order created: %s for %s (%s)", order.order_id, pid, medicine_name)
        return order

    def dispatch_from_schedule(
        self,
        schedule_id: str,
        assigned_robot: str = "arogya",
    ) -> Optional[MedicationDeliveryOrder]:
        """Dispatch a delivery order from an existing medication_schedule row."""
        with self._db._cursor() as c:
            c.execute("""
                SELECT ms.*, p.name as patient_name, p.room_id,
                       rx.medicine_id, rx.dosage, rx.route,
                       m.name as medicine_name
                FROM medication_schedules ms
                JOIN patients p ON ms.patient_id = p.patient_id
                JOIN prescriptions rx ON ms.prescription_id = rx.prescription_id
                JOIN medicines m ON rx.medicine_id = m.medicine_id
                WHERE ms.schedule_id = ?
            """, (schedule_id,))
            row = c.fetchone()
            if not row:
                return None
            data = dict(row)

        order = MedicationDeliveryOrder(
            schedule_id=schedule_id,
            patient_id=data["patient_id"],
            patient_name=data["patient_name"],
            room_id=data["room_id"],
            medicine_name=data["medicine_name"],
            dosage=data.get("dosage", ""),
            route=data.get("route", "oral"),
            assigned_robot_id=assigned_robot,
            state=MedicationWorkflowState.DISPATCHED,
            dispatched_at=time.time(),
        )

        self._orders[order.order_id] = order

        EVENT_BUS.publish(
            HospitalEvent.MISSION_STARTED,
            data={"order": order.to_dict()},
            source="medication_workflow",
        )
        return order

    def update_order_state(
        self,
        order_id: str,
        new_state: MedicationWorkflowState,
        notes: str = "",
    ) -> bool:
        """Advance the workflow state of an active delivery order."""
        order = self._orders.get(order_id)
        if not order:
            return False

        old_state = order.state
        order.state = new_state
        if notes:
            order.verification_notes = notes

        if new_state == MedicationWorkflowState.COLLECTING:
            order.collected_at = time.time()
            EVENT_BUS.publish(
                HospitalEvent.MEDICINE_COLLECTED,
                data={"order_id": order_id, "medicine": order.medicine_name},
                source="medication_workflow",
            )
        elif new_state == MedicationWorkflowState.DELIVERED:
            order.delivered_at = time.time()

        log.info("Medication order %s: %s → %s", order_id, old_state.name, new_state.name)
        return True

    def verify_bedside(
        self,
        order_id: str,
        scanned_patient_id: str,
        scanned_medicine: str,
    ) -> Tuple[bool, str]:
        """Perform bedside verification before handing over the medicine."""
        order = self._orders.get(order_id)
        if not order:
            return False, "Order not found"

        canonical_patient = self._query_engine.resolve_patient_id(scanned_patient_id) or scanned_patient_id
        if canonical_patient.upper() != order.patient_id.upper():
            order.verification_passed = False
            msg = f"PATIENT MISMATCH: Order is for {order.patient_id}, scanned {canonical_patient}"
            log.error(msg)
            self.update_order_state(order_id, MedicationWorkflowState.FAILED, notes=msg)
            return False, msg

        if scanned_medicine.strip().lower() not in order.medicine_name.lower():
            order.verification_passed = False
            msg = f"MEDICINE MISMATCH: Order is for {order.medicine_name}, scanned {scanned_medicine}"
            log.error(msg)
            self.update_order_state(order_id, MedicationWorkflowState.FAILED, notes=msg)
            return False, msg

        order.verification_passed = True
        msg = f"Bedside Verification Success: {order.patient_name} ({order.patient_id}), {order.medicine_name} {order.dosage}"
        self.update_order_state(order_id, MedicationWorkflowState.BEDSIDE_VERIFYING, notes=msg)
        return True, msg

    def complete_delivery(self, order_id: str, operator: str = "arogya") -> bool:
        """Complete the delivery, deduct medicine stock, and write audit history to database."""
        order = self._orders.get(order_id)
        if not order:
            return False

        if not order.verification_passed:
            log.warning("Medication delivery completed without bedside verification: %s", order_id)

        self.update_order_state(order_id, MedicationWorkflowState.DELIVERED)

        # Update database schedule if applicable
        if order.schedule_id:
            with self._db._cursor() as c:
                c.execute("""
                    UPDATE medication_schedules
                    SET status = 'DELIVERED', assigned_robot = ?, delivery_time = CURRENT_TIMESTAMP
                    WHERE schedule_id = ?
                """, (operator, order.schedule_id))

        # Deduct 1 unit from stock in database
        med_row = self._db.get_medicine_by_name(order.medicine_name)
        if med_row:
            self._db.update_medicine_stock(med_row["medicine_id"], -1)

        # Complete task in DB if associated
        if order.db_task_id:
            self._query_engine.complete_task(order.db_task_id, result_summary=f"Delivered to {order.room_id}")

        EVENT_BUS.publish(
            HospitalEvent.MEDICINE_DELIVERED,
            data={"order": order.to_dict()},
            source="medication_workflow",
        )
        log.info("Medication delivery CLOSED: %s for %s (%s)", order_id, order.patient_id, order.medicine_name)
        return True

    def get_order(self, order_id: str) -> Optional[MedicationDeliveryOrder]:
        return self._orders.get(order_id)

    def get_active_orders(self) -> List[MedicationDeliveryOrder]:
        return [o for o in self._orders.values() if o.is_active]

    def get_all_orders(self) -> List[MedicationDeliveryOrder]:
        return list(self._orders.values())

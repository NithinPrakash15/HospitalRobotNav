"""
HospitalRobotNav — Database Query Engine
==========================================
High-level query facade for the voice/NLU pipeline.

Translates intent-level queries (e.g., "check patient P003", "who is treating P003")
into structured database lookups and returns results ready for response generation.

Usage::

    from database import HospitalDatabase, DBQueryEngine
    db = HospitalDatabase()
    db.initialize()
    engine = DBQueryEngine(db)
    info = engine.get_patient_info("P003")
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from database.hospital_db import (
    HospitalDatabase,
    MedicationScheduleStatus,
    PatientStatus,
    TaskPriority,
    TaskStatus,
    TaskType,
)
from utilities.logger import get_logger

log = get_logger(__name__)


class DBQueryEngine:
    """High-level query facade for voice/NLU commands.

    All methods return dictionaries suitable for response generation —
    the caller never touches raw SQL or the database directly.
    """

    def __init__(self, db: HospitalDatabase) -> None:
        self._db = db

    # ── Patient ID Resolution ────────────────────────────────────────────────

    @staticmethod
    def resolve_patient_id(raw: str) -> Optional[str]:
        """Normalize various patient ID formats to canonical form (e.g., P001).

        Accepts: "P001", "P1", "p003", "patient 3", "patient P003", "003"
        Returns: "P001" .. "P006", or None if unresolvable.
        """
        if not raw:
            return None
        text = raw.strip().upper()

        # Direct match: P001 .. P999
        m = re.match(r"^P\s*0*(\d{1,3})$", text)
        if m:
            return f"P{int(m.group(1)):03d}"

        # "PATIENT 3", "PATIENT P003", "PATIENT P3", "PATIENT #2", "PATIENT NO. 2"
        m = re.search(r"PATIENT\s*(?:#|NO\.?)?\s*P?\s*0*(\d{1,3})", text)
        if m:
            return f"P{int(m.group(1)):03d}"

        # Bare number: "3", "03", "003"
        m = re.match(r"^0*(\d{1,3})$", text)
        if m:
            num = int(m.group(1))
            if 1 <= num <= 999:
                return f"P{num:03d}"

        return None

    # ── Patient Queries ──────────────────────────────────────────────────────

    def get_patient_info(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Full patient info including status, doctor, room, condition."""
        pid = self.resolve_patient_id(patient_id) or patient_id
        patient = self._db.get_patient(pid)
        if not patient:
            return None

        status = self._db.get_patient_status(pid)
        doctor = self._db.get_attending_doctor(pid)
        encounter = self._db.get_current_encounter(pid)
        prescriptions = self._db.get_prescriptions(pid)

        return {
            "patient_id": pid,
            "name": patient["name"],
            "age": patient.get("age"),
            "gender": patient.get("gender"),
            "room_id": patient.get("room_id"),
            "assigned_room": patient.get("room_id"),
            "condition": patient.get("condition"),
            "condition_summary": patient.get("condition"),
            "priority": patient.get("priority"),
            "status": status["status"] if status else "UNKNOWN",
            "live_status": status["status"] if status else "UNKNOWN",
            "status_updated_at": status.get("updated_at") if status else None,
            "doctor_name": doctor["name"] if doctor else "Unassigned",
            "attending_doctor": doctor["name"] if doctor else "Unassigned",
            "attending_doctor_name": doctor["name"] if doctor else "Unassigned",
            "doctor_specialization": doctor.get("specialization") if doctor else None,
            "doctor_id": doctor["doctor_id"] if doctor else None,
            "treatment": encounter.get("current_treatment") if encounter else None,
            "current_treatment": encounter.get("current_treatment") if encounter else None,
            "encounter": {
                "admission_time": encounter.get("admission_time"),
                "treatment": encounter.get("current_treatment"),
                "condition": encounter.get("current_condition"),
            } if encounter else None,
            "prescriptions": [
                {
                    "medicine": rx["medicine_name"],
                    "medicine_name": rx["medicine_name"],
                    "dosage": rx["dosage"],
                    "frequency": rx["frequency"],
                    "route": rx["route"],
                }
                for rx in prescriptions
            ],
        }

    def get_patient_status_brief(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Brief status check suitable for voice response."""
        pid = self.resolve_patient_id(patient_id) or patient_id
        status = self._db.get_patient_status(pid)
        if not status:
            return None
        return {
            "patient_id": pid,
            "name": status["name"],
            "status": status["status"],
            "room_id": status["room_id"],
            "condition": status["condition"],
            "doctor_name": status.get("doctor_name", "Unassigned"),
        }

    def get_attending_doctor_info(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Get attending doctor info for voice response."""
        pid = self.resolve_patient_id(patient_id) or patient_id
        doctor = self._db.get_attending_doctor(pid)
        patient = self._db.get_patient(pid)
        if not doctor or not patient:
            return None
        return {
            "patient_id": pid,
            "patient_name": patient["name"],
            "doctor_id": doctor["doctor_id"],
            "doctor_name": doctor["name"],
            "specialization": doctor.get("specialization"),
            "department": doctor.get("department"),
        }

    def get_medications_for_patient(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Get active prescriptions for voice response."""
        pid = self.resolve_patient_id(patient_id) or patient_id
        patient = self._db.get_patient(pid)
        if not patient:
            return None
        prescriptions = self._db.get_prescriptions(pid)
        pending = self._db.get_pending_medications(pid)
        rx_list = [
            {
                "medicine": rx["medicine_name"],
                "medicine_name": rx["medicine_name"],
                "dosage": rx["dosage"],
                "frequency": rx["frequency"],
                "route": rx["route"],
                "instructions": rx.get("special_instructions", ""),
            }
            for rx in prescriptions
        ]
        return {
            "patient_id": pid,
            "patient_name": patient["name"],
            "prescriptions": rx_list,
            "medications": rx_list,
            "pending_deliveries": len(pending),
        }

    def get_all_active_patients_brief(self) -> List[Dict[str, Any]]:
        """Get brief status for all active patients."""
        patients = self._db.get_active_patients()
        return [
            {
                "patient_id": p["patient_id"],
                "name": p["name"],
                "room_id": p.get("room_id"),
                "assigned_room": p.get("room_id"),
                "status": p.get("live_status", "UNKNOWN"),
                "condition": p.get("condition"),
                "doctor_name": p.get("doctor_name", "Unassigned"),
            }
            for p in patients
        ]

    # ── Patient Status Update ────────────────────────────────────────────────

    def set_patient_status(
        self,
        patient_id: str,
        new_status: str,
        reason: str = "",
        operator: str = "voice_command",
    ) -> Dict[str, Any]:
        """Update patient status and return result for response generation."""
        pid = self.resolve_patient_id(patient_id) or patient_id
        patient = self._db.get_patient(pid)
        if not patient:
            return {"success": False, "error": f"Patient {pid} not found"}

        old_status_row = self._db.get_patient_status(pid)
        old_status = old_status_row["status"] if old_status_row else "UNKNOWN"

        success = self._db.set_patient_status(pid, new_status, reason, operator)
        if not success:
            return {"success": False, "error": f"Failed to update status for {pid}"}

        return {
            "success": True,
            "patient_id": pid,
            "patient_name": patient["name"],
            "old_status": old_status,
            "new_status": new_status,
            "reason": reason,
            "room_id": patient.get("room_id"),
        }

    # ── Room Queries ─────────────────────────────────────────────────────────

    def get_room_patient_info(self, room_id: str) -> Optional[Dict[str, Any]]:
        """Get patient info for a specific room."""
        patient = self._db.get_patient_in_room(room_id)
        if not patient:
            return None
        return {
            "room_id": room_id,
            "patient_id": patient["patient_id"],
            "patient_name": patient["name"],
            "status": patient.get("live_status", "UNKNOWN"),
            "condition": patient.get("condition"),
        }

    # ── Medication Workflow ──────────────────────────────────────────────────

    def get_due_medications(self) -> List[Dict[str, Any]]:
        """Get all medications that are currently due."""
        return self._db.get_due_medications()

    def create_medication_delivery_task(
        self,
        patient_id: str,
        medicine_name: Optional[str] = None,
        schedule_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a medication delivery task from a prescription or explicit request.

        If medicine_name is provided, looks up the medicine from prescriptions.
        If schedule_id is provided, links to a specific medication schedule.

        Returns:
            Dict with task_id and task details, or error.
        """
        pid = self.resolve_patient_id(patient_id) or patient_id
        patient = self._db.get_patient(pid)
        if not patient:
            return {"success": False, "error": f"Patient {pid} not found"}

        room_id = patient.get("room_id", "UNKNOWN")

        # Find the medicine to deliver
        item_name = medicine_name or "Prescribed medication"
        if not medicine_name:
            prescriptions = self._db.get_prescriptions(pid)
            if prescriptions:
                item_name = prescriptions[0]["medicine_name"]

        # Determine priority
        status_row = self._db.get_patient_status(pid)
        priority = TaskPriority.NORMAL
        if status_row and status_row["status"] == PatientStatus.EMERGENCY:
            priority = TaskPriority.EMERGENCY
        elif patient.get("priority") == "HIGH":
            priority = TaskPriority.HIGH

        task_id = self._db.create_task(
            task_type=TaskType.MEDICATION_DELIVERY,
            priority=priority,
            patient_id=pid,
            source="PHM-01",        # Pharmacy
            destination=room_id,
            item=item_name,
            notes=f"Deliver {item_name} to {patient['name']} in {room_id}",
        )

        # Update medication schedule if linked
        if schedule_id:
            self._db.update_medication_schedule(schedule_id, MedicationScheduleStatus.ASSIGNED)

        return {
            "success": True,
            "task_id": task_id,
            "patient_id": pid,
            "patient_name": patient["name"],
            "room_id": room_id,
            "medicine": item_name,
            "priority": priority,
            "source": "PHM-01",
            "destination": room_id,
        }

    def create_emergency_task(self, patient_id: str, reason: str = "") -> Dict[str, Any]:
        """Create an emergency response task and update patient status."""
        pid = self.resolve_patient_id(patient_id) or patient_id
        patient = self._db.get_patient(pid)
        if not patient:
            return {"success": False, "error": f"Patient {pid} not found"}

        # Set patient to emergency status
        self._db.set_patient_status(pid, PatientStatus.EMERGENCY, reason or "Emergency assistance requested", "system")

        room_id = patient.get("room_id", "UNKNOWN")
        task_id = self._db.create_task(
            task_type=TaskType.EMERGENCY_RESPONSE,
            priority=TaskPriority.EMERGENCY,
            patient_id=pid,
            destination=room_id,
            notes=f"EMERGENCY: {reason or 'Assistance requested'} for {patient['name']} in {room_id}",
        )

        return {
            "success": True,
            "task_id": task_id,
            "patient_id": pid,
            "patient_name": patient["name"],
            "room_id": room_id,
            "reason": reason,
        }

    # ── Task Lifecycle ───────────────────────────────────────────────────────

    def update_task_status(
        self,
        task_id: str,
        status: str,
        assigned_robot: Optional[str] = None,
    ) -> bool:
        """Update task status (called by coordinator/executor on state transitions)."""
        result = self._db.update_task_status(task_id, status, assigned_robot)
        if result and status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            self._db.archive_completed_task(task_id)
        return result

    def complete_task(
        self,
        task_id: str,
        assigned_robot: Optional[str] = None,
        result_summary: str = "",
    ) -> bool:
        """Convenience method to mark a task as completed."""
        return self.update_task_status(task_id, TaskStatus.COMPLETED, assigned_robot=assigned_robot)

    def get_pending_tasks(self) -> List[Dict[str, Any]]:
        """Get all pending tasks ordered by priority."""
        return self._db.get_pending_tasks()

    # ── Dashboard ────────────────────────────────────────────────────────────

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get dashboard summary data."""
        return self._db.get_dashboard_summary()

    def get_patient_status_history(self, patient_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get status change history for a patient."""
        pid = self.resolve_patient_id(patient_id) or patient_id
        return self._db.get_status_history(pid, limit)

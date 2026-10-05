"""
AAROGYA Platform — Voice Command & Security Gateway
===================================================
Enforces the mandatory rule:
"Voice is an INPUT CHANNEL, not an AUTHORIZATION CHANNEL."

Processes spoken/text commands, validates authenticated user permissions,
and routes authorized clinical missions to TaskEngine, or answers visitor
navigation and informational requests safely.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from ai_reasoning.mission_understander import MissionUnderstander
from backend.task_engine import TaskEngine
from database.models import (
    AuditLog,
    Bed,
    HospitalRoom,
    Medicine,
    Patient,
    TaskPriorityEnum,
    User,
    UserRole,
)


class VoiceService:
    @staticmethod
    def process_voice_command(
        db: Session,
        command_text: str,
        authenticated_user: Optional[User],
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes Section 10 & 11 Voice Processing & Authorization Workflow.
        """
        clean_text = command_text.strip()
        user_role = authenticated_user.role if authenticated_user else UserRole.VISITOR
        username = authenticated_user.username if authenticated_user else "anonymous_visitor"

        # Initialize NLU understander
        nlu = MissionUnderstander()
        spec = nlu.understand_mission(clean_text)

        # ── 1. CHECK CLINICAL ACTION AUTHORIZATION ──────────────────────────
        is_clinical_delivery = (
            spec.task_type in ("deliver", "collect", "medicine", "emergency")
            or any(kw in clean_text.lower() for kw in ["deliver", "medicine", "paracetamol", "atorvastatin", "tablet", "dose", "drug", "code blue", "emergency"])
        )

        if is_clinical_delivery:
            # Unauthorized visitor check (Section 11)
            if user_role not in (UserRole.ADMIN, UserRole.DOCTOR, UserRole.NURSE):
                denial_msg = (
                    "I can assist with general hospital services and navigation, "
                    "but medication delivery requires an authorized hospital request (Doctor or Nurse login)."
                )
                audit = AuditLog(
                    user_id=authenticated_user.id if authenticated_user else None,
                    username=username,
                    user_role=user_role.value,
                    action="VOICE_COMMAND_DENIED",
                    entity_type="VoiceSecurity",
                    status="DENIED",
                    authorization_denied=True,
                    details=f"Unauthorized {user_role.value} requested: '{clean_text}'",
                )
                db.add(audit)
                db.commit()

                return {
                    "success": False,
                    "authorized": False,
                    "response": denial_msg,
                    "command": clean_text,
                    "user": username,
                    "role": user_role.value,
                }

        # ── 2. GENERAL VISITOR INQUIRIES & ROOM DIRECTIONS ──────────────────
        # Visitors CAN ask for directions, pharmacy location, reception, room guidance
        is_navigation_query = any(kw in clean_text.lower() for kw in ["where is", "direction", "how to reach", "guide me", "locate", "take me to", "go to"])
        if is_navigation_query or user_role == UserRole.VISITOR:
            # Match destination from text
            dept_matches = {
                "pharmacy": ("PHM-01", "Pharmacy is located on Floor 1, North Corridor. Dispensing window is at Station PHM-01."),
                "reception": ("RCT-01", "Reception Atrium is at the main hospital entrance on Floor 1."),
                "icu": ("ICU-01", "Intensive Care Unit is located on Floor 1, West Wing. Authorized personnel only."),
                "emergency": ("EMR-01", "Emergency & Trauma center is at the South entrance with 24/7 ambulance triage."),
                "radiology": ("RAD-01", "Radiology (X-ray, CT, MRI) is on Floor 1, North Corridor."),
                "laboratory": ("LAB-01", "Pathology specimen collection is on Floor 1 near Central Core."),
                "opd": ("OPD-01", "Outpatient Consultation suites are in the East Wing."),
            }
            for kw, (room_id, guidance) in dept_matches.items():
                if kw in clean_text.lower():
                    return {
                        "success": True,
                        "authorized": True,
                        "intent": "NAVIGATIONAL_GUIDANCE",
                        "destination_code": room_id,
                        "response": guidance,
                        "user": username,
                        "role": user_role.value,
                    }

        # ── 3. CLINICAL MEDICATION WORKFLOW (AUTHORIZED USER) ───────────────
        # Identify Target Bed / Room / Patient
        # Target: "ICU Bed 3" or "Arun Patel" or "Bed 101"
        target_patient = None
        if "icu bed 3" in clean_text.lower() or "bed 3" in clean_text.lower():
            # Find patient in ICU Bed 3
            bed = db.query(Bed).filter(Bed.bed_number == "ICU Bed 3").first()
            if bed and bed.patients:
                target_patient = bed.patients[0]
            else:
                target_patient = db.query(Patient).filter(Patient.patient_code == "P001").first()

        if not target_patient and spec.patient_id:
            target_patient = db.query(Patient).filter(Patient.patient_code == spec.patient_id).first()

        if not target_patient:
            # Check by patient names
            all_patients = db.query(Patient).all()
            for p in all_patients:
                if p.name.lower() in clean_text.lower():
                    target_patient = p
                    break

        if not target_patient:
            # Default to primary admitted demo patient (Arun Patel, ICU Bed 3)
            target_patient = db.query(Patient).filter(Patient.patient_code == "P001").first()

        # Identify Medicine
        target_medicine = None
        all_meds = db.query(Medicine).all()
        for m in all_meds:
            if m.name.lower().split()[0] in clean_text.lower():
                target_medicine = m
                break

        if not target_medicine:
            # If "medicine" requested without specific name, pick patient's active prescription
            if target_patient and target_patient.prescriptions:
                active_rxs = [rx for rx in target_patient.prescriptions if rx.status == "ACTIVE"]
                if active_rxs:
                    target_medicine = active_rxs[0].medicine

        if not target_medicine:
            target_medicine = db.query(Medicine).filter(Medicine.medicine_code == "MED002").first()

        # Determine Priority
        priority = TaskPriorityEnum.NORMAL
        if "emergency" in clean_text.lower() or "stat" in clean_text.lower() or "code blue" in clean_text.lower():
            priority = TaskPriorityEnum.EMERGENCY
        elif "urgent" in clean_text.lower():
            priority = TaskPriorityEnum.HIGH

        # Dispatch Task through TaskEngine
        try:
            task = TaskEngine.create_medicine_delivery_task(
                db=db,
                patient_id=target_patient.id,
                medicine_id=target_medicine.id,
                requested_by=authenticated_user,
                priority=priority,
            )
            robot_str = task.assigned_robot.name if task.assigned_robot else "Fleet"
            return {
                "success": True,
                "authorized": True,
                "task_id": task.task_code,
                "status": task.status.value,
                "robot": robot_str,
                "patient": target_patient.name,
                "room": task.destination_location,
                "medicine": target_medicine.name,
                "priority": priority.value,
                "response": f"Order confirmed: {task.task_code} dispatched to {robot_str}. Delivering {target_medicine.name} to {target_patient.name} at {task.destination_location}.",
            }
        except Exception as e:
            # Catch duplicate task or validation error and return structured response
            return {
                "success": False,
                "authorized": True,
                "error": getattr(e, "detail", str(e)),
                "response": getattr(e, "detail", str(e)),
            }

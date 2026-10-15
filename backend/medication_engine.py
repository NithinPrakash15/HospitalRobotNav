"""
AAROGYA Platform — Medication Validation & Automation Engine
============================================================
Enforces strict clinical validation, long-term medication scheduling,
and real-time checks to prevent erroneous or discontinued medication deliveries.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from database.models import (
    AuditLog,
    MedicationSchedule,
    Medicine,
    Patient,
    PatientStatusEnum,
    Prescription,
    PrescriptionStatusEnum,
    Robot,
    RobotStatusEnum,
    ScheduleStatusEnum,
)


class MedicationValidationResult:
    def __init__(
        self,
        is_valid: bool,
        reason: str,
        prescription: Optional[Prescription] = None,
        patient: Optional[Patient] = None,
        medicine: Optional[Medicine] = None,
    ) -> None:
        self.is_valid = is_valid
        self.reason = reason
        self.prescription = prescription
        self.patient = patient
        self.medicine = medicine

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "reason": self.reason,
            "prescription_code": self.prescription.prescription_code if self.prescription else None,
            "patient_name": self.patient.name if self.patient else None,
            "medicine_name": self.medicine.name if self.medicine else None,
        }


class MedicationEngine:
    @staticmethod
    def validate_medication_delivery(
        db: Session,
        patient_id: int,
        medicine_id: Optional[int] = None,
        prescription_id: Optional[int] = None,
    ) -> MedicationValidationResult:
        """
        Executes Section 15 & 26 Safety Pre-Conditions:
        - Prescription active?
        - Patient still admitted & active?
        - Prescription discontinued or changed?
        - Patient discharged?
        - Medicine available and in stock?
        """
        # 1. Verify Patient
        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        if not patient:
            return MedicationValidationResult(False, f"Patient ID {patient_id} does not exist in hospital database.")

        if patient.status == PatientStatusEnum.DISCHARGED:
            return MedicationValidationResult(
                False,
                f"SAFETY BLOCK: Patient {patient.name} ({patient.patient_code}) was DISCHARGED on {patient.discharge_date}. Delivery denied.",
                patient=patient,
            )

        if patient.status not in (PatientStatusEnum.ACTIVE, PatientStatusEnum.EMERGENCY):
            return MedicationValidationResult(
                False,
                f"SAFETY BLOCK: Patient status is '{patient.status.value}'. Must be ACTIVE or EMERGENCY for medication delivery.",
                patient=patient,
            )

        if not patient.room_id and not patient.bed_id:
            return MedicationValidationResult(
                False,
                f"Patient {patient.name} is not assigned to any hospital room or bed.",
                patient=patient,
            )

        # 2. Find and Validate Prescription
        rx_query = db.query(Prescription).filter(Prescription.patient_id == patient.id)
        if prescription_id:
            rx_query = rx_query.filter(Prescription.id == prescription_id)
        elif medicine_id:
            rx_query = rx_query.filter(Prescription.medicine_id == medicine_id)

        prescriptions = rx_query.all()
        if not prescriptions:
            return MedicationValidationResult(
                False,
                f"CLINICAL SAFETY BLOCK: No prescription on file for Patient {patient.name} matching requested medicine.",
                patient=patient,
            )

        # Check for active prescription
        active_rx = None
        for rx in prescriptions:
            if rx.status == PrescriptionStatusEnum.DISCONTINUED:
                return MedicationValidationResult(
                    False,
                    f"CLINICAL SAFETY BLOCK: Prescription {rx.prescription_code} for {rx.medicine.name} was DISCONTINUED by attending physician. Cannot deliver.",
                    prescription=rx,
                    patient=patient,
                    medicine=rx.medicine,
                )
            elif rx.status == PrescriptionStatusEnum.PAUSED:
                return MedicationValidationResult(
                    False,
                    f"Prescription {rx.prescription_code} is currently PAUSED by clinical staff.",
                    prescription=rx,
                    patient=patient,
                    medicine=rx.medicine,
                )
            elif rx.status == PrescriptionStatusEnum.COMPLETED:
                return MedicationValidationResult(
                    False,
                    f"Prescription {rx.prescription_code} treatment course has been COMPLETED.",
                    prescription=rx,
                    patient=patient,
                    medicine=rx.medicine,
                )
            elif rx.status == PrescriptionStatusEnum.ACTIVE:
                active_rx = rx
                break

        if not active_rx:
            return MedicationValidationResult(
                False,
                f"No ACTIVE prescription found for patient {patient.name}.",
                patient=patient,
            )

        # 3. Verify Medicine Inventory
        medicine = active_rx.medicine
        if not medicine.is_available or medicine.stock_quantity <= 0:
            return MedicationValidationResult(
                False,
                f"PHARMACY ALERT: Medicine {medicine.name} is currently OUT OF STOCK (Stock: {medicine.stock_quantity}).",
                prescription=active_rx,
                patient=patient,
                medicine=medicine,
            )

        # All clinical preconditions satisfied
        return MedicationValidationResult(
            True,
            f"Validation successful: Prescription {active_rx.prescription_code} active for {patient.name}. Medicine in stock ({medicine.stock_quantity} available).",
            prescription=active_rx,
            patient=patient,
            medicine=medicine,
        )

    @staticmethod
    def generate_schedules_for_prescription(db: Session, prescription: Prescription) -> List[MedicationSchedule]:
        """Generates timed medication schedules across the duration of the prescription."""
        start_time = prescription.start_date or datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        hours_interval = max(1, prescription.frequency_hours)
        total_hours = prescription.duration_days * 24

        schedules = []
        current_time = start_time
        while (current_time - start_time).total_seconds() / 3600.0 < total_hours:
            sched = MedicationSchedule(
                prescription_id=prescription.id,
                patient_id=prescription.patient_id,
                medicine_id=prescription.medicine_id,
                scheduled_time=current_time,
                status=ScheduleStatusEnum.PENDING,
                notes=f"Auto-generated dose ({prescription.frequency})",
            )
            db.add(sched)
            schedules.append(sched)
            current_time += datetime.timedelta(hours=hours_interval)

        db.commit()
        return schedules

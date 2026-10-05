"""
AAROGYA Platform — Clinical & Hospital Management Service
=========================================================
Handles clinical entities, patient admissions, doctor prescriptions,
nursing assignments, and pharmacy inventory management.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from database.models import (
    AuditLog,
    Bed,
    Department,
    Doctor,
    HospitalRoom,
    MedicationSchedule,
    Medicine,
    Nurse,
    Patient,
    PatientStatusEnum,
    Prescription,
    PrescriptionStatusEnum,
    User,
    UserRole,
)


class ClinicalService:
    @staticmethod
    def get_all_patients(db: Session, status_filter: Optional[str] = None) -> List[Patient]:
        query = db.query(Patient)
        if status_filter:
            query = query.filter(Patient.status == status_filter)
        return query.order_by(Patient.id).all()

    @staticmethod
    def get_patient_by_id(db: Session, patient_id: int) -> Patient:
        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient with ID {patient_id} not found.")
        return patient

    @staticmethod
    def get_patient_by_code(db: Session, patient_code: str) -> Optional[Patient]:
        return db.query(Patient).filter(Patient.patient_code == patient_code).first()

    @staticmethod
    def discharge_patient(db: Session, patient_id: int, current_user: User) -> Patient:
        patient = ClinicalService.get_patient_by_id(db, patient_id)
        patient.status = PatientStatusEnum.DISCHARGED
        patient.discharge_date = datetime.datetime.utcnow()

        # Free bed
        if patient.bed_id:
            bed = db.query(Bed).filter(Bed.id == patient.bed_id).first()
            if bed:
                bed.is_occupied = False
                bed.patient_id = None
            patient.bed_id = None
            patient.room_id = None

        # Pause or complete active prescriptions
        for rx in patient.prescriptions:
            if rx.status == PrescriptionStatusEnum.ACTIVE:
                rx.status = PrescriptionStatusEnum.COMPLETED

        # Audit
        audit = AuditLog(
            user_id=current_user.id,
            username=current_user.username,
            user_role=current_user.role.value,
            action="PATIENT_DISCHARGED",
            entity_type="Patient",
            entity_id=str(patient.id),
            patient_code=patient.patient_code,
            details=f"Patient {patient.name} ({patient.patient_code}) discharged by {current_user.full_name}.",
            status="SUCCESS",
        )
        db.add(audit)
        db.commit()
        db.refresh(patient)
        return patient

    @staticmethod
    def get_all_doctors(db: Session) -> List[Doctor]:
        return db.query(Doctor).all()

    @staticmethod
    def get_all_nurses(db: Session) -> List[Nurse]:
        return db.query(Nurse).all()

    @staticmethod
    def get_all_medicines(db: Session) -> List[Medicine]:
        return db.query(Medicine).order_by(Medicine.name).all()

    @staticmethod
    def get_medicine_by_id(db: Session, medicine_id: int) -> Medicine:
        med = db.query(Medicine).filter(Medicine.id == medicine_id).first()
        if not med:
            raise HTTPException(status_code=404, detail=f"Medicine with ID {medicine_id} not found.")
        return med

    @staticmethod
    def get_all_prescriptions(db: Session, patient_id: Optional[int] = None) -> List[Prescription]:
        query = db.query(Prescription)
        if patient_id:
            query = query.filter(Prescription.patient_id == patient_id)
        return query.order_by(Prescription.created_at.desc()).all()

    @staticmethod
    def create_prescription(
        db: Session,
        patient_id: int,
        medicine_id: int,
        dosage: str,
        frequency: str,
        frequency_hours: int,
        route: str,
        duration_days: int,
        instructions: Optional[str],
        current_user: User,
    ) -> Prescription:
        # Authorization check: only DOCTOR or ADMIN
        if current_user.role not in (UserRole.DOCTOR, UserRole.ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only authorized doctors may issue prescriptions.",
            )

        # Validate patient is active
        patient = ClinicalService.get_patient_by_id(db, patient_id)
        if patient.status == PatientStatusEnum.DISCHARGED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot prescribe medication to discharged patient {patient.name}.",
            )

        medicine = ClinicalService.get_medicine_by_id(db, medicine_id)
        doctor = db.query(Doctor).filter(Doctor.user_id == current_user.id).first()
        doctor_id = doctor.id if doctor else 1

        # Generate prescription code
        count = db.query(Prescription).count() + 1
        rx_code = f"RX-{count:03d}"

        rx = Prescription(
            prescription_code=rx_code,
            patient_id=patient.id,
            doctor_id=doctor_id,
            medicine_id=medicine.id,
            dosage=dosage,
            frequency=frequency,
            frequency_hours=frequency_hours,
            route=route,
            duration_days=duration_days,
            instructions=instructions,
            status=PrescriptionStatusEnum.ACTIVE,
        )
        db.add(rx)
        db.flush()

        # Audit
        audit = AuditLog(
            user_id=current_user.id,
            username=current_user.username,
            user_role=current_user.role.value,
            action="CREATE_PRESCRIPTION",
            entity_type="Prescription",
            entity_id=str(rx.id),
            patient_code=patient.patient_code,
            medicine_code=medicine.medicine_code,
            details=f"Prescription {rx_code} created for {patient.name}: {medicine.name} {dosage}, {frequency}.",
            status="SUCCESS",
        )
        db.add(audit)
        db.commit()
        db.refresh(rx)
        return rx

    @staticmethod
    def discontinue_prescription(db: Session, prescription_id: int, reason: str, current_user: User) -> Prescription:
        if current_user.role not in (UserRole.DOCTOR, UserRole.ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only authorized medical doctors can discontinue a prescription.",
            )

        rx = db.query(Prescription).filter(Prescription.id == prescription_id).first()
        if not rx:
            raise HTTPException(status_code=404, detail="Prescription not found.")

        rx.status = PrescriptionStatusEnum.DISCONTINUED
        rx.instructions = f"{rx.instructions or ''} | [DISCONTINUED by {current_user.full_name}: {reason}]"

        # Cancel any pending medication schedules associated with this prescription
        schedules = db.query(MedicationSchedule).filter(
            MedicationSchedule.prescription_id == rx.id,
            MedicationSchedule.status == "PENDING",
        ).all()
        for s in schedules:
            s.status = "CANCELLED"
            s.notes = f"Cancelled due to prescription discontinuation: {reason}"

        # Audit
        audit = AuditLog(
            user_id=current_user.id,
            username=current_user.username,
            user_role=current_user.role.value,
            action="DISCONTINUE_PRESCRIPTION",
            entity_type="Prescription",
            entity_id=str(rx.id),
            details=f"Prescription {rx.prescription_code} discontinued by {current_user.full_name}. Reason: {reason}",
            status="SUCCESS",
        )
        db.add(audit)
        db.commit()
        db.refresh(rx)
        return rx

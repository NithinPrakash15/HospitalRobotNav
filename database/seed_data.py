"""
AAROGYA Hospital Autonomous Assistance Platform — Database Seeding
==================================================================
Seeds realistic hospital entities, RBAC users, rooms matching the Isaac Sim digital twin,
beds (including ICU Bed 3 for patient Arun Patel), medicines, and active prescriptions.
"""

from __future__ import annotations

import datetime
from typing import Optional

from passlib.context import CryptContext
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
    Robot,
    RobotRoleEnum,
    RobotStatusEnum,
    ScheduleStatusEnum,
    User,
    UserRole,
)
from database.session import db_session, init_db

import bcrypt


def hash_password(password: str) -> str:
    """Hash password using direct bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def seed_database(force: bool = False) -> None:
    """Populates the database with initial authentic clinical & operational data."""
    init_db()

    with db_session() as db:
        # Check if already seeded
        if not force and db.query(User).count() > 0:
            return

        # ── 1. DEPARTMENTS ──────────────────────────────────────────────────
        depts_data = [
            {"code": "ICU", "name": "Intensive Care Unit", "floor": 1, "description": "Critical patient care", "is_restricted": True},
            {"code": "PHM", "name": "Central Pharmacy", "floor": 1, "description": "Medication storage & dispensing", "is_restricted": False},
            {"code": "EMR", "name": "Emergency & Trauma", "floor": 1, "description": "Acute & trauma triage", "is_restricted": True},
            {"code": "OT", "name": "Operating Theaters", "floor": 2, "description": "Surgical suites", "is_restricted": True},
            {"code": "LAB", "name": "Pathology & Biochemistry", "floor": 1, "description": "Clinical specimen diagnostics", "is_restricted": False},
            {"code": "RAD", "name": "Radiology & Imaging", "floor": 1, "description": "X-ray, CT, MRI diagnostics", "is_restricted": False},
            {"code": "OPD", "name": "Outpatient Department", "floor": 1, "description": "General consultation", "is_restricted": False},
            {"code": "RCT", "name": "Main Reception & Atrium", "floor": 1, "description": "Visitor & patient intake", "is_restricted": False},
            {"code": "CHG", "name": "Robot Charging & Fleet Hub", "floor": 1, "description": "Autonomous fleet docking", "is_restricted": True},
            {"code": "GW", "name": "Inpatient General Ward", "floor": 1, "description": "Inpatient recovery", "is_restricted": False},
        ]
        dept_map = {}
        for d in depts_data:
            dept = Department(**d)
            db.add(dept)
            db.flush()
            dept_map[d["code"]] = dept

        # ── 2. HOSPITAL ROOMS (Matching Isaac Sim 3D Coordinates) ───────────
        rooms_data = [
            {"room_number": "CHG-01", "name": "Charging Bay 1", "dept": "CHG", "zone": "Fleet", "x": 37.25, "y": 26.0, "z": 0.0},
            {"room_number": "RCT-01", "name": "Reception Atrium", "dept": "RCT", "zone": "Public", "x": 0.0, "y": -5.0, "z": 0.0},
            {"room_number": "PHM-01", "name": "Pharmacy Dispense Station", "dept": "PHM", "zone": "Clinical", "x": 14.0, "y": 23.2, "z": 0.0},
            {"room_number": "ICU-01", "name": "Critical Care Unit A", "dept": "ICU", "zone": "Restricted", "x": -36.5, "y": 11.0, "z": 0.0},
            {"room_number": "EMR-01", "name": "Trauma Staging Area", "dept": "EMR", "zone": "Emergency", "x": -35.0, "y": -26.0, "z": 0.0},
            {"room_number": "OT-01", "name": "Operating Theater 1", "dept": "OT", "zone": "Surgical", "x": -39.0, "y": 26.0, "z": 0.0},
            {"room_number": "LAB-01", "name": "Diagnostic Specimen Intake", "dept": "LAB", "zone": "Diagnostics", "x": -0.5, "y": 26.0, "z": 0.0},
            {"room_number": "RAD-01", "name": "Radiology Suite", "dept": "RAD", "zone": "Diagnostics", "x": -15.5, "y": 26.0, "z": 0.0},
            {"room_number": "OPD-01", "name": "Consultation Desk 1", "dept": "OPD", "zone": "Public", "x": 24.0, "y": -26.0, "z": 0.0},
            {"room_number": "PAT-101", "name": "Patient Ward Room 101", "dept": "GW", "zone": "Inpatient", "x": 10.0, "y": -15.0, "z": 0.0},
            {"room_number": "PAT-102", "name": "Patient Ward Room 102", "dept": "GW", "zone": "Inpatient", "x": 18.0, "y": -15.0, "z": 0.0},
        ]
        room_map = {}
        for r in rooms_data:
            room = HospitalRoom(
                room_number=r["room_number"],
                name=r["name"],
                department_id=dept_map[r["dept"]].id,
                zone=r["zone"],
                x_coord=r["x"],
                y_coord=r["y"],
                z_coord=r["z"],
                is_occupied=False,
            )
            db.add(room)
            db.flush()
            room_map[r["room_number"]] = room

        # ── 3. BEDS ─────────────────────────────────────────────────────────
        beds_data = [
            {"bed_number": "ICU Bed 1", "room": "ICU-01"},
            {"bed_number": "ICU Bed 2", "room": "ICU-01"},
            {"bed_number": "ICU Bed 3", "room": "ICU-01"},  # Target bed for master demonstration
            {"bed_number": "Bed 101-A", "room": "PAT-101"},
            {"bed_number": "Bed 101-B", "room": "PAT-101"},
            {"bed_number": "Bed 102-A", "room": "PAT-102"},
        ]
        bed_map = {}
        for b in beds_data:
            bed = Bed(
                bed_number=b["bed_number"],
                room_id=room_map[b["room"]].id,
                is_occupied=False,
            )
            db.add(bed)
            db.flush()
            bed_map[b["bed_number"]] = bed

        # ── 4. USERS & ROLES (RBAC) ─────────────────────────────────────────
        users_data = [
            {"username": "admin", "full_name": "Hospital Administrator", "role": UserRole.ADMIN, "email": "admin@aarogya.health", "pass": "admin123"},
            {"username": "dr_sharma", "full_name": "Dr. Rajesh Sharma", "role": UserRole.DOCTOR, "email": "dr.sharma@aarogya.health", "pass": "doctor123"},
            {"username": "dr_kapoor", "full_name": "Dr. Ananya Kapoor", "role": UserRole.DOCTOR, "email": "dr.kapoor@aarogya.health", "pass": "doctor123"},
            {"username": "nurse_priya", "full_name": "Nurse Priya Verma", "role": UserRole.NURSE, "email": "priya.verma@aarogya.health", "pass": "nurse123"},
            {"username": "nurse_rahul", "full_name": "Nurse Rahul Nair", "role": UserRole.NURSE, "email": "rahul.nair@aarogya.health", "pass": "nurse123"},
            {"username": "patient_arun", "full_name": "Arun Patel", "role": UserRole.PATIENT, "email": "arun.patel@patient.aarogya", "pass": "patient123"},
            {"username": "visitor_maya", "full_name": "Maya Singh", "role": UserRole.VISITOR, "email": "maya.singh@guest.aarogya", "pass": "visitor123"},
        ]
        user_map = {}
        for u in users_data:
            user = User(
                username=u["username"],
                password_hash=hash_password(u["pass"]),
                full_name=u["full_name"],
                role=u["role"],
                email=u["email"],
                is_active=True,
            )
            db.add(user)
            db.flush()
            user_map[u["username"]] = user

        # ── 5. DOCTORS & NURSES PROFILES ────────────────────────────────────
        doc1 = Doctor(
            user_id=user_map["dr_sharma"].id,
            staff_id="DOC-01",
            specialization="Critical Care & Cardiology",
            department_id=dept_map["ICU"].id,
            is_available=True,
        )
        doc2 = Doctor(
            user_id=user_map["dr_kapoor"].id,
            staff_id="DOC-02",
            specialization="Emergency Medicine & Trauma",
            department_id=dept_map["EMR"].id,
            is_available=True,
        )
        db.add_all([doc1, doc2])
        db.flush()

        nurse1 = Nurse(
            user_id=user_map["nurse_priya"].id,
            staff_id="NUR-01",
            department_id=dept_map["ICU"].id,
            shift="Morning (08:00 - 16:00)",
            is_on_duty=True,
        )
        nurse2 = Nurse(
            user_id=user_map["nurse_rahul"].id,
            staff_id="NUR-02",
            department_id=dept_map["GW"].id,
            shift="Evening (16:00 - 00:00)",
            is_on_duty=True,
        )
        db.add_all([nurse1, nurse2])
        db.flush()

        # ── 6. PATIENTS ─────────────────────────────────────────────────────
        # Arun Patel: Admitted to ICU Bed 3
        pat1 = Patient(
            patient_code="P001",
            name="Arun Patel",
            age=58,
            gender="Male",
            blood_type="B+",
            condition="Post-operative Cardiac Monitoring",
            status=PatientStatusEnum.ACTIVE,
            room_id=room_map["ICU-01"].id,
            bed_id=bed_map["ICU Bed 3"].id,
            attending_doctor_id=doc1.id,
            user_id=user_map["patient_arun"].id,
        )
        # Meera Joshi: In Ward 101 Bed A
        pat2 = Patient(
            patient_code="P002",
            name="Meera Joshi",
            age=34,
            gender="Female",
            blood_type="O+",
            condition="Acute Appendicitis Recovery",
            status=PatientStatusEnum.ACTIVE,
            room_id=room_map["PAT-101"].id,
            bed_id=bed_map["Bed 101-A"].id,
            attending_doctor_id=doc2.id,
        )
        # Rohan Mehta: Discharged patient for validation test
        pat3 = Patient(
            patient_code="P003",
            name="Rohan Mehta",
            age=45,
            gender="Male",
            blood_type="A+",
            condition="Fracture Healing",
            status=PatientStatusEnum.DISCHARGED,
            discharge_date=datetime.datetime.utcnow(),
            room_id=None,
            bed_id=None,
            attending_doctor_id=doc2.id,
        )
        db.add_all([pat1, pat2, pat3])
        db.flush()

        # Mark occupied beds
        bed_map["ICU Bed 3"].is_occupied = True
        bed_map["ICU Bed 3"].patient_id = pat1.id
        bed_map["Bed 101-A"].is_occupied = True
        bed_map["Bed 101-A"].patient_id = pat2.id

        # ── 7. MEDICINES ────────────────────────────────────────────────────
        medicines_data = [
            {"code": "MED001", "name": "Paracetamol 500mg", "cat": "Analgesic", "stock": 250, "loc": "PHM-01 Shelf A", "min": 20},
            {"code": "MED002", "name": "Atorvastatin 20mg", "cat": "Cardiovascular", "stock": 120, "loc": "PHM-01 Shelf B", "min": 15},
            {"code": "MED003", "name": "Amoxicillin 500mg", "cat": "Antibiotic", "stock": 180, "loc": "PHM-01 Shelf C", "min": 25},
            {"code": "MED004", "name": "Insulin Glargine 100IU", "cat": "Endocrine", "stock": 60, "loc": "PHM-01 Cold Storage 1", "min": 10},
            {"code": "MED005", "name": "Salbutamol Inhaler", "cat": "Respiratory", "stock": 45, "loc": "PHM-01 Shelf D", "min": 10},
            {"code": "MED006", "name": "Morphine 10mg/ml", "cat": "Controlled Analgesic", "stock": 15, "loc": "PHM-01 Secure Vault", "min": 5},
            {"code": "MED007", "name": "Normal Saline 500ml", "cat": "IV Fluid", "stock": 300, "loc": "PHM-01 Bulk Bay", "min": 50},
            {"code": "MED008", "name": "Adrenaline 1mg", "cat": "Emergency Code Blue", "stock": 50, "loc": "PHM-01 Emergency Tray", "min": 15},
        ]
        med_map = {}
        for m in medicines_data:
            med = Medicine(
                medicine_code=m["code"],
                name=m["name"],
                category=m["cat"],
                stock_quantity=m["stock"],
                storage_location=m["loc"],
                min_stock_threshold=m["min"],
                is_available=True,
            )
            db.add(med)
            db.flush()
            med_map[m["code"]] = med

        # ── 8. PRESCRIPTIONS & SCHEDULES ────────────────────────────────────
        # Active prescription for Arun Patel (ICU Bed 3)
        rx1 = Prescription(
            prescription_code="RX-001",
            patient_id=pat1.id,
            doctor_id=doc1.id,
            medicine_id=med_map["MED002"].id,  # Atorvastatin 20mg
            dosage="20mg",
            frequency="Every 8 hours",
            frequency_hours=8,
            route="Oral",
            start_date=datetime.datetime.utcnow(),
            duration_days=30,  # Long-term 30 days
            status=PrescriptionStatusEnum.ACTIVE,
            instructions="Administer with water post-meal. Monitor lipid response.",
        )
        rx2 = Prescription(
            prescription_code="RX-002",
            patient_id=pat1.id,
            doctor_id=doc1.id,
            medicine_id=med_map["MED001"].id,  # Paracetamol 500mg
            dosage="500mg",
            frequency="Every 8 hours",
            frequency_hours=8,
            route="Oral",
            start_date=datetime.datetime.utcnow(),
            duration_days=5,
            status=PrescriptionStatusEnum.ACTIVE,
            instructions="PRN for pain or fever > 38.0 C.",
        )
        # Discontinued prescription for safety validation testing
        rx_disc = Prescription(
            prescription_code="RX-003",
            patient_id=pat2.id,
            doctor_id=doc2.id,
            medicine_id=med_map["MED006"].id,  # Morphine
            dosage="10mg",
            frequency="Every 6 hours",
            frequency_hours=6,
            route="IV",
            start_date=datetime.datetime.utcnow() - datetime.timedelta(days=2),
            duration_days=3,
            status=PrescriptionStatusEnum.DISCONTINUED,
            instructions="Discontinued due to improved pain score.",
        )
        db.add_all([rx1, rx2, rx_disc])
        db.flush()

        # Generate medication schedules for Arun Patel
        now = datetime.datetime.utcnow()
        sched1 = MedicationSchedule(
            prescription_id=rx1.id,
            patient_id=pat1.id,
            medicine_id=med_map["MED002"].id,
            scheduled_time=now + datetime.timedelta(minutes=5),  # Due now/soon
            status=ScheduleStatusEnum.PENDING,
            notes="Morning scheduled dose",
        )
        sched2 = MedicationSchedule(
            prescription_id=rx1.id,
            patient_id=pat1.id,
            medicine_id=med_map["MED002"].id,
            scheduled_time=now + datetime.timedelta(hours=8),
            status=ScheduleStatusEnum.PENDING,
            notes="Afternoon scheduled dose",
        )
        db.add_all([sched1, sched2])
        db.flush()

        # ── 9. ROBOTS (Fleet in Isaac Sim) ──────────────────────────────────
        robots_data = [
            {"robot_id": "ROBOT-01", "name": "Arogya_Delivery", "role": RobotRoleEnum.DELIVERY, "room": "CHG-01", "x": 37.25, "y": 26.0, "battery": 98.0},
            {"robot_id": "ROBOT-02", "name": "Mitra_Reception", "role": RobotRoleEnum.RECEPTION, "room": "RCT-01", "x": 0.0, "y": -5.0, "battery": 95.0},
            {"robot_id": "ROBOT-03", "name": "Garuda_Emergency", "role": RobotRoleEnum.EMERGENCY, "room": "EMR-01", "x": -35.0, "y": -26.0, "battery": 100.0},
            {"robot_id": "ROBOT-04", "name": "Sahayak_Support", "role": RobotRoleEnum.SUPPORT, "room": "CHG-01", "x": 35.0, "y": 26.0, "battery": 92.0},
        ]
        for r in robots_data:
            robot = Robot(
                robot_id=r["robot_id"],
                name=r["name"],
                role=r["role"],
                status=RobotStatusEnum.IDLE,
                battery_level=r["battery"],
                current_room=r["room"],
                current_x=r["x"],
                current_y=r["y"],
                is_available=True,
            )
            db.add(robot)

        # ── 10. INITIAL AUDIT LOG ───────────────────────────────────────────
        initial_log = AuditLog(
            username="system",
            user_role="ADMIN",
            action="SYSTEM_INITIALIZE",
            entity_type="System",
            details="AAROGYA Hospital Autonomous Assistance Platform database initialized and seeded with clinical data.",
            status="SUCCESS",
        )
        db.add(initial_log)


if __name__ == "__main__":
    seed_database(force=True)
    print("AAROGYA Database initialized and seeded successfully.")

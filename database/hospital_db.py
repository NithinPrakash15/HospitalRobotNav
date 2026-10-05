"""
HospitalRobotNav — Hospital Database (SQLite)
===============================================
Core hospital knowledge base with full relational schema and synthetic demo data.

Tables:
    patients            — Demographics, room, condition, priority
    doctors             — Name, specialization, department, availability
    medicines           — Name, dosage, stock, location
    prescriptions       — Patient→doctor→medicine with schedule
    medication_schedules — Timed delivery entries
    encounters          — Current hospitalization encounters
    patient_status      — Live status (ACTIVE/WAITING/EMERGENCY/...)
    patient_status_history — Immutable audit trail
    patient_history     — Previous admissions/treatments
    hospital_tasks      — Task queue for robot fleet
    task_history        — Completed/failed task archive

All data is SYNTHETIC DEMO DATA — no real patient information.

Usage::

    db = HospitalDatabase()
    db.initialize()
    patients = db.get_all_patients()
"""

from __future__ import annotations

import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from utilities.logger import get_logger

log = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Database Path
# ─────────────────────────────────────────────────────────────────────────────

_DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
_DB_PATH = os.path.join(_DB_DIR, "hospital.db")


# ─────────────────────────────────────────────────────────────────────────────
# Status Enums (string constants for DB values)
# ─────────────────────────────────────────────────────────────────────────────

class PatientStatus:
    """Patient status constants matching Part 9 specification."""
    ACTIVE = "ACTIVE"              # 🟢 Under treatment
    WAITING = "WAITING"            # 🟡 Waiting
    EMERGENCY = "EMERGENCY"        # 🔴 Emergency
    OUTPATIENT = "OUTPATIENT"      # 🔵 Outpatient
    DISCHARGED = "DISCHARGED"      # ⚪ Discharged
    INACTIVE = "INACTIVE"          # ⚫ Inactive

    ALL = (ACTIVE, WAITING, EMERGENCY, OUTPATIENT, DISCHARGED, INACTIVE)


class TaskStatus:
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    IN_TRANSIT = "IN_TRANSIT"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MedicationScheduleStatus:
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskType:
    MEDICATION_DELIVERY = "MEDICATION_DELIVERY"
    PATIENT_GUIDANCE = "PATIENT_GUIDANCE"
    PATIENT_ROOM_VISIT = "PATIENT_ROOM_VISIT"
    DOCTOR_ASSISTANCE = "DOCTOR_ASSISTANCE"
    LAB_SAMPLE_DELIVERY = "LAB_SAMPLE_DELIVERY"
    MEDICAL_EQUIPMENT_DELIVERY = "MEDICAL_EQUIPMENT_DELIVERY"
    EMERGENCY_RESPONSE = "EMERGENCY_RESPONSE"
    PHARMACY_PICKUP = "PHARMACY_PICKUP"
    PATIENT_TRANSPORT = "PATIENT_TRANSPORT"
    ROOM_CHECK = "ROOM_CHECK"
    SUPPLY_DELIVERY = "SUPPLY_DELIVERY"
    RETURN_TO_CHARGER = "RETURN_TO_CHARGER"


class TaskPriority:
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EMERGENCY = "EMERGENCY"


# ─────────────────────────────────────────────────────────────────────────────
# Hospital Database
# ─────────────────────────────────────────────────────────────────────────────

class HospitalDatabase:
    """SQLite-backed hospital knowledge base.

    Thread-safe: uses ``check_same_thread=False`` and a context manager
    for connection access.  The database file is stored at ``data/hospital.db``
    relative to the project root.

    Lifecycle::

        db = HospitalDatabase()
        db.initialize()   # Creates tables + seeds data if first run
        # ... use query methods ...
        db.close()
    """

    def __init__(self, db_path: Optional[str] = None, auto_init: bool = True) -> None:
        self._db_path = db_path or _DB_PATH
        self._conn: Optional[sqlite3.Connection] = None
        if auto_init:
            self.initialize()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def initialize(self) -> None:
        """Create the database, tables, and seed synthetic data if empty."""
        dir_name = os.path.dirname(self._db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        self._conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        self._create_tables()

        # Seed only if patients table is empty
        cursor = self._conn.execute("SELECT COUNT(*) FROM patients")
        count = cursor.fetchone()[0]
        if count == 0:
            self._seed_synthetic_data()
            log.info("Hospital database seeded with synthetic demo data.")
        else:
            log.info("Hospital database loaded (%d patients).", count)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    @contextmanager
    def _cursor(self):
        """Thread-safe cursor context manager."""
        assert self._conn is not None, "Database not initialized — call initialize() first"
        cursor = self._conn.cursor()
        try:
            yield cursor
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cursor.close()

    # ── Schema ───────────────────────────────────────────────────────────────

    def _create_tables(self) -> None:
        """Create all tables if they don't exist."""
        with self._cursor() as c:
            # Patients
            c.execute("""
                CREATE TABLE IF NOT EXISTS patients (
                    patient_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    age INTEGER,
                    gender TEXT,
                    room_id TEXT,
                    condition TEXT,
                    priority TEXT DEFAULT 'NORMAL',
                    attending_doctor_id TEXT,
                    admission_status TEXT DEFAULT 'ADMITTED',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Doctors
            c.execute("""
                CREATE TABLE IF NOT EXISTS doctors (
                    doctor_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    specialization TEXT,
                    department TEXT,
                    room TEXT,
                    availability TEXT DEFAULT 'AVAILABLE',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Medicines
            c.execute("""
                CREATE TABLE IF NOT EXISTS medicines (
                    medicine_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    dosage TEXT,
                    stock INTEGER DEFAULT 0,
                    location TEXT DEFAULT 'PHARMACY',
                    category TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Prescriptions
            c.execute("""
                CREATE TABLE IF NOT EXISTS prescriptions (
                    prescription_id TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL,
                    doctor_id TEXT NOT NULL,
                    medicine_id TEXT NOT NULL,
                    dosage TEXT,
                    frequency TEXT,
                    route TEXT DEFAULT 'ORAL',
                    start_time TEXT,
                    end_time TEXT,
                    special_instructions TEXT,
                    status TEXT DEFAULT 'ACTIVE',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
                    FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id),
                    FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id)
                )
            """)

            # Medication Schedules
            c.execute("""
                CREATE TABLE IF NOT EXISTS medication_schedules (
                    schedule_id TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL,
                    prescription_id TEXT NOT NULL,
                    scheduled_time TEXT NOT NULL,
                    status TEXT DEFAULT 'PENDING',
                    assigned_robot TEXT,
                    delivery_time TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
                    FOREIGN KEY (prescription_id) REFERENCES prescriptions(prescription_id)
                )
            """)

            # Current Encounters
            c.execute("""
                CREATE TABLE IF NOT EXISTS encounters (
                    encounter_id TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL,
                    admission_time TEXT,
                    room_id TEXT,
                    current_doctor TEXT,
                    current_condition TEXT,
                    current_treatment TEXT,
                    status TEXT DEFAULT 'ACTIVE',
                    priority TEXT DEFAULT 'NORMAL',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
                )
            """)

            # Patient Status (current live status)
            c.execute("""
                CREATE TABLE IF NOT EXISTS patient_status (
                    patient_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_by TEXT DEFAULT 'system',
                    FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
                )
            """)

            # Patient Status History (immutable audit trail)
            c.execute("""
                CREATE TABLE IF NOT EXISTS patient_status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id TEXT NOT NULL,
                    old_status TEXT,
                    new_status TEXT NOT NULL,
                    reason TEXT,
                    operator TEXT DEFAULT 'system',
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
                )
            """)

            # Patient History (previous admissions)
            c.execute("""
                CREATE TABLE IF NOT EXISTS patient_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id TEXT NOT NULL,
                    admission_date TEXT,
                    discharge_date TEXT,
                    condition TEXT,
                    treatment TEXT,
                    doctor_id TEXT,
                    room_id TEXT,
                    notes TEXT,
                    FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
                )
            """)

            # Hospital Tasks
            c.execute("""
                CREATE TABLE IF NOT EXISTS hospital_tasks (
                    task_id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    priority TEXT DEFAULT 'NORMAL',
                    patient_id TEXT,
                    source TEXT,
                    destination TEXT,
                    item TEXT,
                    created_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    assigned_robot TEXT,
                    status TEXT DEFAULT 'PENDING',
                    completed_time TEXT,
                    notes TEXT
                )
            """)

            # Task History
            c.execute("""
                CREATE TABLE IF NOT EXISTS task_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    type TEXT,
                    priority TEXT,
                    patient_id TEXT,
                    source TEXT,
                    destination TEXT,
                    assigned_robot TEXT,
                    status TEXT,
                    created_time TEXT,
                    completed_time TEXT,
                    duration_seconds REAL,
                    notes TEXT
                )
            """)

    # ── Synthetic Data Seeding ───────────────────────────────────────────────

    def _seed_synthetic_data(self) -> None:
        """Populate all tables with realistic but entirely fictional demo data."""
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        with self._cursor() as c:
            # ── Doctors ──────────────────────────────────────────────────────
            doctors = [
                ("D001", "Dr. Anil Varma", "Cardiology", "ICU", "DOC-01", "AVAILABLE"),
                ("D002", "Dr. Meera Nair", "General Medicine", "General Ward", "DOC-02", "AVAILABLE"),
                ("D003", "Dr. Rajesh Kumar", "Orthopedics", "OPD", "OPD-01", "AVAILABLE"),
                ("D004", "Dr. Priya Sharma", "Emergency Medicine", "Emergency", "EMR-01", "AVAILABLE"),
            ]
            c.executemany(
                "INSERT INTO doctors (doctor_id, name, specialization, department, room, availability) VALUES (?,?,?,?,?,?)",
                doctors,
            )

            # ── Medicines ────────────────────────────────────────────────────
            medicines = [
                ("MED001", "Amoxicillin", "500 mg", 120, "PHARMACY", "Antibiotic"),
                ("MED002", "Paracetamol", "650 mg", 200, "PHARMACY", "Analgesic"),
                ("MED003", "Metoprolol", "50 mg", 80, "PHARMACY", "Beta-blocker"),
                ("MED004", "Insulin Glargine", "100 IU/mL", 50, "PHARMACY", "Antidiabetic"),
                ("MED005", "Omeprazole", "20 mg", 150, "PHARMACY", "Antacid"),
                ("MED006", "Ceftriaxone", "1 g IV", 60, "PHARMACY", "Antibiotic"),
                ("MED007", "Morphine Sulfate", "10 mg", 30, "PHARMACY", "Analgesic"),
                ("MED008", "Salbutamol Inhaler", "100 mcg", 45, "PHARMACY", "Bronchodilator"),
            ]
            c.executemany(
                "INSERT INTO medicines (medicine_id, name, dosage, stock, location, category) VALUES (?,?,?,?,?,?)",
                medicines,
            )

            # ── Patients ─────────────────────────────────────────────────────
            patients = [
                ("P001", "Ananya Menon", 34, "F", "PAT-101", "Post-operative recovery", "NORMAL", "D001"),
                ("P002", "Rahul Kumar", 56, "M", "PAT-102", "Type 2 Diabetes management", "NORMAL", "D002"),
                ("P003", "Meera Iyer", 42, "F", "PAT-103", "Cardiac arrhythmia monitoring", "HIGH", "D001"),
                ("P004", "Arjun Reddy", 28, "M", "PAT-104", "Fractured tibia - post-surgery", "NORMAL", "D003"),
                ("P005", "Lakshmi Devi", 68, "F", "PAT-105", "Chronic bronchitis exacerbation", "HIGH", "D002"),
                ("P006", "Vikram Singh", 45, "M", "PAT-106", "Acute appendicitis - pre-op", "HIGH", "D004"),
            ]
            c.executemany(
                "INSERT INTO patients (patient_id, name, age, gender, room_id, condition, priority, attending_doctor_id) VALUES (?,?,?,?,?,?,?,?)",
                patients,
            )

            # ── Patient Status ───────────────────────────────────────────────
            statuses = [
                ("P001", PatientStatus.ACTIVE, now_str, "system"),
                ("P002", PatientStatus.ACTIVE, now_str, "system"),
                ("P003", PatientStatus.ACTIVE, now_str, "system"),
                ("P004", PatientStatus.WAITING, now_str, "system"),
                ("P005", PatientStatus.ACTIVE, now_str, "system"),
                ("P006", PatientStatus.ACTIVE, now_str, "system"),
            ]
            c.executemany(
                "INSERT INTO patient_status (patient_id, status, updated_at, updated_by) VALUES (?,?,?,?)",
                statuses,
            )

            # ── Patient Status History (initial admission events) ────────────
            for pid, status, ts, op in statuses:
                c.execute(
                    "INSERT INTO patient_status_history (patient_id, old_status, new_status, reason, operator, timestamp) VALUES (?,?,?,?,?,?)",
                    (pid, None, status, "Initial admission", op, ts),
                )

            # ── Current Encounters ───────────────────────────────────────────
            encounters = [
                ("ENC-001", "P001", (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
                 "PAT-101", "D001", "Post-operative recovery", "Wound care + physiotherapy", "ACTIVE", "NORMAL"),
                ("ENC-002", "P002", (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
                 "PAT-102", "D002", "Type 2 Diabetes", "Insulin regulation + diet monitoring", "ACTIVE", "NORMAL"),
                ("ENC-003", "P003", (now - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"),
                 "PAT-103", "D001", "Cardiac arrhythmia", "Cardiac monitoring + Metoprolol", "ACTIVE", "HIGH"),
                ("ENC-004", "P004", (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
                 "PAT-104", "D003", "Fractured tibia", "Post-surgical recovery + Paracetamol", "ACTIVE", "NORMAL"),
                ("ENC-005", "P005", (now - timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S"),
                 "PAT-105", "D002", "Chronic bronchitis", "Nebulization + Salbutamol", "ACTIVE", "HIGH"),
                ("ENC-006", "P006", (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"),
                 "PAT-106", "D004", "Acute appendicitis", "Pre-operative preparation", "ACTIVE", "HIGH"),
            ]
            c.executemany(
                "INSERT INTO encounters (encounter_id, patient_id, admission_time, room_id, current_doctor, current_condition, current_treatment, status, priority) VALUES (?,?,?,?,?,?,?,?,?)",
                encounters,
            )

            # ── Prescriptions ────────────────────────────────────────────────
            prescriptions = [
                ("RX-001", "P001", "D001", "MED002", "650 mg", "Every 6 hours", "ORAL",
                 (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
                 (now + timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"),
                 "Take with food", "ACTIVE"),
                ("RX-002", "P001", "D001", "MED001", "500 mg", "Every 8 hours", "ORAL",
                 (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
                 (now + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),
                 "Complete full course", "ACTIVE"),
                ("RX-003", "P002", "D002", "MED004", "100 IU/mL", "Before meals", "SUBCUTANEOUS",
                 (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
                 (now + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S"),
                 "Monitor blood glucose", "ACTIVE"),
                ("RX-004", "P003", "D001", "MED003", "50 mg", "Every 12 hours", "ORAL",
                 (now - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"),
                 (now + timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S"),
                 "Monitor heart rate and BP", "ACTIVE"),
                ("RX-005", "P004", "D003", "MED002", "650 mg", "Every 8 hours", "ORAL",
                 (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
                 (now + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),
                 "For pain management", "ACTIVE"),
                ("RX-006", "P005", "D002", "MED008", "100 mcg", "Every 6 hours", "INHALATION",
                 (now - timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S"),
                 (now + timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S"),
                 "2 puffs each time", "ACTIVE"),
                ("RX-007", "P006", "D004", "MED006", "1 g IV", "Every 24 hours", "INTRAVENOUS",
                 (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"),
                 (now + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
                 "Pre-operative prophylaxis", "ACTIVE"),
            ]
            c.executemany(
                "INSERT INTO prescriptions (prescription_id, patient_id, doctor_id, medicine_id, dosage, frequency, route, start_time, end_time, special_instructions, status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                prescriptions,
            )

            # ── Medication Schedules (next pending doses) ────────────────────
            schedules = []
            schedule_counter = 0
            for rx_id, pid, _, med_id, dosage, freq, *_ in prescriptions:
                # Create 2 pending schedules per prescription
                for offset_hours in (0, 6):
                    schedule_counter += 1
                    sched_time = (now + timedelta(hours=offset_hours)).strftime("%Y-%m-%d %H:%M:%S")
                    schedules.append((
                        f"SCH-{schedule_counter:04d}",
                        pid, rx_id, sched_time, "PENDING", None, None,
                    ))
            c.executemany(
                "INSERT INTO medication_schedules (schedule_id, patient_id, prescription_id, scheduled_time, status, assigned_robot, delivery_time) VALUES (?,?,?,?,?,?,?)",
                schedules,
            )

            # ── Patient History (previous admissions for P001 and P005) ──────
            history = [
                ("P001", (now - timedelta(days=365)).strftime("%Y-%m-%d"),
                 (now - timedelta(days=358)).strftime("%Y-%m-%d"),
                 "Dengue fever", "IV fluids and monitoring", "D002", "PAT-102",
                 "Full recovery. Discharged with follow-up."),
                ("P005", (now - timedelta(days=180)).strftime("%Y-%m-%d"),
                 (now - timedelta(days=174)).strftime("%Y-%m-%d"),
                 "Pneumonia", "Antibiotics IV + Respiratory therapy", "D002", "PAT-103",
                 "Responded well to treatment."),
                ("P005", (now - timedelta(days=60)).strftime("%Y-%m-%d"),
                 (now - timedelta(days=55)).strftime("%Y-%m-%d"),
                 "Bronchitis exacerbation", "Nebulization + steroids", "D002", "PAT-105",
                 "Discharged with inhaler prescription."),
            ]
            c.executemany(
                "INSERT INTO patient_history (patient_id, admission_date, discharge_date, condition, treatment, doctor_id, room_id, notes) VALUES (?,?,?,?,?,?,?,?)",
                history,
            )

            # ── Initial Hospital Tasks ───────────────────────────────────────
            date_prefix = now.strftime("%Y%m%d")
            initial_tasks = [
                (f"MED-{date_prefix}-0001", "MEDICINE_DELIVERY", "NORMAL", "P001", "PHARMACY", "PAT-101", "Amoxicillin 500 mg", "Arogya_Delivery", "IN_TRANSIT", "Routine scheduled dose"),
                (f"GDE-{date_prefix}-0002", "PATIENT_GUIDANCE", "HIGH", "P003", "TRIAGE", "ICU-01", None, "Mitra_Reception", "ASSIGNED", "Priority ICU transfer"),
                (f"SUP-{date_prefix}-0003", "EQUIPMENT_TRANSPORT", "NORMAL", "P005", "PAT-105", "PATHOLOGY", "Blood vial test panel", "Sahayak_Support", "PENDING", "Pathology stat order"),
                (f"EMR-{date_prefix}-0004", "EMERGENCY_RESPONSE", "EMERGENCY", "P006", "EMR-01", "PAT-106", "Trauma Kit", "Garuda_Emergency", "PENDING", "Standby emergency preemption"),
            ]
            c.executemany(
                "INSERT OR IGNORE INTO hospital_tasks (task_id, type, priority, patient_id, source, destination, item, assigned_robot, status, notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                initial_tasks,
            )

        log.info("Seeded: 6 patients, 4 doctors, 8 medicines, 7 prescriptions, %d schedules, 3 history records, 4 tasks.",
                 len(schedules))

    # ── Patient Queries ──────────────────────────────────────────────────────

    def get_patient(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Get a single patient by ID."""
        with self._cursor() as c:
            c.execute("SELECT * FROM patients WHERE patient_id = ?", (patient_id,))
            row = c.fetchone()
            return dict(row) if row else None

    def get_all_patients(self) -> List[Dict[str, Any]]:
        """Get all patients."""
        with self._cursor() as c:
            c.execute("SELECT * FROM patients ORDER BY patient_id")
            return [dict(r) for r in c.fetchall()]

    def get_patient_status(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Get current live status for a patient."""
        with self._cursor() as c:
            c.execute("""
                SELECT ps.*, p.name, p.room_id, p.condition, p.attending_doctor_id,
                       d.name as doctor_name, d.specialization
                FROM patient_status ps
                JOIN patients p ON ps.patient_id = p.patient_id
                LEFT JOIN doctors d ON p.attending_doctor_id = d.doctor_id
                WHERE ps.patient_id = ?
            """, (patient_id,))
            row = c.fetchone()
            return dict(row) if row else None

    def get_active_patients(self) -> List[Dict[str, Any]]:
        """Get all patients with non-discharged, non-inactive status."""
        with self._cursor() as c:
            c.execute("""
                SELECT p.*, ps.status as live_status, d.name as doctor_name
                FROM patients p
                JOIN patient_status ps ON p.patient_id = ps.patient_id
                LEFT JOIN doctors d ON p.attending_doctor_id = d.doctor_id
                WHERE ps.status NOT IN ('DISCHARGED', 'INACTIVE')
                ORDER BY
                    CASE ps.status
                        WHEN 'EMERGENCY' THEN 0
                        WHEN 'ACTIVE' THEN 1
                        WHEN 'WAITING' THEN 2
                        WHEN 'OUTPATIENT' THEN 3
                        ELSE 4
                    END,
                    p.patient_id
            """)
            return [dict(r) for r in c.fetchall()]

    def set_patient_status(
        self,
        patient_id: str,
        new_status: str,
        reason: str = "",
        operator: str = "system",
    ) -> bool:
        """Update patient live status and record history.

        Does NOT overwrite previous status — records an immutable history entry.

        Returns:
            True if the status was changed, False if the patient was not found.
        """
        if new_status not in PatientStatus.ALL:
            log.warning("Invalid patient status: %s", new_status)
            return False

        with self._cursor() as c:
            # Get current status
            c.execute("SELECT status FROM patient_status WHERE patient_id = ?", (patient_id,))
            row = c.fetchone()
            if row is None:
                log.warning("Patient %s not found in patient_status table.", patient_id)
                return False

            old_status = row["status"]
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Update current status
            c.execute(
                "UPDATE patient_status SET status = ?, updated_at = ?, updated_by = ? WHERE patient_id = ?",
                (new_status, now_str, operator, patient_id),
            )

            # Record in immutable history
            c.execute(
                "INSERT INTO patient_status_history (patient_id, old_status, new_status, reason, operator, timestamp) VALUES (?,?,?,?,?,?)",
                (patient_id, old_status, new_status, reason, operator, now_str),
            )

            # Update encounter status if applicable
            if new_status == PatientStatus.DISCHARGED:
                c.execute(
                    "UPDATE encounters SET status = 'DISCHARGED' WHERE patient_id = ? AND status = 'ACTIVE'",
                    (patient_id,),
                )
                c.execute(
                    "UPDATE patients SET admission_status = 'DISCHARGED' WHERE patient_id = ?",
                    (patient_id,),
                )
            elif new_status == PatientStatus.EMERGENCY:
                c.execute(
                    "UPDATE encounters SET priority = 'EMERGENCY' WHERE patient_id = ? AND status = 'ACTIVE'",
                    (patient_id,),
                )
                c.execute(
                    "UPDATE patients SET priority = 'EMERGENCY' WHERE patient_id = ?",
                    (patient_id,),
                )
                # Look up patient room for emergency dispatch
                patient_room = "PAT-103"
                try:
                    c.execute("SELECT room_id FROM patients WHERE patient_id = ?", (patient_id,))
                    row = c.fetchone()
                    if row and row[0]:
                        patient_room = row[0]
                except Exception:
                    pass

                try:
                    from utilities.event_bus import EVENT_BUS, HospitalEvent
                    EVENT_BUS.publish(
                        HospitalEvent.EMERGENCY_ALERT,
                        data={
                            "patient_id": patient_id,
                            "room": patient_room,
                            "condition": reason or "Emergency Code Blue",
                            "priority": 1,
                        },
                        source="hospital_db",
                    )
                except Exception:
                    pass

            log.info("Patient %s status: %s → %s (reason: %s, operator: %s)",
                     patient_id, old_status, new_status, reason, operator)
            return True

    def update_patient_status(self, patient_id: str, new_status: str, reason: str = "", changed_by: str = "system") -> bool:
        """Alias for set_patient_status."""
        return self.set_patient_status(patient_id, new_status, reason, changed_by)

    def get_status_history(self, patient_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get status change history for a patient (most recent first)."""
        with self._cursor() as c:
            c.execute("""
                SELECT id, patient_id,
                       old_status, old_status AS previous_status,
                       new_status, reason, operator,
                       timestamp, timestamp AS changed_at
                FROM patient_status_history
                WHERE patient_id = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
            """, (patient_id, limit))
            return [dict(r) for r in c.fetchall()]

    def get_patient_status_history(self, patient_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Alias for get_status_history."""
        return self.get_status_history(patient_id, limit)

    # ── Doctor Queries ───────────────────────────────────────────────────────

    def get_doctor(self, doctor_id: str) -> Optional[Dict[str, Any]]:
        """Get doctor by ID."""
        with self._cursor() as c:
            c.execute("SELECT * FROM doctors WHERE doctor_id = ?", (doctor_id,))
            row = c.fetchone()
            return dict(row) if row else None

    def get_attending_doctor(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Get the doctor attending a specific patient."""
        with self._cursor() as c:
            c.execute("""
                SELECT d.* FROM doctors d
                JOIN patients p ON p.attending_doctor_id = d.doctor_id
                WHERE p.patient_id = ?
            """, (patient_id,))
            row = c.fetchone()
            return dict(row) if row else None

    def get_all_doctors(self) -> List[Dict[str, Any]]:
        """Get all doctors."""
        with self._cursor() as c:
            c.execute("SELECT * FROM doctors ORDER BY doctor_id")
            return [dict(r) for r in c.fetchall()]

    # ── Medicine Queries ─────────────────────────────────────────────────────

    def get_medicine(self, medicine_id: str) -> Optional[Dict[str, Any]]:
        """Get medicine by ID."""
        with self._cursor() as c:
            c.execute("SELECT * FROM medicines WHERE medicine_id = ?", (medicine_id,))
            row = c.fetchone()
            return dict(row) if row else None

    def get_medicine_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get medicine by name (case-insensitive)."""
        with self._cursor() as c:
            c.execute("SELECT * FROM medicines WHERE LOWER(name) = LOWER(?)", (name,))
            row = c.fetchone()
            return dict(row) if row else None

    def get_all_medicines(self) -> List[Dict[str, Any]]:
        """Get all medicines."""
        with self._cursor() as c:
            c.execute("SELECT * FROM medicines ORDER BY medicine_id")
            return [dict(r) for r in c.fetchall()]

    def update_medicine_stock(self, medicine_id: str, delta: int) -> bool:
        """Adjust medicine stock by delta (positive = add, negative = consume)."""
        with self._cursor() as c:
            c.execute("UPDATE medicines SET stock = MAX(0, stock + ?) WHERE medicine_id = ?",
                      (delta, medicine_id))
            return c.rowcount > 0

    # ── Prescription Queries ─────────────────────────────────────────────────

    def get_prescriptions(self, patient_id: str) -> List[Dict[str, Any]]:
        """Get all active prescriptions for a patient."""
        with self._cursor() as c:
            c.execute("""
                SELECT rx.*, m.name as medicine_name, m.category as medicine_category,
                       d.name as doctor_name
                FROM prescriptions rx
                JOIN medicines m ON rx.medicine_id = m.medicine_id
                JOIN doctors d ON rx.doctor_id = d.doctor_id
                WHERE rx.patient_id = ? AND rx.status = 'ACTIVE'
                ORDER BY rx.created_at DESC
            """, (patient_id,))
            return [dict(r) for r in c.fetchall()]

    # ── Medication Schedule Queries ──────────────────────────────────────────

    def get_pending_medications(self, patient_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get pending medication schedules, optionally filtered by patient."""
        with self._cursor() as c:
            if patient_id:
                c.execute("""
                    SELECT ms.*, p.name as patient_name, p.room_id,
                           rx.medicine_id, rx.dosage, rx.route,
                           m.name as medicine_name
                    FROM medication_schedules ms
                    JOIN patients p ON ms.patient_id = p.patient_id
                    JOIN prescriptions rx ON ms.prescription_id = rx.prescription_id
                    JOIN medicines m ON rx.medicine_id = m.medicine_id
                    WHERE ms.patient_id = ? AND ms.status = 'PENDING'
                    ORDER BY ms.scheduled_time
                """, (patient_id,))
            else:
                c.execute("""
                    SELECT ms.*, p.name as patient_name, p.room_id,
                           rx.medicine_id, rx.dosage, rx.route,
                           m.name as medicine_name
                    FROM medication_schedules ms
                    JOIN patients p ON ms.patient_id = p.patient_id
                    JOIN prescriptions rx ON ms.prescription_id = rx.prescription_id
                    JOIN medicines m ON rx.medicine_id = m.medicine_id
                    WHERE ms.status = 'PENDING'
                    ORDER BY ms.scheduled_time
                """)
            return [dict(r) for r in c.fetchall()]

    def get_medication_schedules(self, patient_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all medication schedules, optionally filtered by patient."""
        with self._cursor() as c:
            if patient_id:
                c.execute("""
                    SELECT ms.*, p.name as patient_name, p.room_id,
                           rx.medicine_id, rx.dosage, rx.route,
                           m.name as medicine_name
                    FROM medication_schedules ms
                    JOIN patients p ON ms.patient_id = p.patient_id
                    JOIN prescriptions rx ON ms.prescription_id = rx.prescription_id
                    JOIN medicines m ON rx.medicine_id = m.medicine_id
                    WHERE ms.patient_id = ?
                    ORDER BY ms.scheduled_time
                """, (patient_id,))
            else:
                c.execute("""
                    SELECT ms.*, p.name as patient_name, p.room_id,
                           rx.medicine_id, rx.dosage, rx.route,
                           m.name as medicine_name
                    FROM medication_schedules ms
                    JOIN patients p ON ms.patient_id = p.patient_id
                    JOIN prescriptions rx ON ms.prescription_id = rx.prescription_id
                    JOIN medicines m ON rx.medicine_id = m.medicine_id
                    ORDER BY ms.scheduled_time
                """)
            return [dict(r) for r in c.fetchall()]


    def get_due_medications(self) -> List[Dict[str, Any]]:
        """Get medications that are due now (scheduled_time <= current time and still PENDING)."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._cursor() as c:
            c.execute("""
                SELECT ms.*, p.name as patient_name, p.room_id,
                       rx.medicine_id, rx.dosage, rx.route, rx.special_instructions,
                       m.name as medicine_name
                FROM medication_schedules ms
                JOIN patients p ON ms.patient_id = p.patient_id
                JOIN prescriptions rx ON ms.prescription_id = rx.prescription_id
                JOIN medicines m ON rx.medicine_id = m.medicine_id
                JOIN patient_status ps ON ms.patient_id = ps.patient_id
                WHERE ms.status = 'PENDING'
                  AND ms.scheduled_time <= ?
                  AND ps.status NOT IN ('DISCHARGED', 'INACTIVE')
                ORDER BY ms.scheduled_time
            """, (now_str,))
            return [dict(r) for r in c.fetchall()]

    def update_medication_schedule(
        self,
        schedule_id: str,
        status: str,
        assigned_robot: Optional[str] = None,
    ) -> bool:
        """Update a medication schedule entry."""
        with self._cursor() as c:
            if assigned_robot:
                c.execute(
                    "UPDATE medication_schedules SET status = ?, assigned_robot = ? WHERE schedule_id = ?",
                    (status, assigned_robot, schedule_id),
                )
            else:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                delivery_time = now_str if status == MedicationScheduleStatus.DELIVERED else None
                c.execute(
                    "UPDATE medication_schedules SET status = ?, delivery_time = ? WHERE schedule_id = ?",
                    (status, delivery_time, schedule_id),
                )
            return c.rowcount > 0

    def record_medication_delivery(
        self,
        patient_id: str,
        medicine_name: str,
        delivered_by: str = "Arogya_Delivery",
        room_id: Optional[str] = None,
        schedule_id: Optional[str] = None,
        verification_passed: bool = True,
        verification_notes: str = "",
        mission_id: Optional[str] = None,
    ) -> bool:
        """Record a verified bedside medication delivery event.

        - Deducts stock from medicines table
        - Updates medication_schedules row to DELIVERED with timestamp and delivering robot
        - Updates hospital_tasks status for mission_id (or patient_id) to COMPLETED
        - Inserts an immutable audit history event in patient_status_history
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._cursor() as c:
            # 1. Deduct stock from medicines
            c.execute("SELECT medicine_id, stock FROM medicines WHERE LOWER(name) = LOWER(?)", (medicine_name,))
            med_row = c.fetchone()
            if med_row:
                med_id = med_row["medicine_id"]
                c.execute("UPDATE medicines SET stock = MAX(0, stock - 1) WHERE medicine_id = ?", (med_id,))

            # 2. Update schedule if given or find pending schedule for patient and medicine
            if schedule_id:
                c.execute(
                    "UPDATE medication_schedules SET status = 'DELIVERED', assigned_robot = ?, delivery_time = ? WHERE schedule_id = ?",
                    (delivered_by, now_str, schedule_id),
                )
            else:
                c.execute("""
                    SELECT ms.schedule_id
                    FROM medication_schedules ms
                    JOIN prescriptions rx ON ms.prescription_id = rx.prescription_id
                    JOIN medicines m ON rx.medicine_id = m.medicine_id
                    WHERE ms.patient_id = ? AND LOWER(m.name) = LOWER(?) AND ms.status = 'PENDING'
                    ORDER BY ms.scheduled_time
                    LIMIT 1
                """, (patient_id, medicine_name))
                sched = c.fetchone()
                if sched:
                    c.execute(
                        "UPDATE medication_schedules SET status = 'DELIVERED', assigned_robot = ?, delivery_time = ? WHERE schedule_id = ?",
                        (delivered_by, now_str, sched["schedule_id"]),
                    )

            # 3. Update task in hospital_tasks if mission_id is provided
            if mission_id:
                notes = f"Verified bedside delivery by {delivered_by}. {verification_notes}".strip()
                c.execute("""
                    UPDATE hospital_tasks
                    SET status = 'COMPLETED', completed_time = ?, notes = ?
                    WHERE task_id = ?
                """, (now_str, notes, mission_id))

            # 4. Record audit history in patient_status_history
            v_status = "VERIFIED" if verification_passed else "UNVERIFIED"
            audit_reason = f"Medication {medicine_name} delivered ({v_status}) by {delivered_by} to room {room_id or 'Bedside'} [Mission: {mission_id or 'N/A'}]"
            c.execute("SELECT status FROM patient_status WHERE patient_id = ?", (patient_id,))
            p_status_row = c.fetchone()
            curr_status = p_status_row["status"] if p_status_row else "ACTIVE"
            c.execute("""
                INSERT INTO patient_status_history (patient_id, old_status, new_status, reason, operator, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (patient_id, curr_status, curr_status, audit_reason, delivered_by, now_str))

        log.info(
            "Recorded medication delivery: patient=%s, medicine=%s, robot=%s, verified=%s, mission=%s",
            patient_id, medicine_name, delivered_by, verification_passed, mission_id,
        )
        return True

    # ── Encounter Queries ────────────────────────────────────────────────────

    def get_current_encounter(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Get the current active encounter for a patient."""
        with self._cursor() as c:
            c.execute("""
                SELECT e.*, d.name as doctor_name, d.specialization
                FROM encounters e
                LEFT JOIN doctors d ON e.current_doctor = d.doctor_id
                WHERE e.patient_id = ? AND e.status = 'ACTIVE'
                ORDER BY e.admission_time DESC
                LIMIT 1
            """, (patient_id,))
            row = c.fetchone()
            return dict(row) if row else None

    # ── Task Management ──────────────────────────────────────────────────────

    def create_task(
        self,
        task_type: str,
        priority: str = "NORMAL",
        patient_id: Optional[str] = None,
        source: Optional[str] = None,
        destination: Optional[str] = None,
        item: Optional[str] = None,
        notes: Optional[str] = None,
        task_id: Optional[str] = None,
        assigned_robot: Optional[str] = None,
    ) -> str:
        """Create a new hospital task and return its persistent ID."""
        if task_id:
            tid = task_id
        else:
            date_tag = datetime.now().strftime("%Y%m%d")
            rand_suffix = uuid.uuid4().hex[:4].upper()
            t_upper = task_type.upper()
            if "DELIVER" in t_upper or "MEDIC" in t_upper:
                prefix = "MED"
            elif "EMERGENCY" in t_upper or "CODE" in t_upper:
                prefix = "EMR"
            elif "GUIDE" in t_upper or "ESCORT" in t_upper:
                prefix = "GDE"
            elif "SUPPORT" in t_upper or "SUPPLY" in t_upper or "SAMPLE" in t_upper or "EQUIPMENT" in t_upper:
                prefix = "SUP"
            else:
                prefix = "MISSION"
            tid = f"{prefix}-{date_tag}-{rand_suffix}"

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._cursor() as c:
            c.execute("""
                INSERT INTO hospital_tasks (task_id, type, priority, patient_id, source, destination, item, created_time, assigned_robot, status, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (tid, task_type, priority, patient_id, source, destination, item, now_str, assigned_robot, TaskStatus.PENDING, notes))
        log.info("Created task %s: %s (priority=%s, patient=%s, robot=%s)", tid, task_type, priority, patient_id, assigned_robot)
        return tid

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a single task by its task_id or mission_id."""
        with self._cursor() as c:
            c.execute("""
                SELECT task_id,
                       task_id AS mission_id,
                       type,
                       type AS task_type,
                       priority,
                       patient_id,
                       source,
                       destination,
                       destination AS destination_room,
                       item,
                       created_time,
                       assigned_robot,
                       assigned_robot AS assigned_robot_id,
                       status,
                       completed_time,
                       notes
                FROM hospital_tasks
                WHERE task_id = ?
            """, (task_id,))
            row = c.fetchone()
            return dict(row) if row else None

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get all hospital tasks regardless of status."""
        with self._cursor() as c:
            c.execute("""
                SELECT task_id,
                       task_id AS mission_id,
                       type,
                       type AS task_type,
                       priority,
                       patient_id,
                       source,
                       destination,
                       destination AS destination_room,
                       item,
                       created_time,
                       assigned_robot,
                       assigned_robot AS assigned_robot_id,
                       status,
                       completed_time,
                       notes
                FROM hospital_tasks
                ORDER BY created_time DESC
            """)
            return [dict(r) for r in c.fetchall()]

    def get_tasks_by_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        """Get all tasks for a specific patient."""
        with self._cursor() as c:
            c.execute("""
                SELECT task_id,
                       task_id AS mission_id,
                       type,
                       type AS task_type,
                       priority,
                       patient_id,
                       source,
                       destination,
                       destination AS destination_room,
                       item,
                       created_time,
                       assigned_robot,
                       assigned_robot AS assigned_robot_id,
                       status,
                       completed_time,
                       notes
                FROM hospital_tasks
                WHERE patient_id = ?
                ORDER BY created_time DESC
            """, (patient_id,))
            return [dict(r) for r in c.fetchall()]

    def update_task_status(
        self,
        task_id: str,
        status: str,
        assigned_robot: Optional[str] = None,
    ) -> bool:
        """Update task status and optionally assign a robot."""
        with self._cursor() as c:
            updates = ["status = ?"]
            params: list = [status]
            if assigned_robot:
                updates.append("assigned_robot = ?")
                params.append(assigned_robot)
            if status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                updates.append("completed_time = ?")
                params.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            params.append(task_id)
            c.execute(f"UPDATE hospital_tasks SET {', '.join(updates)} WHERE task_id = ?", params)
            return c.rowcount > 0

    def archive_completed_task(self, task_id: str) -> bool:
        """Move a completed/failed task to the history table."""
        with self._cursor() as c:
            c.execute("SELECT * FROM hospital_tasks WHERE task_id = ?", (task_id,))
            row = c.fetchone()
            if not row:
                return False
            d = dict(row)
            duration = None
            if d.get("completed_time") and d.get("created_time"):
                try:
                    t0 = datetime.strptime(d["created_time"], "%Y-%m-%d %H:%M:%S")
                    t1 = datetime.strptime(d["completed_time"], "%Y-%m-%d %H:%M:%S")
                    duration = (t1 - t0).total_seconds()
                except (ValueError, TypeError):
                    pass
            c.execute("""
                INSERT INTO task_history (task_id, type, priority, patient_id, source, destination, assigned_robot, status, created_time, completed_time, duration_seconds, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (d["task_id"], d["type"], d["priority"], d.get("patient_id"),
                  d.get("source"), d.get("destination"), d.get("assigned_robot"),
                  d["status"], d.get("created_time"), d.get("completed_time"),
                  duration, d.get("notes")))
            c.execute("DELETE FROM hospital_tasks WHERE task_id = ?", (task_id,))
            return True

    def get_pending_tasks(self) -> List[Dict[str, Any]]:
        """Get all pending/assigned/in-progress tasks."""
        with self._cursor() as c:
            c.execute("""
                SELECT * FROM hospital_tasks
                WHERE status IN ('PENDING', 'ASSIGNED', 'IN_TRANSIT', 'IN_PROGRESS')
                ORDER BY
                    CASE priority
                        WHEN 'EMERGENCY' THEN 0
                        WHEN 'HIGH' THEN 1
                        WHEN 'NORMAL' THEN 2
                        ELSE 3
                    END,
                    created_time
            """)
            return [dict(r) for r in c.fetchall()]

    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """Get all active, pending, or in-progress hospital tasks for robot fleet."""
        with self._cursor() as c:
            c.execute("""
                SELECT task_id,
                       task_id AS mission_id,
                       type,
                       type AS task_type,
                       priority,
                       patient_id,
                       source,
                       destination,
                       destination AS destination_room,
                       item,
                       created_time,
                       assigned_robot,
                       assigned_robot AS assigned_robot_id,
                       status,
                       completed_time,
                       notes
                FROM hospital_tasks
                WHERE status NOT IN ('COMPLETED', 'CANCELLED', 'FAILED')
                ORDER BY
                    CASE priority
                        WHEN 'EMERGENCY' THEN 0
                        WHEN 'HIGH' THEN 1
                        WHEN 'NORMAL' THEN 2
                        ELSE 3
                    END,
                    created_time DESC
            """)
            rows = [dict(r) for r in c.fetchall()]
            if not rows:
                date_prefix = datetime.now().strftime("%Y%m%d")
                sample_tasks = [
                    (f"MED-{date_prefix}-0001", "MEDICINE_DELIVERY", "NORMAL", "P001", "PHARMACY", "PAT-101", "Amoxicillin 500 mg", "Arogya_Delivery", "IN_TRANSIT", "Routine scheduled dose"),
                    (f"GDE-{date_prefix}-0002", "PATIENT_GUIDANCE", "HIGH", "P003", "TRIAGE", "ICU-01", None, "Mitra_Reception", "ASSIGNED", "Priority ICU transfer"),
                    (f"SUP-{date_prefix}-0003", "EQUIPMENT_TRANSPORT", "NORMAL", "P005", "PAT-105", "PATHOLOGY", "Blood vial test panel", "Sahayak_Support", "PENDING", "Pathology stat order"),
                    (f"EMR-{date_prefix}-0004", "EMERGENCY_RESPONSE", "EMERGENCY", "P006", "EMR-01", "PAT-106", "Trauma Kit", "Garuda_Emergency", "PENDING", "Standby emergency preemption"),
                ]
                for tid, ttype, prio, pid, src, dst, itm, robot, stat, nts in sample_tasks:
                    c.execute("""
                        INSERT OR IGNORE INTO hospital_tasks
                        (task_id, type, priority, patient_id, source, destination, item, assigned_robot, status, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (tid, ttype, prio, pid, src, dst, itm, robot, stat, nts))
                c.execute("""
                    SELECT task_id,
                           task_id AS mission_id,
                           type,
                           type AS task_type,
                           priority,
                           patient_id,
                           source,
                           destination,
                           destination AS destination_room,
                           item,
                           created_time,
                           assigned_robot,
                           assigned_robot AS assigned_robot_id,
                           status,
                           completed_time,
                           notes
                    FROM hospital_tasks
                    WHERE status NOT IN ('COMPLETED', 'CANCELLED', 'FAILED')
                    ORDER BY
                        CASE priority
                            WHEN 'EMERGENCY' THEN 0
                            WHEN 'HIGH' THEN 1
                            WHEN 'NORMAL' THEN 2
                            ELSE 3
                        END,
                        created_time DESC
                """)
                rows = [dict(r) for r in c.fetchall()]
            return rows

    # ── Patient Room Lookup ──────────────────────────────────────────────────

    def get_patient_in_room(self, room_id: str) -> Optional[Dict[str, Any]]:
        """Get the patient currently assigned to a room."""
        with self._cursor() as c:
            c.execute("""
                SELECT p.*, ps.status as live_status
                FROM patients p
                JOIN patient_status ps ON p.patient_id = ps.patient_id
                WHERE p.room_id = ? AND ps.status NOT IN ('DISCHARGED', 'INACTIVE')
            """, (room_id,))
            row = c.fetchone()
            return dict(row) if row else None

    # ── Summary / Dashboard ──────────────────────────────────────────────────

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get a high-level summary for the dashboard."""
        with self._cursor() as c:
            c.execute("SELECT COUNT(*) FROM patients")
            total_patients = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM patient_status WHERE status = 'ACTIVE'")
            active = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM patient_status WHERE status = 'EMERGENCY'")
            emergency = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM patient_status WHERE status = 'WAITING'")
            waiting = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM hospital_tasks WHERE status IN ('PENDING','ASSIGNED','IN_TRANSIT','IN_PROGRESS')")
            pending_tasks = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM medication_schedules WHERE status = 'PENDING'")
            pending_meds = c.fetchone()[0]
            return {
                "total_patients": total_patients,
                "active": active,
                "emergency": emergency,
                "waiting": waiting,
                "pending_tasks": pending_tasks,
                "pending_medications": pending_meds,
            }

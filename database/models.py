"""
AAROGYA Hospital Autonomous Assistance Platform — Database Models (SQLAlchemy 2.0)
==================================================================================
Comprehensive relational schema for hospital operations, clinical workflows,
robot task lifecycle, RBAC authentication, and audit trails.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── ENUMS ───────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    DOCTOR = "DOCTOR"
    NURSE = "NURSE"
    PATIENT = "PATIENT"
    VISITOR = "VISITOR"


class PatientStatusEnum(str, enum.Enum):
    ACTIVE = "ACTIVE"          # Under treatment
    WAITING = "WAITING"        # Triage / waiting
    EMERGENCY = "EMERGENCY"    # Critical care / Code Blue
    OUTPATIENT = "OUTPATIENT"  # Day care
    DISCHARGED = "DISCHARGED"  # Released
    INACTIVE = "INACTIVE"


class PrescriptionStatusEnum(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DISCONTINUED = "DISCONTINUED"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"


class ScheduleStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    MISSED = "MISSED"
    CANCELLED = "CANCELLED"


class TaskPriorityEnum(str, enum.Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EMERGENCY = "EMERGENCY"


class TaskTypeEnum(str, enum.Enum):
    MEDICINE_DELIVERY = "MEDICINE_DELIVERY"
    PATIENT_ESCORT = "PATIENT_ESCORT"
    EMERGENCY_RESPONSE = "EMERGENCY_RESPONSE"
    SUPPLY_FETCH = "SUPPLY_FETCH"
    ROOM_GUIDANCE = "ROOM_GUIDANCE"


class TaskStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    APPROVED = "APPROVED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    ARRIVED = "ARRIVED"
    DELIVERED = "DELIVERED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RobotRoleEnum(str, enum.Enum):
    DELIVERY = "DELIVERY"
    RECEPTION = "RECEPTION"
    EMERGENCY = "EMERGENCY"
    SUPPORT = "SUPPORT"


class RobotStatusEnum(str, enum.Enum):
    IDLE = "IDLE"
    PLANNING = "PLANNING"
    NAVIGATING = "NAVIGATING"
    EXECUTING = "EXECUTING"
    CHARGING = "CHARGING"
    MAINTENANCE = "MAINTENANCE"
    OFFLINE = "OFFLINE"


# ── RELATIONAL ENTITIES ─────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False, default=UserRole.VISITOR, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Profiles
    doctor_profile: Mapped[Optional[Doctor]] = relationship("Doctor", back_populates="user", uselist=False)
    nurse_profile: Mapped[Optional[Nurse]] = relationship("Nurse", back_populates="user", uselist=False)
    patient_profile: Mapped[Optional[Patient]] = relationship("Patient", back_populates="user", uselist=False)
    audit_logs: Mapped[List[AuditLog]] = relationship("AuditLog", back_populates="user")


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    floor: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    is_restricted: Mapped[bool] = mapped_column(Boolean, default=False)

    rooms: Mapped[List[HospitalRoom]] = relationship("HospitalRoom", back_populates="department")
    doctors: Mapped[List[Doctor]] = relationship("Doctor", back_populates="department")
    nurses: Mapped[List[Nurse]] = relationship("Nurse", back_populates="department")


class HospitalRoom(Base):
    __tablename__ = "hospital_rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    department_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("departments.id"), nullable=True)
    zone: Mapped[str] = mapped_column(String(32), default="General")
    x_coord: Mapped[float] = mapped_column(Float, default=0.0)
    y_coord: Mapped[float] = mapped_column(Float, default=0.0)
    z_coord: Mapped[float] = mapped_column(Float, default=0.0)
    approach_yaw: Mapped[float] = mapped_column(Float, default=0.0)
    is_occupied: Mapped[bool] = mapped_column(Boolean, default=False)

    department: Mapped[Optional[Department]] = relationship("Department", back_populates="rooms")
    beds: Mapped[List[Bed]] = relationship("Bed", back_populates="room")
    patients: Mapped[List[Patient]] = relationship("Patient", back_populates="room")


class Bed(Base):
    __tablename__ = "beds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bed_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    room_id: Mapped[int] = mapped_column(Integer, ForeignKey("hospital_rooms.id"), nullable=False)
    is_occupied: Mapped[bool] = mapped_column(Boolean, default=False)

    room: Mapped[HospitalRoom] = relationship("HospitalRoom", back_populates="beds")
    patients: Mapped[List[Patient]] = relationship("Patient", back_populates="bed")


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    staff_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    specialization: Mapped[str] = mapped_column(String(64), nullable=False)
    department_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("departments.id"), nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship("User", back_populates="doctor_profile")
    department: Mapped[Optional[Department]] = relationship("Department", back_populates="doctors")
    patients: Mapped[List[Patient]] = relationship("Patient", back_populates="attending_doctor")
    prescriptions: Mapped[List[Prescription]] = relationship("Prescription", back_populates="doctor")


class Nurse(Base):
    __tablename__ = "nurses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    staff_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    department_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("departments.id"), nullable=True)
    shift: Mapped[str] = mapped_column(String(32), default="Morning")
    is_on_duty: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship("User", back_populates="nurse_profile")
    department: Mapped[Optional[Department]] = relationship("Department", back_populates="nurses")


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    age: Mapped[int] = mapped_column(Integer, default=30)
    gender: Mapped[str] = mapped_column(String(16), default="Other")
    blood_type: Mapped[str] = mapped_column(String(8), default="O+")
    condition: Mapped[str] = mapped_column(String(128), default="Stable")
    admission_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    discharge_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[PatientStatusEnum] = mapped_column(
        Enum(PatientStatusEnum), default=PatientStatusEnum.ACTIVE, nullable=False, index=True
    )
    room_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("hospital_rooms.id"), nullable=True)
    bed_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("beds.id"), nullable=True)
    attending_doctor_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("doctors.id"), nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=True)

    user: Mapped[Optional[User]] = relationship("User", back_populates="patient_profile")
    room: Mapped[Optional[HospitalRoom]] = relationship("HospitalRoom", back_populates="patients")
    bed: Mapped[Optional[Bed]] = relationship("Bed", back_populates="patients")
    attending_doctor: Mapped[Optional[Doctor]] = relationship("Doctor", back_populates="patients")
    prescriptions: Mapped[List[Prescription]] = relationship("Prescription", back_populates="patient")
    medication_schedules: Mapped[List[MedicationSchedule]] = relationship("MedicationSchedule", back_populates="patient")
    tasks: Mapped[List[RobotTask]] = relationship("RobotTask", back_populates="patient")


class Medicine(Base):
    __tablename__ = "medicines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    medicine_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), default="General")
    stock_quantity: Mapped[int] = mapped_column(Integer, default=100)
    unit: Mapped[str] = mapped_column(String(32), default="tablets")
    storage_location: Mapped[str] = mapped_column(String(128), default="PHM-01 Shelf A")
    expiry_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    min_stock_threshold: Mapped[int] = mapped_column(Integer, default=15)
    unit_price: Mapped[float] = mapped_column(Float, default=10.0)

    prescriptions: Mapped[List[Prescription]] = relationship("Prescription", back_populates="medicine")
    tasks: Mapped[List[RobotTask]] = relationship("RobotTask", back_populates="medicine")


class Prescription(Base):
    __tablename__ = "prescriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prescription_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id: Mapped[int] = mapped_column(Integer, ForeignKey("doctors.id"), nullable=False)
    medicine_id: Mapped[int] = mapped_column(Integer, ForeignKey("medicines.id"), nullable=False)
    dosage: Mapped[str] = mapped_column(String(64), nullable=False)
    frequency: Mapped[str] = mapped_column(String(64), default="Every 8 hours")
    frequency_hours: Mapped[int] = mapped_column(Integer, default=8)
    route: Mapped[str] = mapped_column(String(32), default="Oral")
    start_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_days: Mapped[int] = mapped_column(Integer, default=7)
    status: Mapped[PrescriptionStatusEnum] = mapped_column(
        Enum(PrescriptionStatusEnum), default=PrescriptionStatusEnum.ACTIVE, nullable=False, index=True
    )
    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient: Mapped[Patient] = relationship("Patient", back_populates="prescriptions")
    doctor: Mapped[Doctor] = relationship("Doctor", back_populates="prescriptions")
    medicine: Mapped[Medicine] = relationship("Medicine", back_populates="prescriptions")
    schedules: Mapped[List[MedicationSchedule]] = relationship("MedicationSchedule", back_populates="prescription")
    tasks: Mapped[List[RobotTask]] = relationship("RobotTask", back_populates="prescription")


class MedicationSchedule(Base):
    __tablename__ = "medication_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prescription_id: Mapped[int] = mapped_column(Integer, ForeignKey("prescriptions.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    medicine_id: Mapped[int] = mapped_column(Integer, ForeignKey("medicines.id"), nullable=False)
    scheduled_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    status: Mapped[ScheduleStatusEnum] = mapped_column(
        Enum(ScheduleStatusEnum), default=ScheduleStatusEnum.PENDING, nullable=False, index=True
    )
    administered_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    prescription: Mapped[Prescription] = relationship("Prescription", back_populates="schedules")
    patient: Mapped[Patient] = relationship("Patient", back_populates="medication_schedules")
    tasks: Mapped[List[RobotTask]] = relationship("RobotTask", back_populates="schedule")


class Robot(Base):
    __tablename__ = "robots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    robot_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[RobotRoleEnum] = mapped_column(Enum(RobotRoleEnum), default=RobotRoleEnum.DELIVERY)
    status: Mapped[RobotStatusEnum] = mapped_column(
        Enum(RobotStatusEnum), default=RobotStatusEnum.IDLE, nullable=False, index=True
    )
    battery_level: Mapped[float] = mapped_column(Float, default=100.0)
    current_room: Mapped[str] = mapped_column(String(32), default="CHG-01")
    current_x: Mapped[float] = mapped_column(Float, default=0.0)
    current_y: Mapped[float] = mapped_column(Float, default=0.0)
    current_z: Mapped[float] = mapped_column(Float, default=0.0)
    target_x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tasks: Mapped[List[RobotTask]] = relationship("RobotTask", back_populates="assigned_robot")


class RobotTask(Base):
    __tablename__ = "robot_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    task_type: Mapped[TaskTypeEnum] = mapped_column(Enum(TaskTypeEnum), nullable=False)
    priority: Mapped[TaskPriorityEnum] = mapped_column(
        Enum(TaskPriorityEnum), default=TaskPriorityEnum.NORMAL, nullable=False, index=True
    )
    status: Mapped[TaskStatusEnum] = mapped_column(
        Enum(TaskStatusEnum), default=TaskStatusEnum.PENDING, nullable=False, index=True
    )
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id"), nullable=True)
    medicine_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("medicines.id"), nullable=True)
    prescription_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("prescriptions.id"), nullable=True)
    schedule_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("medication_schedules.id"), nullable=True)
    source_location: Mapped[str] = mapped_column(String(64), default="PHM-01")
    destination_location: Mapped[str] = mapped_column(String(64), nullable=False)
    destination_x: Mapped[float] = mapped_column(Float, default=0.0)
    destination_y: Mapped[float] = mapped_column(Float, default=0.0)
    assigned_robot_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("robots.id"), nullable=True)
    assigned_agent: Mapped[str] = mapped_column(String(64), default="DeliveryAgent")
    created_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    authorized_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    cancellation_reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Unique deduplication hash for active medication tasks (prevents duplicate deliveries)
    dedupe_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    patient: Mapped[Optional[Patient]] = relationship("Patient", back_populates="tasks")
    medicine: Mapped[Optional[Medicine]] = relationship("Medicine", back_populates="tasks")
    prescription: Mapped[Optional[Prescription]] = relationship("Prescription", back_populates="tasks")
    schedule: Mapped[Optional[MedicationSchedule]] = relationship("MedicationSchedule", back_populates="tasks")
    assigned_robot: Mapped[Optional[Robot]] = relationship("Robot", back_populates="tasks")
    events: Mapped[List[TaskEvent]] = relationship("TaskEvent", back_populates="task", cascade="all, delete-orphan")


class TaskEvent(Base):
    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("robot_tasks.id"), nullable=False, index=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(64), default="System")
    message: Mapped[str] = mapped_column(String(256), default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    task: Mapped[RobotTask] = relationship("RobotTask", back_populates="events")


class Attendance(Base):
    __tablename__ = "attendance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    check_in: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    check_out: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PRESENT")


class EmergencyEvent(Base):
    __tablename__ = "emergency_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), default="CODE_BLUE")
    department_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("departments.id"), nullable=True)
    room_number: Mapped[str] = mapped_column(String(32), default="ICU-01")
    reported_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_robot_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("robots.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(64), default="anonymous")
    user_role: Mapped[str] = mapped_column(String(32), default="VISITOR")
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), default="Task")
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    patient_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    medicine_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    robot_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    agent_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="SUCCESS")
    duplicate_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    authorization_denied: Mapped[bool] = mapped_column(Boolean, default=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped[Optional[User]] = relationship("User", back_populates="audit_logs")

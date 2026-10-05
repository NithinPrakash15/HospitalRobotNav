"""
AAROGYA Platform — Robot Task Lifecycle & Duplicate Prevention Engine
=====================================================================
Strict backend-level duplicate detection, multi-step validation,
state machine transitions, and audit trail logging.
"""

from __future__ import annotations

import datetime
import hashlib
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.medication_engine import MedicationEngine, MedicationValidationResult
from database.models import (
    AuditLog,
    HospitalRoom,
    Medicine,
    Patient,
    Robot,
    RobotRoleEnum,
    RobotStatusEnum,
    RobotTask,
    TaskEvent,
    TaskPriorityEnum,
    TaskStatusEnum,
    TaskTypeEnum,
    User,
    UserRole,
)


class DuplicateTaskException(HTTPException):
    def __init__(self, existing_task: RobotTask):
        robot_name = existing_task.assigned_robot.name if existing_task.assigned_robot else "Pending Assignment"
        detail = {
            "error": "DUPLICATE_TASK_DETECTED",
            "message": f"Medication delivery is already assigned/in progress for this patient and medicine.",
            "existing_task": {
                "task_id": existing_task.task_code,
                "robot": robot_name,
                "requested_by": existing_task.created_by_user_id,
                "status": existing_task.status.value,
                "timestamp": existing_task.created_at.isoformat(),
            },
        }
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class TaskEngine:
    @staticmethod
    def generate_dedupe_hash(task_type: str, patient_id: Optional[int], medicine_id: Optional[int]) -> str:
        """Computes deterministic hash for detecting active duplicate tasks."""
        raw = f"{task_type}:{patient_id or ''}:{medicine_id or ''}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def check_duplicate_task(
        db: Session,
        task_type: TaskTypeEnum,
        patient_id: Optional[int],
        medicine_id: Optional[int],
    ) -> Optional[RobotTask]:
        """
        Database-level duplicate task check (Section 16).
        Queries for active, non-terminal tasks matching the target patient & medication.
        """
        active_statuses = [
            TaskStatusEnum.PENDING,
            TaskStatusEnum.VALIDATING,
            TaskStatusEnum.APPROVED,
            TaskStatusEnum.ASSIGNED,
            TaskStatusEnum.IN_PROGRESS,
            TaskStatusEnum.ARRIVED,
        ]

        query = db.query(RobotTask).filter(
            RobotTask.task_type == task_type,
            RobotTask.status.in_(active_statuses),
        )
        if patient_id is not None:
            query = query.filter(RobotTask.patient_id == patient_id)
        if medicine_id is not None:
            query = query.filter(RobotTask.medicine_id == medicine_id)

        return query.first()

    @staticmethod
    def create_medicine_delivery_task(
        db: Session,
        patient_id: int,
        medicine_id: int,
        requested_by: User,
        priority: TaskPriorityEnum = TaskPriorityEnum.NORMAL,
        prescription_id: Optional[int] = None,
    ) -> RobotTask:
        """
        Creates a medicine delivery task through the complete clinical & duplicate check pipeline.
        """
        # Step 1: Authorization check
        if requested_by.role not in (UserRole.ADMIN, UserRole.DOCTOR, UserRole.NURSE):
            # Audit denied request
            audit = AuditLog(
                user_id=requested_by.id,
                username=requested_by.username,
                user_role=requested_by.role.value,
                action="TASK_CREATION_DENIED",
                entity_type="Task",
                status="DENIED",
                authorization_denied=True,
                details=f"Unauthorized user {requested_by.username} ({requested_by.role.value}) attempted to create medication delivery task.",
            )
            db.add(audit)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="I can assist with general hospital services, but medication delivery requires an authorized hospital request (Doctor, Nurse, or Admin).",
            )

        # Step 2: Duplicate check at Database level (Section 16)
        existing_task = TaskEngine.check_duplicate_task(
            db,
            task_type=TaskTypeEnum.MEDICINE_DELIVERY,
            patient_id=patient_id,
            medicine_id=medicine_id,
        )
        if existing_task:
            audit = AuditLog(
                user_id=requested_by.id,
                username=requested_by.username,
                user_role=requested_by.role.value,
                action="DUPLICATE_TASK_BLOCKED",
                entity_type="Task",
                entity_id=str(existing_task.id),
                status="BLOCKED",
                duplicate_detected=True,
                details=f"Duplicate request blocked. Task {existing_task.task_code} is already in status {existing_task.status.value}.",
            )
            db.add(audit)
            db.commit()
            raise DuplicateTaskException(existing_task)

        # Step 3: Clinical Pre-condition Validation (Section 15 & 26)
        val = MedicationEngine.validate_medication_delivery(
            db,
            patient_id=patient_id,
            medicine_id=medicine_id,
            prescription_id=prescription_id,
        )
        if not val.is_valid:
            audit = AuditLog(
                user_id=requested_by.id,
                username=requested_by.username,
                user_role=requested_by.role.value,
                action="VALIDATION_FAILED",
                entity_type="Task",
                status="FAILED",
                details=val.reason,
            )
            db.add(audit)
            db.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=val.reason)

        patient = val.patient
        medicine = val.medicine
        rx = val.prescription

        # Resolve destination room
        dest_room = patient.room
        if not dest_room:
            # Fallback to patient's bed room
            dest_room = patient.bed.room if patient.bed else None

        dest_name = dest_room.room_number if dest_room else "ICU-01"
        dest_x = dest_room.x_coord if dest_room else -36.5
        dest_y = dest_room.y_coord if dest_room else 11.0

        # Generate unique Task Code (e.g. TASK-001)
        count = db.query(RobotTask).count() + 1
        task_code = f"TASK-{count:03d}"

        dedupe_hash = TaskEngine.generate_dedupe_hash(
            TaskTypeEnum.MEDICINE_DELIVERY.value, patient.id, medicine.id
        )

        task = RobotTask(
            task_code=task_code,
            task_type=TaskTypeEnum.MEDICINE_DELIVERY,
            priority=priority,
            status=TaskStatusEnum.PENDING,
            patient_id=patient.id,
            medicine_id=medicine.id,
            prescription_id=rx.id,
            source_location="PHM-01",
            destination_location=dest_name,
            destination_x=dest_x,
            destination_y=dest_y,
            assigned_agent="DeliveryAgent",
            created_by_user_id=requested_by.id,
            authorized_by_user_id=requested_by.id,
            dedupe_hash=dedupe_hash,
            created_at=datetime.datetime.utcnow(),
        )
        db.add(task)
        db.flush()

        # Step 4: Log Initial Task Lifecycle Event
        event = TaskEvent(
            task_id=task.id,
            from_status=None,
            to_status=TaskStatusEnum.PENDING.value,
            triggered_by=requested_by.username,
            message=f"Task {task_code} created by {requested_by.full_name}. Priority: {priority.value}.",
        )
        db.add(event)

        # Audit Log
        audit = AuditLog(
            user_id=requested_by.id,
            username=requested_by.username,
            user_role=requested_by.role.value,
            action="CREATE_TASK",
            entity_type="Task",
            entity_id=str(task.id),
            patient_code=patient.patient_code,
            medicine_code=medicine.medicine_code,
            agent_name="CoordinatorAgent",
            details=f"Task {task_code} created: deliver {medicine.name} to {patient.name} at {dest_name}.",
            status="SUCCESS",
        )
        db.add(audit)
        db.commit()
        db.refresh(task)

        # Automatically allocate robot via CoordinatorAgent
        TaskEngine.allocate_and_dispatch(db, task)
        return task

    @staticmethod
    def allocate_and_dispatch(db: Session, task: RobotTask) -> RobotTask:
        """
        CoordinatorAgent allocates the most suitable, available robot for the mission.
        """
        # Find best available robot
        role_pref = RobotRoleEnum.DELIVERY if task.task_type == TaskTypeEnum.MEDICINE_DELIVERY else RobotRoleEnum.EMERGENCY
        robot = db.query(Robot).filter(
            Robot.role == role_pref,
            Robot.is_available == True,
            Robot.status == RobotStatusEnum.IDLE,
        ).first()

        if not robot:
            # Fallback to any IDLE robot
            robot = db.query(Robot).filter(
                Robot.is_available == True,
                Robot.status == RobotStatusEnum.IDLE,
            ).first()

        if robot:
            task.assigned_robot_id = robot.id
            task.status = TaskStatusEnum.ASSIGNED
            robot.is_available = False
            robot.status = RobotStatusEnum.PLANNING

            event = TaskEvent(
                task_id=task.id,
                from_status=TaskStatusEnum.PENDING.value,
                to_status=TaskStatusEnum.ASSIGNED.value,
                triggered_by="CoordinatorAgent",
                message=f"Mission assigned to robot {robot.name} ({robot.robot_id}).",
            )
            db.add(event)
            db.commit()
            db.refresh(task)

        return task

    @staticmethod
    def transition_task_status(
        db: Session,
        task_id: int,
        new_status: TaskStatusEnum,
        triggered_by: str = "System",
        message: str = "",
        progress_pct: Optional[float] = None,
    ) -> RobotTask:
        """
        Manages the strict task lifecycle state machine and logs every transition into TaskEvent.
        """
        task = db.query(RobotTask).filter(RobotTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found.")

        old_status = task.status.value
        task.status = new_status
        if progress_pct is not None:
            task.progress_pct = progress_pct

        now = datetime.datetime.utcnow()
        if new_status == TaskStatusEnum.IN_PROGRESS and not task.started_at:
            task.started_at = now
        elif new_status in (TaskStatusEnum.DELIVERED, TaskStatusEnum.VERIFIED, TaskStatusEnum.FAILED, TaskStatusEnum.CANCELLED):
            task.completed_at = now
            # Free robot upon terminal status
            if task.assigned_robot:
                task.assigned_robot.is_available = True
                task.assigned_robot.status = RobotStatusEnum.IDLE

        event = TaskEvent(
            task_id=task.id,
            from_status=old_status,
            to_status=new_status.value,
            triggered_by=triggered_by,
            message=message or f"Status transitioned from {old_status} to {new_status.value}.",
        )
        db.add(event)
        db.commit()
        db.refresh(task)
        return task

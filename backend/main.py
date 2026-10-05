"""
AAROGYA — Hospital Autonomous Assistance Platform
Master FastAPI Backend Server & Simulation Hub
"""

from __future__ import annotations

import asyncio
import datetime
import os
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth import (
    create_access_token,
    get_current_user,
    get_optional_user,
    require_roles,
    verify_password,
)
from backend.clinical_service import ClinicalService
from backend.medication_engine import MedicationEngine
from backend.simulation_orchestrator import CameraMode, ORCHESTRATOR
from backend.task_engine import DuplicateTaskException, TaskEngine
from backend.voice_service import VoiceService
from database.models import (
    AuditLog,
    Bed,
    Department,
    Doctor,
    EmergencyEvent,
    HospitalRoom,
    MedicationSchedule,
    Medicine,
    Nurse,
    Patient,
    Prescription,
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
from database.seed_data import seed_database
from database.session import get_db, init_db

# Initialize database schema and synthetic data if needed
init_db()
seed_database(force=False)

app = FastAPI(
    title="AAROGYA — Hospital Autonomous Assistance Platform",
    description="Multi-Agent Embodied AI Hospital Robot Integration and Management Backend",
    version="3.0.0",
)

# CORS configuration for Web Application
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── REQUEST/RESPONSE SCHEMAS ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class PrescriptionCreateRequest(BaseModel):
    patient_id: int
    medicine_id: int
    dosage: str
    frequency: str = "Every 8 hours"
    frequency_hours: int = 8
    route: str = "Oral"
    duration_days: int = 7
    instructions: Optional[str] = None


class DiscontinuePrescriptionRequest(BaseModel):
    reason: str


class CreateDeliveryTaskRequest(BaseModel):
    patient_id: int
    medicine_id: int
    priority: str = "NORMAL"  # LOW, NORMAL, HIGH, EMERGENCY
    prescription_id: Optional[int] = None


class TaskTransitionRequest(BaseModel):
    status: str
    message: Optional[str] = None
    progress_pct: Optional[float] = None


class VoiceCommandRequest(BaseModel):
    command: str


class CameraControlRequest(BaseModel):
    mode: str
    target_robot_id: Optional[str] = None


class EmergencyTriggerRequest(BaseModel):
    event_type: str = "CODE_BLUE"
    room_number: str = "ICU-01"
    details: Optional[str] = "Critical patient cardiopulmonary emergency."


# ── 1. AUTHENTICATION & SESSIONS ────────────────────────────────────────────

@app.post("/api/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated.")

    token = create_access_token({"sub": user.username, "role": user.role.value, "uid": user.id})

    # Log login audit
    audit = AuditLog(
        user_id=user.id,
        username=user.username,
        user_role=user.role.value,
        action="LOGIN_SUCCESS",
        entity_type="Auth",
        status="SUCCESS",
        details=f"User {user.username} logged in with role {user.role.value}.",
    )
    db.add(audit)
    db.commit()

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role.value,
            "email": user.email,
        },
    }


@app.get("/api/auth/me")
def get_current_user_profile(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role.value,
        "email": user.email,
    }


# ── 2. HOSPITAL MANAGEMENT ROUTES ───────────────────────────────────────────

@app.get("/api/departments")
def list_departments(db: Session = Depends(get_db)):
    depts = db.query(Department).all()
    return [{
        "id": d.id, "code": d.code, "name": d.name, "floor": d.floor,
        "description": d.description, "is_restricted": d.is_restricted,
    } for d in depts]


@app.get("/api/rooms")
def list_rooms(db: Session = Depends(get_db)):
    rooms = db.query(HospitalRoom).all()
    return [{
        "id": r.id, "room_number": r.room_number, "name": r.name,
        "zone": r.zone, "x": r.x_coord, "y": r.y_coord, "z": r.z_coord,
        "is_occupied": r.is_occupied,
    } for r in rooms]


@app.get("/api/beds")
def list_beds(db: Session = Depends(get_db)):
    beds = db.query(Bed).all()
    return [{
        "id": b.id, "bed_number": b.bed_number, "room_id": b.room_id,
        "room_number": b.room.room_number if b.room else None,
        "is_occupied": b.is_occupied,
    } for b in beds]


@app.get("/api/patients")
def list_patients(status: Optional[str] = None, db: Session = Depends(get_db)):
    patients = ClinicalService.get_all_patients(db, status)
    return [{
        "id": p.id,
        "patient_code": p.patient_code,
        "name": p.name,
        "age": p.age,
        "gender": p.gender,
        "blood_type": p.blood_type,
        "condition": p.condition,
        "status": p.status.value,
        "room": p.room.room_number if p.room else None,
        "bed": p.bed.bed_number if p.bed else None,
        "attending_doctor": p.attending_doctor.user.full_name if p.attending_doctor else None,
        "admission_date": p.admission_date.isoformat(),
        "discharge_date": p.discharge_date.isoformat() if p.discharge_date else None,
    } for p in patients]


@app.get("/api/patients/{patient_id}")
def get_patient_detail(patient_id: int, db: Session = Depends(get_db)):
    p = ClinicalService.get_patient_by_id(db, patient_id)
    return {
        "id": p.id,
        "patient_code": p.patient_code,
        "name": p.name,
        "age": p.age,
        "gender": p.gender,
        "blood_type": p.blood_type,
        "condition": p.condition,
        "status": p.status.value,
        "room": p.room.room_number if p.room else None,
        "bed": p.bed.bed_number if p.bed else None,
        "attending_doctor": p.attending_doctor.user.full_name if p.attending_doctor else None,
        "admission_date": p.admission_date.isoformat(),
        "prescriptions": [{
            "id": rx.id,
            "code": rx.prescription_code,
            "medicine": rx.medicine.name,
            "dosage": rx.dosage,
            "frequency": rx.frequency,
            "status": rx.status.value,
            "instructions": rx.instructions,
        } for rx in p.prescriptions],
    }


@app.post("/api/patients/{patient_id}/discharge")
def discharge_patient(
    patient_id: int,
    user: User = Depends(require_roles(UserRole.DOCTOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    p = ClinicalService.discharge_patient(db, patient_id, user)
    return {"message": f"Patient {p.name} successfully discharged.", "status": p.status.value}


@app.get("/api/doctors")
def list_doctors(db: Session = Depends(get_db)):
    doctors = ClinicalService.get_all_doctors(db)
    return [{
        "id": doc.id,
        "staff_id": doc.staff_id,
        "name": doc.user.full_name,
        "specialization": doc.specialization,
        "department": doc.department.name if doc.department else None,
        "is_available": doc.is_available,
    } for doc in doctors]


@app.get("/api/nurses")
def list_nurses(db: Session = Depends(get_db)):
    nurses = ClinicalService.get_all_nurses(db)
    return [{
        "id": n.id,
        "staff_id": n.staff_id,
        "name": n.user.full_name,
        "department": n.department.name if n.department else None,
        "shift": n.shift,
        "is_on_duty": n.is_on_duty,
    } for n in nurses]


@app.get("/api/medicines")
def list_medicines(db: Session = Depends(get_db)):
    meds = ClinicalService.get_all_medicines(db)
    return [{
        "id": m.id,
        "code": m.medicine_code,
        "name": m.name,
        "category": m.category,
        "stock": m.stock_quantity,
        "location": m.storage_location,
        "min_threshold": m.min_stock_threshold,
        "is_available": m.is_available,
        "is_low_stock": m.stock_quantity <= m.min_stock_threshold,
    } for m in meds]


@app.get("/api/prescriptions")
def list_prescriptions(patient_id: Optional[int] = None, db: Session = Depends(get_db)):
    rxs = ClinicalService.get_all_prescriptions(db, patient_id)
    return [{
        "id": rx.id,
        "code": rx.prescription_code,
        "patient_id": rx.patient_id,
        "patient_name": rx.patient.name,
        "room": rx.patient.room.room_number if rx.patient and rx.patient.room else "Unassigned",
        "doctor_name": rx.doctor.user.full_name if rx.doctor else "Unknown",
        "medicine_id": rx.medicine_id,
        "medicine_name": rx.medicine.name,
        "dosage": rx.dosage,
        "frequency": rx.frequency,
        "route": rx.route,
        "duration_days": rx.duration_days,
        "status": rx.status.value,
        "created_at": rx.created_at.isoformat(),
        "instructions": rx.instructions,
    } for rx in rxs]


@app.post("/api/prescriptions")
def create_prescription(
    req: PrescriptionCreateRequest,
    user: User = Depends(require_roles(UserRole.DOCTOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    rx = ClinicalService.create_prescription(
        db=db,
        patient_id=req.patient_id,
        medicine_id=req.medicine_id,
        dosage=req.dosage,
        frequency=req.frequency,
        frequency_hours=req.frequency_hours,
        route=req.route,
        duration_days=req.duration_days,
        instructions=req.instructions,
        current_user=user,
    )
    # Generate schedule
    MedicationEngine.generate_schedules_for_prescription(db, rx)
    return {"message": "Prescription created successfully.", "prescription_code": rx.prescription_code}


@app.post("/api/prescriptions/{rx_id}/discontinue")
def discontinue_prescription(
    rx_id: int,
    req: DiscontinuePrescriptionRequest,
    user: User = Depends(require_roles(UserRole.DOCTOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    rx = ClinicalService.discontinue_prescription(db, rx_id, req.reason, user)
    return {"message": f"Prescription {rx.prescription_code} has been DISCONTINUED.", "status": rx.status.value}


@app.get("/api/schedules")
def list_schedules(db: Session = Depends(get_db)):
    scheds = db.query(MedicationSchedule).order_by(MedicationSchedule.scheduled_time.asc()).limit(50).all()
    return [{
        "id": s.id,
        "patient": s.patient.name,
        "room": s.patient.room.room_number if s.patient.room else None,
        "medicine": s.prescription.medicine.name if s.prescription else None,
        "scheduled_time": s.scheduled_time.isoformat(),
        "status": s.status.value,
        "notes": s.notes,
    } for s in scheds]


# ── 3. ROBOT TASKS & MULTI-AGENT WORKFLOWS ──────────────────────────────────

@app.get("/api/tasks")
def list_tasks(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(RobotTask).order_by(RobotTask.created_at.desc())
    if status:
        query = query.filter(RobotTask.status == status)
    tasks = query.all()
    return [{
        "id": t.id,
        "task_code": t.task_code,
        "type": t.task_type.value,
        "priority": t.priority.value,
        "status": t.status.value,
        "patient": t.patient.name if t.patient else None,
        "medicine": t.medicine.name if t.medicine else None,
        "source": t.source_location,
        "destination": t.destination_location,
        "robot": t.assigned_robot.name if t.assigned_robot else "Unassigned",
        "agent": t.assigned_agent,
        "progress": t.progress_pct,
        "created_at": t.created_at.isoformat(),
    } for t in tasks]


@app.post("/api/tasks/create-delivery")
def create_medicine_delivery(
    req: CreateDeliveryTaskRequest,
    user: User = Depends(require_roles(UserRole.DOCTOR, UserRole.NURSE, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Creates a medication delivery task with database-level duplicate prevention (Section 16).
    """
    priority_enum = TaskPriorityEnum(req.priority.upper()) if req.priority.upper() in TaskPriorityEnum._value2member_map_ else TaskPriorityEnum.NORMAL
    task = TaskEngine.create_medicine_delivery_task(
        db=db,
        patient_id=req.patient_id,
        medicine_id=req.medicine_id,
        requested_by=user,
        priority=priority_enum,
        prescription_id=req.prescription_id,
    )
    return {
        "success": True,
        "message": f"Task {task.task_code} dispatched to {task.assigned_robot.name if task.assigned_robot else 'Fleet'}.",
        "task": {
            "id": task.id,
            "task_code": task.task_code,
            "status": task.status.value,
            "destination": task.destination_location,
            "robot": task.assigned_robot.name if task.assigned_robot else None,
        },
    }


@app.post("/api/tasks/{task_id}/transition")
def transition_task(
    task_id: int,
    req: TaskTransitionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        new_status = TaskStatusEnum(req.status.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid task status '{req.status}'.")

    task = TaskEngine.transition_task_status(
        db=db,
        task_id=task_id,
        new_status=new_status,
        triggered_by=user.full_name,
        message=req.message or f"Transitioned by {user.role.value} {user.username}",
        progress_pct=req.progress_pct,
    )
    return {"message": "Status updated successfully.", "task_code": task.task_code, "status": task.status.value}


@app.get("/api/robots")
def list_robots(db: Session = Depends(get_db)):
    robots = db.query(Robot).all()
    # Merge live telemetry from ORCHESTRATOR if active
    telemetry_map = {r["id"]: r for r in ORCHESTRATOR.fleet_telemetry.values()}

    result = []
    for r in robots:
        live = telemetry_map.get(r.robot_id, {})
        result.append({
            "id": r.id,
            "robot_id": r.robot_id,
            "name": r.name,
            "role": r.role.value,
            "status": live.get("status", r.status.value),
            "battery": live.get("battery", r.battery_level),
            "room": live.get("room", r.current_room),
            "x": live.get("x", r.current_x),
            "y": live.get("y", r.current_y),
            "speed": live.get("speed", 0.0),
            "active_task": live.get("task", None),
            "progress": live.get("progress", 0.0),
        })
    return result


# ── 4. VOICE COMMAND & SECURITY GATEWAY (Section 10 & 11) ───────────────────

@app.post("/api/voice/command")
def process_voice_command(
    req: VoiceCommandRequest,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """
    Voice Command Workflow enforcing:
    'Voice is an INPUT CHANNEL, not an AUTHORIZATION CHANNEL.'
    """
    result = VoiceService.process_voice_command(
        db=db,
        command_text=req.command,
        authenticated_user=user,
    )
    return result


# ── 5. SIMULATION ORCHESTRATION & TELEMETRY (Section 21, 22, 23) ────────────

@app.post("/api/simulation/start")
def start_simulation(user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DOCTOR, UserRole.NURSE))):
    """
    Section 22: RUN SIMULATION Endpoint.
    """
    res = ORCHESTRATOR.start_simulation()
    return res


@app.post("/api/simulation/stop")
def stop_simulation(user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DOCTOR))):
    res = ORCHESTRATOR.stop_simulation()
    return res


@app.get("/api/simulation/status")
def get_simulation_status():
    return ORCHESTRATOR.get_full_state()


@app.post("/api/simulation/camera")
def control_camera(req: CameraControlRequest):
    """
    Section 21: Automatic Camera Director (FOLLOW ROBOT, FOLLOW TASK, OVERVIEW).
    """
    state = ORCHESTRATOR.set_camera_mode(req.mode.upper(), req.target_robot_id)
    return {"message": f"Camera mode set to {req.mode}.", "camera": state}


@app.post("/api/emergency/trigger")
def trigger_emergency(
    req: EmergencyTriggerRequest,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DOCTOR, UserRole.NURSE)),
    db: Session = Depends(get_db),
):
    """
    Triggers Priority-1 Code Blue emergency escalation and robot reassignment.
    """
    count = db.query(EmergencyEvent).count() + 1
    event_code = f"EMR-EVENT-{count:03d}"

    event = EmergencyEvent(
        event_code=event_code,
        event_type=req.event_type,
        room_number=req.room_number,
        reported_by_user_id=user.id,
        status="ACTIVE",
        details=req.details,
    )
    db.add(event)

    # Create EMERGENCY robot mission
    task = RobotTask(
        task_code=f"TASK-EMR-{count:03d}",
        task_type=TaskTypeEnum.EMERGENCY_RESPONSE,
        priority=TaskPriorityEnum.EMERGENCY,
        status=TaskStatusEnum.ASSIGNED,
        destination_location=req.room_number,
        destination_x=-35.0,
        destination_y=-26.0,
        assigned_agent="EmergencyAgent",
        created_by_user_id=user.id,
        authorized_by_user_id=user.id,
    )
    db.add(task)
    db.flush()

    # Preempt best robot
    garuda = db.query(Robot).filter(Robot.role == RobotRoleEnum.EMERGENCY).first()
    if garuda:
        task.assigned_robot_id = garuda.id
        garuda.status = RobotStatusEnum.NAVIGATING

    db.commit()

    ORCHESTRATOR.log_message("EMERGENCY", f"CODE BLUE triggered at {req.room_number} by {user.full_name}!", "EMERGENCY")
    ORCHESTRATOR.set_camera_mode(CameraMode.FOLLOW_TASK)

    return {"message": "Emergency alert broadcasted. Garuda_Emergency AMR dispatched.", "event_code": event_code}


@app.get("/api/audit-logs")
def list_audit_logs(limit: int = 50, db: Session = Depends(get_db)):
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [{
        "id": l.id,
        "timestamp": l.timestamp.isoformat(),
        "username": l.username,
        "role": l.user_role,
        "action": l.action,
        "entity": l.entity_type,
        "status": l.status,
        "details": l.details,
        "duplicate_detected": l.duplicate_detected,
        "authorization_denied": l.authorization_denied,
    } for l in logs]


# ── 6. WEBSOCKET REAL-TIME TELEMETRY ────────────────────────────────────────

@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await websocket.accept()
    ORCHESTRATOR.telemetry_clients.add(websocket)
    try:
        while True:
            # Stream state at 10Hz
            state = ORCHESTRATOR.get_full_state()
            await websocket.send_json(state)
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        ORCHESTRATOR.telemetry_clients.discard(websocket)
    except Exception:
        ORCHESTRATOR.telemetry_clients.discard(websocket)


# ── 7. FRONTEND MOUNT ───────────────────────────────────────────────────────

frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_dir, "static")), name="static")

    @app.get("/")
    def serve_frontend_index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

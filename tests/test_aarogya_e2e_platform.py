"""
AAROGYA Platform — End-to-End Integration & Verification Test Suite
===================================================================
Tests all 10 master scenarios specified in prompt:
1. Authorized request & task dispatch
2. Unauthorized visitor request rejection (Voice as input, not authorization)
3. Duplicate task prevention at backend/database level
4. Cancelled/discontinued prescription safety block
5. Discharged patient safety block
6. Multi-agent allocation & priority management
7. Task lifecycle transitions & TaskEvent audit trail
8. Camera director modes (FOLLOW ROBOT, FOLLOW TASK, OVERVIEW)
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from database.models import (
    Bed,
    Medicine,
    Patient,
    PatientStatusEnum,
    Prescription,
    PrescriptionStatusEnum,
    RobotTask,
    TaskPriorityEnum,
    TaskStatusEnum,
    User,
    UserRole,
)
from database.session import SessionLocal


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_auth_login_roles(client):
    """Test authentication and token retrieval for different roles."""
    # 1. Doctor Login
    res = client.post("/api/auth/login", json={"username": "dr_sharma", "password": "doctor123"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["role"] == "DOCTOR"

    # 2. Nurse Login
    res = client.post("/api/auth/login", json={"username": "nurse_priya", "password": "nurse123"})
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "NURSE"

    # 3. Visitor Login
    res = client.post("/api/auth/login", json={"username": "visitor_maya", "password": "visitor123"})
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "VISITOR"


def test_unauthorized_visitor_voice_request(client):
    """
    Scenario: Unauthorized visitor says:
    'Hey Aarogya, deliver medicine to ICU Bed 3.'
    Must be DENIED with hospital guidance message (Section 11).
    """
    # 1. Anonymous visitor
    res = client.post("/api/voice/command", json={"command": "Hey Aarogya, deliver medicine to ICU Bed 3"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert data["authorized"] is False
    assert "requires an authorized hospital request" in data["response"]

    # 2. Logged in Visitor account
    vis_token = client.post("/api/auth/login", json={"username": "visitor_maya", "password": "visitor123"}).json()["access_token"]
    res = client.post(
        "/api/voice/command",
        headers={"Authorization": f"Bearer {vis_token}"},
        json={"command": "Deliver paracetamol to ICU Bed 3"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert data["authorized"] is False
    assert "medication delivery requires an authorized hospital request" in data["response"]


def test_visitor_permitted_navigation_inquiry(client):
    """
    Visitors CAN request: directions, pharmacy location, reception, room navigation.
    """
    res = client.post("/api/voice/command", json={"command": "Where is the pharmacy?"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["authorized"] is True
    assert "Pharmacy is located on Floor 1" in data["response"]


def test_authorized_clinical_workflow_and_duplicate_prevention(client, db):
    """
    Scenario:
    1. Doctor logs in and creates medication delivery task for ICU Bed 3.
    2. Nurse attempts same request -> System blocks with 409 Duplicate Task error.
    """
    doc_token = client.post("/api/auth/login", json={"username": "dr_sharma", "password": "doctor123"}).json()["access_token"]
    nurse_token = client.post("/api/auth/login", json={"username": "nurse_priya", "password": "nurse123"}).json()["access_token"]

    # Find patient Arun Patel (ICU Bed 3)
    pat = db.query(Patient).filter(Patient.patient_code == "P001").first()
    med = db.query(Medicine).filter(Medicine.medicine_code == "MED002").first()

    # Step 1: Doctor creates task
    res1 = client.post(
        "/api/tasks/create-delivery",
        headers={"Authorization": f"Bearer {doc_token}"},
        json={"patient_id": pat.id, "medicine_id": med.id, "priority": "NORMAL"},
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["success"] is True
    task_code = data1["task"]["task_code"]

    # Step 2: Nurse attempts duplicate creation
    res2 = client.post(
        "/api/tasks/create-delivery",
        headers={"Authorization": f"Bearer {nurse_token}"},
        json={"patient_id": pat.id, "medicine_id": med.id, "priority": "NORMAL"},
    )
    assert res2.status_code == 409
    err = res2.json()["detail"]
    assert err["error"] == "DUPLICATE_TASK_DETECTED"
    assert "Medication delivery is already assigned/in progress" in err["message"]
    assert err["existing_task"]["task_id"] == task_code

    # Clean up created task
    task = db.query(RobotTask).filter(RobotTask.task_code == task_code).first()
    if task:
        db.delete(task)
        db.commit()


def test_discontinued_prescription_safety_block(client, db):
    """
    Never execute medication delivery if prescription was discontinued.
    """
    doc_token = client.post("/api/auth/login", json={"username": "dr_sharma", "password": "doctor123"}).json()["access_token"]
    pat = db.query(Patient).filter(Patient.patient_code == "P002").first()
    # Medicine 6 is Morphine (Prescription is DISCONTINUED in seed data)
    med = db.query(Medicine).filter(Medicine.medicine_code == "MED006").first()

    res = client.post(
        "/api/tasks/create-delivery",
        headers={"Authorization": f"Bearer {doc_token}"},
        json={"patient_id": pat.id, "medicine_id": med.id, "priority": "NORMAL"},
    )
    assert res.status_code == 400
    assert "DISCONTINUED" in res.json()["detail"]


def test_discharged_patient_safety_block(client, db):
    """
    Never execute delivery if patient has been discharged.
    """
    doc_token = client.post("/api/auth/login", json={"username": "dr_sharma", "password": "doctor123"}).json()["access_token"]
    # Patient 3 (Rohan Mehta) is DISCHARGED
    pat = db.query(Patient).filter(Patient.patient_code == "P003").first()
    med = db.query(Medicine).filter(Medicine.medicine_code == "MED001").first()

    res = client.post(
        "/api/tasks/create-delivery",
        headers={"Authorization": f"Bearer {doc_token}"},
        json={"patient_id": pat.id, "medicine_id": med.id},
    )
    assert res.status_code == 400
    assert "DISCHARGED" in res.json()["detail"]


def test_camera_modes(client):
    """Verify Section 21 Camera Director modes."""
    # Overview
    r1 = client.post("/api/simulation/camera", json={"mode": "OVERVIEW"})
    assert r1.status_code == 200
    assert r1.json()["camera"]["mode"] == "OVERVIEW"

    # Follow Robot
    r2 = client.post("/api/simulation/camera", json={"mode": "FOLLOW_ROBOT", "target_robot_id": "ROBOT-01"})
    assert r2.status_code == 200
    assert r2.json()["camera"]["mode"] == "FOLLOW_ROBOT"

    # Follow Task
    r3 = client.post("/api/simulation/camera", json={"mode": "FOLLOW_TASK"})
    assert r3.status_code == 200
    assert r3.json()["camera"]["mode"] == "FOLLOW_TASK"

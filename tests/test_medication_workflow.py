"""
Unit and integration tests for MedicationWorkflowManager.
"""

import pytest
from database.hospital_db import HospitalDatabase
from database.db_query_engine import DBQueryEngine
from missions.medication_workflow import MedicationWorkflowManager, MedicationWorkflowState


@pytest.fixture
def mem_db():
    db = HospitalDatabase(":memory:")
    yield db
    db.close()


@pytest.fixture
def query_engine(mem_db):
    return DBQueryEngine(mem_db)


@pytest.fixture
def workflow_mgr(mem_db, query_engine):
    return MedicationWorkflowManager(mem_db, query_engine)


def test_create_order_for_patient(workflow_mgr):
    """Test creating a medication delivery order directly for a patient."""
    order = workflow_mgr.create_order_for_patient("P001", "Paracetamol", assigned_robot="arogya")
    assert order is not None
    assert order.patient_id == "P001"
    assert order.medicine_name == "Paracetamol"
    assert order.room_id == "PAT-101"
    assert order.state == MedicationWorkflowState.DISPATCHED
    assert order.db_task_id is not None
    assert order.is_active


def test_bedside_verification_success(workflow_mgr):
    """Test successful bedside verification and handover completion."""
    order = workflow_mgr.create_order_for_patient("P003", "Metoprolol")
    assert order is not None

    # Advance state to en route to patient
    workflow_mgr.update_order_state(order.order_id, MedicationWorkflowState.EN_ROUTE_PATIENT)

    # Bedside scan: patient 3 and metoprolol
    ok, msg = workflow_mgr.verify_bedside(order.order_id, "patient 3", "Metoprolol")
    assert ok
    assert order.verification_passed
    assert order.state == MedicationWorkflowState.BEDSIDE_VERIFYING

    # Complete delivery
    completed = workflow_mgr.complete_delivery(order.order_id)
    assert completed
    assert order.state == MedicationWorkflowState.DELIVERED
    assert not order.is_active


def test_bedside_verification_mismatch(workflow_mgr):
    """Test detection of patient identity mismatch at bedside."""
    order = workflow_mgr.create_order_for_patient("P002", "Insulin Glargine")
    assert order is not None

    # Patient mismatch (scanned P001 instead of P002)
    ok, msg = workflow_mgr.verify_bedside(order.order_id, "P001", "Insulin Glargine")
    assert not ok
    assert "PATIENT MISMATCH" in msg
    assert not order.verification_passed
    assert order.state == MedicationWorkflowState.FAILED


def test_dispatch_from_schedule(workflow_mgr, mem_db):
    """Test dispatching an order directly from an existing schedule row."""
    # Find any pending schedule
    pending = mem_db.get_pending_medications()
    assert len(pending) > 0
    sched = pending[0]

    order = workflow_mgr.dispatch_from_schedule(sched["schedule_id"])
    assert order is not None
    assert order.schedule_id == sched["schedule_id"]
    assert order.patient_id == sched["patient_id"]
    assert order.medicine_name == sched["medicine_name"]


def test_embodied_medicine_container_attachment_and_detachment():
    """Test 3D container attachment, lock states, and detachment on ArogyaRobot."""
    from isaac_sim_hospital.robots.arogya_robot import ArogyaRobot

    robot = ArogyaRobot(
        prim_path="/World/Robots/Arogya_Delivery",
        name="Arogya_Delivery",
        role="DELIVERY",
        start_position=(34.5, 33.0, 0.0),
    )
    assert not robot.has_medicine_container
    assert robot.attached_medication is None
    assert robot.is_container_locked

    # Attach medicine container at pharmacy
    robot.attach_medicine_container(
        medicine_name="Amoxicillin",
        dosage="500mg",
        patient_id="P001",
        patient_name="John Doe",
        room_id="PAT-101",
    )
    assert robot.has_medicine_container
    assert robot.is_container_locked
    assert robot.attached_medication["name"] == "Amoxicillin"
    assert robot.attached_medication["patient_id"] == "P001"

    # Unlock and lock
    assert robot.unlock_medicine_container()
    assert not robot.is_container_locked
    robot.lock_medicine_container()
    assert robot.is_container_locked

    # Detach
    robot.detach_medicine_container()
    assert not robot.has_medicine_container
    assert robot.attached_medication is None


def test_embodied_bedside_patient_verification_success():
    """Test successful bedside verification cross-checking RFID and room placards."""
    from isaac_sim_hospital.robots.arogya_robot import ArogyaRobot

    robot = ArogyaRobot(
        prim_path="/World/Robots/Arogya_Delivery",
        name="Arogya_Delivery",
        role="DELIVERY",
        start_position=(34.5, 33.0, 0.0),
    )
    robot.attach_medicine_container(
        medicine_name="Paracetamol",
        patient_id="P001",
        room_id="PAT-101",
    )
    robot.destination_name = "PAT-101"

    ok, msg = robot.verify_bedside_target(
        expected_patient_id="P001",
        expected_room="PAT-101",
        perceived_patient_id="P001",
        perceived_room="PAT-101",
    )
    assert ok
    assert "SUCCESS" in msg
    assert not robot.is_container_locked
    assert robot.last_verification_result["status"] == "SUCCESS"


def test_embodied_bedside_patient_verification_mismatch():
    """Test safety lockout when bedside patient RFID does not match prescription."""
    from isaac_sim_hospital.robots.arogya_robot import ArogyaRobot

    robot = ArogyaRobot(
        prim_path="/World/Robots/Arogya_Delivery",
        name="Arogya_Delivery",
        role="DELIVERY",
        start_position=(34.5, 33.0, 0.0),
    )
    robot.attach_medicine_container(
        medicine_name="Insulin Glargine",
        patient_id="P002",
        room_id="PAT-102",
    )

    # Scanned wrong patient
    ok, msg = robot.verify_bedside_target(
        expected_patient_id="P002",
        expected_room="PAT-102",
        perceived_patient_id="P003",
        perceived_room="PAT-102",
    )
    assert not ok
    assert "MISMATCH" in msg
    assert robot.is_container_locked
    assert robot.last_verification_result["status"] == "FAILED"


def test_hospital_db_record_medication_delivery(mem_db):
    """Test record_medication_delivery updates schedules, decrements stock, and completes tasks."""
    med = mem_db.get_medicine_by_name("Paracetamol")
    assert med is not None
    initial_stock = med["stock"]

    m_id = "MED-20261001-TEST"
    mem_db.create_task(
        task_type="MEDICATION_DELIVERY",
        patient_id="P001",
        destination="PAT-101",
        item="Paracetamol",
        task_id=m_id,
    )

    success = mem_db.record_medication_delivery(
        patient_id="P001",
        medicine_name="Paracetamol",
        delivered_by="Arogya_Delivery",
        room_id="PAT-101",
        verification_passed=True,
        verification_notes="RFID tag verified bedside",
        mission_id=m_id,
    )
    assert success

    # Verify stock decrement
    updated_med = mem_db.get_medicine_by_name("Paracetamol")
    assert updated_med["stock"] == initial_stock - 1

    # Verify task completion
    task = mem_db.get_task(m_id)
    assert task is not None
    assert task["status"] == "COMPLETED"
    assert "RFID tag verified" in task["notes"]

    # Verify audit history
    with mem_db._cursor() as c:
        c.execute("SELECT * FROM patient_status_history WHERE patient_id = 'P001' ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        assert row is not None
        assert "Paracetamol delivered" in row["reason"]
        assert row["operator"] == "Arogya_Delivery"


def test_two_phase_clinical_delivery_stepping():
    """Test ArogyaRobot stepping through Phase 1 pickup and Phase 2 delivery."""
    import numpy as np
    from isaac_sim_hospital.robots.arogya_robot import ArogyaRobot
    from robots.robot_state_machine import RobotState

    robot = ArogyaRobot(
        prim_path="/World/Robots/Arogya_Delivery",
        name="Arogya_Delivery",
        role="DELIVERY",
        start_position=(0.0, 0.0, 0.0),
    )

    phase_callback_called = []
    mission_callback_called = []

    def on_phase(r, desc, nxt):
        phase_callback_called.append((desc, nxt["destination_name"]))

    def on_done(r, desc):
        mission_callback_called.append(desc)

    robot.assign_clinical_delivery_mission(
        pickup_waypoints=[np.array([0.1, 0.0, 0.0])],
        pickup_dest="PHM-01",
        pickup_action_desc="Collect Medication at Pharmacy",
        delivery_waypoints=[np.array([0.2, 0.0, 0.0])],
        delivery_dest="PAT-101",
        delivery_action_desc="Bedside Handover at PAT-101",
        priority_level=2,
        mission_id="MED-20261001-AUTO",
        context={"item": "Amoxicillin", "patient_id": "P001", "room_id": "PAT-101"},
        on_phase_complete=on_phase,
        on_mission_complete=on_done,
    )

    assert robot.mission_active
    assert robot.current_mission_id == "MED-20261001-AUTO"
    assert len(robot.pending_mission_phases) == 1

    # Step to arrive at pickup waypoint
    robot.x = 0.1
    robot.y = 0.0
    robot.step_autonomous(dt=0.1)
    assert robot.action_active
    assert robot.state_machine.state == RobotState.EXECUTING_TASK

    # Finish pickup action
    robot.action_timer = robot.action_duration + 0.1
    robot.step_autonomous(dt=0.1)

    # Robot must have attached medicine container and transitioned to delivery phase
    assert len(phase_callback_called) == 1
    assert robot.has_medicine_container
    assert robot.destination_name == "PAT-101"
    assert robot.current_mission_id == "MED-20261001-AUTO"

    # Step to arrive at delivery waypoint
    robot.x = 0.2
    robot.y = 0.0
    robot.step_autonomous(dt=0.1)
    assert robot.action_active

    # Finish bedside delivery action
    robot.action_timer = robot.action_duration + 0.1
    robot.step_autonomous(dt=0.1)

    # Verification should succeed, container detaches, and mission completes
    assert len(mission_callback_called) == 1
    assert not robot.has_medicine_container
    assert robot.state_machine.state == RobotState.MISSION_COMPLETE


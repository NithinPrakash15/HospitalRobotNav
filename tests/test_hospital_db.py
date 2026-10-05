"""
Unit and integration tests for Hospital Database, DBQueryEngine, and Voice/NLU integration.
"""

import pytest
from database.hospital_db import HospitalDatabase, PatientStatus, TaskType, TaskStatus
from database.db_query_engine import DBQueryEngine
from language.intent_parser import IntentParser, IntentType
from language.entity_extractor import EntityExtractor
from language.command_resolver import CommandResolver, MissionType
from language.db_response_generator import DBResponseGenerator


@pytest.fixture
def mem_db():
    """In-memory hospital database with demo data."""
    db = HospitalDatabase(":memory:")
    yield db
    db.close()


@pytest.fixture
def query_engine(mem_db):
    return DBQueryEngine(mem_db)


# ── HospitalDatabase Tests ───────────────────────────────────────────────────

def test_database_tables_and_seed(mem_db):
    """Verify all 11 tables exist and synthetic data is seeded."""
    patients = mem_db.get_all_patients()
    assert len(patients) == 6
    p_ids = [p["patient_id"] for p in patients]
    assert "P001" in p_ids
    assert "P006" in p_ids

    # Doctors
    doctors = mem_db.get_all_doctors()
    assert len(doctors) == 4

    # Medicines
    meds = mem_db.get_all_medicines()
    assert len(meds) == 8

    # Prescriptions
    p1_presc = mem_db.get_prescriptions("P001")
    assert len(p1_presc) >= 1


def test_patient_status_update(mem_db):
    """Verify patient status update and history recording."""
    status_row = mem_db.get_patient_status("P001")
    assert status_row["status"] == PatientStatus.ACTIVE

    ok = mem_db.set_patient_status("P001", PatientStatus.EMERGENCY, "Vitals dropping rapidly", "Nurse")
    assert ok

    status_updated = mem_db.get_patient_status("P001")
    assert status_updated["status"] == PatientStatus.EMERGENCY

    hist = mem_db.get_status_history("P001")
    assert len(hist) >= 1
    assert hist[0]["new_status"] == PatientStatus.EMERGENCY


# ── DBQueryEngine Tests ──────────────────────────────────────────────────────

def test_resolve_patient_id():
    """Test flexible normalization of patient identifiers."""
    assert DBQueryEngine.resolve_patient_id("P001") == "P001"
    assert DBQueryEngine.resolve_patient_id("p1") == "P001"
    assert DBQueryEngine.resolve_patient_id("P3") == "P003"
    assert DBQueryEngine.resolve_patient_id("patient 3") == "P003"
    assert DBQueryEngine.resolve_patient_id("patient P003") == "P003"
    assert DBQueryEngine.resolve_patient_id("patient #2") == "P002"
    assert DBQueryEngine.resolve_patient_id("005") == "P005"
    assert DBQueryEngine.resolve_patient_id("4") == "P004"


def test_query_engine_patient_info(query_engine):
    """Test getting full patient info through query engine facade."""
    info = query_engine.get_patient_info("patient 3")
    assert info is not None
    assert info["patient_id"] == "P003"
    assert info["name"] == "Meera Iyer"
    assert info["assigned_room"] == "PAT-103"
    assert info["attending_doctor_name"] is not None


def test_query_engine_medications(query_engine):
    """Test getting medication schedules for a patient."""
    meds = query_engine.get_medications_for_patient("P001")
    assert meds is not None
    assert len(meds["prescriptions"]) >= 1
    assert "medicine_name" in meds["prescriptions"][0]


def test_query_engine_active_patients(query_engine):
    """Test active patient overview query."""
    active = query_engine.get_all_active_patients_brief()
    assert len(active) >= 4  # P001, P002, P003, P005 (P004 is discharged, P006 pending)
    rooms = [p["assigned_room"] for p in active]
    assert "PAT-101" in rooms


# ── Language & DB Integration Tests ──────────────────────────────────────────

def test_intent_parsing_new_intents():
    """Verify IntentParser classifies the 5 new hospital database intents."""
    parser = IntentParser()

    # Patient status query
    res = parser.parse("What is the status of patient 3?")
    assert res.intent == IntentType.PATIENT_STATUS_QUERY

    # Doctor query
    res = parser.parse("Who is the attending doctor for patient 1?")
    assert res.intent == IntentType.DOCTOR_QUERY

    # Medication query
    res = parser.parse("What medication does patient 2 need?")
    assert res.intent == IntentType.MEDICATION_QUERY

    # Patient emergency
    res = parser.parse("Emergency code blue for patient 3 in room 103!")
    assert res.intent == IntentType.PATIENT_EMERGENCY

    # Show active patients
    res = parser.parse("Show all active patients in the hospital")
    assert res.intent == IntentType.SHOW_ACTIVE_PATIENTS


def test_entity_extraction_patient_id():
    """Verify EntityExtractor extracts and normalizes patient ID."""
    extractor = EntityExtractor()

    entities = extractor.extract("Check status of patient 3 please")
    assert entities.has_patient_id
    assert entities.patient_id == "P003"

    entities2 = extractor.extract("Deliver paracetamol to patient P1 in room 101")
    assert entities2.has_patient_id
    assert entities2.patient_id == "P001"
    assert "paracetamol" in entities2.medicines


def test_command_resolver_with_db(query_engine):
    """Verify CommandResolver bridges NLU to DBQueryEngine and generates responses."""
    parser = IntentParser()
    extractor = EntityExtractor()
    resolver = CommandResolver()
    resolver.set_db_engine(query_engine)

    cmd = "What is the status of patient 3?"
    intent = parser.parse(cmd)
    entities = extractor.extract(cmd)

    req = resolver.resolve(intent, entities)
    assert req.is_valid
    assert req.mission_type == MissionType.PATIENT_STATUS_QUERY
    assert req.patient_id == "P003"
    assert req.db_result is not None
    assert req.delivery_location == "PAT-103"
    assert "Meera Iyer" in req.response_text
    assert "PAT-103" in req.response_text


def test_db_response_generator():
    """Verify DBResponseGenerator text generation."""
    sample_patient = {
        "patient_id": "P003",
        "name": "Meera Iyer",
        "status": "ACTIVE",
        "assigned_room": "PAT-103",
        "attending_doctor_name": "Dr. Anil Varma",
        "condition_summary": "Stable, post-appendectomy",
        "vitals": {"heart_rate": 78, "bp": "120/80", "spo2": 98},
    }
    resp = DBResponseGenerator.format_patient_status(sample_patient)
    assert "Meera Iyer" in resp
    assert "PAT-103" in resp
    assert "oxygen saturation 98%" in resp

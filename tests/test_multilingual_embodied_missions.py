"""
Unit tests for Multilingual AI Mission Understanding Layer (English, Hindi, Malayalam, Manglish).
================================================================================================
Verifies Part 11:
- Native Malayalam script detection & parsing
- Manglish (transliterated Malayalam) clinical verbs & routing
- Standard Hindi (Devanagari) & English parsing
- Canonical persistent MissionID formatting (MED-YYYYMMDD-XXXX, etc.)
- Trilingual spoken response generation (English + Hindi + Malayalam)
"""

import re
import pytest
from isaac_sim_hospital.ai_reasoning.mission_understander import (
    MissionUnderstander,
    EmbodiedMissionSpec,
)


@pytest.fixture
def understander():
    return MissionUnderstander()


def test_english_medication_delivery(understander):
    cmd = "Deliver antibiotics to ICU Bed 2"
    spec: EmbodiedMissionSpec = understander.reason_mission(cmd)
    assert spec.language == "en"
    assert spec.task_type == "MEDICINE_DELIVERY"
    assert spec.dest_dept == "ICU-01"
    assert spec.target_bed == "Bed 2"
    assert "Antibiotics" in spec.item
    assert spec.priority_level == 3
    assert not spec.is_emergency
    assert re.match(r"^MED-\d{8}-[A-F0-9]{4}$", spec.mission_id)
    assert "ICU-01" in spec.spoken_response_en
    assert "आईसीयू" in spec.spoken_response_hi
    assert "ഐസിയു" in spec.spoken_response_ml


def test_english_code_blue_emergency(understander):
    cmd = "Code Blue emergency in Trauma resuscitation immediately"
    spec: EmbodiedMissionSpec = understander.reason_mission(cmd)
    assert spec.language == "en"
    assert spec.task_type == "EMERGENCY_RESPONSE"
    assert spec.dest_dept == "TRM-01"
    assert spec.priority_level == 1
    assert spec.is_emergency
    assert re.match(r"^EMR-\d{8}-[A-F0-9]{4}$", spec.mission_id)
    assert "Emergency Alert confirmed" in spec.spoken_response_en
    assert "आपातकालीन" in spec.spoken_response_hi
    assert "അടിയന്തര" in spec.spoken_response_ml


def test_hindi_medication_delivery(understander):
    cmd = "आईसीयू बिस्तर 1 में दवा पहुंचाएं"
    spec: EmbodiedMissionSpec = understander.reason_mission(cmd)
    assert spec.language == "hi"
    assert spec.task_type == "MEDICINE_DELIVERY"
    assert spec.dest_dept == "ICU-01"
    assert spec.target_bed == "Bed 1"
    assert re.match(r"^MED-\d{8}-[A-F0-9]{4}$", spec.mission_id)


def test_hindi_emergency_response(understander):
    cmd = "इमरजेंसी! वार्ड 101 में तुरंत सहायता चाहिए"
    spec: EmbodiedMissionSpec = understander.reason_mission(cmd)
    assert spec.language == "hi"
    assert spec.task_type == "EMERGENCY_RESPONSE"
    assert spec.dest_dept == "PAT-101"
    assert spec.priority_level == 1
    assert spec.is_emergency
    assert re.match(r"^EMR-\d{8}-[A-F0-9]{4}$", spec.mission_id)


def test_malayalam_unicode_delivery(understander):
    cmd = "ഐസിയുവിൽ മരുന്ന് എത്തിക്കൂ"
    spec: EmbodiedMissionSpec = understander.reason_mission(cmd)
    assert spec.language == "ml"
    assert spec.task_type == "MEDICINE_DELIVERY"
    assert spec.dest_dept == "ICU-01"
    assert re.match(r"^MED-\d{8}-[A-F0-9]{4}$", spec.mission_id)
    assert "ഐസിയു" in spec.spoken_response_ml


def test_malayalam_unicode_emergency(understander):
    cmd = "അടിയന്തര സാഹചര്യം! ഐസിയുവിൽ വേഗം എത്തുക"
    spec: EmbodiedMissionSpec = understander.reason_mission(cmd)
    assert spec.language == "ml"
    assert spec.task_type == "EMERGENCY_RESPONSE"
    assert spec.dest_dept == "ICU-01"
    assert spec.priority_level == 1
    assert spec.is_emergency
    assert re.match(r"^EMR-\d{8}-[A-F0-9]{4}$", spec.mission_id)


def test_manglish_transliterated_delivery(understander):
    cmd = "marunnu ICU-il kondupoku"
    spec: EmbodiedMissionSpec = understander.reason_mission(cmd)
    assert spec.language == "ml-translit"
    assert spec.task_type == "MEDICINE_DELIVERY"
    assert spec.dest_dept == "ICU-01"
    assert re.match(r"^MED-\d{8}-[A-F0-9]{4}$", spec.mission_id)


def test_manglish_transliterated_emergency(understander):
    cmd = "emergency aanu vegam ICU-il po"
    spec: EmbodiedMissionSpec = understander.reason_mission(cmd)
    assert spec.language == "ml-translit"
    assert spec.task_type == "EMERGENCY_RESPONSE"
    assert spec.dest_dept == "ICU-01"
    assert spec.priority_level == 1
    assert spec.is_emergency
    assert re.match(r"^EMR-\d{8}-[A-F0-9]{4}$", spec.mission_id)


def test_manglish_visitor_guidance(understander):
    cmd = "lab-il pokoo vazhi sahayikku"
    spec: EmbodiedMissionSpec = understander.reason_mission(cmd)
    assert spec.task_type == "RECEPTION_GUIDE"
    assert spec.dest_dept == "LAB-01"
    assert re.match(r"^GDE-\d{8}-[A-F0-9]{4}$", spec.mission_id)


def test_spec_to_dict_serialization(understander):
    cmd = "Take insulin to PAT-102"
    spec: EmbodiedMissionSpec = understander.reason_mission(cmd)
    d = spec.to_dict()
    assert isinstance(d, dict)
    assert "mission_id" in d
    assert "spoken_response_en" in d
    assert "spoken_response_hi" in d
    assert "spoken_response_ml" in d
    assert d["dest_dept"] == "PAT-102"

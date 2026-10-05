"""
HospitalRobotNav — Database Response Generator
================================================
Generates natural language responses from hospital database query results.
Formatted for Text-to-Speech (TTS) verbal feedback and HUD display.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from utilities.logger import get_logger

log = get_logger(__name__)


class DBResponseGenerator:
    """Converts structured database query outputs into natural language sentences."""

    @staticmethod
    def format_patient_status(info: Optional[Dict[str, Any]], patient_id: str = "") -> str:
        """Format a single patient's information into a spoken sentence.

        Args:
            info: Dictionary returned by DBQueryEngine.get_patient_info()
            patient_id: Optional fallback ID if info is None

        Returns:
            Natural language status string.
        """
        if not info:
            pid = patient_id or "specified"
            return f"Patient {pid} was not found in the hospital database records."

        pid = info.get("patient_id", "")
        name = info.get("name", "Unknown")
        status = info.get("status", "Unknown").upper()
        room = info.get("assigned_room", "Unassigned")
        condition = info.get("condition_summary") or "Under observation"
        doctor = info.get("attending_doctor_name")

        parts = [f"Patient {pid}, {name}, status is {status}."]
        parts.append(f"Located in room {room}.")
        if doctor:
            parts.append(f"Attending physician is Dr. {doctor}.")
        parts.append(f"Clinical condition: {condition}.")

        vitals = info.get("vitals")
        if vitals and isinstance(vitals, dict):
            hr = vitals.get("heart_rate")
            bp = vitals.get("bp")
            spo2 = vitals.get("spo2")
            vital_parts = []
            if hr:
                vital_parts.append(f"heart rate {hr} bpm")
            if bp:
                vital_parts.append(f"blood pressure {bp}")
            if spo2:
                vital_parts.append(f"oxygen saturation {spo2}%")
            if vital_parts:
                parts.append("Latest vitals: " + ", ".join(vital_parts) + ".")

        return " ".join(parts)

    @staticmethod
    def format_doctor_info(doc_info: Optional[Dict[str, Any]], query_name: str = "") -> str:
        """Format doctor details into a spoken sentence.

        Args:
            doc_info: Dictionary returned by DBQueryEngine.get_attending_doctor_info() or DB doctor query
            query_name: Name searched if not found

        Returns:
            Natural language doctor info string.
        """
        if not doc_info:
            target = f"Dr. {query_name}" if query_name else "The attending doctor"
            return f"{target} could not be located in the hospital staff directory."

        name = doc_info.get("name", "Unknown")
        specialty = doc_info.get("specialty", "General Medicine")
        phone = doc_info.get("phone", "")
        pager = doc_info.get("pager", "")
        status = doc_info.get("status", "AVAILABLE")

        msg = f"Dr. {name} is a specialist in {specialty}, status is {status}."
        if phone:
            msg += f" Contact extension is {phone}."
        elif pager:
            msg += f" Pager is {pager}."

        patients = doc_info.get("assigned_patients", [])
        if patients:
            names = [f"{p.get('patient_id')}: {p.get('name')}" for p in patients]
            msg += f" Currently attending {len(patients)} patient(s): {', '.join(names)}."

        return msg

    @staticmethod
    def format_medications(
        medications: Optional[List[Dict[str, Any]]], patient_id: str = "", patient_name: str = ""
    ) -> str:
        """Format medication schedules and prescriptions into a spoken summary.

        Args:
            medications: List of medication/schedule dicts
            patient_id: Patient ID
            patient_name: Patient Name if available

        Returns:
            Natural language medication summary.
        """
        target = f"Patient {patient_id}" if patient_id else "The patient"
        if patient_name:
            target += f" ({patient_name})"

        if not medications:
            return f"{target} has no active medication schedules or pending prescriptions."

        lines = [f"{target} has {len(medications)} medication order(s):"]
        for idx, m in enumerate(medications, 1):
            med_name = m.get("medicine_name") or m.get("brand_name") or "Medication"
            dosage = m.get("dosage", "")
            route = m.get("route", "oral")
            time_slot = m.get("scheduled_time") or m.get("frequency", "")
            status = m.get("status", "SCHEDULED").upper()
            lines.append(f"{idx}: {med_name} {dosage} ({route}), scheduled for {time_slot} [Status: {status}].")

        return " ".join(lines)

    @staticmethod
    def format_active_patients(patients: Optional[List[Dict[str, Any]]]) -> str:
        """Format a list of active patients for verbal status update.

        Args:
            patients: List of patient summary dicts

        Returns:
            Spoken summary of active patients.
        """
        if not patients:
            return "There are currently no active patients registered in the hospital wards."

        count = len(patients)
        entries = []
        for p in patients:
            pid = p.get("patient_id", "")
            name = p.get("name", "Unknown")
            room = p.get("assigned_room", "Unassigned")
            cond = p.get("condition_summary") or p.get("status", "ACTIVE")
            entries.append(f"{pid} {name} in {room} ({cond})")

        return f"Hospital Ward Status: {count} active patient(s). " + "; ".join(entries) + "."

    @staticmethod
    def format_emergency_response(
        patient_info: Optional[Dict[str, Any]],
        patient_id: str = "",
        location: str = "",
    ) -> str:
        """Format emergency alert announcement.

        Args:
            patient_info: Patient data if known
            patient_id: Patient ID
            location: Room or location of emergency

        Returns:
            Urgent Code Blue alert string.
        """
        loc = location
        p_desc = f"Patient {patient_id}" if patient_id else "Patient"
        if patient_info:
            p_desc = f"Patient {patient_info.get('patient_id', patient_id)}, {patient_info.get('name', '')}"
            if not loc:
                loc = patient_info.get("assigned_room", "")

        loc_str = f" in room {loc}" if loc else ""
        return (
            f"URGENT CODE BLUE: Emergency reported for {p_desc}{loc_str}. "
            f"Immediate medical intervention dispatched. All available units standby."
        )

    @classmethod
    def generate(
        cls,
        mission_type_name: str,
        db_result: Optional[Dict[str, Any]],
        patient_id: str = "",
        query_text: str = "",
    ) -> str:
        """General dispatcher to generate response text based on mission type and DB result."""
        mt = mission_type_name.upper()

        if "PATIENT_STATUS" in mt:
            return cls.format_patient_status(db_result, patient_id=patient_id)

        elif "DOCTOR" in mt:
            return cls.format_doctor_info(db_result, query_name=patient_id or query_text)

        elif "MEDICATION" in mt:
            meds = db_result.get("medications", []) if db_result else []
            return cls.format_medications(meds, patient_id=patient_id)

        elif "ACTIVE_PATIENTS" in mt:
            pts = db_result.get("active_patients", []) if db_result else []
            return cls.format_active_patients(pts)

        elif "EMERGENCY" in mt:
            return cls.format_emergency_response(db_result, patient_id=patient_id)

        return f"Query completed for {query_text}."

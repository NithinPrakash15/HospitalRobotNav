"""
HospitalRobotNav — Patient Identifier Interface
=================================================
Patient identification system interface (wristband, badge, face verification).

In the simulation, queries the internal patient database.
In deployment, integrates with camera/RFID wristband readers.

Architecture Note (ROS2):
    Subscribes to /robot/patient_id (std_msgs/String) and queries EMR service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]


@dataclass
class PatientRecord:
    """Patient record metadata."""
    patient_id: str
    name: str
    room: str
    assigned_bed: str
    room_pos: GridPos
    attending_doctor: str
    medications: list[str]
    is_active: bool = True


class PatientIdentifier:
    """Patient identification system with local mock database."""

    def __init__(self) -> None:
        # Synthetic database of hospital patients
        self._database: Dict[str, PatientRecord] = {
            "P101": PatientRecord(
                patient_id="P101",
                name="John Doe",
                room="Room 101",
                assigned_bed="101-A",
                room_pos=(15, 20),
                attending_doctor="Dr. Smith",
                medications=["Paracetamol", "Amoxicillin"],
            ),
            "P205": PatientRecord(
                patient_id="P205",
                name="Jane Miller",
                room="Room 205",
                assigned_bed="205-B",
                room_pos=(35, 60),
                attending_doctor="Dr. Sharma",
                medications=["Ibuprofen", "Aspirin"],
            ),
            "P302": PatientRecord(
                patient_id="P302",
                name="Robert Johnson",
                room="ICU Bed 2",
                assigned_bed="ICU-2",
                room_pos=(80, 25),
                attending_doctor="Dr. Patel",
                medications=["Morphine", "Saline"],
            ),
        }

    def identify_by_id(self, patient_id: str) -> Optional[PatientRecord]:
        """Look up patient record by patient ID (e.g. 'P205')."""
        return self._database.get(patient_id.upper())

    def identify_by_room(self, room_name: str) -> Optional[PatientRecord]:
        """Look up patient record assigned to a specific room or bed."""
        room_name_clean = room_name.lower()
        for rec in self._database.values():
            if room_name_clean in rec.room.lower() or room_name_clean in rec.assigned_bed.lower():
                return rec
        return None

    def verify_patient_identity(self, patient_id: str, expected_room: str) -> bool:
        """Verify that patient is located in expected room."""
        rec = self.identify_by_id(patient_id)
        if not rec:
            return False
        return expected_room.lower() in rec.room.lower()

    def register_patient(self, record: PatientRecord) -> None:
        """Register a new patient into the active system."""
        self._database[record.patient_id.upper()] = record
        log.info("Registered patient %s (%s) in %s", record.patient_id, record.name, record.room)

    def __repr__(self) -> str:
        return f"PatientIdentifier(total_patients={len(self._database)})"

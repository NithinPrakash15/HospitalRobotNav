"""
HospitalRobotNav — Entity Extractor
======================================
Named Entity Recognition (NER) for hospital robot commands.

Extracts structured entities from natural language text:
    - **Location**: Room names, department names, room numbers.
    - **Medicine**: Drug names from the built-in formulary.
    - **Person**: Patient names, doctor references, nurse references.
    - **Priority**: Urgency levels (emergency, urgent, normal, low).
    - **Quantity**: Amounts and units ("2 tablets", "one box").
    - **Time**: Temporal references ("now", "in 5 minutes").

Implementation:
    Uses regex patterns and dictionary lookup against the medicine
    formulary and room definitions.  Designed for clean replacement
    with a transformer-based NER model or LLM entity extraction.

ROS2 Deployment Note:
    In production, this would be part of the NLU node or replaced by
    a dedicated NER service node.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from language.language_config import (
    LANGUAGE_CONFIG,
    KNOWN_MEDICINES,
    MEDICINE_FORMULARY,
    PRIORITY_KEYWORDS,
)
from utilities.logger import get_logger

log = get_logger(__name__)

# Try to import room definitions for location matching
try:
    from maps.hospital.room_definitions import ROOM_DATABASE, RoomCategory
    _ROOMS_AVAILABLE = True
except ImportError:
    _ROOMS_AVAILABLE = False
    log.info("EntityExtractor: Room definitions not available for location matching.")


# ─────────────────────────────────────────────────────────────────────────────
# Extracted Entities Dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExtractedEntities:
    """All entities extracted from a single utterance.

    Attributes:
        locations:    Recognised location/room references.
        medicines:    Recognised medicine/drug names.
        persons:      Recognised person references (patient, doctor, nurse).
        priority:     Extracted priority level (1=critical, 5=low, default=4).
        quantity:     Extracted quantity string (e.g., "2 tablets").
        quantity_num: Numeric quantity (e.g., 2).
        time_ref:     Temporal reference (e.g., "now", "in 5 minutes").
        room_number:  Extracted room number (e.g., "205").
        raw_text:     Original input text.
    """
    locations: List[str] = field(default_factory=list)
    medicines: List[str] = field(default_factory=list)
    persons: List[str] = field(default_factory=list)
    priority: int = 4                     # Default: Normal
    priority_label: str = "normal"
    quantity: str = ""
    quantity_num: int = 1
    time_ref: str = ""
    room_number: str = ""
    patient_id: str = ""
    raw_text: str = ""

    @property
    def has_location(self) -> bool:
        return len(self.locations) > 0

    @property
    def has_medicine(self) -> bool:
        return len(self.medicines) > 0

    @property
    def has_person(self) -> bool:
        return len(self.persons) > 0

    @property
    def has_patient_id(self) -> bool:
        return len(self.patient_id) > 0

    @property
    def primary_location(self) -> Optional[str]:
        """The first (most likely destination) location."""
        return self.locations[0] if self.locations else None

    @property
    def primary_medicine(self) -> Optional[str]:
        """The first (primary) medicine name."""
        return self.medicines[0] if self.medicines else None

    def __repr__(self) -> str:
        parts = []
        if self.locations:
            parts.append(f"loc={self.locations}")
        if self.medicines:
            parts.append(f"med={self.medicines}")
        if self.persons:
            parts.append(f"per={self.persons}")
        if self.room_number:
            parts.append(f"room={self.room_number}")
        if self.patient_id:
            parts.append(f"pat={self.patient_id}")
        parts.append(f"pri={self.priority_label}")
        return f"Entities({', '.join(parts)})"


# ─────────────────────────────────────────────────────────────────────────────
# Pre-compiled Regex Patterns
# ─────────────────────────────────────────────────────────────────────────────

# Room number patterns: "Room 205", "room #205", "ward 3B"
_ROOM_NUMBER_RE = re.compile(
    r"(?:room|rm|ward|bed)\s*(?:#|no\.?|number)?\s*(\d{1,4}[a-zA-Z]?)",
    re.IGNORECASE,
)

# Quantity patterns: "2 tablets", "one box", "3 units"
_QUANTITY_RE = re.compile(
    r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
    r"\s+"
    r"(tablets?|pills?|capsules?|boxes?|units?|vials?|ampoules?|"
    r"bottles?|packets?|doses?|syringes?|bags?|strips?)",
    re.IGNORECASE,
)

# Word-to-number mapping for quantity parsing
_WORD_TO_NUM: Dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

# Doctor reference: "Dr. Sharma", "doctor smith", "Dr Kumar"
_DOCTOR_RE = re.compile(
    r"(?:dr\.?|doctor|prof\.?|professor)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
    re.IGNORECASE,
)

# Patient ID patterns: "patient P003", "patient 3", "P003", "patient P1", "pt 2", "patient #1"
_PATIENT_ID_RE = re.compile(
    r"\b(?:patient|pt)\s*(?:#|no\.?|id)?\s*([pP]?\s*0*\d{1,3})\b|\b([pP]0*\d{1,3})\b",
    re.IGNORECASE,
)

# Nurse reference: "nurse Priya", "Nurse Mary"
_NURSE_RE = re.compile(
    r"nurse\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
    re.IGNORECASE,
)

# Patient reference: "patient in bed 3", "patient Kumar"
_PATIENT_RE = re.compile(
    r"patient\s+(?:in\s+)?(?:bed|room|ward)?\s*(?:#)?\s*(\w+)",
    re.IGNORECASE,
)

# Time reference: "now", "immediately", "in 5 minutes"
_TIME_RE = re.compile(
    r"(now|immediately|right away|asap|urgently|"
    r"in\s+\d+\s+(?:minutes?|mins?|hours?|hrs?|seconds?|secs?)|"
    r"within\s+\d+\s+(?:minutes?|mins?|hours?|hrs?))",
    re.IGNORECASE,
)

# Known department/location keywords (supplement room definitions)
_DEPARTMENT_KEYWORDS: Dict[str, str] = {
    "icu":              "ICU",
    "intensive care":   "ICU",
    "emergency":        "Emergency Room",
    "emergency room":   "Emergency Room",
    "er":               "Emergency Room",
    "ot":               "Operation Theatre",
    "operation theatre": "Operation Theatre",
    "operating room":   "Operation Theatre",
    "surgery":          "Operation Theatre",
    "pharmacy":         "Pharmacy",
    "lab":              "Laboratory",
    "laboratory":       "Laboratory",
    "radiology":        "Radiology",
    "x-ray":            "Radiology",
    "xray":             "Radiology",
    "mri":              "MRI",
    "ct scan":          "CT Scan",
    "ct":               "CT Scan",
    "reception":        "Reception",
    "front desk":       "Reception",
    "lobby":            "Reception",
    "waiting hall":     "Waiting Hall",
    "waiting room":     "Waiting Hall",
    "nurse station":    "Nurse Station",
    "nursing station":  "Nurse Station",
    "storage":          "Storage",
    "store":            "Storage",
    "charging dock":    "Charging Dock",
    "dock":             "Charging Dock",
    "charging station": "Charging Dock",
    "cafeteria":        "Cafeteria",
    "canteen":          "Cafeteria",
    "blood bank":       "Blood Bank",
    "nicu":             "NICU",
    "pediatrics":       "Pediatrics",
    "maternity":        "Maternity",
    "oncology":         "Oncology",
    "cardiology":       "Cardiology",
    "neurology":        "Neurology",
    "orthopedics":      "Orthopedics",
    "dermatology":      "Dermatology",
    "ophthalmology":    "Ophthalmology",
    "ent":              "ENT",
    "physiotherapy":    "Physiotherapy",
    "mortuary":         "Mortuary",
    "फार्मेसी":          "Pharmacy",
    "ഫാർമസി":          "Pharmacy",
    "ഐ.സ.യു":           "ICU",
    "आईसीयू":           "ICU",
    "कमरा":             "Room",
    "ക്യാമ്പസ്":          "Room",
    "റൂം":               "Room",
    "लैब":              "Laboratory",
    "ലാബ്":             "Laboratory",
    "रिसेप्शन":         "Reception",
    "റെസ്പ്ഷൻ":         "Reception",
}

_MULTI_LANGUAGE_MEDICINE_ALIASES: Dict[str, str] = {
    "paracetamol": "paracetamol",
    "acetaminophen": "paracetamol",
    "दवा": "paracetamol",
    "दवाई": "paracetamol",
    "മരുന്ന്": "paracetamol",
    "മരുന്നുകള്": "paracetamol",
    "medicine": "paracetamol",
    "medication": "paracetamol",
}


# ─────────────────────────────────────────────────────────────────────────────
# Entity Extractor
# ─────────────────────────────────────────────────────────────────────────────

class EntityExtractor:
    """Named entity recognition engine for hospital commands.

    Usage::

        extractor = EntityExtractor()
        entities = extractor.extract(
            "Go to the nearest pharmacy, collect Paracetamol, "
            "and deliver it to Room 205 urgently"
        )
        print(entities.locations)   # ["Pharmacy", "Room 205"]
        print(entities.medicines)   # ["paracetamol"]
        print(entities.priority)    # 2  (urgent)
        print(entities.room_number) # "205"

    Thread-safe for concurrent use (stateless extraction).
    """

    def __init__(self) -> None:
        self._cfg = LANGUAGE_CONFIG.entity
        self.total_extractions: int = 0

        log.info(
            "EntityExtractor initialised. Formulary: %d medicines, "
            "Departments: %d locations.",
            len(KNOWN_MEDICINES),
            len(_DEPARTMENT_KEYWORDS),
        )

    def extract(self, text: str) -> ExtractedEntities:
        """Extract all entities from a natural language command.

        Args:
            text: Raw text from the speech recogniser or text input.

        Returns:
            ExtractedEntities with all recognised entities.
        """
        self.total_extractions += 1

        if not text or not text.strip():
            return ExtractedEntities(raw_text=text)

        entities = ExtractedEntities(raw_text=text)
        normalised = text.strip().lower()

        # Extract each entity type
        self._extract_locations(normalised, text, entities)
        self._extract_medicines(normalised, entities)
        self._extract_persons(text, entities)
        self._extract_priority(normalised, entities)
        self._extract_quantity(normalised, entities)
        self._extract_time(normalised, entities)
        self._extract_room_number(normalised, entities)
        self._extract_patient_id(normalised, entities)

        log.info("EntityExtractor: %s", entities)
        return entities

    # ─────────────────────────────────────────────────────────────────────────
    # Individual Entity Extractors
    # ─────────────────────────────────────────────────────────────────────────

    def _extract_locations(
        self, normalised: str, original: str, entities: ExtractedEntities
    ) -> None:
        """Extract location/department references, including relative spatial expressions."""
        seen: Set[str] = set()

        # Check relative spatial expressions first (e.g., "opposite ICU", "next to pharmacy")
        spatial_re = re.compile(
            r"\b(?:opposite|across\s+from|facing|next\s+to|beside|adjacent\s+to|near|between|nearest|closest|least\s+congested|less\s+congested)\s+([a-z0-9\s\-]+?)(?:\s+(?:please|now|urgently)|$)",
            re.IGNORECASE
        )
        spatial_match = spatial_re.search(original)
        if spatial_match:
            full_clause = spatial_match.group(0).strip()
            # Clean trailing polite words
            full_clause = re.sub(r"\s+(?:please|now|urgently)$", "", full_clause, flags=re.IGNORECASE).strip()
            entities.locations.append(full_clause)
            seen.add(full_clause)

        # Check department keywords (including multilingual aliases)
        for keyword, canonical in _DEPARTMENT_KEYWORDS.items():
            if keyword in normalised and canonical not in seen:
                entities.locations.append(canonical)
                seen.add(canonical)

        for keyword, canonical in _DEPARTMENT_KEYWORDS.items():
            if keyword.lower() in normalised and canonical not in seen:
                entities.locations.append(canonical)
                seen.add(canonical)

        # Check room number patterns (e.g., "Room 205")
        room_match = _ROOM_NUMBER_RE.search(original)
        if room_match:
            room_ref = f"Room {room_match.group(1)}"
            if room_ref not in seen:
                entities.locations.append(room_ref)
                seen.add(room_ref)

    def _extract_medicines(self, normalised: str, entities: ExtractedEntities) -> None:
        """Extract medicine/drug names from the formulary."""
        seen: Set[str] = set()

        for alias, canonical in _MULTI_LANGUAGE_MEDICINE_ALIASES.items():
            if alias in normalised and canonical not in seen:
                entities.medicines.append(canonical)
                seen.add(canonical)

        for medicine in KNOWN_MEDICINES:
            if medicine in normalised and medicine not in seen:
                entities.medicines.append(medicine)
                seen.add(medicine)

                # Also check for the "aka" name
                aka = MEDICINE_FORMULARY.get(medicine, {}).get("aka", "")
                if aka and aka.lower() in normalised and aka.lower() not in seen:
                    seen.add(aka.lower())  # Don't double-add via alias

    def _extract_persons(self, text: str, entities: ExtractedEntities) -> None:
        """Extract person references (doctors, nurses, patients)."""
        # Doctor
        doctor_match = _DOCTOR_RE.search(text)
        if doctor_match:
            entities.persons.append(f"Dr. {doctor_match.group(1)}")

        # Nurse
        nurse_match = _NURSE_RE.search(text)
        if nurse_match:
            entities.persons.append(f"Nurse {nurse_match.group(1)}")

        # Patient
        patient_match = _PATIENT_RE.search(text)
        if patient_match:
            entities.persons.append(f"Patient {patient_match.group(1)}")

    def _extract_priority(self, normalised: str, entities: ExtractedEntities) -> None:
        """Extract priority/urgency level."""
        best_priority = 4  # Default: Normal
        best_label = "normal"

        for keyword, level in PRIORITY_KEYWORDS.items():
            if keyword in normalised and level < best_priority:
                best_priority = level
                best_label = keyword

        entities.priority = best_priority

        # Map numeric priority to label
        priority_labels = {1: "critical", 2: "urgent", 3: "high", 4: "normal", 5: "low"}
        entities.priority_label = priority_labels.get(best_priority, best_label)

    def _extract_quantity(self, normalised: str, entities: ExtractedEntities) -> None:
        """Extract quantity and unit information."""
        match = _QUANTITY_RE.search(normalised)
        if match:
            num_str = match.group(1).lower()
            unit_str = match.group(2).lower()

            # Convert word to number if needed
            if num_str in _WORD_TO_NUM:
                num = _WORD_TO_NUM[num_str]
            else:
                try:
                    num = int(num_str)
                except ValueError:
                    num = 1

            entities.quantity = f"{num} {unit_str}"
            entities.quantity_num = num

    def _extract_time(self, normalised: str, entities: ExtractedEntities) -> None:
        """Extract temporal references."""
        match = _TIME_RE.search(normalised)
        if match:
            entities.time_ref = match.group(0).strip()

    def _extract_room_number(self, normalised: str, entities: ExtractedEntities) -> None:
        """Extract standalone room numbers."""
        match = _ROOM_NUMBER_RE.search(normalised)
        if match:
            entities.room_number = match.group(1).strip()

    def _extract_patient_id(self, normalised: str, entities: ExtractedEntities) -> None:
        """Extract patient ID references (e.g., 'patient 3', 'P003', 'patient P1')."""
        match = _PATIENT_ID_RE.search(normalised)
        if match:
            raw_id = match.group(1) or match.group(2)
            if raw_id:
                clean = re.sub(r"\s+", "", raw_id).upper()
                m_num = re.match(r"^(\d{1,3})$", clean)
                if m_num:
                    clean = f"P{int(m_num.group(1)):03d}"
                else:
                    m_p = re.match(r"^P0*(\d{1,3})$", clean)
                    if m_p:
                        clean = f"P{int(m_p.group(1)):03d}"
                entities.patient_id = clean

"""
Interactive Command & Voice Wake Word System for Arogya Hospital Robot
======================================================================
Implements strict two-stage wake-word voice flow:

1. AWAITING_WAKE_WORD:
   - System is completely quiet: NO random speech, NO autonomous movement.
   - Listens for case-insensitive wake words:
     "HEY AROGYA", "HI AROGYA", "AROGYA" (and "hey arogya", "Hey Arogya")
   - Ignores extraneous background noise/speech.

2. Wake Word Detected:
   - Responds: "Hello, how can I help you?" (Audible via SAPI + HUD display)
   - Transitions to LISTENING_FOR_COMMAND state (20s listening window)

3. Natural Language Task Understanding:
   - Flexible parsing of clinical variations:
     * "Deliver antibiotics to ICU Bed 3"
     * "Take medicine to ICU"
     * "Please bring medicine to the patient in ICU"
     * "Can you guide me to the laboratory?"
     * "Emergency assistance required in the ICU"
     * "Charge battery at dock"
   - Emits structured RobotCommand with task_type, source, destination, and priority.
"""

from __future__ import annotations

import os
import queue
import re
import sys
import threading
import time
import unicodedata
import uuid
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional, Tuple

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class CommandType(Enum):
    WAKE_WORD       = auto()
    GO_LOCATION     = auto()
    DELIVER_ITEM    = auto()
    EMERGENCY       = auto()
    CHARGE_DOCK     = auto()
    STOP            = auto()
    STATUS          = auto()
    RESUME          = auto()
    HELP            = auto()
    QUIT            = auto()
    UNKNOWN         = auto()


# Backward compatibility aliases
CommandType.DOCK_CHARGER = CommandType.CHARGE_DOCK


class VoiceInteractionState(Enum):
    SLEEPING               = auto()
    WAKE_DETECTED          = auto()
    LISTENING_FOR_COMMAND  = auto()
    TRANSCRIBING           = auto()
    PROCESSING_COMMAND     = auto()
    COMMAND_ACCEPTED       = auto()
    COMMAND_NOT_UNDERSTOOD = auto()
    TIMEOUT                = auto()
    ERROR                  = auto()

    # Backward compatibility aliases
    AWAITING_WAKE_WORD = SLEEPING
    COMMAND_RECEIVED = COMMAND_ACCEPTED
    PROCESSING = PROCESSING_COMMAND
    EXECUTING = COMMAND_ACCEPTED


NOISE_TOKENS = frozenset({
    "huh", "uh", "um", "ah", "ha", "the", "a", "an", "oh", "hmm", "shh", "eh", "what", "ok", "yes", "no"
})


def is_garbage_asr(text: str) -> bool:
    """Detect single-syllable noise or ambient filler tokens without clinical intent."""
    t = clean_text(text).strip()
    if not t:
        return True
    words = t.split()
    # Allow short keywords that are genuine clinical departments or commands
    valid_short = {"icu", "ot", "opd", "lab", "bed", "stop", "stat", "help"}
    if len(t) < 3 and t not in valid_short:
        return True
    if all(w in NOISE_TOKENS for w in words):
        return True
    return False


@dataclass
class RobotCommand:
    """Structured clinical mission command."""
    cmd_type: CommandType
    raw_text: str
    argument: str = ""
    source_location: str = ""
    destination_location: str = ""
    item: str = ""
    priority: int = 3
    timestamp: float = field(default_factory=time.time)
    source: str = "keyboard"
    target_robot: str = "AUTO"  # "AUTO" = Contract-Net auction; robot name = forced assignment
    mission_id: str = ""

    def __getitem__(self, item: str):
        key = item.lower()
        if key in ("type", "cmd_type"):
            return self.cmd_type
        if key == "target":
            if self.destination_location == "PHM-01":
                return "PHARM"
            return self.destination_location
        if key in ("destination", "destination_location"):
            return self.destination_location
        if key in ("arg", "argument"):
            return self.argument
        if key in ("item", "payload"):
            return self.item
        if key == "raw_text":
            return self.raw_text
        if key in ("priority", "prio"):
            return self.priority
        if key == "mission_id":
            return self.mission_id
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def __contains__(self, item: str) -> bool:
        try:
            self[item]
            return True
        except KeyError:
            return False

    def get(self, item: str, default: Any = None) -> Any:
        try:
            return self[item]
        except KeyError:
            return default


# Recognized wake words with phonetic and conversational variations
WAKE_WORDS = [
    "hey arogya", "hi arogya", "hai arogya", "hello arogya", "ok arogya", "namaste arogya",
    "arogya", "aarogya", "erogya", "aerogya", "aroga", "arogyam", "aroya", "arogiya", "arogia", "arogy", "aarogy",
    "hiroki", "hey hiroki", "hi hiroki", "a roger", "hey roger", "hi roger", "roger", "i roger", "a rogue", "hey rogue",
    "aeroge", "eroge", "arokya", "arokiya",
    "hey robot", "hi robot", "hai robot", "hello robot", "ok robot", "namaste robot", "robot",
    "hey mitra", "mitra", "hey garuda", "garuda", "hey sahayak", "sahayak",
    "alexa", "assistant",
]


def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


# Department destination mappings
ROOM_ALIASES: dict[str, str] = {
    "reception": "RCT-01",
    "triage": "RCT-01",
    "waiting": "WAT-01",
    "lounge": "WAT-01",
    "entrance": "ENT-01",
    "foyer": "ENT-01",
    "opd": "OPD-01",
    "opd 1": "OPD-01",
    "general medicine": "OPD-01",
    "opd 2": "OPD-02",
    "pediatrics": "PED-01",
    "pediatric": "PED-01",
    "pediatric ward": "PED-01",
    "opd 3": "OPD-03",
    "cardiology": "OPD-03",
    "radiology": "RAD-01",
    "x-ray": "RAD-01",
    "xray": "RAD-01",
    "ct scan": "RAD-01",
    "imaging": "RAD-01",
    "pharmacy": "PHM-01",
    "dispensary": "PHM-01",
    "medicine store": "STR-01",
    "icu": "ICU-01",
    "i see you": "ICU-01",
    "eye see you": "ICU-01",
    "i c u": "ICU-01",
    "icu bed 1": "ICU-BED-01",
    "icu bed 2": "ICU-BED-02",
    "icu bed 3": "ICU-BED-03",
    "bed 1": "ICU-BED-01",
    "bed 2": "ICU-BED-02",
    "bed 3": "ICU-BED-03",
    "intensive care": "ICU-01",
    "critical care": "ICU-01",
    "charger": "CHG-01",
    "charging station": "CHG-01",
    "recharge": "CHG-01",
    "nurse station": "NST-01",
    "nurse station 1": "NST-01",
    "nurse station 2": "NST-02",
    "laboratory": "LAB-01",
    "lab": "LAB-01",
    "pathology": "LAB-01",
    "blood bank": "BLB-01",
    "blood": "BLB-01",
    "transfusion": "BLB-01",
    "operation theatre": "OT-01",
    "operating theatre": "OT-01",
    "operation theater": "OT-01",
    "operating theater": "OT-01",
    "operation theatre 1": "OT-01",
    "operation theater 1": "OT-01",
    "operation theatre 2": "OT-02",
    "operation theater 2": "OT-02",
    "operating theatre 2": "OT-02",
    "operating theater 2": "OT-02",
    "ot": "OT-01",
    "ot 1": "OT-01",
    "ot 2": "OT-02",
    "theater": "OT-01",
    "theatre": "OT-01",
    "operating room": "OT-01",
    "operating room 1": "OT-01",
    "operating room 2": "OT-02",
    "surgery": "OT-01",
    "general ward": "GW-01",
    "ward": "GW-01",
    "ward 101": "PAT-101",
    "ward 102": "PAT-102",
    "ward 103": "PAT-103",
    "ward 104": "PAT-104",
    "ward 105": "PAT-105",
    "ward 106": "PAT-106",
    "room 101": "PAT-101",
    "room 102": "PAT-102",
    "room 103": "PAT-103",
    "room 104": "PAT-104",
    "room 105": "PAT-105",
    "room 106": "PAT-106",
    "patient room 101": "PAT-101",
    "patient room 102": "PAT-102",
    "patient room 103": "PAT-103",
    "patient room 104": "PAT-104",
    "patient room 105": "PAT-105",
    "patient room 106": "PAT-106",
    "patient 101": "PAT-101",
    "patient 102": "PAT-102",
    "patient 103": "PAT-103",
    "patient 104": "PAT-104",
    "patient 105": "PAT-105",
    "patient 106": "PAT-106",
    "pat 101": "PAT-101",
    "pat 102": "PAT-102",
    "pat 103": "PAT-103",
    "pat 104": "PAT-104",
    "pat 105": "PAT-105",
    "pat 106": "PAT-106",
    "pat-101": "PAT-101",
    "pat-102": "PAT-102",
    "pat-103": "PAT-103",
    "pat-104": "PAT-104",
    "pat-105": "PAT-105",
    "pat-106": "PAT-106",
    "pat-01": "PAT-101",
    "pat-02": "PAT-102",
    # Direct Patient ID to Room Mappings (P001 -> PAT-101 .. P006 -> PAT-106)
    "p001": "PAT-101",
    "p01": "PAT-101",
    "p1": "PAT-101",
    "patient p001": "PAT-101",
    "patient 1": "PAT-101",
    "patient p1": "PAT-101",
    "p002": "PAT-102",
    "p02": "PAT-102",
    "p2": "PAT-102",
    "patient p002": "PAT-102",
    "patient 2": "PAT-102",
    "patient p2": "PAT-102",
    "p003": "PAT-103",
    "p03": "PAT-103",
    "p3": "PAT-103",
    "patient p003": "PAT-103",
    "patient 3": "PAT-103",
    "patient p3": "PAT-103",
    "p004": "PAT-104",
    "p04": "PAT-104",
    "p4": "PAT-104",
    "patient p004": "PAT-104",
    "patient 4": "PAT-104",
    "patient p4": "PAT-104",
    "p005": "PAT-105",
    "p05": "PAT-105",
    "p5": "PAT-105",
    "patient p005": "PAT-105",
    "patient 5": "PAT-105",
    "patient p5": "PAT-105",
    "p006": "PAT-106",
    "p06": "PAT-106",
    "p6": "PAT-106",
    "patient p006": "PAT-106",
    "patient 6": "PAT-106",
    "patient p6": "PAT-106",
    "isolation": "ISO-01",
    "emergency": "EMR-01",
    "trauma": "TRM-01",
    "ambulance": "AMB-01",
    "ambulance bay": "AMB-01",
    "sanitization": "SAN-01",
    "bio sanitization": "SAN-01",
    "cssd": "SAN-01",
    "charging": "CHG-01",
    "charging station": "CHG-01",
    "dock": "CHG-01",
    "docking pad": "CHG-01",
    "cafeteria": "CAF-01",
    "canteen": "CAF-01",
    "washroom": "WSH-01",
    "restroom": "WSH-01",
}

# Default patient knowledge base mapping: Patient ID -> (Room ID, Prescribed Medicine)
PATIENT_DB_PRESETS: dict[str, tuple[str, str]] = {
    "P001": ("PAT-101", "Amoxicillin 500mg"),
    "P002": ("PAT-102", "Paracetamol 650mg"),
    "P003": ("PAT-103", "Metoprolol 25mg"),
    "P004": ("PAT-104", "Atorvastatin 20mg"),
    "P005": ("PAT-105", "Insulin Glargine 10 units"),
    "P006": ("PAT-106", "Ceftriaxone 1g"),
}


def clean_text(text: str) -> str:
    """Normalize input text by removing punctuation, extra whitespace,
    and converting spoken speech acoustic artifacts (e.g. 'i see you' -> 'icu',
    'zero zero three' -> '003', 'p zero zero three' -> 'p003', 'peace euro zero three' -> 'p003').
    """
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", " ", text)
    text = " ".join(text.split())

    # 1. Spoken acronyms
    text = re.sub(r"\b(i\s*see\s*you|eye\s*see\s*you|i\s*c\s*u)\b", "icu", text)

    # 2. Spoken number words to digits
    num_map = {
        "zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3",
        "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    }
    for word, digit in num_map.items():
        text = re.sub(rf"\b{word}\b", digit, text)

    # Clean up spaces between digits (e.g. "0 0 3" -> "003")
    text = re.sub(r"(\d)\s+(\d)", r"\1\2", text)
    text = re.sub(r"(\d)\s+(\d)", r"\1\2", text)

    # 3. Spoken patient identifiers and zero sequences
    text = re.sub(r"\b(peace|piece|pea|p)\s*(?:euro\s*)?0*([1-6])\b", r"p00\2", text)
    text = re.sub(r"\bp\s+0*([1-6])\b", r"p00\1", text)
    text = re.sub(r"\bp\s+00([1-6])\b", r"p00\1", text)

    # 4. Canonical chargers / docks
    text = re.sub(r"\b(charging\s*dock|docking\s*station|charging\s*station)\b", "charger", text)

    return " ".join(text.split())


def normalize_wake_phrase(text: str) -> str:
    """Robust normalization for wake-word matching (Phase 5.2):
    - lowercase
    - strip diacritics / unicode accents ('arōgya' -> 'arogya', 'arogyā' -> 'arogya')
    - punctuation stripped
    - repeated spaces collapsed
    - acoustic phonetic variants ('arogia', 'arogy', 'aarogya', 'erogya' -> 'arogya')
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFD", text.lower().strip())
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    cleaned = re.sub(r"[^\w\s]", " ", stripped)
    cleaned = " ".join(cleaned.split())

    # Normalize wake word token variations
    cleaned = re.sub(
        r"\b(aarogya|arogia|arogy|aroga|aroya|erogya|aerogya|arogyam|arokya|arokiya|aeroga)\b",
        "arogya",
        cleaned,
    )
    # Common salutations
    cleaned = re.sub(r"\b(hay|hai|hi|hello)\b", "hey", cleaned)
    return cleaned


def detect_wake_word(text: str) -> Tuple[bool, str]:
    """
    Check if text starts with or contains any variation of 'Hey Arogya' / 'Arogya' / 'Robot'.
    Supports robust Unicode normalization, regex matching, dictionary lookup, and fuzzy phonetic edit-distance.
    Returns (detected, remaining_text).
    """
    if not text or not text.strip():
        return False, ""

    # Phase 5.2: Normalized wake phrase matching
    norm = normalize_wake_phrase(text)

    # 1. Regex check on normalized phrase
    wake_regex = r"\b(hey|ok|namaste)?\s*(arogya|robot|mitra|garuda|sahayak)\b"
    match = re.search(wake_regex, norm)
    if match:
        start, end = match.span()
        remaining = (norm[:start] + " " + norm[end:]).strip()
        return True, remaining

    # 2. Check canonical text cleaning fallback
    cleaned = clean_text(text)
    if not cleaned:
        return False, ""

    wake_regex_raw = r"\b(hey|hi|hai|hello|ok|namaste|a|i)?\s*(arogya|aarogya|erogya|aerogya|aroga|arogyam|aroya|arogiya|arogia|arokya|arokiya|hiroki|roger|rogue|aeroge|eroge|robot|mitra|garuda|sahayak|alexa|assistant)\b"
    match = re.search(wake_regex_raw, cleaned)
    if match:
        start, end = match.span()
        remaining = (cleaned[:start] + " " + cleaned[end:]).strip()
        return True, remaining

    # 3. Direct exact or prefix match against WAKE_WORDS list
    for ww in sorted(WAKE_WORDS, key=len, reverse=True):
        if cleaned.startswith(ww):
            remaining = cleaned[len(ww):].strip()
            return True, remaining
        pattern = r"\b" + re.escape(ww) + r"\b"
        match = re.search(pattern, cleaned)
        if match:
            start, end = match.span()
            remaining = (cleaned[:start] + " " + cleaned[end:]).strip()
            return True, remaining

    # 4. Fuzzy phonetic matching: check each token against 'arogya' / 'robot' with Levenshtein distance <= 2
    words = cleaned.split()
    wake_targets = ["arogya", "hiroki", "roger", "rogue", "robot", "mitra", "garuda", "sahayak"]
    for i, word in enumerate(words):
        for target in wake_targets:
            max_dist = 2 if len(target) > 5 else 1
            if _levenshtein(word, target) <= max_dist:
                start_idx = i - 1 if (i > 0 and words[i - 1] in ("hey", "hi", "hai", "hello", "ok", "namaste", "a", "i")) else i
                remaining_words = words[:start_idx] + words[i + 1:]
                return True, " ".join(remaining_words).strip()

    return False, cleaned


def resolve_destination(text: str, exclude: Optional[set] = None) -> Optional[str]:
    """Extract canonical department code from text, optionally excluding certain codes."""
    cleaned = clean_text(text)
    exclude_set = exclude or set()
    # Check longest alias matches first
    for alias in sorted(ROOM_ALIASES.keys(), key=len, reverse=True):
        pattern = r"\b" + re.escape(alias) + r"\b"
        if re.search(pattern, cleaned):
            code = ROOM_ALIASES[alias]
            if code not in exclude_set:
                return code
    return None


def generate_canonical_mission_id(cmd_type: CommandType, raw_text: str = "") -> str:
    """Generate a persistent standardized Mission ID:
    MED-YYYYMMDD-XXXX (Medication delivery)
    EMR-YYYYMMDD-XXXX (Emergency Code Blue)
    GDE-YYYYMMDD-XXXX (Patient guidance)
    CHG-YYYYMMDD-XXXX (Recharge / Dock)
    MSN-YYYYMMDD-XXXX (General / Administrative)
    """
    date_str = datetime.now().strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:4].upper()
    if cmd_type == CommandType.DELIVER_ITEM:
        return f"MED-{date_str}-{suffix}"
    elif cmd_type == CommandType.EMERGENCY:
        return f"EMR-{date_str}-{suffix}"
    elif cmd_type == CommandType.GO_LOCATION:
        return f"GDE-{date_str}-{suffix}"
    elif cmd_type == CommandType.CHARGE_DOCK:
        return f"CHG-{date_str}-{suffix}"
    else:
        return f"MSN-{date_str}-{suffix}"


def parse_natural_command(raw: str) -> RobotCommand:
    """Convert flexible natural language into a structured RobotCommand.
    Supports English, Hindi, and Malayalam / Manglish transliterations,
    clinical database queries (P003), and emergency alerts.
    """
    cmd = _parse_natural_command_internal(raw)
    if cmd.cmd_type != CommandType.UNKNOWN and not cmd.mission_id:
        cmd.mission_id = generate_canonical_mission_id(cmd.cmd_type, raw)
    return cmd


def _parse_natural_command_internal(raw: str) -> RobotCommand:
    text = clean_text(raw)
    if not text:
        return RobotCommand(cmd_type=CommandType.UNKNOWN, raw_text=raw)

    # Detect patient ID reference if present (e.g. "p003", "patient p003", "patient 3", "p3")
    patient_id: Optional[str] = None
    m_pid = re.search(r"\b(p\s*0*([1-6])|patient\s*(?:#|no\.?)?\s*p?\s*0*([1-6]))\b", text)
    if m_pid:
        num = m_pid.group(2) or m_pid.group(3)
        if num:
            patient_id = f"P{int(num):03d}"

    # 1. Administrative / Terminal Commands
    if text in ("stop", "idle", "halt", "pause", "cancel"):
        return RobotCommand(cmd_type=CommandType.STOP, raw_text=raw)
    if text in ("status", "stat", "fleet", "state"):
        return RobotCommand(cmd_type=CommandType.STATUS, raw_text=raw)
    if text in ("resume", "continue", "restart"):
        return RobotCommand(cmd_type=CommandType.RESUME, raw_text=raw)
    if text in ("help", "h", "?", "commands"):
        return RobotCommand(cmd_type=CommandType.HELP, raw_text=raw)
    if text in ("quit", "exit", "q", "close", "bye"):
        return RobotCommand(cmd_type=CommandType.QUIT, raw_text=raw)

    # 1b. Clinical Database Queries (Doctor, Medication, Patient Status)
    if any(k in text for k in ("who is treating", "attending doctor", "treating doctor", "which doctor", "doctor for patient", "doctor name")):
        pid = patient_id or "P003"
        dest = PATIENT_DB_PRESETS.get(pid, ("PAT-103", ""))[0]
        return RobotCommand(
            cmd_type=CommandType.STATUS,
            raw_text=raw,
            argument=f"DOCTOR_QUERY:{pid}",
            destination_location=dest,
            priority=3,
        )

    if any(k in text for k in ("what medicine", "what medication", "which medicine", "what is prescribed", "medicine prescribed")) and not any(k in text for k in ("deliver", "take", "bring", "send", "kodukku")):
        pid = patient_id or "P003"
        dest = PATIENT_DB_PRESETS.get(pid, ("PAT-103", ""))[0]
        return RobotCommand(
            cmd_type=CommandType.STATUS,
            raw_text=raw,
            argument=f"MEDICATION_QUERY:{pid}",
            destination_location=dest,
            priority=3,
        )

    if any(k in text for k in ("check patient", "status of patient", "patient status", "how is patient", "patient condition", "check on patient", "patient ne check")):
        pid = patient_id or "P003"
        dest = PATIENT_DB_PRESETS.get(pid, ("PAT-103", ""))[0]
        return RobotCommand(
            cmd_type=CommandType.STATUS,
            raw_text=raw,
            argument=f"PATIENT_QUERY:{pid}",
            destination_location=dest,
            priority=3,
        )

    # 2. Battery & Charging Commands
    if any(k in text for k in ("charg", "dock", "recharg", "battery low", "low battery")):
        return RobotCommand(
            cmd_type=CommandType.CHARGE_DOCK,
            raw_text=raw,
            destination_location="CHG-01",
            argument="CHG-01",
            priority=5,
        )

    # 3. Emergency / Code Blue Commands
    if any(k in text for k in ("emergency", "code blue", "trauma", "urgent assist", "cardiac arrest", "emergency aanu", "vegam po", "aapathkaal", "stat", "send help")):
        # First try to find a target department other than emergency department itself
        dest = resolve_destination(text, exclude={"EMR-01", "TRM-01"})
        if not dest:
            if patient_id and patient_id in PATIENT_DB_PRESETS:
                dest = PATIENT_DB_PRESETS[patient_id][0]
            else:
                dest = resolve_destination(text) or "ICU-01"
        arg = f"PATIENT_EMERGENCY:{patient_id}" if patient_id else dest
        return RobotCommand(
            cmd_type=CommandType.EMERGENCY,
            raw_text=raw,
            destination_location=dest,
            argument=arg,
            priority=1,
        )

    # 4. Medicine / Item Delivery Commands
    # "deliver the prescribed medicine to P003", "deliver antibiotics to icu", "take medicine to icu"
    is_take_me = any(phrase in text for phrase in ("take me", "lead me", "guide me", "walk me", "show me"))
    if not is_take_me and any(k in text for k in ("deliver", "take", "bring", "carry", "transport", "send", "dispense", "kodukku", "kondu poyi", "marunnu")):
        dest = resolve_destination(text)
        if not dest:
            if patient_id and patient_id in PATIENT_DB_PRESETS:
                dest = PATIENT_DB_PRESETS[patient_id][0]
            else:
                dest = "ICU-01"

        # Determine clinical payload item
        if patient_id and patient_id in PATIENT_DB_PRESETS and any(k in text for k in ("prescribe", "prescribed", "medicine", "medication", "pill", "marunnu")):
            item = PATIENT_DB_PRESETS[patient_id][1]
        else:
            item = "Medicine Package"
            for med in ("antibiotics", "insulin", "paracetamol", "painkiller", "iv fluid", "blood", "saline", "sample", "prescription", "ointment", "syrup", "dressing", "gauze", "medication", "medicine", "metoprolol", "amoxicillin", "atorvastatin", "ceftriaxone"):
                if med in text:
                    item = med.title()
                    break

        return RobotCommand(
            cmd_type=CommandType.DELIVER_ITEM,
            raw_text=raw,
            source_location="PHM-01",
            destination_location=dest,
            item=item,
            argument=f"{item} -> {dest}",
            priority=3,
        )

    # 5. Sanitization / Disinfection / UV-C Decontamination & Restock Commands
    if any(k in text for k in ("sanitiz", "disinfect", "decontaminat", "clean", "steriliz", "restock", "resupply", "uv sweep", "uv-c")):
        dest = resolve_destination(text) or "SAN-01"
        return RobotCommand(
            cmd_type=CommandType.GO_LOCATION,
            raw_text=raw,
            destination_location=dest,
            argument=f"UV-C Sanitize -> {dest}",
            priority=4,
        )

    # 6. Patient Vitals Scanning / Triage / Guidance Commands
    if any(k in text for k in ("scan", "vitals", "check vitals", "register", "triage assist", "examine")):
        dest = resolve_destination(text) or "RCT-01"
        return RobotCommand(
            cmd_type=CommandType.GO_LOCATION,
            raw_text=raw,
            destination_location=dest,
            argument=f"Vitals Scan -> {dest}",
            priority=3,
        )

    # 7. Guidance / Navigation Commands (with Malayalam / Manglish verbs)
    if any(k in text for k in ("guide", "escort", "go", "navigate", "show me", "lead", "where is", "take me", "po", "poyi", "pokoo", "chal", "le chalo")):
        dest = resolve_destination(text) or "RCT-01"
        return RobotCommand(
            cmd_type=CommandType.GO_LOCATION,
            raw_text=raw,
            destination_location=dest,
            argument=dest,
            priority=3,
        )

    # Fallback: check if the text contains a recognizable destination name
    dest = resolve_destination(text)
    if dest:
        return RobotCommand(
            cmd_type=CommandType.GO_LOCATION,
            raw_text=raw,
            destination_location=dest,
            argument=dest,
            priority=3,
        )

    return RobotCommand(cmd_type=CommandType.UNKNOWN, raw_text=raw)


HELP_TEXT = """
+==============================================================================+
|  AROGYA MULTI-AGENT HOSPITAL ROBOT - COMMAND TERMINAL                        |
|  (Bilingual English + Hindi Voice Interaction)                               |
+==============================================================================+
|  WAKE WORD ACTIVATION (Voice & Console):                                     |
|    "Hey Arogya" / "Hi Arogya" / "Arogya"                                     |
|    -> Robot responds: "Hello, how can I help you?"                           |
|    -> Then speak or type your clinical request.                              |
|                                                                              |
|  EXAMPLE NATURAL LANGUAGE COMMANDS:                                          |
|    "Deliver medicine to ICU Bed 3"                                           |
|    "Deliver antibiotics to ICU"                                              |
|    "Can you guide me to the laboratory?"                                     |
|    "Emergency assistance required in the ICU"                                |
|    "Navigate to Pharmacy"                                                    |
|    "Charge battery at dock"                                                  |
|                                                                              |
|  SYSTEM COMMANDS:                                                            |
|    status      - Show live multi-agent fleet & battery status                |
|    stop        - Halt all robots, transition to IDLE                         |
|    resume      - Resume last preempted task                                  |
|    help        - Show this help text                                         |
|    quit / exit - Close the simulation                                        |
+==============================================================================+
"""


class CommandInterface:
    """
    Event-driven command terminal with strict two-stage wake-word state machine:
    - Stage 1: AWAITING_WAKE_WORD -> ignores random inputs until wake word is heard.
    - Stage 2: LISTENING_FOR_COMMAND -> listens for clinical task, dispatches to coordinator.
    """

    @staticmethod
    def is_garbage_asr(text: str) -> bool:
        """Detect single-syllable noise or ambient filler tokens without clinical intent."""
        return is_garbage_asr(text)

    def __init__(
        self,
        voice_callback: Optional[Callable[[str], None]] = None,
        enable_microphone: bool = False,
        vosk_model_path: Optional[str] = None,
        is_speaking_fn: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._cmd_queue: queue.Queue = queue.Queue()
        self._running = True
        self._voice_callback = voice_callback
        self._enable_mic = enable_microphone
        self._vosk_model_path = vosk_model_path
        self._is_speaking_fn = is_speaking_fn

        self.voice_state = VoiceInteractionState.SLEEPING
        self._listening_deadline = 0.0
        self._tts_mute_until: float = 0.0
        self._unrecognized_count: int = 0
        self._silence_threshold: float = 250.0  # RMS noise floor

        # Live voice pipeline debug tracking (for GUI Control Window & telemetry)
        self.mic_status: str = "Disabled (Keyboard Mode)" if not enable_microphone else "Initializing..."
        self.last_transcript: str = ""
        self.last_intent: str = "None"
        self.last_destination: str = "None"
        self.last_payload: str = "None"
        self.last_priority: str = "None"
        self.last_assigned_robot: str = "None"
        self.last_response: str = "None"
        self.last_wake_debug: dict[str, Any] = {
            "status": "SLEEPING",
            "detected": "",
            "normalized": "",
            "confidence": 0.0,
            "timestamp": time.time(),
        }
        self._voice_listeners: list[Callable[[dict], None]] = []

        # Background threads
        self._mic_thread: Optional[threading.Thread] = None

        # Start background stdin thread
        self._stdin_thread = threading.Thread(
            target=self._stdin_reader_worker,
            name="ArogyaStdinListener",
            daemon=True,
        )
        self._stdin_thread.start()

        # Optional microphone ASR
        if enable_microphone:
            self.start_mic()

        print()
        print("+==================================================================+")
        print("|  AROGYA COMMAND INTERFACE READY                                  |")
        print("|  State: IDLE (Awaiting Wake Word: 'Hey Arogya' / 'Hi Arogya')     |")
        print(f"|  Mic Status: {self.mic_status:<51}|")
        print("|  Robots will NOT move or speak until awakened by user command!   |")
        print("+==================================================================+")
        print()

    def add_voice_listener(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for voice pipeline events (GUI, HUD, logger)."""
        if callback not in self._voice_listeners:
            self._voice_listeners.append(callback)

    def _notify_listeners(self) -> None:
        """Notify all registered listeners with current voice state."""
        info = self.get_voice_debug_info()
        for cb in self._voice_listeners:
            try:
                cb(info)
            except Exception:
                pass

    def get_voice_debug_info(self) -> dict:
        """Return snapshot dictionary of live voice debug telemetry."""
        return {
            "mic_status": self.mic_status,
            "voice_state": self.voice_state.name,
            "transcript": self.last_transcript,
            "intent": self.last_intent,
            "destination": self.last_destination,
            "payload": self.last_payload,
            "priority": self.last_priority,
            "assigned_robot": self.last_assigned_robot,
            "response": self.last_response,
            "wake_debug": dict(self.last_wake_debug),
        }

    def set_assigned_robot(self, robot_id: str) -> None:
        """Record which robot took the last voice command."""
        self.last_assigned_robot = robot_id
        self._notify_listeners()

    def _find_vosk_model_path(self) -> Optional[str]:
        """Exhaustively find the Vosk model across relative and absolute candidate paths."""
        candidates = []
        if self._vosk_model_path:
            candidates.append(self._vosk_model_path)
            candidates.append(os.path.abspath(self._vosk_model_path))

        # Current working dir
        candidates.append(os.path.join(os.getcwd(), "models", "vosk-model-small-en-us-0.15"))
        candidates.append(os.path.join(os.getcwd(), "models"))

        # Relative to this file: environments/ -> isaac_sim_hospital/ -> HospitalRobotNav/models/
        this_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.normpath(os.path.join(this_dir, "..", "..", "models", "vosk-model-small-en-us-0.15")))
        candidates.append(os.path.normpath(os.path.join(this_dir, "..", "models", "vosk-model-small-en-us-0.15")))

        # Check ancestors
        curr = this_dir
        for _ in range(4):
            test_path = os.path.join(curr, "models", "vosk-model-small-en-us-0.15")
            candidates.append(test_path)
            curr = os.path.dirname(curr)

        for p in candidates:
            if os.path.exists(p) and os.path.isdir(p):
                # Verify it looks like a valid vosk model (contains am or conf or model files)
                return os.path.abspath(p)
        return None

    def start_mic(self) -> bool:
        """Start microphone ASR thread."""
        if self._mic_thread and self._mic_thread.is_alive():
            return True
        self._enable_mic = True
        self._mic_thread = threading.Thread(
            target=self._vosk_asr_worker,
            name="ArogyaMicListener",
            daemon=True,
        )
        self._mic_thread.start()
        return True

    def suppress_mic_for_tts(self, duration_sec: float = 2.0) -> None:
        """Temporarily mute incoming microphone stream to prevent self-transcription of TTS output."""
        self._tts_mute_until = max(self._tts_mute_until, time.time() + duration_sec)

    def _trigger_wake_response(self) -> None:
        """Acknowledge wake word: speak greeting and enter command listening mode."""
        self.voice_state = VoiceInteractionState.WAKE_DETECTED
        self.last_wake_debug["status"] = "WAKE DETECTED"
        self._notify_listeners()
        greeting = "Hello, I am Arogya. How can I help you?"
        self.last_response = greeting
        print("\n" + "=" * 60)
        print(f"[AROGYA] {greeting}")
        print("=" * 60)
        self.suppress_mic_for_tts(2.5)
        if self._voice_callback:
            try:
                self._voice_callback(greeting)
            except Exception:
                pass
        self.voice_state = VoiceInteractionState.LISTENING_FOR_COMMAND
        self.last_wake_debug["status"] = "LISTENING"
        self._listening_deadline = time.time() + 25.0
        self._unrecognized_count = 0
        print("[VOICE] Entering COMMAND_LISTENING state")
        print("[VOICE] Listening for command...")
        self._notify_listeners()

    def process_raw_input(self, text: str, source: str = "keyboard", target_robot: str = "AUTO", mission_id: Optional[str] = None) -> None:
        """Handle raw text according to the wake-word state machine."""
        text_clean = text.strip()
        if not text_clean:
            return

        if not is_garbage_asr(text_clean):
            self.last_transcript = text_clean
        elif self.voice_state in (VoiceInteractionState.LISTENING_FOR_COMMAND, VoiceInteractionState.TRANSCRIBING):
            self.last_transcript = "COMMAND NOT UNDERSTOOD"

        # Check wake word presence on every incoming text
        detected, remaining = detect_wake_word(text_clean)
        if detected:
            norm_wake = normalize_wake_phrase(text_clean)
            conf = 1.0 if any(k in norm_wake for k in ("hey arogya", "hi arogya", "arogya")) else 0.95
            self.last_wake_debug = {
                "status": "WAKE DETECTED",
                "detected": text_clean,
                "normalized": norm_wake,
                "confidence": conf,
                "timestamp": time.time(),
            }
            # Pure wake phrase with no attached command -> trigger wake response and listen
            if not remaining or remaining.strip() == "":
                self._trigger_wake_response()
                return

        # 0. Always execute direct GUI/Mobile/Web DB inputs immediately without blocking on wake word
        if source in ("web_db", "gui", "ui", "button", "mobile_voice", "mobile_tap", "mobile_text"):
            cmd_text = remaining if (detected and remaining) else text_clean
            cmd = parse_natural_command(cmd_text)
            cmd.source = source
            cmd.target_robot = target_robot  # propagate robot selection
            if mission_id:
                cmd.mission_id = mission_id
            if cmd.cmd_type != CommandType.UNKNOWN:
                self.voice_state = VoiceInteractionState.COMMAND_ACCEPTED
                self._notify_listeners()
                self.voice_state = VoiceInteractionState.PROCESSING_COMMAND
                self.last_intent = cmd.cmd_type.name
                self.last_destination = cmd.destination_location or "N/A"
                self.last_payload = cmd.item or "N/A"
                self.last_priority = f"P{cmd.priority}"
                self._cmd_queue.put(cmd)
                self.voice_state = VoiceInteractionState.SLEEPING
                self.last_wake_debug["status"] = "SLEEPING"
                self._notify_listeners()
                return

        # 1. Always permit direct administrative commands (status, help, stop, quit)
        norm = clean_text(text_clean)
        if norm in ("status", "stat", "fleet", "help", "h", "?", "stop", "idle", "resume", "quit", "exit", "q"):
            cmd = parse_natural_command(text_clean)
            cmd.source = source
            self.last_intent = cmd.cmd_type.name
            self.last_destination = "N/A"
            self.last_payload = "N/A"
            self.last_priority = f"P{cmd.priority}"
            self._cmd_queue.put(cmd)
            self._notify_listeners()
            return

        # 2. Voice / Microphone flow
        if self.voice_state in (VoiceInteractionState.SLEEPING, VoiceInteractionState.AWAITING_WAKE_WORD):
            print(f'[VOICE] Wake detection active. Checking: "{text_clean}"')
            if detected:
                print(f'[VOICE] Wake word detected: "{text_clean}"')
                self._trigger_wake_response()
                # If command is attached to wake word (e.g. "Hey Arogya deliver medicine to ICU")
                if remaining and not is_garbage_asr(remaining):
                    cmd = parse_natural_command(remaining)
                    cmd.source = source
                    if cmd.cmd_type != CommandType.UNKNOWN:
                        print(f'[VOICE] Command accepted: "{remaining}"')
                        self.voice_state = VoiceInteractionState.COMMAND_ACCEPTED
                        self._notify_listeners()
                        self.voice_state = VoiceInteractionState.PROCESSING_COMMAND
                        self.last_intent = cmd.cmd_type.name
                        self.last_destination = cmd.destination_location or "N/A"
                        self.last_payload = cmd.item or "N/A"
                        self.last_priority = f"P{cmd.priority}"
                        print(f'[VOICE] Intent: {cmd.cmd_type.name} | Destination: {self.last_destination} | Payload: {self.last_payload}')
                        self._cmd_queue.put(cmd)
                        print(f'[VOICE] Mission created & sent to coordinator')
                        self.voice_state = VoiceInteractionState.SLEEPING
                        self.last_wake_debug["status"] = "SLEEPING"
                        self._notify_listeners()
            else:
                self._notify_listeners()

        elif self.voice_state in (VoiceInteractionState.LISTENING_FOR_COMMAND, VoiceInteractionState.TRANSCRIBING):
            print(f'[VOICE] Speech detected: "{text_clean}"')
            # Check timeout
            if time.time() > self._listening_deadline:
                print("  [VOICE] TIMEOUT: Listening window expired. No valid command heard.")
                self.voice_state = VoiceInteractionState.TIMEOUT
                self.last_transcript = "TIMEOUT: NO COMMAND HEARD"
                self._notify_listeners()
                self.voice_state = VoiceInteractionState.SLEEPING
                self.last_wake_debug["status"] = "SLEEPING"
                self._notify_listeners()
                return

            # Check noise/garbage ASR token (e.g. "huh", "um")
            if is_garbage_asr(text_clean):
                print(f'  [ASR FILTER] Discarded noise/filler ASR token: "{text_clean}"')
                self.voice_state = VoiceInteractionState.COMMAND_NOT_UNDERSTOOD
                self._notify_listeners()
                return

            cmd = parse_natural_command(text_clean)
            cmd.source = source
            if cmd.cmd_type != CommandType.UNKNOWN:
                print(f'[VOICE] Command accepted: "{text_clean}"')
                self.voice_state = VoiceInteractionState.COMMAND_ACCEPTED
                self._notify_listeners()
                self.voice_state = VoiceInteractionState.PROCESSING_COMMAND
                self.last_intent = cmd.cmd_type.name
                self.last_destination = cmd.destination_location or "N/A"
                self.last_payload = cmd.item or "N/A"
                self.last_priority = f"P{cmd.priority}"
                print(f'[VOICE] Intent: {cmd.cmd_type.name} | Destination: {self.last_destination} | Payload: {self.last_payload}')
                self._cmd_queue.put(cmd)
                print(f'[VOICE] Mission created & sent to coordinator')
                self.voice_state = VoiceInteractionState.COMMAND_ACCEPTED
                self._unrecognized_count = 0
                self._notify_listeners()
                self.voice_state = VoiceInteractionState.SLEEPING
                self.last_wake_debug["status"] = "SLEEPING"
                self._notify_listeners()
            else:
                print(f"  [VOICE] COMMAND_NOT_UNDERSTOOD: Could not understand clinical request: '{text_clean}'.")
                self.voice_state = VoiceInteractionState.COMMAND_NOT_UNDERSTOOD
                self.last_transcript = f"NOT UNDERSTOOD: \"{text_clean}\""
                self._unrecognized_count += 1
                clarification = "Sorry, I didn't understand the command. Please try again."
                self.last_response = clarification
                print(f"[AROGYA] {clarification}")
                self.suppress_mic_for_tts(2.2)
                if self._voice_callback:
                    try:
                        self._voice_callback(clarification)
                    except Exception:
                        pass
                if self._unrecognized_count >= 2:
                    print("  [VOICE] Max retries reached. Returning to sleep.")
                    self.voice_state = VoiceInteractionState.SLEEPING
                else:
                    self._listening_deadline = time.time() + 15.0
                    self.voice_state = VoiceInteractionState.LISTENING_FOR_COMMAND
                self._notify_listeners()

    def _stdin_reader_worker(self) -> None:
        """Background thread reading console stdin."""
        while self._running:
            try:
                if sys.stdin and not sys.stdin.closed:
                    try:
                        line = sys.stdin.readline()
                    except Exception:
                        time.sleep(0.5)
                        continue
                    if not line:
                        time.sleep(1.0)
                        continue
                    self.process_raw_input(line, source="keyboard")
                else:
                    time.sleep(1.0)
            except Exception:
                time.sleep(0.5)

    def _vosk_asr_worker(self) -> None:
        """Background thread for offline Vosk microphone ASR with sounddevice callback."""
        model_path = self._find_vosk_model_path()
        if not model_path:
            self.mic_status = "ERROR: Vosk model directory not found"
            self._notify_listeners()
            print("[MIC ERROR] Vosk acoustic model directory not found.")
            return

        try:
            import json
            import sounddevice as sd
            import vosk

            # Suppress verbose Vosk Kaldi log output
            vosk.SetLogLevel(-1)
            model = vosk.Model(model_path)
            rec = vosk.KaldiRecognizer(model, 16000)

            # PHASE 2: Enumerate available input devices
            devices = sd.query_devices()
            default_device = int(sd.default.device[0]) if hasattr(sd.default.device, "__getitem__") else int(sd.default.device)
            print("\n[MIC DEBUG] Available input devices:")
            input_devices = []
            for idx, d in enumerate(devices):
                if d.get("max_input_channels", 0) > 0:
                    is_def = " [DEFAULT]" if idx == default_device else ""
                    input_devices.append((idx, d))
                    print(f"  {len(input_devices)}. [{idx}] {d.get('name')} (channels: {d.get('max_input_channels')}, default_sr: {d.get('default_samplerate')}){is_def}")

            selected_idx = default_device if (default_device is not None and default_device >= 0) else (input_devices[0][0] if input_devices else None)
            if selected_idx is None:
                raise RuntimeError("No hardware audio input devices with input channels found on system.")

            selected_dev = devices[selected_idx]
            selected_name = selected_dev.get("name", "Unknown")
            print(f"[MIC DEBUG] Selected input device: [{selected_idx}] {selected_name}")

            # PHASE 1: Audio callback & diagnostics
            print("[VOICE] Microphone initialized")
            print(f"[MIC DEBUG] Device: [{selected_idx}] {selected_name}")
            print("[MIC DEBUG] Sample rate: 16000")
            print("[MIC DEBUG] Channels: 1")

            audio_queue: queue.Queue[bytes] = queue.Queue()
            self._audio_frames_received = 0
            self._callback_count = 0

            def is_tts_active() -> bool:
                if time.time() < self._tts_mute_until:
                    return True
                if self._is_speaking_fn and self._is_speaking_fn():
                    self._tts_mute_until = max(self._tts_mute_until, time.time() + 0.8)
                    return True
                return False

            def audio_callback(indata, frames, time_info, status):
                if status:
                    pass
                self._audio_frames_received += frames
                self._callback_count += 1
                if self._callback_count % 100 == 0:
                    print(f"[MIC DEBUG] Audio frames received: {self._audio_frames_received}")

                # If robot is currently speaking via TTS, drop incoming audio to prevent self-transcription
                if is_tts_active():
                    return

                # Calculate RMS audio energy for speech / silence discrimination
                try:
                    import numpy as np
                    samples = np.frombuffer(indata, dtype=np.int16).astype(np.float32)
                    rms = float(np.sqrt(np.mean(np.square(samples)))) if len(samples) > 0 else 0.0
                    # VAD energy gating: discard low-energy ambient noise frames when sleeping
                    if self.voice_state in (VoiceInteractionState.SLEEPING, VoiceInteractionState.AWAITING_WAKE_WORD):
                        if rms < self._silence_threshold:
                            return
                    elif rms > self._silence_threshold:
                        if self.voice_state == VoiceInteractionState.LISTENING_FOR_COMMAND:
                            self.voice_state = VoiceInteractionState.TRANSCRIBING
                            self._notify_listeners()
                except Exception:
                    pass

                audio_queue.put(bytes(indata))

            self.mic_status = f"ONLINE: [{selected_idx}] {selected_name[:20]}"
            self._notify_listeners()

            with sd.RawInputStream(
                samplerate=16000,
                blocksize=4000,
                device=selected_idx,
                dtype="int16",
                channels=1,
                callback=audio_callback,
            ) as stream:
                last_partial = ""
                last_speech_time = 0.0
                chunk_counter = 0

                while self._running and self._enable_mic:
                    try:
                        data = audio_queue.get(timeout=0.15)
                    except queue.Empty:
                        # Check silence finalization for buffered partial text
                        if self.voice_state in (VoiceInteractionState.LISTENING_FOR_COMMAND, VoiceInteractionState.TRANSCRIBING):
                            if last_partial and (time.time() - last_speech_time) >= 0.85:
                                try:
                                    final_res = json.loads(rec.FinalResult())
                                    f_txt = final_res.get("text", "").strip() or last_partial
                                    if f_txt and not is_garbage_asr(f_txt):
                                        print(f'[VOICE] Finalized from partial on silence: "{f_txt}"')
                                        self.last_transcript = f_txt
                                        self._notify_listeners()
                                        self.process_raw_input(f_txt, source="microphone")
                                        rec.Reset()
                                        last_partial = ""
                                        last_speech_time = 0.0
                                except Exception as ex:
                                    print(f"[VOSK ERROR] FinalResult failed: {ex}")

                            # Check listening deadline
                            if time.time() > self._listening_deadline:
                                print("  [VOICE] Listening window expired (silence timeout). Returning to sleep.")
                                self.voice_state = VoiceInteractionState.TIMEOUT
                                self.last_transcript = "TIMEOUT: NO COMMAND HEARD"
                                self._notify_listeners()
                                rec.Reset()
                                last_partial = ""
                                time.sleep(0.5)
                                self.voice_state = VoiceInteractionState.SLEEPING
                                self._notify_listeners()
                        continue

                    # If within TTS mute suppression window, clear recognizer buffer
                    if is_tts_active():
                        rec.Reset()
                        last_partial = ""
                        continue

                    # Check command listening deadline
                    if self.voice_state in (VoiceInteractionState.LISTENING_FOR_COMMAND, VoiceInteractionState.TRANSCRIBING):
                        if time.time() > self._listening_deadline:
                            print("  [VOICE] Listening window expired. Returning to sleep.")
                            self.voice_state = VoiceInteractionState.TIMEOUT
                            self.last_transcript = "TIMEOUT: NO COMMAND HEARD"
                            self._notify_listeners()
                            rec.Reset()
                            last_partial = ""
                            time.sleep(0.5)
                            self.voice_state = VoiceInteractionState.SLEEPING
                            self._notify_listeners()
                            continue

                    chunk_counter += 1
                    if chunk_counter % 50 == 0:
                        print("[VOICE] Audio frame received")

                    if rec.AcceptWaveform(data):
                        res = json.loads(rec.Result())
                        final_text = res.get("text", "").strip()
                        if final_text:
                            if is_garbage_asr(final_text):
                                rec.Reset()
                                last_partial = ""
                                continue
                            print(f'[VOICE] Vosk final: "{final_text}"')
                            self.last_transcript = final_text
                            self._notify_listeners()
                            self.process_raw_input(final_text, source="microphone")
                            last_partial = ""
                            last_speech_time = 0.0
                    else:
                        part = json.loads(rec.PartialResult())
                        partial_text = part.get("partial", "").strip()
                        if partial_text and partial_text != last_partial:
                            last_partial = partial_text
                            last_speech_time = time.time()
                            print(f'[VOICE] Vosk partial: "{partial_text}"')
                            if not is_garbage_asr(partial_text) and len(partial_text) >= 3:
                                self.last_transcript = partial_text
                                self._notify_listeners()

                            if self.voice_state in (VoiceInteractionState.SLEEPING, VoiceInteractionState.AWAITING_WAKE_WORD):
                                detected, remaining = detect_wake_word(partial_text)
                                if detected:
                                    print(f'[VOICE] Wake word detected: "{partial_text}"')
                                    rec.Reset()
                                    last_partial = ""
                                    self._trigger_wake_response()
                                    if remaining and not is_garbage_asr(remaining):
                                        self.process_raw_input(remaining, source="microphone")
                            elif self.voice_state in (VoiceInteractionState.LISTENING_FOR_COMMAND, VoiceInteractionState.TRANSCRIBING):
                                p_cmd = parse_natural_command(partial_text)
                                if p_cmd.cmd_type != CommandType.UNKNOWN and (p_cmd.destination_location or p_cmd.cmd_type in (CommandType.STOP, CommandType.RESUME, CommandType.STATUS, CommandType.EMERGENCY, CommandType.CHARGE_DOCK)):
                                    print(f'[VOICE] High-confidence command in partial: "{partial_text}"')
                                    try:
                                        final_res = json.loads(rec.FinalResult())
                                        f_txt = final_res.get("text", "").strip() or partial_text
                                    except Exception:
                                        f_txt = partial_text
                                    rec.Reset()
                                    last_partial = ""
                                    last_speech_time = 0.0
                                    self.process_raw_input(f_txt, source="microphone")

        except ImportError as e:
            print(f"[MIC ERROR] Required audio module missing: {e}")
            self.mic_status = f"ERROR: Missing module {e}"
            self._notify_listeners()
        except Exception as e:
            print(f"[MIC ERROR] Audio input stream failed to open: {e}")
            self.mic_status = f"ERROR: {e}"
            self._notify_listeners()

    def poll_command(self) -> Optional[RobotCommand]:
        """Non-blocking poll for pending commands."""
        try:
            return self._cmd_queue.get_nowait()
        except queue.Empty:
            return None

    def has_commands(self) -> bool:
        return not self._cmd_queue.empty()

    def shutdown(self) -> None:
        self._running = False
        self._enable_mic = False


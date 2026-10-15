"""
HospitalRobotNav & Isaac Sim Hospital — Mission Understanding Layer
===================================================================
Provides natural language reasoning and intent/entity extraction for
autonomous hospital assistance.

Bridges unstructured clinical voice and text commands (English and Hindi)
into structured, priority-ranked EmbodiedMissionSpec objects ready for
multi-agent allocation and navigation.

Key Capabilities:
    1. Bilingual NLU (English + हिंदी):
       - Natural voice / text comprehension
       - Automatic language detection (Devanagari script detection)
       - Clinical entity grounding (medications, departments, bed numbers, urgency)
    2. Deep Integration with Core Language Engine:
       - Uses `language.intent_parser.IntentParser`
       - Uses `language.entity_extractor.EntityExtractor`
       - Maps extracted rooms to verified Isaac Sim 60m x 60m Department IDs
    3. Multi-Level Clinical Priority Resolution:
       - Level 1: CRITICAL_EMERGENCY (Code Blue, Trauma, Life Threat)
       - Level 2: URGENT_MEDICINE (Stat medications, IV fluids)
       - Level 3: SCHEDULED_DELIVERY (Routine medications, chart handoffs)
       - Level 4: VISITOR_ESCORT (Patient guidance, directory assistance)
       - Level 5: RETURN_TO_DOCK (Low battery, idle maintenance)
    4. Bilingual Spoken Dialogue Generation:
       - Produces natural acknowledgment phrases in English and Hindi
"""

from __future__ import annotations

import os
import re
import sys
import uuid
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

# Ensure repository root is on sys.path
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from language.intent_parser import IntentParser, IntentType, ParsedIntent
from language.entity_extractor import EntityExtractor, ExtractedEntities
from utilities.logger import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Clinical Priority Levels
# ─────────────────────────────────────────────────────────────────────────────

class ClinicalPriority(Enum):
    """5-tier priority hierarchy for hospital AMR operations."""
    CRITICAL_EMERGENCY  = 1   # Code Blue, Trauma resuscitation, Cardiac arrest
    URGENT_MEDICINE     = 2   # Stat medications, Adrenaline, Naloxone, Blood
    SCHEDULED_DELIVERY  = 3   # Routine prescription, Chart handoff, Meal tray
    VISITOR_ESCORT      = 4   # Patient guidance, Wheelchair assist, Information
    RETURN_TO_DOCK      = 5   # Recharging, Diagnostics, Idle standby


# ─────────────────────────────────────────────────────────────────────────────
# Structured Embodied Mission Specification
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EmbodiedMissionSpec:
    """Structured clinical mission representation ready for multi-agent allocation."""
    mission_id: str = ""
    raw_text: str = ""
    language: str = "en"                        # "en", "hi", "ml", or "ml-translit"
    task_type: str = "PATIENT_GUIDANCE"         # e.g. "MEDICINE_DELIVERY", "EMERGENCY_RESPONSE"
    item: str = "None"                          # e.g. "Paracetamol 500mg", "Trauma Kit"
    quantity: int = 1                           # e.g. 1
    source_dept: str = "RCT-01"                 # e.g. "PHM-01"
    dest_dept: str = "None"                     # e.g. "PAT-101"
    target_bed: Optional[str] = None            # e.g. "Bed 1"
    patient_id: Optional[str] = None            # e.g. "P001" canonical patient code
    target_patient: Optional[str] = None        # e.g. "Arun Patel"
    priority_level: int = 3                     # 1 (Critical) to 5 (Low)
    priority_label: str = "NORMAL"              # "CRITICAL_EMERGENCY", "URGENT", etc.
    urgency_string: str = "ROUTINE"             # "STAT", "URGENT", "ROUTINE"
    confidence: float = 1.0                     # NLU parsing confidence (0.0 to 1.0)
    spoken_response_en: str = ""                # Robot's spoken response in English
    spoken_response_hi: str = ""                # Robot's spoken response in Hindi
    spoken_response_ml: str = ""                # Robot's spoken response in Malayalam
    matched_triggers: List[str] = field(default_factory=list)
    is_emergency: bool = False

    @property
    def mission_type(self):
        class _MissionType:
            def __init__(self, name):
                self.name = str(name)
                self.value = str(name)
            def __str__(self):
                return self.name
        return _MissionType(self.task_type)

    @property
    def priority(self):
        class _Priority:
            def __init__(self, name, level):
                self.name = str(name)
                self.value = level
            def __str__(self):
                return self.name
        return _Priority(self.priority_label, self.priority_level)

    def to_dict(self) -> Dict[str, Any]:
        """Convert specification to JSON-serializable dictionary."""
        return {
            "mission_id": self.mission_id,
            "raw_text": self.raw_text,
            "language": self.language,
            "task_type": self.task_type,
            "item": self.item,
            "quantity": self.quantity,
            "source_dept": self.source_dept,
            "dest_dept": self.dest_dept,
            "target_bed": self.target_bed,
            "patient_id": self.patient_id,
            "target_patient": self.target_patient,
            "priority_level": self.priority_level,
            "priority_label": self.priority_label,
            "urgency_string": self.urgency_string,
            "confidence": self.confidence,
            "spoken_response_en": self.spoken_response_en,
            "spoken_response_hi": self.spoken_response_hi,
            "spoken_response_ml": self.spoken_response_ml,
            "matched_triggers": self.matched_triggers,
            "is_emergency": self.is_emergency,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Hospital Department Semantic Mappings
# ─────────────────────────────────────────────────────────────────────────────

DEPARTMENT_ALIASES: Dict[str, List[str]] = {
    "PHM-01": [
        "pharmacy", "dispensary", "chemist", "drug store", "medicine counter", "pharmacyil", "pharmacy-il",
        "ഫാർമസി", "മരുന്ന് കട", "दवाखाना", "औषधि कक्ष", "केमिस्ट", "फार्मेसी"
    ],
    "RCT-01": [
        "reception", "triage", "front desk", "admissions", "lobby counter", "receptionil", "reception-il",
        "റിസപ്ഷൻ", "സ്വാഗത മുറി", "അന്വേഷണം", "रिसेप्शन", "स्वागत कक्ष", "पूछताछ", "प्रवेश कक्ष"
    ],
    "NST-01": [
        "nurse station", "nurses station", "central nursing", "nurse desk", "ward sister",
        "നഴ്‌സ് സ്റ്റേഷൻ", "നഴ്‌സിംഗ് ഡെസ്ക്", "नर्स स्टेशन", "नर्सिंग डेस्क", "सिस्टर स्टेशन"
    ],
    "PAT-101": [
        "ward 101", "room 101", "patient 101", "recovery 101", "bed 101", "pat-101", "pat 101",
        "വാർഡ് 101", "മുറി 101", "രോഗി മുറി 101", "वार्ड 101", "कमरा 101", "मरीज कक्ष 101"
    ],
    "PAT-102": [
        "ward 102", "room 102", "patient 102", "recovery 102", "bed 102", "pat-102", "pat 102",
        "വാർഡ് 102", "മുറി 102", "वार्ड 102", "कमरा 102", "मरीज कक्ष 102"
    ],
    "PAT-103": [
        "ward 103", "room 103", "patient 103", "recovery 103", "bed 103", "pat-103", "pat 103",
        "വാർഡ് 103", "മുറി 103", "वार्ड 103", "कमरा 103", "मरीज कक्ष 103"
    ],
    "GW-01": [
        "general ward", "general inpatient", "inpatient ward", "male ward", "female ward",
        "ജനറൽ വാർഡ്", "सामान्य वार्ड", "जनरल वार्ड"
    ],
    "EMR-01": [
        "emergency", "casualty", "er", "emergency department", "emergency room", "urgent care", "emergency-il",
        "അടിയന്തര വിഭാഗം", "എമർജൻസി", "കാഷ്വാലിറ്റി", "इमरजेंसी", "आपातकाल", "कैजुअल्टी", "आपातकालीन विभाग"
    ],
    "TRM-01": [
        "trauma", "trauma bay", "trauma resuscitation", "resuscitation room",
        "ട്രോമ", "ട്രോമ സെന്റർ", "ट्रॉमा", "ट्रॉमा सेंटर", "रिससिटेशन"
    ],
    "ICU-01": [
        "icu", "intensive care", "critical care", "ccu", "cardiac icu", "icu-il", "icuyil",
        "ഐസിയു", "തീവ്രപരിചരണ വിഭാഗം", "आईसीयू", "गहन चिकित्सा इकाई", "क्रिटिकल केयर"
    ],
    "NIC-01": [
        "nicu", "neonatal", "pediatric", "nursery", "baby care",
        "എൻഐസിയു", "ശിശു പരിചരണം", "एनआईसीयू", "नवजात शिशु कक्ष", "बाल चिकित्सा"
    ],
    "OT-01": [
        "operation theatre 1", "ot 1", "or 1", "surgery room 1", "operation theater",
        "ഓപ്പറേഷൻ തിയറ്റർ 1", "ഓപ്പറേഷൻ തിയറ്റർ", "शल्यക്രിയ മുറി", "ऑपरेशन थिएटर 1", "सर्जरी कक्ष 1", "शल्य चिकित्सा"
    ],
    "OT-02": [
        "operation theatre 2", "ot 2", "or 2", "surgery room 2",
        "ഓപ്പറേഷൻ തിയറ്റർ 2", "ऑपरेशन थिएटर 2", "सर्जरी कक्ष 2"
    ],
    "LAB-01": [
        "pathology", "path lab", "laboratory", "blood bank", "sample lab", "diagnostic lab", "lab-il", "labil",
        "ലാബ്", "ലബോറട്ടറി", "രക്തപരിശോധന", "പാത്തോളജി", "पैथोलॉजी", "लैब", "प्रयोगशाला", "रक्त जांच केंद्र"
    ],
    "RAD-01": [
        "radiology", "x-ray", "ultrasound", "imaging",
        "റേഡിയോളജി", "എക്സ്-റേ", "റെഡിയോലോജി", "रेडियोलॉजी", "एक्स-रे", "अल्ट्रासाउंड"
    ],
    "MRI-01": [
        "mri", "ct scan", "mri suite", "computed tomography",
        "എംആർഐ", "സിടി സ്കാൻ", "एमआरआई", "सीटी स्कैन", "एमआरआई सुइट"
    ],
    "CON-01": [
        "consultation 1", "opd 1", "doctor clinic 1", "clinic 1",
        "കൺസൾട്ടേഷൻ 1", "ഡോക്ടർ മുറി 1", "परामर्श कक्ष 1", "ओपीडी 1", "डॉक्टर क्लिनिक 1"
    ],
    "CON-02": [
        "consultation 2", "opd 2", "doctor clinic 2", "clinic 2",
        "കൺസൾട്ടേഷൻ 2", "परामर्श कक्ष 2", "ओपीडी 2", "डॉक्टर क्लिनिक 2"
    ],
    "CON-03": [
        "consultation 3", "opd 3", "doctor clinic 3", "clinic 3",
        "കൺസൾട്ടേഷൻ 3", "परामर्श कक्ष 3", "ओपीडी 3", "डॉक्टर क्लिनिक 3"
    ],
    "ENT-01": [
        "entrance", "main entrance", "foyer", "lobby", "gate", "front gate",
        "പ്രവേശന കവാടം", "മുൻവാതിൽ", "मुख्य प्रवेश", "प्रवेश द्वार"
    ],
    "OPD-01": [
        "opd 1", "opd", "outpatient", "general opd", "opd clinic 1", "consultation 1",
        "ഒപിഡി", "ഒപിഡി 1", "ओपीडी", "ओपीडी 1"
    ],
    "OPD-02": [
        "opd 2", "pediatrics opd", "child clinic", "opd clinic 2", "consultation 2",
        "ഒപിഡി 2", "ओपीडी 2", "बाल ओपीडी"
    ],
    "OPD-03": [
        "opd 3", "cardiology opd", "heart clinic", "opd clinic 3", "consultation 3",
        "ഒപിഡി 3", "ओपीडी 3"
    ],
    "DOC-01": [
        "doctor office 1", "doctor room", "physician office", "doctor 1", "doctor",
        "ഡോക്ടർ മുറി 1", "ഡോക്ടർ 1", "डॉक्टर कक्ष", "डॉक्टर 1"
    ],
    "DOC-02": [
        "doctor office 2", "surgeon office", "doctor 2",
        "ഡോക്ടർ മുറി 2", "ഡോക്ടർ 2", "डॉक्टर कक्ष 2", "डॉक्टर 2"
    ],
    "STR-01": [
        "medicine storage", "pharmacy store", "drug vault", "medicine store", "drug storage",
        "മരുന്ന് കലവറ", "दवा भंडार", "औषधि भंडार"
    ],
    "STR-02": [
        "equipment storage", "wheelchair storage", "equipment depot", "equipment store",
        "ഉപകരണ കലവറ", "उपकरण भंडार"
    ],
    "NST-02": [
        "south nurse station", "nurse station 2", "ward nurse station",
        "തെക്ക് നഴ്സ് സ്റ്റേഷൻ", "दक्षिण नर्स स्टेशन"
    ],
    "ISO-01": [
        "isolation room", "isolation ward", "isolation", "quarantine",
        "ഐസൊലേഷൻ വാർഡ്", "ക്വാറന്റൈൻ", "आइसोलेशन वार्ड", "आइसोलेशन"
    ],
    "BLB-01": [
        "blood bank", "blood transfusion", "blood lab",
        "ബ്ലഡ് ബാങ്ക്", "രക്ത ബാങ്ക്", "रक्त बैंक", "ब्लड बैंक"
    ],
    "WAT-01": [
        "waiting area", "waiting lounge", "atrium", "visitor lounge",
        "കാത്തിരിപ്പ് കേന്ദ്രം", "പ്രതീക്ഷാലയം", "प्रतीक्षालय", "वेटिंग रूम", "लाउंज"
    ],
    "CAF-01": [
        "cafeteria", "canteen", "coffee shop", "dining", "staff lounge",
        "കാന്റീൻ", "ഭക്ഷണശാല", "ചായക്കട", "कैंटीन", "कैफेटेरिया", "भोजनालय"
    ],
    "CHG-01": [
        "charging bay", "dock", "charging pad", "base station", "robot station",
        "ചാർജിംഗ് സ്റ്റേഷൻ", "ചാർജിംഗ് ബേ", "ഡൊക്ക്", "चार्जिंग स्टेशन", "डॉक", "रोबोट बेस"
    ],
}

# Medicine Hindi mapping
HINDI_MEDICINE_MAP = {
    "पैरासिटामोल": "Paracetamol 500mg",
    "दवा": "Prescription Medication",
    "औषधि": "Prescription Medication",
    "आईबू्प्रोफेन": "Ibuprofen 400mg",
    "एस्पिरिन": "Aspirin 75mg",
    "इंसुलिन": "Insulin Glargine",
    "एड्रेनालाईन": "Adrenaline 1mg",
    "सलाइन": "Normal Saline 500ml",
    "एंटीबायोटिक": "Broad-Spectrum Antibiotic",
    "ऑक्सीजन": "Oxygen Cylinder",
    "ट्रॉमा किट": "Emergency Trauma Kit",
}

# Medicine Malayalam mapping
MALAYALAM_MEDICINE_MAP = {
    "പാരസെറ്റമോൾ": "Paracetamol 500mg",
    "മരുന്ന്": "Prescription Medication",
    "ഇൻസുലിൻ": "Insulin Glargine",
    "ആന്റിബയോട്ടിക്": "Broad-Spectrum Antibiotic",
    "ഓക്സിജൻ": "Oxygen Cylinder",
    "ട്രോമ കിറ്റ്": "Emergency Trauma Kit",
    "സലൈൻ": "Normal Saline 500ml",
    "അമോക്സിസിലിൻ": "Amoxicillin 500mg",
    "മെറ്റോപ്രോലോൾ": "Metoprolol 25mg",
}


# ─────────────────────────────────────────────────────────────────────────────
# Mission Understander Class
# ─────────────────────────────────────────────────────────────────────────────

class MissionUnderstander:
    """
    Intelligent Vision-Language Mission Understanding Engine for Arogya AMR.
    
    Transforms natural voice/text commands in English or Hindi into structured
    EmbodiedMissionSpec objects with verifiable department routing.
    """

    def __init__(self) -> None:
        self.intent_parser = IntentParser()
        self.entity_extractor = EntityExtractor()
        log.info("[MissionUnderstander] Initialized with bilingual NLU and 24 clinical department mappings.")

    def is_hindi(self, text: str) -> bool:
        """Check whether utterance contains Devanagari Unicode characters (0x0900 to 0x097F)."""
        return any('\u0900' <= char <= '\u097f' for char in text)

    def is_malayalam(self, text: str) -> bool:
        """Check whether utterance contains Malayalam Unicode characters (0x0D00 to 0x0D7F)."""
        return any('\u0d00' <= char <= '\u0d7f' for char in text)

    def is_manglish(self, text: str) -> bool:
        """Detect transliterated Malayalam (Manglish) clinical keywords in Latin script."""
        manglish_tokens = (
            "marunnu", "kondupoku", "kondu poyi", "kodukku", "edukkuka",
            "vegam", "aapathu", "aanu", "ashupathri", "rogikku", "pokoo",
            "sahayikku", "evide", "icu-il", "pharmacy-il", "lab-il", "patientinu", "poyi"
        )
        lower = text.lower()
        return any(t in lower for t in manglish_tokens)

    def resolve_department(self, text: str) -> Optional[str]:
        """Match textual references against hospital department aliases."""
        lower = text.lower()
        matched_depts = []
        for dept_id, aliases in DEPARTMENT_ALIASES.items():
            for alias in aliases:
                # Word boundary match for Latin script, substring match for Indic scripts (Devanagari, Malayalam)
                if any(('\u0900' <= c <= '\u097f') or ('\u0d00' <= c <= '\u0d7f') for c in alias):
                    if alias in lower:
                        matched_depts.append((len(alias), dept_id, alias))
                else:
                    pattern = rf"\b{re.escape(alias)}\b"
                    if re.search(pattern, lower):
                        matched_depts.append((len(alias), dept_id, alias))

        if not matched_depts:
            return None

        # Sort matches by alias length descending (most specific alias first)
        matched_depts.sort(key=lambda x: x[0], reverse=True)

        # If top match is EMR-01 due solely to the word "emergency", but there is another clinical destination present
        if matched_depts[0][1] == "EMR-01" and matched_depts[0][2] in ("emergency", "casualty", "emergency-il"):
            other_matches = [m for m in matched_depts if m[1] != "EMR-01"]
            if other_matches:
                return other_matches[0][1]

        return matched_depts[0][1]

    def extract_bed_number(self, text: str) -> Optional[str]:
        """Extract bed number from command (e.g. 'Bed 1', 'Bed 2', 'बिस्तर 1', 'കിടക്ക 1')."""
        match_en = re.search(r"\bbed\s*#?\s*(\d{1,2})\b", text, re.IGNORECASE)
        if match_en:
            return f"Bed {match_en.group(1)}"
        match_hi = re.search(r"(?:बिस्तर|बेड)\s*#?\s*(\d{1,2})", text)
        if match_hi:
            return f"Bed {match_hi.group(1)}"
        match_ml = re.search(r"(?:കിടക്ക|ബെഡ്)\s*#?\s*(\d{1,2})", text)
        if match_ml:
            return f"Bed {match_ml.group(1)}"
        return None

    def understand_mission(self, user_command: str) -> EmbodiedMissionSpec:
        """Alias for reason_mission."""
        return self.reason_mission(user_command)

    def parse_command(self, user_command: str) -> EmbodiedMissionSpec:
        """Alias for reason_mission."""
        return self.reason_mission(user_command)

    def parse(self, user_command: str) -> EmbodiedMissionSpec:
        """Alias for reason_mission."""
        return self.reason_mission(user_command)

    def reason_mission(self, user_command: str) -> EmbodiedMissionSpec:
        """
        Execute deep vision-language reasoning on a clinical command.
        Supports English, Hindi, Malayalam Unicode script, and Manglish transliteration.
        
        Args:
            user_command: Raw text or transcribed speech.
            
        Returns:
            EmbodiedMissionSpec dataclass fully populated with clinical routing.
        """
        raw = user_command.strip()
        if self.is_malayalam(raw):
            lang = "ml"
        elif self.is_hindi(raw):
            lang = "hi"
        elif self.is_manglish(raw):
            lang = "ml-translit"
        else:
            lang = "en"

        # 1. Core Intent Parsing
        parsed_intent: ParsedIntent = self.intent_parser.parse(raw)
        intent_type = parsed_intent.intent

        # 2. Core Entity Extraction
        entities: ExtractedEntities = self.entity_extractor.extract(raw)

        # 3. Department Grounding
        target_dept = self.resolve_department(raw)
        target_bed = self.extract_bed_number(raw)

        # 4. Item / Medication Identification
        item = "Clinical Supplies"
        if entities.medicines:
            item = f"{entities.medicines[0].capitalize()}"
        else:
            # Common English medicine names
            for med in ("antibiotics", "antibiotic", "insulin", "paracetamol", "aspirin", "ibuprofen", "metoprolol", "amoxicillin", "atorvastatin", "ceftriaxone", "adrenaline", "saline", "oxygen"):
                if med in raw.lower():
                    item = med.capitalize()
                    break
            # Check Hindi medicine triggers
            if item == "Clinical Supplies":
                for hi_k, hi_v in HINDI_MEDICINE_MAP.items():
                    if hi_k in raw:
                        item = hi_v
                        break
            # Check Malayalam medicine triggers
            if item == "Clinical Supplies":
                for ml_k, ml_v in MALAYALAM_MEDICINE_MAP.items():
                    if ml_k in raw:
                        item = ml_v
                        break

        # 5. Priority & Urgency Classification
        is_emergency = False
        priority_level = 3
        priority_label = "SCHEDULED_DELIVERY"
        urgency_string = "ROUTINE"

        raw_lower = raw.lower()
        if (
            intent_type == IntentType.EMERGENCY
            or "code blue" in raw_lower
            or "emergency" in raw_lower
            or "trauma" in raw_lower
            or "emergency aanu" in raw_lower
            or "vegam po" in raw_lower
            or "aapathu" in raw_lower
            or "aapathkaal" in raw_lower
            or "ഇമർജൻസി" in raw
            or "അടിയന്തര" in raw
            or "കോഡ് ബ്ലൂ" in raw
            or "इमरजेंसी" in raw
            or "कोड ब्लू" in raw
            or "आपातकाल" in raw
        ):
            is_emergency = True
            priority_level = 1
            priority_label = "CRITICAL_EMERGENCY"
            urgency_string = "STAT"
        elif (
            entities.priority <= 2
            or "immediately" in raw_lower
            or "urgently" in raw_lower
            or "stat" in raw_lower
            or "asap" in raw_lower
            or "vegam" in raw_lower
            or "udane" in raw_lower
            or "ഉടൻ" in raw
            or "പെട്ടെന്ന്" in raw
            or "तुरंत" in raw
            or "जल्दी" in raw
        ):
            priority_level = 2
            priority_label = "URGENT_MEDICINE"
            urgency_string = "URGENT"
        elif intent_type in (IntentType.GUIDE_PATIENT, IntentType.ESCORT_VISITOR) or any(k in raw_lower for k in ("vazhi", "sahayikku", "pokoo", "വഴി", "നയിക്കൂ")):
            priority_level = 4
            priority_label = "VISITOR_ESCORT"
            urgency_string = "STANDARD"

        # 6. Task Type, Source & Destination Assignment
        source_dept = "PHM-01"
        dest_dept = target_dept or "PAT-101"

        if is_emergency:
            task_type = "EMERGENCY_RESPONSE"
            source_dept = "CHG-01"
            dest_dept = target_dept or "ICU-01"
            item = "Emergency Resuscitation Kit"
        elif (
            intent_type == IntentType.DELIVER_MEDICINE
            or bool(entities.medicines)
            or any(k in raw for k in HINDI_MEDICINE_MAP)
            or any(k in raw for k in MALAYALAM_MEDICINE_MAP)
            or "deliver" in raw_lower
            or "medicine" in raw_lower
            or "antibiotic" in raw_lower
            or "antibiotics" in raw_lower
            or "medication" in raw_lower
            or "marunnu" in raw_lower
            or "kondupoku" in raw_lower
            or "kodukku" in raw_lower
            or "മരുന്ന്" in raw
            or "എത്തിക്കൂ" in raw
            or "നൽകൂ" in raw
        ):
            task_type = "MEDICINE_DELIVERY"
            source_dept = "PHM-01"
            dest_dept = target_dept or "PAT-101"
            if item == "Clinical Supplies":
                item = "Prescribed Medications"
        elif (
            intent_type in (IntentType.GUIDE_PATIENT, IntentType.ESCORT_VISITOR)
            or any(k in raw_lower for k in ("guide", "escort", "lead", "where is", "vazhi", "sahayikku", "pokoo"))
            or any(k in raw for k in ("വഴി", "നയിക്കൂ", "കൂട്ടിപ്പോകൂ"))
        ):
            task_type = "RECEPTION_GUIDE"
            source_dept = "RCT-01"
            dest_dept = target_dept or "CON-01"
            item = "Patient Escort Service"
        elif intent_type == IntentType.CALL_NURSE or "nurse" in raw_lower or "നഴ്സ്" in raw:
            task_type = "NURSE_ALERT"
            source_dept = "NST-01"
            dest_dept = target_dept or "PAT-101"
            item = "Nurse Assistance Request"
        elif intent_type in (IntentType.TRANSPORT_SAMPLE, IntentType.DELIVER_REPORT) or "sample" in raw_lower or "രക്ത സാമ്പിൾ" in raw:
            task_type = "SPECIMEN_TRANSPORT"
            source_dept = "NST-01"
            dest_dept = "LAB-01"
            item = "Pathology Diagnostic Specimens"
        elif "charge" in raw_lower or "dock" in raw_lower or "चार्ज" in raw or "ചാർജ്" in raw:
            task_type = "RETURN_TO_DOCK"
            source_dept = "CHG-01"
            dest_dept = "CHG-01"
            item = "AMR Self-Recharge"
            priority_level = 5
            priority_label = "RETURN_TO_DOCK"
        else:
            task_type = "CLINICAL_TASK"

        # Determine canonical Mission ID format matching Section 10 specification:
        # MED-YYYYMMDD-XXXX, EMR-YYYYMMDD-XXXX, GDE-YYYYMMDD-XXXX, SUP-YYYYMMDD-XXXX, MSN-YYYYMMDD-XXXX
        date_str = datetime.now().strftime("%Y%m%d")
        rand_suffix = uuid.uuid4().hex[:4].upper()
        if is_emergency:
            mission_id = f"EMR-{date_str}-{rand_suffix}"
        elif "DELIVER" in task_type:
            mission_id = f"MED-{date_str}-{rand_suffix}"
        elif "GUIDE" in task_type or "ESCORT" in task_type or "RECEPTION" in task_type:
            mission_id = f"GDE-{date_str}-{rand_suffix}"
        elif "SUPPORT" in task_type or "EQUIPMENT" in task_type:
            mission_id = f"SUP-{date_str}-{rand_suffix}"
        elif "CHARGE" in task_type or "DOCK" in task_type:
            mission_id = f"CHG-{date_str}-{rand_suffix}"
        else:
            mission_id = f"MSN-{date_str}-{rand_suffix}"

        # 7. Trilingual Spoken Dialogue Generation (English + Hindi + Malayalam)
        dept_name_en = dest_dept
        dept_hindi_names = {
            "PAT-101": "वार्ड 101",
            "PAT-102": "वार्ड 102",
            "PAT-103": "वार्ड 103",
            "ICU-01": "आईसीयू",
            "EMR-01": "इमरजेंसी",
            "TRM-01": "ट्रॉमा यूनिट",
            "PHM-01": "फार्मेसी",
            "RCT-01": "रिसेप्शन",
            "NST-01": "नर्स स्टेशन",
            "CHG-01": "चार्जिंग स्टेशन",
            "LAB-01": "पैथोलॉजी लैब",
            "GW-01": "जनरल वार्ड",
        }
        dept_malayalam_names = {
            "PAT-101": "വാർഡ് 101",
            "PAT-102": "വാർഡ് 102",
            "PAT-103": "വാർഡ് 103",
            "ICU-01": "ഐസിയു",
            "EMR-01": "അടിയന്തര വിഭാഗം",
            "TRM-01": "ട്രോമ യൂണിറ്റ്",
            "PHM-01": "ഫാർമസി",
            "RCT-01": "റിസപ്ഷൻ",
            "NST-01": "നഴ്സിംഗ് സ്റ്റേഷൻ",
            "CHG-01": "ചാർജിംഗ് സ്റ്റേഷൻ",
            "LAB-01": "പാത്തോളജി ലാബ്",
            "GW-01": "ജനറൽ വാർഡ്",
        }
        dept_name_hi = dept_hindi_names.get(dest_dept, dest_dept)
        dept_name_ml = dept_malayalam_names.get(dest_dept, dest_dept)

        bed_str_en = f", {target_bed}" if target_bed else ""
        bed_str_hi = f", {target_bed}" if target_bed else ""
        bed_str_ml = f", ബെഡ് {target_bed.replace('Bed ', '')}" if target_bed else ""

        if is_emergency:
            resp_en = f"Emergency Alert confirmed! Code Blue protocol activated for {dest_dept}. Rerouting immediately!"
            resp_hi = f"आपातकालीन अलर्ट की पुष्टि! {dept_name_hi} के लिए तुरंत रवाना हो रहा हूँ। कृपया रास्ता दें!"
            resp_ml = f"അടിയന്തര മുന്നറിയിപ്പ് സ്ഥിരീകരിച്ചു! {dept_name_ml}-ലേക്ക് കോഡ് ബ്ലൂ പ്രോട്ടോക്കോൾ സജീവമാക്കി. ഉടൻ എത്തുന്നു!"
        elif task_type == "MEDICINE_DELIVERY":
            resp_en = f"Mission confirmed. Collecting {item} from Pharmacy and delivering to {dest_dept}{bed_str_en}."
            resp_hi = f"मिशन की पुष्टि हुई। फार्मेसी से {item} लेकर {dept_name_hi}{bed_str_hi} में पहुंचा रहा हूँ।"
            resp_ml = f"ദൗത്യം സ്ഥിരീകരിച്ചു. ഫാർമസിയിൽ നിന്ന് {item} എടുത്ത് {dept_name_ml}{bed_str_ml}-ലേക്ക് എത്തിക്കുന്നു."
        elif task_type == "RECEPTION_GUIDE":
            resp_en = f"Guidance mission active. Please follow me to {dest_dept}."
            resp_hi = f"मार्गदर्शन प्रारंभ। कृपया मेरे पीछे {dept_name_hi} की ओर आएं।"
            resp_ml = f"വഴികാട്ടൽ ദൗത്യം സജീവമാണ്. ദയവായി എന്നെ പിന്തുടർന്ന് {dept_name_ml}-ലേക്ക് വരിക."
        elif task_type == "RETURN_TO_DOCK":
            resp_en = "Mission complete. Returning autonomously to Charging Bay 1."
            resp_hi = "कार्य संपन्न हुआ। चार्जिंग स्टेशन 1 पर वापस लौट रहा हूँ।"
            resp_ml = "ദൗത്യം പൂർത്തിയായി. ചാർജിംഗ് സ്റ്റേഷൻ ഒന്നിലേക്ക് സ്വയം തിരികെ പോകുന്നു."
        else:
            resp_en = f"Command acknowledged. Proceeding with {task_type} to {dest_dept}."
            resp_hi = f"आदेश स्वीकार किया गया। {dept_name_hi} के लिए कार्य प्रारंभ।"
            resp_ml = f"ആജ്ഞ സ്വീകരിച്ചു. {dept_name_ml}-ലേക്ക് {task_type} നടപടികൾ ആരംഭിക്കുന്നു."

        # Resolve patient_id and target_patient from entities
        extracted_patient_id = entities.patient_id if getattr(entities, "patient_id", None) else None
        extracted_patient_name = None
        if getattr(entities, "persons", None):
            for person in entities.persons:
                if person.lower().startswith("patient"):
                    extracted_patient_name = person.replace("Patient", "").strip()
                    break

        spec = EmbodiedMissionSpec(
            mission_id=mission_id,
            raw_text=raw,
            language=lang,
            task_type=task_type,
            item=item,
            quantity=entities.quantity or 1,
            source_dept=source_dept,
            dest_dept=dest_dept,
            target_bed=target_bed,
            patient_id=extracted_patient_id,
            target_patient=extracted_patient_name,
            priority_level=priority_level,
            priority_label=priority_label,
            urgency_string=urgency_string,
            confidence=round(parsed_intent.confidence, 3),
            spoken_response_en=resp_en,
            spoken_response_hi=resp_hi,
            spoken_response_ml=resp_ml,
            matched_triggers=parsed_intent.matched_triggers,
            is_emergency=is_emergency,
        )

        log.info(
            "[MissionUnderstander] Parsed mission: %s (%s, Lang=%s, Pri=%d, Urgency=%s, Target=%s)",
            spec.mission_id, spec.task_type, spec.language, spec.priority_level, spec.urgency_string, spec.dest_dept
        )
        return spec

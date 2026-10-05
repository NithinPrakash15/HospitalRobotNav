"""
HospitalRobotNav — Intent Parser
===================================
Rule-based intent classification engine for hospital robot commands.

Classifies natural language text into structured intent categories using
keyword pattern matching with weighted confidence scoring.

Design:
    Each ``IntentType`` has a set of trigger phrases.  The parser
    counts how many trigger phrases appear in the input text, normalises
    by the intent's strongest single trigger weight, and produces a
    confidence score.  The highest-confidence intent (above the threshold)
    wins.

    Scoring:  confidence = (sum of matched trigger weights) / (strongest
    trigger weight) + a small compound boost for multiple matches.
    Normalising by the strongest trigger (rather than the sum of *all*
    triggers for the intent) keeps confidence interpretable regardless of
    how many total phrases an intent defines — one decisive phrase yields
    a high score, while many weak overlapping phrases can stack.

    This architecture is designed for clean **drop-in replacement** with
    an LLM-based classifier — the ``ParsedIntent`` output dataclass
    remains identical regardless of the backend.

Supported Intents:
    DELIVER_MEDICINE   — Collect and deliver medications.
    GUIDE_PATIENT      — Escort a patient to a department.
    CALL_NURSE         — Summon a nurse to a location.
    EMERGENCY          — Emergency response / code alerts.
    DELIVER_REPORT     — Transport lab reports / test results.
    TRANSPORT_SAMPLE   — Transport lab samples between departments.
    FETCH_WHEELCHAIR   — Retrieve a wheelchair.
    ESCORT_VISITOR     — Guide a visitor through the hospital.
    NAVIGATE           — Simple navigation to a location.
    STATUS_QUERY       — Query robot status / battery / ETA.
    CANCEL             — Cancel current mission.
    CONFIRM            — Affirm a pending confirmation.
    DENY               — Deny / reject a pending confirmation.
    UNKNOWN            — Unrecognised command.

ROS2 Deployment Note:
    In production, this module would be replaced by an LLM node
    subscribing to /transcript and publishing /parsed_intent (custom msg).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

from language.language_config import LANGUAGE_CONFIG
from utilities.logger import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Intent Types
# ─────────────────────────────────────────────────────────────────────────────

class IntentType(Enum):
    """All supported robot command intents."""
    DELIVER_MEDICINE   = auto()
    GUIDE_PATIENT      = auto()
    CALL_NURSE         = auto()
    EMERGENCY          = auto()
    DELIVER_REPORT     = auto()
    TRANSPORT_SAMPLE   = auto()
    FETCH_WHEELCHAIR   = auto()
    ESCORT_VISITOR     = auto()
    NAVIGATE           = auto()
    STATUS_QUERY       = auto()
    CANCEL             = auto()
    CONFIRM            = auto()
    DENY               = auto()
    # Database-driven patient/doctor/medication queries
    PATIENT_STATUS_QUERY  = auto()
    DOCTOR_QUERY          = auto()
    MEDICATION_QUERY      = auto()
    PATIENT_EMERGENCY     = auto()
    SHOW_ACTIVE_PATIENTS  = auto()
    UNKNOWN            = auto()


# ─────────────────────────────────────────────────────────────────────────────
# Intent Trigger Phrases
# ─────────────────────────────────────────────────────────────────────────────

# Each intent maps to a list of (phrase, weight) tuples.
# Higher weight = stronger signal for this intent.

_INTENT_TRIGGERS: Dict[IntentType, List[Tuple[str, float]]] = {

    IntentType.DELIVER_MEDICINE: [
        ("deliver medicine",    1.0),
        ("deliver medication",  1.0),
        ("collect medicine",    1.0),
        ("collect medication",  1.0),
        ("bring medicine",      1.0),
        ("bring medication",    1.0),
        ("get medicine",        0.9),
        ("get medication",      0.9),
        ("take medicine",       0.8),
        ("take medication",     0.8),
        ("pick up medicine",    0.9),
        ("pick up medication",  0.9),
        ("deliver drug",        0.8),
        ("deliver tablet",      0.8),
        ("medicine delivery",   1.0),
        ("दवा ले आजाओ",         1.0),
        ("दवा लाओ",             1.0),
        ("दवा दे",               1.0),
        ("फार्मेसी से दवा",       1.0),
        ("മരുന്ന് കൊണ്ടുവരൂ",     1.0),
        ("മരുന്ന് തരക്കോ",         1.0),
        ("മരുന്ന് എടുക്കൂ",        1.0),
        ("pharmacy",            0.5),
        ("prescription",        0.7),
        ("paracetamol",         0.6),
        ("ibuprofen",           0.6),
        ("aspirin",             0.6),
        ("antibiotic",          0.6),
        ("dosage",              0.5),
        ("pills",               0.5),
        ("tablets",             0.5),
        ("capsules",            0.5),
        ("injection",           0.5),
        ("iv fluid",            0.5),
        ("saline",              0.5),
    ],

    IntentType.GUIDE_PATIENT: [
        ("guide patient",       1.0),
        ("guide the patient",   1.0),
        ("escort patient",      1.0),
        ("take patient",        0.9),
        ("lead patient",        0.9),
        ("show patient",        0.8),
        ("accompany patient",   0.9),
        ("walk patient",        0.8),
        ("help patient find",   0.8),
        ("show the way",        0.7),
        ("patient to",          0.6),
    ],

    IntentType.CALL_NURSE: [
        ("call nurse",          1.0),
        ("call a nurse",        1.0),
        ("need nurse",          1.0),
        ("nurse help",          0.9),
        ("get nurse",           0.9),
        ("summon nurse",        0.9),
        ("page nurse",          0.9),
        ("nurse station",       0.7),
        ("nursing assistance",  0.8),
        ("send nurse",          0.9),
        ("alert nurse",         0.8),
        ("need help",           0.5),
        ("need assistance",     0.5),
    ],

    IntentType.EMERGENCY: [
        ("emergency",           1.0),
        ("code blue",           1.0),
        ("code red",            1.0),
        ("critical",            0.8),
        ("life threatening",    1.0),
        ("cardiac arrest",      1.0),
        ("heart attack",        1.0),
        ("stroke",              0.8),
        ("fire",                0.7),
        ("crash cart",          1.0),
        ("urgent help",         0.8),
        ("not breathing",       1.0),
        ("collapsed",           0.8),
        ("unresponsive",        0.9),
        ("bleeding",            0.7),
        ("anaphylaxis",         1.0),
        ("आपातकाल",            1.0),
        ("तत्काल मदद",          1.0),
        ("अति आवश्यक",          1.0),
        ("അടിയന്തിരം",           1.0),
        ("തരത്തിലുള്ള സഹായം",     0.8),
    ],

    IntentType.DELIVER_REPORT: [
        ("deliver report",      1.0),
        ("deliver results",     1.0),
        ("deliver test results",1.0),
        ("lab results",         0.9),
        ("test report",         0.9),
        ("bring report",        0.9),
        ("bring results",       0.9),
        ("collect report",      0.9),
        ("get results",         0.8),
        ("blood report",        0.9),
        ("x-ray report",        0.9),
        ("scan results",        0.8),
        ("mri results",         0.8),
        ("ct results",          0.8),
        ("pathology report",    0.9),
    ],

    IntentType.TRANSPORT_SAMPLE: [
        ("transport sample",    1.0),
        ("lab sample",          1.0),
        ("blood sample",        1.0),
        ("urine sample",        1.0),
        ("tissue sample",       1.0),
        ("collect sample",      0.9),
        ("deliver sample",      0.9),
        ("take sample",         0.8),
        ("specimen",            0.8),
        ("biopsy",              0.7),
        ("swab",                0.6),
        ("sample to lab",       1.0),
        ("sample to laboratory",1.0),
    ],

    IntentType.FETCH_WHEELCHAIR: [
        ("wheelchair",          1.0),
        ("bring wheelchair",    1.0),
        ("get wheelchair",      1.0),
        ("fetch wheelchair",    1.0),
        ("need wheelchair",     1.0),
        ("wheel chair",         0.9),
        ("stretcher",           0.7),
        ("gurney",              0.7),
    ],

    IntentType.ESCORT_VISITOR: [
        ("escort visitor",      1.0),
        ("guide visitor",       1.0),
        ("take visitor",        0.9),
        ("show visitor",        0.8),
        ("visitor to",          0.7),
        ("lead visitor",        0.9),
        ("accompany visitor",   0.9),
        ("family member",       0.6),
        ("guest",               0.5),
    ],

    IntentType.NAVIGATE: [
        ("go to",               1.0),
        ("move to",             1.0),
        ("navigate to",         1.0),
        ("head to",             0.9),
        ("drive to",            0.8),
        ("travel to",           0.8),
        ("proceed to",          0.9),
        ("return to",           0.8),
        ("go back to",          0.8),
        ("come to",             0.7),
        ("जाओ",                 0.9),
        ("चलें",                 1.0),
        ("ले चलो",               0.8),
        ("പോകൂ",                 1.0),
        ("വന്നു പോകൂ",            0.8),
    ],

    IntentType.STATUS_QUERY: [
        ("what is your status",     1.0),
        ("status update",           1.0),
        ("where are you",           1.0),
        ("battery level",           1.0),
        ("how much battery",        1.0),
        ("current mission",         0.9),
        ("what are you doing",      0.9),
        ("eta",                     0.8),
        ("estimated time",          0.8),
        ("how long",                0.6),
        ("are you busy",            0.7),
        ("progress",                0.6),
        ("report status",           1.0),
        ("स्थिति क्या है",          1.0),
        ("आप कहाँ हैं",              1.0),
        ("അവസ്ഥ എന്താണ്",            1.0),
    ],

    IntentType.CANCEL: [
        ("cancel",              1.0),
        ("abort",               1.0),
        ("stop",                0.8),
        ("cancel mission",      1.0),
        ("abort mission",       1.0),
        ("stop mission",        0.9),
        ("halt",                0.7),
        ("never mind",          0.8),
        ("forget it",           0.8),
        ("रद्द करें",             1.0),
        ("रद्द कर दो",             1.0),
        ("റദ്ദ് ചെയ്യൂ",           1.0),
    ],

    IntentType.CONFIRM: [
        ("yes",         1.0),
        ("yeah",        1.0),
        ("yep",         1.0),
        ("yup",         1.0),
        ("sure",        1.0),
        ("ok",          0.9),
        ("okay",        0.9),
        ("go ahead",    1.0),
        ("proceed",     1.0),
        ("do it",       0.9),
        ("start",       0.8),
        ("begin",       0.8),
        ("confirmed",   1.0),
        ("affirmative", 1.0),
        ("correct",     0.8),
        ("right",       0.6),
    ],

    IntentType.DENY: [
        ("no",          1.0),
        ("nah",         1.0),
        ("nope",        1.0),
        ("don't",       0.8),
        ("negative",    1.0),
        ("not now",     0.7),
        ("wrong",       0.6),
        ("incorrect",   0.7),
    ],

    # ── Database-Driven Patient/Doctor/Medication Queries ─────────────────

    IntentType.PATIENT_STATUS_QUERY: [
        ("check patient",           1.0),
        ("patient status",          1.0),
        ("how is patient",          1.0),
        ("how is the patient",      1.0),
        ("what is the status of patient", 1.0),
        ("status of patient",       1.0),
        ("patient condition",       0.9),
        ("condition of patient",    0.9),
        ("update on patient",       0.8),
        ("patient update",          0.8),
        ("patient info",            0.8),
        ("patient information",     0.8),
        ("patient report",          0.7),
        ("check on patient",        0.9),
        ("look up patient",         0.8),
    ],

    IntentType.DOCTOR_QUERY: [
        ("who is treating",         1.0),
        ("who is the doctor",       1.0),
        ("attending doctor",        1.0),
        ("doctor for patient",      1.0),
        ("which doctor",            0.9),
        ("treating doctor",         0.9),
        ("doctor assigned",         0.9),
        ("assigned doctor",         0.9),
        ("who treats",              0.8),
        ("doctor name",             0.8),
    ],

    IntentType.MEDICATION_QUERY: [
        ("what medicine",           1.0),
        ("what medication",         1.0),
        ("prescribed medicine",     1.0),
        ("prescribed medication",   1.0),
        ("prescription for",        1.0),
        ("medicine prescribed",     1.0),
        ("medication for patient",  1.0),
        ("what is prescribed",      0.9),
        ("dosage for patient",      0.8),
        ("treatment plan",          0.7),
        ("current medications",     0.9),
        ("active prescriptions",    0.9),
    ],

    IntentType.PATIENT_EMERGENCY: [
        ("patient needs emergency",       1.0),
        ("patient emergency",             1.0),
        ("emergency code blue for patient", 1.0),
        ("code blue for patient",         1.0),
        ("patient code blue",             1.0),
        ("code blue in patient",          1.0),
        ("emergency in patient",          1.0),
        ("patient needs help",            0.9),
        ("patient needs assistance",      0.9),
        ("patient is critical",           1.0),
        ("patient is unresponsive",       1.0),
        ("patient collapsed",             1.0),
        ("patient not breathing",         1.0),
        ("emergency for patient",         1.0),
        ("emergency assistance patient",  1.0),
        ("code blue patient",             1.0),
        ("patient in distress",           0.9),
    ],

    IntentType.SHOW_ACTIVE_PATIENTS: [
        ("show active patients",          1.0),
        ("show all patients",             1.0),
        ("list patients",                 1.0),
        ("patient list",                  1.0),
        ("active patients",               0.9),
        ("all patients",                  0.8),
        ("show patients",                 0.8),
        ("who is admitted",               0.8),
        ("current patients",              0.8),
        ("admitted patients",             0.8),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Parsed Intent Result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ParsedIntent:
    """Result of intent classification.

    Attributes:
        intent:       The classified intent type.
        confidence:   Confidence score (0.0 – 1.0).
        raw_text:     The original input text.
        matched_triggers: Which trigger phrases matched.
        all_scores:   Scores for all candidate intents (for debugging).
    """
    intent: IntentType = IntentType.UNKNOWN
    confidence: float = 0.0
    raw_text: str = ""
    matched_triggers: List[str] = field(default_factory=list)
    all_scores: Dict[str, float] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """True if the intent is above the confidence threshold."""
        return (
            self.intent != IntentType.UNKNOWN
            and self.confidence >= LANGUAGE_CONFIG.intent.MIN_CONFIDENCE
        )

    def __repr__(self) -> str:
        return (
            f"ParsedIntent({self.intent.name}, "
            f"conf={self.confidence:.2f}, "
            f"triggers={self.matched_triggers[:3]})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Intent Parser
# ─────────────────────────────────────────────────────────────────────────────

class IntentParser:
    """Rule-based intent classification engine.

    Usage::

        parser = IntentParser()
        result = parser.parse("Go to the pharmacy and collect Paracetamol")
        print(result.intent)       # IntentType.DELIVER_MEDICINE
        print(result.confidence)   # 0.78

    The parser is stateless — each ``parse()`` call is independent.
    Thread-safe for concurrent use.
    """

    def __init__(self) -> None:
        self._cfg = LANGUAGE_CONFIG.intent
        self._triggers = _INTENT_TRIGGERS

        # Pre-compile regex patterns for each trigger phrase
        self._compiled: Dict[IntentType, List[Tuple[re.Pattern, float]]] = {}
        for intent, triggers in self._triggers.items():
            self._compiled[intent] = [
                (re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", re.IGNORECASE), weight)
                for phrase, weight in triggers
            ]

        # Statistics
        self.total_parses: int = 0
        self.successful_parses: int = 0

        log.info(
            "IntentParser initialised with %d intent types, %d total triggers.",
            len(self._compiled),
            sum(len(v) for v in self._compiled.values()),
        )

    def parse(self, text: str) -> ParsedIntent:
        """Classify the intent of a natural language command.

        Args:
            text: Raw text from the speech recogniser or text input.

        Returns:
            ParsedIntent with the best-matching intent and confidence.
        """
        self.total_parses += 1

        if not text or not text.strip():
            return ParsedIntent(raw_text=text)

        normalised = text.strip().lower()
        scores: Dict[IntentType, float] = {}
        triggers_matched: Dict[IntentType, List[str]] = {}

        for intent, patterns in self._compiled.items():
            total_weight = 0.0
            matched: List[str] = []
            # Normalise by the strongest single trigger weight for this intent
            # (NOT the sum of all triggers — that dilutes confidence for
            # intents that simply define many phrases).
            max_possible = max(w for _, w in patterns)

            for pattern, weight in patterns:
                if pattern.search(normalised):
                    total_weight += weight
                    matched.append(pattern.pattern)

            if total_weight > 0 and max_possible > 0:
                # Normalised score: fraction of strongest trigger weight matched.
                # Apply a boost for multiple triggers (compound evidence).
                raw_score = total_weight / max_possible
                compound_boost = min(len(matched) * 0.05, 0.25)
                scores[intent] = min(raw_score + compound_boost, 1.0)
                triggers_matched[intent] = matched

        # Select highest-scoring intent; break ties by total matched trigger length
        if not scores:
            return ParsedIntent(
                intent=IntentType.UNKNOWN,
                confidence=0.0,
                raw_text=text,
            )

        best_intent = max(
            scores,
            key=lambda k: (scores[k], sum(len(t) for t in triggers_matched.get(k, []))),
        )
        best_score = scores[best_intent]

        # Build all_scores dict for debugging
        all_scores = {k.name: round(v, 3) for k, v in sorted(
            scores.items(), key=lambda x: x[1], reverse=True
        )}

        result = ParsedIntent(
            intent=best_intent if best_score >= self._cfg.MIN_CONFIDENCE else IntentType.UNKNOWN,
            confidence=round(best_score, 3),
            raw_text=text,
            matched_triggers=triggers_matched.get(best_intent, []),
            all_scores=all_scores,
        )

        if result.is_valid:
            self.successful_parses += 1

        log.info("IntentParser: %s", result)
        return result

    def parse_multi(self, text: str) -> List[ParsedIntent]:
        """Parse text for multiple intents (when enabled).

        Returns a list of all intents above the confidence threshold,
        sorted by confidence (descending).

        Args:
            text: Raw text from the speech recogniser.

        Returns:
            List of ParsedIntents (may be empty).
        """
        primary = self.parse(text)
        if not self._cfg.MULTI_INTENT or not primary.is_valid:
            return [primary] if primary.is_valid else []

        results: List[ParsedIntent] = []
        for intent_name, score in primary.all_scores.items():
            if score >= self._cfg.MIN_CONFIDENCE:
                intent = IntentType[intent_name]
                results.append(ParsedIntent(
                    intent=intent,
                    confidence=score,
                    raw_text=text,
                ))

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

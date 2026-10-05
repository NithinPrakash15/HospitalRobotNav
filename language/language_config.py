"""
HospitalRobotNav — Language Configuration
============================================
All configurable parameters for the NLU pipeline.

Centralises intent patterns, entity dictionaries, medicine formulary,
confidence thresholds, and dialogue parameters.

Design:
    Frozen dataclasses ensure immutability.  The singleton
    ``LANGUAGE_CONFIG`` is used by all language sub-modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Set, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Intent Recognition Parameters
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class IntentConfig:
    """Parameters for intent classification.

    Attributes:
        MIN_CONFIDENCE:   Minimum confidence score to accept an intent.
        FALLBACK_INTENT:  Intent used when no pattern matches.
        MULTI_INTENT:     Allow multiple intents from one utterance.
    """
    MIN_CONFIDENCE: float = 0.20
    FALLBACK_INTENT: str = "UNKNOWN"
    MULTI_INTENT: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Entity Extraction Parameters
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EntityConfig:
    """Parameters for named entity recognition.

    Attributes:
        ROOM_NUMBER_PATTERN:   Regex for room number extraction.
        MEDICINE_FUZZY_MATCH:  Enable fuzzy medicine name matching.
        FUZZY_THRESHOLD:       Max edit distance for fuzzy entity matching.
    """
    ROOM_NUMBER_PATTERN: str = r"(?:room|rm|ward)\s*(?:#|no\.?|number)?\s*(\d{1,4}[a-zA-Z]?)"
    MEDICINE_FUZZY_MATCH: bool = True
    FUZZY_THRESHOLD: int = 2


# ─────────────────────────────────────────────────────────────────────────────
# Medicine Formulary
# ─────────────────────────────────────────────────────────────────────────────

# Common hospital medications with category tags
MEDICINE_FORMULARY: Dict[str, Dict[str, str]] = {
    "paracetamol":      {"category": "analgesic",       "aka": "acetaminophen"},
    "acetaminophen":    {"category": "analgesic",       "aka": "paracetamol"},
    "ibuprofen":        {"category": "nsaid",           "aka": "advil"},
    "aspirin":          {"category": "nsaid",           "aka": "acetylsalicylic acid"},
    "amoxicillin":      {"category": "antibiotic",      "aka": "amoxil"},
    "azithromycin":     {"category": "antibiotic",      "aka": "zithromax"},
    "ciprofloxacin":    {"category": "antibiotic",      "aka": "cipro"},
    "metformin":        {"category": "antidiabetic",    "aka": "glucophage"},
    "insulin":          {"category": "antidiabetic",    "aka": "humulin"},
    "atorvastatin":     {"category": "statin",          "aka": "lipitor"},
    "omeprazole":       {"category": "antacid",         "aka": "prilosec"},
    "pantoprazole":     {"category": "antacid",         "aka": "protonix"},
    "amlodipine":       {"category": "antihypertensive","aka": "norvasc"},
    "lisinopril":       {"category": "antihypertensive","aka": "zestril"},
    "morphine":         {"category": "opioid",          "aka": "ms contin"},
    "tramadol":         {"category": "analgesic",       "aka": "ultram"},
    "diazepam":         {"category": "benzodiazepine",  "aka": "valium"},
    "lorazepam":        {"category": "benzodiazepine",  "aka": "ativan"},
    "epinephrine":      {"category": "emergency",       "aka": "adrenaline"},
    "adrenaline":       {"category": "emergency",       "aka": "epinephrine"},
    "naloxone":         {"category": "emergency",       "aka": "narcan"},
    "dexamethasone":    {"category": "steroid",         "aka": "decadron"},
    "prednisolone":     {"category": "steroid",         "aka": "prelone"},
    "salbutamol":       {"category": "bronchodilator",  "aka": "albuterol"},
    "cetirizine":       {"category": "antihistamine",   "aka": "zyrtec"},
    "saline":           {"category": "iv_fluid",        "aka": "normal saline"},
    "dextrose":         {"category": "iv_fluid",        "aka": "glucose"},
    "heparin":          {"category": "anticoagulant",   "aka": "hep-lock"},
    "warfarin":         {"category": "anticoagulant",   "aka": "coumadin"},
    "ceftriaxone":      {"category": "antibiotic",      "aka": "rocephin"},
}

# Set of all known medicine names (lowercased) for fast lookup
KNOWN_MEDICINES: FrozenSet[str] = frozenset(MEDICINE_FORMULARY.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Priority Keywords
# ─────────────────────────────────────────────────────────────────────────────

PRIORITY_KEYWORDS: Dict[str, int] = {
    # Highest priority (1) → lowest priority (5)
    "critical":     1,
    "code blue":    1,
    "code red":     1,
    "emergency":    1,
    "stat":         1,
    "life threat":  1,
    "urgent":       2,
    "asap":         2,
    "immediately":  2,
    "right away":   2,
    "high":         2,
    "important":    3,
    "soon":         3,
    "normal":       4,
    "routine":      4,
    "standard":     4,
    "low":          5,
    "whenever":     5,
    "no rush":      5,
    "when free":    5,
}


# ─────────────────────────────────────────────────────────────────────────────
# Dialogue Parameters
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DialogueConfig:
    """Multi-turn dialogue management parameters.

    Attributes:
        CONFIRMATION_REQUIRED: Require user confirmation before executing.
        CLARIFICATION_MAX:     Max clarification rounds before giving up.
        SESSION_TIMEOUT_SEC:   Seconds of inactivity before session resets.
        AFFIRMATIVE_WORDS:     Words the user can say to confirm.
        NEGATIVE_WORDS:        Words the user can say to cancel.
    """
    CONFIRMATION_REQUIRED: bool = True
    CLARIFICATION_MAX: int = 3
    SESSION_TIMEOUT_SEC: float = 30.0

    AFFIRMATIVE_WORDS: Tuple[str, ...] = (
        "yes", "yeah", "yep", "yup", "sure", "ok", "okay",
        "go ahead", "proceed", "do it", "start", "begin",
        "confirmed", "affirmative", "correct", "right",
    )

    NEGATIVE_WORDS: Tuple[str, ...] = (
        "no", "nah", "nope", "cancel", "stop", "abort",
        "never mind", "forget it", "don't", "negative",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Aggregated Configuration Singleton
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LanguageConfig:
    """Top-level language/NLU configuration.

    Usage:
        from language.language_config import LANGUAGE_CONFIG
        threshold = LANGUAGE_CONFIG.intent.MIN_CONFIDENCE
    """
    intent: IntentConfig = field(default_factory=IntentConfig)
    entity: EntityConfig = field(default_factory=EntityConfig)
    dialogue: DialogueConfig = field(default_factory=DialogueConfig)


# Global singleton
LANGUAGE_CONFIG = LanguageConfig()

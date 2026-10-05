"""
HospitalRobotNav — Language Understanding Module
===================================================
Natural Language Understanding (NLU) pipeline for parsing spoken commands
into structured mission requests.

Submodules:
    language_config:    NLU parameters, intent patterns, entity dictionaries.
    intent_parser:      Rule-based intent classification with confidence scoring.
    entity_extractor:   Named entity recognition for locations, medicines, people.
    dialogue_manager:   Multi-turn conversation state machine.
    dialogue_templates: Response template database (50+ contextual responses).
    command_resolver:   Bridges NLU output to Mission system input.

Pipeline:
    SpeechRecognizer.text ──► IntentParser ──► EntityExtractor
                                    │                 │
                                    ▼                 ▼
                              ParsedIntent    ExtractedEntities
                                    │                 │
                                    └────── ┬ ────────┘
                                            ▼
                                     CommandResolver
                                            │
                                            ▼
                                      MissionRequest
                                            │
                                   DialogueManager
                                            │
                                    (confirm / execute)

ROS2 Deployment Note:
    In a deployed system, the intent parser and entity extractor would be
    replaced by an LLM-based NLU node subscribing to /transcript and
    publishing /mission_request (custom msg).
"""

from language.language_config import LanguageConfig, LANGUAGE_CONFIG
from language.intent_parser import IntentParser, IntentType, ParsedIntent
from language.entity_extractor import EntityExtractor, ExtractedEntities
from language.dialogue_manager import DialogueManager, DialogueState
from language.dialogue_templates import DialogueTemplates
from language.command_resolver import CommandResolver
from language.vision_language_reasoner import (
    VisionLanguageReasoner,
    SpatialReasoningResult,
    SpatialRelationType,
)

__all__ = [
    "LanguageConfig",
    "LANGUAGE_CONFIG",
    "IntentParser",
    "IntentType",
    "ParsedIntent",
    "EntityExtractor",
    "ExtractedEntities",
    "DialogueManager",
    "DialogueState",
    "DialogueTemplates",
    "CommandResolver",
    "VisionLanguageReasoner",
    "SpatialReasoningResult",
    "SpatialRelationType",
]


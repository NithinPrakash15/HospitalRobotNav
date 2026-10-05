# NLU Pipeline — Natural Language Understanding

## Overview

The NLU pipeline converts transcribed speech into structured intent + entity tuples
used to generate `MissionRequest` objects for the mission planning system.

```
Raw transcript
    ↓
IntentParser          (classify command intent)
    ↓
EntityExtractor       (extract room, medicine, person, priority)
    ↓
CommandResolver       (validate + resolve to MissionRequest)
    ↓
DialogueManager       (manage multi-turn conversation state)
    ↓
MissionPlanner        (decompose to TaskStep sequence)
```

---

## Intent Classification (`language/intent_parser.py`)

### Supported Intents

| Intent | Example Utterance |
|---|---|
| `DELIVER_MEDICINE` | "Deliver Paracetamol to Room 205" |
| `GUIDE_PATIENT` | "Guide patient to Radiology" |
| `CALL_NURSE` | "Call nurse to ward B" |
| `EMERGENCY` | "Code blue in ICU" |
| `DELIVER_REPORT` | "Deliver lab results to Dr Smith" |
| `TRANSPORT_SAMPLE` | "Transport blood sample to laboratory" |
| `FETCH_WHEELCHAIR` | "Bring wheelchair to Ward 3" |
| `ESCORT_VISITOR` | "Escort visitor to Room 101" |
| `NAVIGATE` | "Go to pharmacy" |
| `STATUS_QUERY` | "What is your battery level?" |
| `CANCEL` | "Cancel mission" |
| `CONFIRM` | "Yes, confirm" |
| `DENY` | "No, stop" |
| `UNKNOWN` | (fallback) |

### Confidence Scoring

Scores are computed as a weighted trigger-match fraction with a compound boost:

```
raw_score = Σ(matched_weight) / Σ(all_weights)
score     = min(raw_score + len(matches) × 0.05, 1.0)
```

Classification only accepted when `score ≥ MIN_CONFIDENCE (0.20)`.

---

## Entity Extraction (`language/entity_extractor.py`)

Extracts structured fields from the utterance:

| Field | Example | Notes |
|---|---|---|
| `locations` | `["Room 205", "ICU"]` | Room names, departments |
| `medicines` | `["paracetamol"]` | 30-item hospital formulary |
| `persons` | `["Dr Smith"]` | Doctor, nurse, patient references |
| `priority` | `2` | 1=critical … 5=low |
| `priority_label` | `"urgent"` | Human-readable |
| `quantity_num` | `2` | Numeric quantity |
| `room_number` | `"205"` | Extracted room number |

---

## Dialogue Manager (`language/dialogue_manager.py`)

### State Machine

```
IDLE ──(wake word)──▶ GREETING
                          │
              (auto, 1 s after greeting)
                          │
                          ▼
                     LISTENING ──(speech)──▶ UNDERSTANDING
                                                  │
                                        (NLU parse success)
                                                  │
                                                  ▼
                                           CONFIRMING ──(yes)──▶ EXECUTING
                                               │                     │
                                           (no/cancel)          (done)
                                               │                     │
                                               ▼                     ▼
                                             IDLE              REPORTING ──▶ IDLE
```

### Clarification Loop

When a required entity is missing, the manager enters `CLARIFYING` and asks a
targeted follow-up question:

```python
dm.on_user_input("Deliver medicine")
# Robot: "Which medicine should I deliver?"
dm.on_user_input("Paracetamol")
# Robot: "Which room should I deliver Paracetamol to?"
dm.on_user_input("Room 205")
# Robot: "Deliver Paracetamol to Room 205. Shall I begin?"
```

---

## Dialogue Templates (`language/dialogue_templates.py`)

All robot responses are loaded from templates with slot filling:

```python
templates["greet"]           = ["Hello! I'm ready to help.", "How can I assist you?"]
templates["confirm_delivery"] = ["Deliver {medicine} to {room}. Shall I begin?"]
templates["mission_started"]  = ["Mission started. I'm on my way to {destination}."]
```

---

## Command Resolver (`language/command_resolver.py`)

Validates and resolves NLU output into a `MissionRequest`:

1. Maps intent → `MissionType`
2. Resolves room names using `SemanticMap`
3. Sets default pickup location (pharmacy for medicine missions)
4. Validates required fields (raises `CommandResolverError` if critical data missing)

---

## LLM Provider Interface (`ai_interfaces/llm_interface.py`)

Abstraction layer for plugging in an LLM instead of rule-based NLU:

| Provider | Notes |
|---|---|
| `RuleBasedProvider` | Default — no API key, works offline |
| `OpenAIProvider` | GPT-4, requires `OPENAI_API_KEY` |
| `GeminiProvider` | Gemini Pro, requires `GOOGLE_API_KEY` |
| `LocalLLMProvider` | Ollama/LLaMA, requires local server |

```python
from ai_interfaces.llm_interface import get_llm_provider
provider = get_llm_provider("gemini")
result = provider.parse_instruction("Deliver Paracetamol to Room 205")
# result.intent == "DELIVER_MEDICINE"
# result.entities["medicine"] == "Paracetamol"
```

---

## ROS2 Migration Path

| Module | ROS2 Node | Topics |
|---|---|---|
| `IntentParser` | `intent_node` | `/speech/transcript` → `/nlu/intent` |
| `EntityExtractor` | `nlu_node` | `/nlu/intent` → `/nlu/entities` |
| `DialogueManager` | `dialogue_node` | `/nlu/entities` → `/robot/speak`, `/mission/request` |
| `CommandResolver` | (embedded in dialogue_node) | `/mission/request` |

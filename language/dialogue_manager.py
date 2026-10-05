"""
HospitalRobotNav — Dialogue Manager
======================================
Multi-turn conversational state machine for the hospital assistant robot.

Manages the full lifecycle of a human-robot interaction:
    1. Robot hears wake word → greets the user.
    2. User speaks a command → NLU parses intent + entities.
    3. Robot confirms the parsed task → asks for user approval.
    4. User confirms → mission begins.
    5. Robot reports progress → announces completion.

State Machine::

    IDLE ──(wake word)──► GREETING
                              │
                    (auto, after greeting)
                              │
                              ▼
                         LISTENING ──(speech)──► UNDERSTANDING
                                                      │
                                            (NLU parse success)
                                                      │
                                                      ▼
                                               CONFIRMING ──(yes)──► EXECUTING
                                                   │                     │
                                               (no / cancel)      (mission done)
                                                   │                     │
                                                   ▼                     ▼
                                                 IDLE              REPORTING ──► IDLE
                                                                        │
                                                                  (ask if more)

Clarification Loop:
    If the NLU cannot fully parse the command (missing location, medicine,
    etc.), the dialogue manager enters a CLARIFYING state and asks the
    user targeted questions before returning to CONFIRMING.

ROS2 Deployment Note:
    Maps to a dialogue management node subscribing to /parsed_intent
    and /user_response, publishing /robot_say and /mission_request.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

from language.intent_parser import IntentParser, IntentType, ParsedIntent
from language.entity_extractor import EntityExtractor, ExtractedEntities
from language.dialogue_templates import DialogueTemplates
from language.language_config import LANGUAGE_CONFIG
from utilities.logger import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Dialogue States
# ─────────────────────────────────────────────────────────────────────────────

class DialogueState(Enum):
    """Conversational state machine states."""
    IDLE          = auto()  # No active conversation
    GREETING      = auto()  # Robot just greeted the user
    LISTENING     = auto()  # Waiting for user command
    UNDERSTANDING = auto()  # Processing NLU
    CONFIRMING    = auto()  # Awaiting user confirmation
    CLARIFYING    = auto()  # Asking for missing information
    EXECUTING     = auto()  # Mission is executing
    REPORTING     = auto()  # Reporting mission result
    ERROR         = auto()  # Error in dialogue


# ─────────────────────────────────────────────────────────────────────────────
# Dialogue Context
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DialogueContext:
    """Session context for a single conversation.

    Tracks the current intent, entities, clarification rounds,
    and the generated task summary for confirmation.
    """
    session_id: int = 0
    intent: Optional[ParsedIntent] = None
    entities: Optional[ExtractedEntities] = None
    task_summary: str = ""
    clarification_count: int = 0
    missing_fields: List[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = time.monotonic()

    @property
    def age_seconds(self) -> float:
        """Seconds since session started."""
        return time.monotonic() - self.started_at

    @property
    def idle_seconds(self) -> float:
        """Seconds since last activity."""
        return time.monotonic() - self.last_activity


# ─────────────────────────────────────────────────────────────────────────────
# Dialogue Turn
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DialogueTurn:
    """A single turn in the conversation (robot or user).

    Attributes:
        speaker:    "robot" or "user".
        text:       The spoken/typed text.
        state:      Dialogue state at time of this turn.
        timestamp:  Wall-clock time.
    """
    speaker: str
    text: str
    state: DialogueState
    timestamp: float = field(default_factory=time.monotonic)

    def __repr__(self) -> str:
        return f"[{self.speaker.upper()}] {self.text[:60]}"


# ─────────────────────────────────────────────────────────────────────────────
# Dialogue Manager
# ─────────────────────────────────────────────────────────────────────────────

class DialogueManager:
    """Multi-turn conversation controller for the hospital robot.

    Usage::

        dm = DialogueManager()

        # Wake word detected:
        greeting = dm.on_wake_word()

        # User speaks a command:
        response = dm.on_user_input("Go to pharmacy and collect Paracetamol for Room 205")
        # → "I understood your request. Collect Paracetamol from Pharmacy,
        #    deliver to Room 205. Would you like me to begin?"

        # User confirms:
        response = dm.on_user_input("Yes")
        # → "Mission started. I'm on my way."

    Callbacks:
        Set ``on_mission_request`` to receive structured mission data when
        the user confirms a task.  Set ``on_robot_speak`` to handle TTS output.
    """

    def __init__(self, semantic_map: Optional[Any] = None) -> None:
        self.semantic_map = semantic_map
        self._cfg = LANGUAGE_CONFIG.dialogue
        self._intent_parser = IntentParser()
        self._entity_extractor = EntityExtractor()
        self._templates = DialogueTemplates()

        # State
        self.state: DialogueState = DialogueState.IDLE
        self._context: Optional[DialogueContext] = None
        self._session_counter: int = 0

        # Conversation history
        self._history: List[DialogueTurn] = []
        self._history_max = 100

        # Callbacks
        self.on_mission_request: Optional[Callable[[ParsedIntent, ExtractedEntities], None]] = None
        self.on_robot_speak: Optional[Callable[[str], None]] = None

        # Statistics
        self.total_sessions: int = 0
        self.completed_missions: int = 0

        log.info("DialogueManager initialised.")

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def on_wake_word(self) -> str:
        """Handle wake word detection — start a new conversation.

        Returns:
            Greeting text to speak/display.
        """
        self._start_session()
        greeting = self._templates.greeting()
        self.state = DialogueState.LISTENING
        self._record_turn("robot", greeting)

        log.info("DialogueManager: Session #%d started (wake word).", self._session_counter)
        self._emit_speech(greeting)
        return greeting

    def on_user_input(self, text: str) -> str:
        """Process user input and return the robot's response.

        This is the main entry point called after speech recognition
        produces a final result, or when the user types a command.

        Args:
            text: User's spoken/typed text.

        Returns:
            Robot's response text.
        """
        if not text or not text.strip():
            return ""

        self._record_turn("user", text)

        # Handle session timeout
        if self._context and self._context.idle_seconds > self._cfg.SESSION_TIMEOUT_SEC:
            log.info("DialogueManager: Session timed out.")
            self._end_session()

        # If no active session, auto-start one
        if self.state == DialogueState.IDLE:
            self._start_session()
            self.state = DialogueState.LISTENING

        # Route based on current state
        if self.state == DialogueState.LISTENING:
            return self._handle_command(text)
        elif self.state == DialogueState.CONFIRMING:
            return self._handle_confirmation(text)
        elif self.state == DialogueState.CLARIFYING:
            return self._handle_clarification(text)
        elif self.state == DialogueState.EXECUTING:
            return self._handle_during_execution(text)
        else:
            return self._handle_command(text)

    def on_mission_complete(self, summary: str) -> str:
        """Handle mission completion — report to the user.

        Args:
            summary: What was accomplished.

        Returns:
            Completion announcement text.
        """
        self.completed_missions += 1
        self.state = DialogueState.REPORTING

        completion = self._templates.mission_complete(summary)
        farewell = self._templates.farewell()
        response = f"{completion} {farewell}"

        self._record_turn("robot", response)
        self._emit_speech(response)

        self._end_session()
        return response

    def on_mission_error(self, error: str) -> str:
        """Handle mission failure — report error to the user.

        Args:
            error: Error description.

        Returns:
            Error message text.
        """
        self.state = DialogueState.ERROR

        response = self._templates.error(error)
        self._record_turn("robot", response)
        self._emit_speech(response)

        self._end_session()
        return response

    def on_progress_update(self, destination: str, eta: str) -> str:
        """Generate and emit a progress update.

        Args:
            destination: Current navigation target.
            eta: Estimated time of arrival.

        Returns:
            Progress update text.
        """
        response = self._templates.navigation_progress(destination, eta)
        self._record_turn("robot", response)
        self._emit_speech(response)
        return response

    def get_state_display(self) -> str:
        """Get a human-readable state string for the dashboard."""
        return self.state.name.replace("_", " ").title()

    @property
    def current_context(self) -> Optional[DialogueContext]:
        """Access the current dialogue context (read-only)."""
        return self._context

    @property
    def history(self) -> List[DialogueTurn]:
        """Conversation history (read-only)."""
        return list(self._history)

    @property
    def recent_history(self) -> List[DialogueTurn]:
        """Last 10 dialogue turns."""
        return list(self._history[-10:])

    def reset(self) -> None:
        """Reset the dialogue manager to IDLE state."""
        self._end_session()
        log.info("DialogueManager reset.")

    # ─────────────────────────────────────────────────────────────────────────
    # State Handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _handle_command(self, text: str) -> str:
        """Parse a new command from the user.

        Runs the NLU pipeline (intent + entity extraction), then either
        confirms the task or requests clarification.
        """
        self.state = DialogueState.UNDERSTANDING

        # Run NLU
        intent = self._intent_parser.parse(text)
        entities = self._entity_extractor.extract(text)

        if self._context:
            self._context.intent = intent
            self._context.entities = entities
            self._context.touch()

        # Handle special intents
        if intent.intent == IntentType.CANCEL:
            response = self._templates.cancelled()
            self._record_turn("robot", response)
            self._emit_speech(response)
            self._end_session()
            return response

        if intent.intent == IntentType.STATUS_QUERY:
            response = self._templates.status_report(
                state="standing by",
                battery=85,
                extra="No active mission.",
            )
            self._record_turn("robot", response)
            self._emit_speech(response)
            return response

        if not intent.is_valid:
            response = self._templates.clarification_general()
            self.state = DialogueState.LISTENING
            self._record_turn("robot", response)
            self._emit_speech(response)
            return response

        # Check for missing required entities
        missing = self._check_missing_entities(intent, entities)

        if missing:
            return self._request_clarification(missing)

        # Build task summary and confirm
        summary = self._build_task_summary(intent, entities)
        if self._context:
            self._context.task_summary = summary

        if self._cfg.CONFIRMATION_REQUIRED:
            self.state = DialogueState.CONFIRMING
            response = self._templates.confirmation(task_summary=summary)
        else:
            # No confirmation needed — execute directly
            response = self._execute_mission(intent, entities)

        self._record_turn("robot", response)
        self._emit_speech(response)
        return response

    def _handle_confirmation(self, text: str) -> str:
        """Handle user's confirmation or denial response."""
        normalised = text.strip().lower()

        # Check affirmative
        for word in self._cfg.AFFIRMATIVE_WORDS:
            if word in normalised:
                if self._context and self._context.intent and self._context.entities:
                    return self._execute_mission(
                        self._context.intent,
                        self._context.entities,
                    )
                break

        # Check negative
        for word in self._cfg.NEGATIVE_WORDS:
            if word in normalised:
                response = self._templates.cancelled()
                self._record_turn("robot", response)
                self._emit_speech(response)
                self._end_session()
                return response

        # Ambiguous response — ask again
        response = "I didn't catch that. Please say 'yes' to proceed or 'no' to cancel."
        self._record_turn("robot", response)
        self._emit_speech(response)
        return response

    def _handle_clarification(self, text: str) -> str:
        """Handle user's response to a clarification request.

        Re-runs entity extraction on the new input and checks if the
        missing fields have been resolved.
        """
        if not self._context:
            return self._handle_command(text)

        self._context.clarification_count += 1
        self._context.touch()

        # Too many clarification rounds
        if self._context.clarification_count > self._cfg.CLARIFICATION_MAX:
            response = self._templates.error(
                "I'm having trouble understanding. Let's start over."
            )
            self._record_turn("robot", response)
            self._emit_speech(response)
            self._end_session()
            return response

        # Re-extract entities from the new input
        new_entities = self._entity_extractor.extract(text)

        # Merge new entities into existing context
        if self._context.entities:
            if new_entities.has_location and not self._context.entities.has_location:
                self._context.entities.locations = new_entities.locations
            if new_entities.has_medicine and not self._context.entities.has_medicine:
                self._context.entities.medicines = new_entities.medicines
            if new_entities.room_number and not self._context.entities.room_number:
                self._context.entities.room_number = new_entities.room_number
        else:
            self._context.entities = new_entities

        # Check if missing fields are now resolved
        remaining = self._check_missing_entities(
            self._context.intent, self._context.entities  # type: ignore
        )

        if remaining:
            return self._request_clarification(remaining)

        # All resolved — confirm
        summary = self._build_task_summary(
            self._context.intent, self._context.entities  # type: ignore
        )
        self._context.task_summary = summary
        self.state = DialogueState.CONFIRMING

        response = self._templates.confirmation(task_summary=summary)
        self._record_turn("robot", response)
        self._emit_speech(response)
        return response

    def _handle_during_execution(self, text: str) -> str:
        """Handle user input while a mission is executing."""
        intent = self._intent_parser.parse(text)

        if intent.intent == IntentType.CANCEL:
            response = self._templates.cancelled()
            self._record_turn("robot", response)
            self._emit_speech(response)
            self._end_session()
            return response

        if intent.intent == IntentType.STATUS_QUERY:
            response = self._templates.status_report(
                state="executing mission",
                battery=75,
                extra=self._context.task_summary if self._context else "",
            )
            self._record_turn("robot", response)
            self._emit_speech(response)
            return response

        response = "I'm currently busy with a task. Say 'cancel' to stop, or wait for completion."
        self._record_turn("robot", response)
        self._emit_speech(response)
        return response

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _execute_mission(self, intent: ParsedIntent, entities: ExtractedEntities) -> str:
        """Trigger mission execution via callback.

        Args:
            intent: Parsed intent.
            entities: Extracted entities.

        Returns:
            Mission started announcement.
        """
        self.state = DialogueState.EXECUTING

        if self.on_mission_request is not None:
            try:
                self.on_mission_request(intent, entities)
            except Exception as exc:
                log.error("DialogueManager: Mission callback error — %s", exc)

        response = self._templates.mission_started()
        self._record_turn("robot", response)
        self._emit_speech(response)
        return response

    def _request_clarification(self, missing: List[str]) -> str:
        """Ask the user for missing information.

        Args:
            missing: List of missing entity field names.

        Returns:
            Clarification request text.
        """
        self.state = DialogueState.CLARIFYING

        if self._context:
            self._context.missing_fields = missing

        if "location" in missing:
            response = self._templates.clarification_location()
        elif "medicine" in missing:
            response = self._templates.clarification_medicine()
        else:
            response = self._templates.clarification_general()

        self._record_turn("robot", response)
        self._emit_speech(response)
        return response

    def _check_missing_entities(
        self,
        intent: Optional[ParsedIntent],
        entities: Optional[ExtractedEntities],
    ) -> List[str]:
        """Check which required entities are missing for the given intent.

        Returns:
            List of missing field names (empty if all present).
        """
        if intent is None or entities is None:
            return ["intent"]

        missing: List[str] = []

        # Intent-specific required fields
        if intent.intent in (
            IntentType.DELIVER_MEDICINE,
        ):
            if not entities.has_medicine:
                missing.append("medicine")
            if not entities.has_location and not entities.room_number:
                missing.append("location")

        elif intent.intent in (
            IntentType.GUIDE_PATIENT,
            IntentType.ESCORT_VISITOR,
        ):
            if not entities.has_location:
                missing.append("location")

        elif intent.intent in (
            IntentType.NAVIGATE,
        ):
            if not entities.has_location and not entities.room_number:
                missing.append("location")

        elif intent.intent in (
            IntentType.DELIVER_REPORT,
            IntentType.TRANSPORT_SAMPLE,
        ):
            if not entities.has_location:
                missing.append("location")

        return missing

    def _build_task_summary(
        self,
        intent: Optional[ParsedIntent],
        entities: Optional[ExtractedEntities],
    ) -> str:
        """Build a human-readable task summary for confirmation.

        Args:
            intent: Parsed intent.
            entities: Extracted entities.

        Returns:
            Summary string.
        """
        if intent is None or entities is None:
            return "Unknown task"

        parts: List[str] = []
        dest = entities.primary_location or f"Room {entities.room_number}" if entities.room_number else "unspecified"

        if intent.intent == IntentType.DELIVER_MEDICINE:
            med = entities.primary_medicine or "medication"
            qty = entities.quantity if entities.quantity else ""
            parts.append(f"Collect {qty} {med} from Pharmacy".strip())
            parts.append(f"Deliver to {dest}")

        elif intent.intent == IntentType.GUIDE_PATIENT:
            parts.append(f"Guide patient to {dest}")

        elif intent.intent == IntentType.CALL_NURSE:
            loc = dest if entities.has_location else "current location"
            parts.append(f"Call nurse to {loc}")

        elif intent.intent == IntentType.EMERGENCY:
            parts.append(f"Emergency response to {dest}")

        elif intent.intent == IntentType.DELIVER_REPORT:
            parts.append(f"Collect report from Laboratory")
            parts.append(f"Deliver to {dest}")

        elif intent.intent == IntentType.TRANSPORT_SAMPLE:
            parts.append(f"Collect sample")
            parts.append(f"Transport to Laboratory")

        elif intent.intent == IntentType.FETCH_WHEELCHAIR:
            parts.append(f"Fetch wheelchair from Storage")
            parts.append(f"Deliver to {dest}")

        elif intent.intent == IntentType.ESCORT_VISITOR:
            parts.append(f"Escort visitor to {dest}")

        elif intent.intent == IntentType.NAVIGATE:
            parts.append(f"Navigate to {dest}")

        else:
            parts.append(f"Perform {intent.intent.name.replace('_', ' ').lower()}")

        if entities.priority <= 2:
            parts.append(f"Priority: {entities.priority_label.upper()}")

        return "\n• ".join([""] + parts) if len(parts) > 1 else parts[0] if parts else "Unknown task"

    def _start_session(self) -> None:
        """Begin a new dialogue session."""
        self._session_counter += 1
        self.total_sessions += 1
        self._context = DialogueContext(session_id=self._session_counter)
        self.state = DialogueState.GREETING

    def _end_session(self) -> None:
        """End the current dialogue session."""
        self._context = None
        self.state = DialogueState.IDLE

    def _record_turn(self, speaker: str, text: str) -> None:
        """Record a dialogue turn in history."""
        turn = DialogueTurn(speaker=speaker, text=text, state=self.state)
        self._history.append(turn)
        if len(self._history) > self._history_max:
            self._history.pop(0)

    def _emit_speech(self, text: str) -> None:
        """Send text to the TTS callback if registered."""
        if self.on_robot_speak is not None:
            try:
                self.on_robot_speak(text)
            except Exception as exc:
                log.debug("DialogueManager: Speech callback error — %s", exc)

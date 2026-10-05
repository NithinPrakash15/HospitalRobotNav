"""
HospitalRobotNav — Language & Interaction Agent
===================================================
Specialised agent responsible for conversational natural language understanding,
entity verification, user clarification loops, and mission request generation.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from agents.agent_base import HospitalAgent, AgentState, AgentBid
from agents.agent_messages import AgentMessage, MessageType
from agents.message_bus import MESSAGE_BUS
from language.intent_parser import IntentParser, IntentType
from language.entity_extractor import EntityExtractor
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]


class LanguageAgent(HospitalAgent):
    """
    Language & Interaction Agent.
    
    Processes human commands from audio/text transcripts, validates mandatory task fields,
    triggers interactive clarification loops if critical entities are missing, and synthesizes
    structured MISSION_REQUEST envelopes sent directly to the coordinator.
    """

    def __init__(self, home_position: GridPos = (0, 0)) -> None:
        super().__init__(
            agent_type="language",
            capabilities=frozenset({
                "speech",
                "interact"
            }),
            home_position=home_position,
        )
        self._intent_parser = IntentParser()
        self._entity_extractor = EntityExtractor()
        self._pending_clarifications: Dict[str, Dict[str, Any]] = {}

        # Register on message bus
        MESSAGE_BUS.register_agent(self.agent_id)
        
        # Subscribe to speech transcripts and clarification responses
        MESSAGE_BUS.subscribe(self.agent_id, MessageType.SPEECH_TRANSCRIPT_READY, self.handle_transcript)
        MESSAGE_BUS.subscribe(self.agent_id, MessageType.CLARIFICATION_RESPONSE, self.handle_clarification_response)

        log.info("LanguageAgent %s initialized and subscribed.", self.agent_id)

    def evaluate_mission(
        self,
        mission_type: str,
        destination: Optional[GridPos],
        priority: int,
    ) -> Optional[AgentBid]:
        """Software-only agent. Bids 0.0 or declines physical missions."""
        return None

    def accept_mission(self, mission_id: str, mission_data: Dict[str, Any]) -> bool:
        return False

    def abort_mission(self, reason: str = "") -> None:
        pass

    def handle_transcript(self, message: AgentMessage) -> None:
        """Process new user input from speech/keyboard transcripts."""
        text = message.payload.get("text", "")
        if not text:
            return
        log.info("LanguageAgent '%s' processing utterance: '%s'", self.agent_id, text)
        self.process_command(text, message.sender)

    def handle_clarification_response(self, message: AgentMessage) -> None:
        """Merge clarification answer with original context and retry task resolution."""
        reply_to = message.in_reply_to
        response_text = message.payload.get("text", "")
        if not reply_to or reply_to not in self._pending_clarifications:
            log.warning("LanguageAgent received clarification response for unknown request ID: %s", reply_to)
            return

        ctx = self._pending_clarifications.pop(reply_to)
        original_text = ctx["original_text"]
        missing_field = ctx["missing_field"]
        entities = ctx["entities"]
        intent = ctx["intent"]
        sender = ctx["sender"]

        log.info("LanguageAgent clarification received for field '%s': '%s'", missing_field, response_text)

        # Inject missing details back into the entities payload
        if missing_field == "location":
            entities.locations = [response_text]
        elif missing_field == "medicine":
            entities.medicines = [response_text]
        elif missing_field == "room_number":
            entities.room_number = response_text
            entities.locations = [f"Room {response_text}"]

        # Re-attempt validation and routing
        self.resolve_and_dispatch(intent, entities, f"{original_text} [clarified: {response_text}]", sender)

    def process_command(self, text: str, sender: str) -> None:
        """Core NLP parsing, entity validation and clarification trigger loop."""
        intent_res = self._intent_parser.parse(text)
        entities_res = self._entity_extractor.extract(text)

        intent_type = intent_res.intent

        # 1. Unrecognized intent clarification
        if intent_type == IntentType.UNKNOWN or not intent_res.is_valid:
            self.send_clarification_request(
                "I'm sorry, I didn't catch that command. Could you please specify if you want medicine delivery or patient guidance?",
                text, "intent", intent_res, entities_res, sender
            )
            return

        # 2. Command-specific validation checks
        if intent_type == IntentType.DELIVER_MEDICINE:
            if not entities_res.medicines:
                self.send_clarification_request(
                    "Which medicine should I deliver?",
                    text, "medicine", intent_res, entities_res, sender
                )
                return
            if not entities_res.locations and not entities_res.room_number:
                self.send_clarification_request(
                    "Where or to which room should I deliver the medicine?",
                    text, "location", intent_res, entities_res, sender
                )
                return

        elif intent_type in (IntentType.GUIDE_PATIENT, IntentType.NAVIGATE, IntentType.ESCORT_VISITOR):
            if not entities_res.locations and not entities_res.room_number:
                self.send_clarification_request(
                    "Which location or room number should I navigate to?",
                    text, "location", intent_res, entities_res, sender
                )
                return

        # 3. Validation passed: build and dispatch MissionRequest
        self.resolve_and_dispatch(intent_res, entities_res, text, sender)

    def send_clarification_request(
        self, question: str, original_text: str, missing_field: str,
        intent: Any, entities: Any, sender: str
    ) -> None:
        """Emit a CLARIFICATION_NEEDED packet and store conversation context."""
        msg = AgentMessage(
            msg_type=MessageType.CLARIFICATION_NEEDED,
            sender=self.agent_id,
            receiver=sender,
            payload={
                "question": question,
                "missing_field": missing_field,
                "original_text": original_text
            }
        )
        self._pending_clarifications[msg.msg_id] = {
            "original_text": original_text,
            "missing_field": missing_field,
            "entities": entities,
            "intent": intent,
            "sender": sender
        }
        MESSAGE_BUS.send(msg)
        log.info("LanguageAgent sent clarification request for '%s': %s", missing_field, question)

    def resolve_and_dispatch(self, intent: Any, entities: Any, raw_text: str, sender: str) -> None:
        """Map parsed intent elements to structured MissionRequest payload and broadcast."""
        from language.command_resolver import _INTENT_TO_MISSION
        mission_enum = _INTENT_TO_MISSION.get(intent.intent)
        
        mission_name = mission_enum.name if mission_enum else "NAVIGATE"
        
        # Package validated details
        payload = {
            "mission_id": f"MSN-{uuid.uuid4().hex[:6].upper()}",
            "mission_type": mission_name,
            "raw_text": raw_text,
            "priority": entities.priority,
            "priority_label": entities.priority_label,
            "item": entities.primary_medicine,
            "quantity": entities.quantity,
            "quantity_num": entities.quantity_num,
            "time_ref": entities.time_ref,
            "room_number": entities.room_number,
            "locations": entities.locations,
        }

        # Dispatch structured request to coordinator
        req_msg = AgentMessage(
            msg_type=MessageType.MISSION_REQUEST,
            sender=self.agent_id,
            receiver="coordinator",
            payload=payload
        )
        MESSAGE_BUS.send(req_msg)
        log.info("LanguageAgent dispatched MISSION_REQUEST: %s (Type: %s)", payload["mission_id"], mission_name)

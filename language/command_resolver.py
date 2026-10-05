"""
HospitalRobotNav — Command Resolver
======================================
Bridges the NLU output (ParsedIntent + ExtractedEntities) to the Mission
system input (MissionRequest).

Responsibilities:
    1. Convert intent type → mission type mapping.
    2. Resolve location names to grid coordinates via SemanticQueryEngine.
    3. Validate mission feasibility (destination exists, medicine in stock).
    4. Build a structured MissionRequest ready for the MissionPlanner.

This module is the coupling point between the Language Understanding
layer and the Mission Execution layer.

ROS2 Deployment Note:
    In production, this would be a service node:
        Service: /resolve_command
        Request: ParsedIntent + ExtractedEntities
        Response: MissionRequest
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from language.intent_parser import IntentType, ParsedIntent
from language.entity_extractor import ExtractedEntities
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]


# ─────────────────────────────────────────────────────────────────────────────
# Mission Request (output of this module)
# ─────────────────────────────────────────────────────────────────────────────

class MissionType(Enum):
    """High-level mission type categories."""
    MEDICINE_DELIVERY   = auto()
    GUIDE_PATIENT       = auto()
    CALL_NURSE          = auto()
    EMERGENCY_RESPONSE  = auto()
    DELIVER_REPORT      = auto()
    TRANSPORT_SAMPLE    = auto()
    FETCH_WHEELCHAIR    = auto()
    ESCORT_VISITOR      = auto()
    NAVIGATE            = auto()
    RETURN_TO_DOCK      = auto()
    PATIENT_STATUS_QUERY = auto()
    DOCTOR_QUERY        = auto()
    MEDICATION_QUERY    = auto()
    PATIENT_EMERGENCY   = auto()
    SHOW_ACTIVE_PATIENTS = auto()


# Intent → Mission mapping
_INTENT_TO_MISSION: Dict[IntentType, MissionType] = {
    IntentType.DELIVER_MEDICINE:     MissionType.MEDICINE_DELIVERY,
    IntentType.GUIDE_PATIENT:        MissionType.GUIDE_PATIENT,
    IntentType.CALL_NURSE:           MissionType.CALL_NURSE,
    IntentType.EMERGENCY:            MissionType.EMERGENCY_RESPONSE,
    IntentType.DELIVER_REPORT:       MissionType.DELIVER_REPORT,
    IntentType.TRANSPORT_SAMPLE:     MissionType.TRANSPORT_SAMPLE,
    IntentType.FETCH_WHEELCHAIR:     MissionType.FETCH_WHEELCHAIR,
    IntentType.ESCORT_VISITOR:       MissionType.ESCORT_VISITOR,
    IntentType.NAVIGATE:             MissionType.NAVIGATE,
    IntentType.PATIENT_STATUS_QUERY: MissionType.PATIENT_STATUS_QUERY,
    IntentType.DOCTOR_QUERY:         MissionType.DOCTOR_QUERY,
    IntentType.MEDICATION_QUERY:     MissionType.MEDICATION_QUERY,
    IntentType.PATIENT_EMERGENCY:    MissionType.PATIENT_EMERGENCY,
    IntentType.SHOW_ACTIVE_PATIENTS: MissionType.SHOW_ACTIVE_PATIENTS,
}


@dataclass
class MissionRequest:
    """Structured mission request ready for the MissionPlanner.

    This is the standardised handoff format between the Language module
    and the Mission module.

    Attributes:
        mission_type:   What kind of mission.
        pickup_location:  Where to collect items (e.g., "Pharmacy").
        delivery_location: Where to deliver items (e.g., "Room 205").
        item:           What to collect/deliver (medicine name, report, etc.).
        quantity:        How many items.
        priority:        Priority level (1=critical, 5=low).
        priority_label:  Human-readable priority string.
        patient_name:    Patient reference (if applicable).
        raw_text:        Original spoken command.
        intent:          The parsed intent that generated this request.
        entities:        The extracted entities.
        resolved_pickup:  Grid coordinates of pickup location (if resolved).
        resolved_delivery: Grid coordinates of delivery location (if resolved).
        is_valid:         Whether the request passed validation.
        validation_error: Error message if validation failed.
    """
    mission_type: MissionType = MissionType.NAVIGATE
    pickup_location: str = ""
    delivery_location: str = ""
    item: str = ""
    quantity: int = 1
    priority: int = 4
    priority_label: str = "normal"
    patient_name: str = ""
    patient_id: str = ""
    doctor_name: str = ""
    db_result: Optional[Dict[str, Any]] = None
    response_text: str = ""
    raw_text: str = ""
    intent: Optional[ParsedIntent] = None
    entities: Optional[ExtractedEntities] = None
    resolved_pickup: Optional[GridPos] = None
    resolved_delivery: Optional[GridPos] = None
    is_valid: bool = True
    validation_error: str = ""

    def __repr__(self) -> str:
        return (
            f"MissionRequest({self.mission_type.name}, "
            f"item='{self.item}', "
            f"from='{self.pickup_location}', "
            f"to='{self.delivery_location}', "
            f"pri={self.priority_label})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Command Resolver
# ─────────────────────────────────────────────────────────────────────────────

class CommandResolver:
    """Converts NLU output into structured MissionRequests.

    Usage::

        resolver = CommandResolver()

        # Optional: connect the semantic map for coordinate resolution
        resolver.set_semantic_resolver(semantic_query_engine)

        request = resolver.resolve(parsed_intent, extracted_entities)
        if request.is_valid:
            mission_planner.submit(request)

    Attributes:
        total_resolved: Count of successfully resolved commands.
    """

    def __init__(self) -> None:
        self._semantic_resolver: Optional[Any] = None  # SemanticQueryEngine
        self._db_engine: Optional[Any] = None          # DBQueryEngine
        self.total_resolved: int = 0

        log.info("CommandResolver initialised.")

    def set_semantic_resolver(self, resolver: Any) -> None:
        """Connect the semantic query engine for coordinate resolution.

        Args:
            resolver: SemanticQueryEngine instance with ``resolve(query)`` method.
        """
        self._semantic_resolver = resolver
        log.info("CommandResolver: Semantic resolver connected.")

    def set_db_engine(self, engine: Any) -> None:
        """Connect the hospital database query engine.

        Args:
            engine: DBQueryEngine instance.
        """
        self._db_engine = engine
        log.info("CommandResolver: Database query engine connected.")

    def resolve(
        self,
        intent: ParsedIntent,
        entities: ExtractedEntities,
    ) -> MissionRequest:
        """Resolve a parsed intent and entities into a MissionRequest.

        Args:
            intent: Classified intent from IntentParser.
            entities: Extracted entities from EntityExtractor.

        Returns:
            A validated MissionRequest.
        """
        # Map intent to mission type
        mission_type = _INTENT_TO_MISSION.get(intent.intent)
        if mission_type is None:
            return MissionRequest(
                is_valid=False,
                validation_error=f"Unsupported intent: {intent.intent.name}",
                raw_text=intent.raw_text,
                intent=intent,
                entities=entities,
            )

        # Build the request based on mission type
        request = self._build_request(mission_type, intent, entities)

        # Resolve coordinates if semantic resolver is available
        self._resolve_coordinates(request)

        # Validate the request
        self._validate(request)

        if request.is_valid:
            self.total_resolved += 1
            log.info("CommandResolver: Resolved → %s", request)
        else:
            log.warning("CommandResolver: Validation failed — %s", request.validation_error)

        return request

    # ─────────────────────────────────────────────────────────────────────────
    # Request Building (per mission type)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_request(
        self,
        mission_type: MissionType,
        intent: ParsedIntent,
        entities: ExtractedEntities,
    ) -> MissionRequest:
        """Build a MissionRequest from the mission type and entities."""

        request = MissionRequest(
            mission_type=mission_type,
            priority=entities.priority,
            priority_label=entities.priority_label,
            raw_text=intent.raw_text,
            intent=intent,
            entities=entities,
            quantity=entities.quantity_num,
        )

        # Person
        if entities.has_person:
            request.patient_name = entities.persons[0]

        # Patient ID
        if entities.patient_id:
            request.patient_id = entities.patient_id

        # Mission-specific field mapping
        if mission_type == MissionType.MEDICINE_DELIVERY:
            request.pickup_location = "Pharmacy"
            request.item = entities.primary_medicine or "medication"
            request.delivery_location = self._get_destination(entities)
            if not request.delivery_location and request.patient_id and self._db_engine:
                p_info = self._db_engine.get_patient_info(request.patient_id)
                if p_info and p_info.get("assigned_room"):
                    request.delivery_location = p_info["assigned_room"]

        elif mission_type == MissionType.GUIDE_PATIENT:
            request.delivery_location = self._get_destination(entities)
            request.item = "patient guidance"

        elif mission_type == MissionType.CALL_NURSE:
            request.pickup_location = "Nurse Station"
            request.delivery_location = self._get_destination(entities) or "current location"
            request.item = "nurse assistance"

        elif mission_type == MissionType.EMERGENCY_RESPONSE:
            request.delivery_location = self._get_destination(entities) or "Emergency Room"
            request.item = "emergency response"
            request.priority = 1
            request.priority_label = "critical"

        elif mission_type == MissionType.DELIVER_REPORT:
            request.pickup_location = "Laboratory"
            request.item = "lab report"
            request.delivery_location = self._get_destination(entities)

        elif mission_type == MissionType.TRANSPORT_SAMPLE:
            request.delivery_location = "Laboratory"
            request.item = "lab sample"
            # Pickup is the first non-lab location, or the room number
            for loc in entities.locations:
                if loc.lower() != "laboratory":
                    request.pickup_location = loc
                    break
            if not request.pickup_location:
                request.pickup_location = self._get_destination(entities, exclude="Laboratory")

        elif mission_type == MissionType.FETCH_WHEELCHAIR:
            request.pickup_location = "Storage"
            request.item = "wheelchair"
            request.delivery_location = self._get_destination(entities)

        elif mission_type == MissionType.ESCORT_VISITOR:
            request.delivery_location = self._get_destination(entities)
            request.item = "visitor escort"

        elif mission_type == MissionType.NAVIGATE:
            request.delivery_location = self._get_destination(entities)

        elif mission_type == MissionType.PATIENT_STATUS_QUERY:
            if self._db_engine and request.patient_id:
                info = self._db_engine.get_patient_info(request.patient_id)
                request.db_result = info
                if info and info.get("assigned_room"):
                    request.delivery_location = info["assigned_room"]
            from language.db_response_generator import DBResponseGenerator
            request.response_text = DBResponseGenerator.format_patient_status(
                request.db_result, patient_id=request.patient_id
            )

        elif mission_type == MissionType.DOCTOR_QUERY:
            if self._db_engine and request.patient_id:
                doc_info = self._db_engine.get_attending_doctor_info(request.patient_id)
                request.db_result = doc_info
            from language.db_response_generator import DBResponseGenerator
            request.response_text = DBResponseGenerator.format_doctor_info(
                request.db_result, query_name=entities.persons[0] if entities.persons else request.patient_id
            )

        elif mission_type == MissionType.MEDICATION_QUERY:
            request.item = entities.primary_medicine or "medication"
            if self._db_engine and request.patient_id:
                meds = self._db_engine.get_medications_for_patient(request.patient_id)
                request.db_result = {"medications": meds}
            from language.db_response_generator import DBResponseGenerator
            request.response_text = DBResponseGenerator.format_medications(
                request.db_result.get("medications") if request.db_result else None,
                patient_id=request.patient_id,
            )

        elif mission_type == MissionType.PATIENT_EMERGENCY:
            request.priority = 1
            request.priority_label = "critical"
            request.item = "patient emergency"
            if self._db_engine and request.patient_id:
                info = self._db_engine.get_patient_info(request.patient_id)
                request.db_result = info
                if info and info.get("assigned_room"):
                    request.delivery_location = info["assigned_room"]
            if not request.delivery_location:
                request.delivery_location = self._get_destination(entities) or "Emergency Room"
            from language.db_response_generator import DBResponseGenerator
            request.response_text = DBResponseGenerator.format_emergency_response(
                request.db_result, patient_id=request.patient_id, location=request.delivery_location
            )

        elif mission_type == MissionType.SHOW_ACTIVE_PATIENTS:
            if self._db_engine:
                active = self._db_engine.get_all_active_patients_brief()
                request.db_result = {"active_patients": active}
            from language.db_response_generator import DBResponseGenerator
            request.response_text = DBResponseGenerator.format_active_patients(
                request.db_result.get("active_patients") if request.db_result else None
            )

        return request

    # ─────────────────────────────────────────────────────────────────────────
    # Coordinate Resolution
    # ─────────────────────────────────────────────────────────────────────────

    def _resolve_coordinates(self, request: MissionRequest) -> None:
        """Resolve location names to grid coordinates using semantic maps and vision-language reasoning."""
        if self._semantic_resolver is None:
            return

        from language.vision_language_reasoner import VisionLanguageReasoner
        vlr = VisionLanguageReasoner(self._semantic_resolver)

        if request.pickup_location:
            try:
                pos = self._semantic_resolver.resolve(request.pickup_location)
                if pos is None:
                    # Try Vision-Language reasoning
                    vlr_res = vlr.parse_and_ground(request.pickup_location)
                    if vlr_res:
                        pos = vlr_res.target_pos
                if pos is not None:
                    request.resolved_pickup = pos
            except Exception as exc:
                log.debug("CommandResolver: Failed to resolve pickup '%s': %s",
                         request.pickup_location, exc)

        if request.delivery_location:
            try:
                pos = self._semantic_resolver.resolve(request.delivery_location)
                if pos is None:
                    # Try Vision-Language spatial reasoning on delivery_location or raw_text
                    vlr_res = vlr.parse_and_ground(request.delivery_location) or vlr.parse_and_ground(request.raw_text)
                    if vlr_res:
                        pos = vlr_res.target_pos
                        if not request.delivery_location or request.delivery_location == request.raw_text:
                            request.delivery_location = vlr_res.resolved_name
                if pos is not None:
                    request.resolved_delivery = pos
            except Exception as exc:
                log.debug("CommandResolver: Failed to resolve delivery '%s': %s",
                         request.delivery_location, exc)

    # ─────────────────────────────────────────────────────────────────────────
    # Validation
    # ─────────────────────────────────────────────────────────────────────────

    def _validate(self, request: MissionRequest) -> None:
        """Validate the mission request for completeness."""
        errors: List[str] = []

        # All missions need a destination (except RETURN_TO_DOCK and queries)
        query_types = {
            MissionType.RETURN_TO_DOCK,
            MissionType.PATIENT_STATUS_QUERY,
            MissionType.DOCTOR_QUERY,
            MissionType.MEDICATION_QUERY,
            MissionType.SHOW_ACTIVE_PATIENTS,
        }
        if request.mission_type not in query_types:
            if not request.delivery_location:
                errors.append("No destination specified.")

        # Medicine delivery needs medicine name
        if request.mission_type == MissionType.MEDICINE_DELIVERY:
            if not request.item or request.item == "medication":
                errors.append("No specific medicine name provided.")

        if errors:
            request.is_valid = False
            request.validation_error = " ".join(errors)
        else:
            request.is_valid = True

    # ─────────────────────────────────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _get_destination(entities: ExtractedEntities, exclude: str = "") -> str:
        """Get the best destination from entities.

        Prefers room numbers over department names.

        Args:
            entities: Extracted entities.
            exclude: Location name to exclude.

        Returns:
            Destination string, or empty string if not found.
        """
        # Check room number first
        if entities.room_number:
            return f"Room {entities.room_number}"

        # Then check locations
        for loc in entities.locations:
            if loc.lower() != exclude.lower():
                return loc

        return ""

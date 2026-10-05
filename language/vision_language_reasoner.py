"""
HospitalRobotNav — Vision-Language Reasoner (VLR)
===================================================
Research-grade spatial & contextual grounding engine for embodied AI robots.

Processes natural language spatial queries, resolves relative and contextual spatial
relationships ("opposite ICU", "next to pharmacy", "between cardiology and triage",
"nearest charging station", "less congested pharmacy"), and grounds them into validated
navigation goals using the hospital digital twin's semantic map and real-time perception.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from utilities.logger import get_logger
from maps.hospital.room_definitions import RoomCategory, ROOM_DATABASE, ROOMS_BY_ID

log = get_logger(__name__)

GridPos = Tuple[int, int]


class SpatialRelationType(Enum):
    DIRECT = auto()
    OPPOSITE = auto()
    NEXT_TO = auto()
    BETWEEN = auto()
    NEAREST = auto()
    LEAST_CONGESTED = auto()
    RELATIVE_OFFSET = auto()


@dataclass
class SpatialReasoningResult:
    """Output of the Vision-Language Reasoning process."""
    raw_query: str
    relation_type: SpatialRelationType
    resolved_name: str
    target_pos: GridPos
    reference_locations: List[str] = field(default_factory=list)
    reasoning_chain: List[str] = field(default_factory=list)
    confidence: float = 1.0


class VisionLanguageReasoner:
    """
    Vision-Language Spatial Grounding Engine.
    
    Translates complex human-robot spatial dialogue into precise metric coordinates
    using topological room adjacency, line-of-sight corridor relations, and live
    dynamic obstacle density.
    """

    def __init__(self, semantic_map: Any) -> None:
        self.semantic_map = semantic_map
        log.info("VisionLanguageReasoner initialised with semantic map.")

    def parse_and_ground(
        self,
        text: str,
        current_robot_pos: Optional[GridPos] = None,
        obstacle_positions: Optional[List[GridPos]] = None,
    ) -> Optional[SpatialReasoningResult]:
        """
        Parse natural language command and ground relative spatial references.

        Args:
            text: Raw or extracted user command string.
            current_robot_pos: Robot's current (row, col) grid coordinates.
            obstacle_positions: List of active dynamic obstacle positions.

        Returns:
            SpatialReasoningResult if spatial grounding succeeds, or None.
        """
        text_lower = text.lower().strip()
        chain = []

        # 1. Opposite / Across from ("opposite ICU", "across from pharmacy", "facing room 101")
        opp_match = re.search(r'\b(?:opposite|across\s+from|facing)\s+(?:the\s+)?([a-z0-9\s\-]+?)(?:\s+(?:please|now|urgently)|$)', text_lower)
        if opp_match:
            ref_raw = opp_match.group(1).strip()
            chain.append(f"Detected OPPOSITE relation with reference '{ref_raw}'")
            opp_room = self.semantic_map.get_opposite_room(ref_raw)
            if opp_room:
                chain.append(f"Grounded '{ref_raw}' across corridor to {opp_room.room_id} ({opp_room.label})")
                return SpatialReasoningResult(
                    raw_query=text,
                    relation_type=SpatialRelationType.OPPOSITE,
                    resolved_name=opp_room.label,
                    target_pos=opp_room.entry_point,
                    reference_locations=[ref_raw],
                    reasoning_chain=chain,
                    confidence=0.96,
                )

        # 2. Next to / Beside / Adjacent to ("next to radiology", "beside pharmacy", "adjacent to room 201")
        next_match = re.search(r'\b(?:next\s+to|beside|adjacent\s+to|near)\s+(?:the\s+)?([a-z0-9\s\-]+?)(?:\s+(?:please|now|urgently)|$)', text_lower)
        if next_match:
            ref_raw = next_match.group(1).strip()
            chain.append(f"Detected NEXT_TO relation with reference '{ref_raw}'")
            adj_rooms = self.semantic_map.get_adjacent_rooms(ref_raw)
            if adj_rooms:
                chosen = adj_rooms[0]
                chain.append(f"Grounded '{ref_raw}' adjacent room to {chosen.room_id} ({chosen.label})")
                return SpatialReasoningResult(
                    raw_query=text,
                    relation_type=SpatialRelationType.NEXT_TO,
                    resolved_name=chosen.label,
                    target_pos=chosen.entry_point,
                    reference_locations=[ref_raw],
                    reasoning_chain=chain,
                    confidence=0.92,
                )

        # 3. Between ("between pharmacy and ICU", "between ward 101 and ward 102")
        between_match = re.search(r'\bbetween\s+(?:the\s+)?(.+?)\s+and\s+(?:the\s+)?(.+?)(?:\s+(?:please|now|urgently)|$)', text_lower)
        if between_match:
            ref_a = between_match.group(1).strip()
            ref_b = between_match.group(2).strip()
            chain.append(f"Detected BETWEEN relation between '{ref_a}' and '{ref_b}'")
            between_rooms = self.semantic_map.get_rooms_between(ref_a, ref_b)
            if between_rooms:
                chosen = between_rooms[0]
                chain.append(f"Grounded mid-point room to {chosen.room_id} ({chosen.label})")
                return SpatialReasoningResult(
                    raw_query=text,
                    relation_type=SpatialRelationType.BETWEEN,
                    resolved_name=chosen.label,
                    target_pos=chosen.entry_point,
                    reference_locations=[ref_a, ref_b],
                    reasoning_chain=chain,
                    confidence=0.90,
                )
            else:
                # Compute midpoint between the two rooms' entry points
                pos_a = self.semantic_map.resolve(ref_a)
                pos_b = self.semantic_map.resolve(ref_b)
                if pos_a and pos_b:
                    mid_pos = ((pos_a[0] + pos_b[0]) // 2, (pos_a[1] + pos_b[1]) // 2)
                    chain.append(f"Computed geometric corridor midpoint {mid_pos} between '{ref_a}' and '{ref_b}'")
                    return SpatialReasoningResult(
                        raw_query=text,
                        relation_type=SpatialRelationType.BETWEEN,
                        resolved_name=f"Midpoint between {ref_a} and {ref_b}",
                        target_pos=mid_pos,
                        reference_locations=[ref_a, ref_b],
                        reasoning_chain=chain,
                        confidence=0.88,
                    )

        # 4. Less congested / least crowded ("less congested pharmacy", "least crowded nurse station")
        if "least congested" in text_lower or "less congested" in text_lower or "least crowded" in text_lower:
            cat_match = re.search(r'\b(?:least|less)\s+(?:congested|crowded)\s+([a-z0-9\s\-]+)', text_lower)
            target_cat = cat_match.group(1).strip() if cat_match else "pharmacy"
            chain.append(f"Detected LEAST_CONGESTED query for '{target_cat}'")
            pos = self.semantic_map.get_least_congested_room(target_cat, obstacle_positions or [])
            if pos:
                chain.append(f"Evaluated obstacle density and resolved position {pos}")
                return SpatialReasoningResult(
                    raw_query=text,
                    relation_type=SpatialRelationType.LEAST_CONGESTED,
                    resolved_name=f"Least congested {target_cat}",
                    target_pos=pos,
                    reference_locations=[target_cat],
                    reasoning_chain=chain,
                    confidence=0.95,
                )

        # 5. Nearest / Closest ("nearest pharmacy", "closest charging station", "nearest nurse station")
        nearest_match = re.search(r'\b(?:nearest|closest)\s+(?:the\s+)?([a-z0-9\s\-]+)', text_lower)
        if nearest_match:
            cat_query = nearest_match.group(1).strip()
            chain.append(f"Detected NEAREST query for category/label '{cat_query}'")
            robot_pos = current_robot_pos or (80, 11)
            # Check for charging dock
            if "dock" in cat_query or "charger" in cat_query or "charging" in cat_query:
                pos = self.semantic_map.get_nearest_charging_station(robot_pos)
                if pos:
                    return SpatialReasoningResult(
                        raw_query=text,
                        relation_type=SpatialRelationType.NEAREST,
                        resolved_name="Nearest Charging Station",
                        target_pos=pos,
                        reference_locations=[cat_query],
                        reasoning_chain=chain,
                        confidence=0.98,
                    )
            # General category lookup
            for cat in RoomCategory:
                if cat.name.lower() in cat_query:
                    pos = self.semantic_map.find_nearest_room_of_category(cat, robot_pos)
                    if pos:
                        return SpatialReasoningResult(
                            raw_query=text,
                            relation_type=SpatialRelationType.NEAREST,
                            resolved_name=f"Nearest {cat.name}",
                            target_pos=pos,
                            reference_locations=[cat_query],
                            reasoning_chain=chain,
                            confidence=0.95,
                        )

        # 6. Direct semantic resolution fallback
        pos = self.semantic_map.resolve(text)
        if pos:
            room_id = self.semantic_map.resolve_to_room_id(text)
            label = self.semantic_map.get_room_info(room_id).get("label") if room_id else text
            return SpatialReasoningResult(
                raw_query=text,
                relation_type=SpatialRelationType.DIRECT,
                resolved_name=label or text,
                target_pos=pos,
                reference_locations=[text],
                reasoning_chain=[f"Direct semantic lookup for '{text}' -> {pos}"],
                confidence=1.0,
            )

        return None

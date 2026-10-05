"""
HospitalRobotNav — Environment Grounding & Vision-Language Agent
==================================================================
Resolves natural-language spatial references and relative descriptions
("opposite ICU", "nearest pharmacy", "less congested ward") into environment-grounded
grid coordinates using visual observations and semantic scene maps.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from agents.agent_base import HospitalAgent, AgentState, AgentBid
from agents.agent_messages import AgentMessage, MessageType
from agents.message_bus import MESSAGE_BUS
from language.vision_language_reasoner import VisionLanguageReasoner, SpatialReasoningResult
from utilities.logger import get_logger
from ai_interfaces.vlm_interface import SceneDescription, SimulatedVLMProvider

log = get_logger(__name__)

GridPos = Tuple[int, int]


class EnvironmentGroundingAgent(HospitalAgent):
    """
    Environment Grounding & Vision-Language Reasoning Agent.
    
    Bridges user instruction semantics with physical metric coordinates.
    Implements a structured grounding pipeline:
        Perception Input 
              ↓ 
        Scene Representation 
              ↓ 
        Language Grounding 
              ↓ 
        Validated Action Representation
    """

    def __init__(self, world_state: Optional[Any] = None, home_position: GridPos = (50, 50)) -> None:
        super().__init__(
            agent_type="grounding",
            capabilities=frozenset({
                "vision",
                "monitor"
            }),
            home_position=home_position,
        )
        self.world_state = world_state
        self._vlm_provider = SimulatedVLMProvider()
        self._reasoner: Optional[VisionLanguageReasoner] = None

        # Register on message bus
        MESSAGE_BUS.register_agent(self.agent_id)
        
        # Subscribe to grounding and perception requests
        MESSAGE_BUS.subscribe(self.agent_id, MessageType.GROUNDING_REQUEST, self.handle_grounding_request)
        MESSAGE_BUS.subscribe(self.agent_id, MessageType.PERCEPTION_REQUEST, self.handle_perception_request)

        log.info("EnvironmentGroundingAgent %s initialized.", self.agent_id)

    def _lazy_init_reasoner(self) -> None:
        """Initialize the spatial reasoner using semantic map reference from world state."""
        if self._reasoner is None and self.world_state is not None:
            sem_map = getattr(self.world_state, "semantic_map", None)
            if sem_map is not None:
                self._reasoner = VisionLanguageReasoner(sem_map)
                log.info("EnvironmentGroundingAgent successfully initialized VisionLanguageReasoner.")

    def evaluate_mission(
        self,
        mission_type: str,
        destination: Optional[GridPos],
        priority: int,
    ) -> Optional[AgentBid]:
        """Software-only agent. Bids 0.0 or declines physical navigation tasks."""
        return None

    def accept_mission(self, mission_id: str, mission_data: Dict[str, Any]) -> bool:
        return False

    def abort_mission(self, reason: str = "") -> None:
        pass

    def handle_grounding_request(self, message: AgentMessage) -> None:
        """Resolve spatial query to grid coordinate and reply with GROUNDING_RESULT."""
        self._lazy_init_reasoner()
        
        query = message.payload.get("query", "")
        robot_pos = message.payload.get("robot_position")
        
        log.info("GroundingAgent received GROUNDING_REQUEST for query: '%s'", query)
        
        if not query:
            self._send_failure(message, "Empty query received.")
            return

        # ─── Visual-Semantic Grounding Pipeline ──────────────────────────────────
        
        # Step 1: Perception Input (Retrieve environment status from Shared World State)
        obstacles = []
        if self.world_state is not None:
            obstacles = self.world_state.get_obstacles()
            if robot_pos is None:
                robot_pos = self.world_state.get_robot_position()

        if robot_pos is None:
            robot_pos = (80, 11)  # Default simulator dock position

        # Step 2: Scene/Semantic Representation (Simulate VLM camera frame analysis)
        # Note: Since this is a 2D simulated environment, we retrieve the simulated VLM provider
        # metadata grounded in the robot's local topological neighborhood.
        simulated_frame = None  # In physical robot, this is self.world_state.get_camera_frame()
        scene_desc: SceneDescription = self._vlm_provider.describe_scene(simulated_frame, query)
        
        # Step 3: Language Grounding (Spatial relationship parsing)
        resolved_pos = None
        reasoning_chain = []
        
        if self._reasoner is not None:
            res: Optional[SpatialReasoningResult] = self._reasoner.parse_and_ground(
                query,
                current_robot_pos=robot_pos,
                obstacle_positions=obstacles
            )
            if res:
                resolved_pos = res.target_pos
                reasoning_chain = res.reasoning_chain
                log.info("GroundingAgent resolved query using VisionLanguageReasoner to %s", resolved_pos)
        
        # Fallback to direct world state semantic lookup
        if resolved_pos is None and self.world_state is not None:
            resolved_pos = self.world_state.find_location(query)
            if resolved_pos:
                reasoning_chain.append(f"Direct semantic lookup in world state for '{query}' -> {resolved_pos}")

        # Step 4: Validated Action Representation (Format coordinates for coordination agent)
        if resolved_pos is not None:
            # Check grid occupancy (safety check)
            snapped_pos = resolved_pos
            if self.world_state is not None and getattr(self.world_state, "occupancy_grid", None) is not None:
                grid = self.world_state.occupancy_grid
                if not grid.is_free(resolved_pos[0], resolved_pos[1]):
                    snapped_pos = grid.find_nearest_free(resolved_pos[0], resolved_pos[1])
                    reasoning_chain.append(f"Snapped target from occupied {resolved_pos} to free cell {snapped_pos}")

            # Send GROUNDING_RESULT back to sender
            reply = AgentMessage(
                msg_type=MessageType.GROUNDING_RESULT,
                sender=self.agent_id,
                receiver=message.sender,
                in_reply_to=message.msg_id,
                payload={
                    "query": query,
                    "resolved_position": snapped_pos,
                    "success": True,
                    "scene_description": scene_desc.description,
                    "reasoning_chain": reasoning_chain,
                }
            )
            MESSAGE_BUS.send(reply)
            log.info("GroundingAgent dispatched GROUNDING_RESULT for '%s' -> %s", query, snapped_pos)
        else:
            self._send_failure(message, f"Could not ground query '{query}' in semantic map.")

    def handle_perception_request(self, message: AgentMessage) -> None:
        """Process scene analysis query and return PERCEPTION_RESULT."""
        query = message.payload.get("query", "Describe what you see.")
        
        # Obtain simulated VLM results
        scene_desc = self._vlm_provider.describe_scene(None, query)
        
        reply = AgentMessage(
            msg_type=MessageType.PERCEPTION_RESULT,
            sender=self.agent_id,
            receiver=message.sender,
            in_reply_to=message.msg_id,
            payload={
                "description": scene_desc.description,
                "objects": scene_desc.objects,
                "people_count": scene_desc.people_count,
                "is_clear_path": scene_desc.is_clear_path,
                "confidence": scene_desc.confidence,
                "provider": scene_desc.provider
            }
        )
        MESSAGE_BUS.send(reply)
        log.info("GroundingAgent dispatched PERCEPTION_RESULT for query: '%s'", query)

    def _send_failure(self, request_msg: AgentMessage, reason: str) -> None:
        """Helper to send failed grounding response."""
        reply = AgentMessage(
            msg_type=MessageType.GROUNDING_RESULT,
            sender=self.agent_id,
            receiver=request_msg.sender,
            in_reply_to=request_msg.msg_id,
            payload={
                "success": False,
                "reason": reason
            }
        )
        MESSAGE_BUS.send(reply)
        log.warning("GroundingAgent grounding FAILED: %s", reason)

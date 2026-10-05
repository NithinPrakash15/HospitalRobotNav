"""
HospitalRobotNav — Inter-Agent Messaging Framework
===================================================
Defines structured message types and communication primitives for
collaborative multi-agent Embodied AI reasoning in the hospital environment.

Design:
    - Typed message envelopes with UUID, priority, timestamp, and payload.
    - Decoupled point-to-point and broadcast message delivery.
    - Seamless mapping to ROS2 custom message types (hospital_robot_nav_msgs).

Message Flow (End-to-End Mission):
    User Text
      → LanguageAgent  ──MISSION_REQUEST──►  Coordinator
      → Coordinator    ──GROUNDING_REQUEST──► GroundingAgent
      ← GroundingAgent ──GROUNDING_RESULT──► Coordinator
      → Coordinator    ──TASK_ASSIGNED──►     TaskExecutionAgent
      → Coordinator    ──NAVIGATION_REQUEST──► NavigationAgent
      ← NavigationAgent──NAVIGATION_STATUS──► Coordinator
      ← TaskExecAgent  ──TASK_COMPLETED──►   Coordinator
      → Coordinator    ──MISSION_COMPLETED──► (all)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

GridPos = Tuple[int, int]


class MessageType(Enum):
    """Enumeration of all inter-agent communication message types.

    Organised by the pipeline stage where the message is used.
    """
    # ── Mission Lifecycle ────────────────────────────────────────────────────
    MISSION_REQUEST         = auto()  # Language → Coordinator
    MISSION_ACCEPTED        = auto()  # Coordinator → Language
    MISSION_REJECTED        = auto()  # Coordinator → Language (infeasible)
    MISSION_COMPLETED       = auto()  # Coordinator → all
    MISSION_FAILED          = auto()  # Coordinator → all

    # ── Task Assignment & Progress ───────────────────────────────────────────
    TASK_ASSIGNED           = auto()  # Coordinator → specialist agent
    TASK_STARTED            = auto()  # Specialist → Coordinator
    TASK_PROGRESS           = auto()  # Specialist → Coordinator (periodic)
    TASK_COMPLETED          = auto()  # Specialist → Coordinator
    TASK_FAILED             = auto()  # Specialist → Coordinator

    # ── Environment Grounding ────────────────────────────────────────────────
    GROUNDING_REQUEST       = auto()  # Coordinator → GroundingAgent
    GROUNDING_RESULT        = auto()  # GroundingAgent → Coordinator

    # ── Navigation ───────────────────────────────────────────────────────────
    NAVIGATION_REQUEST      = auto()  # Coordinator → NavigationAgent
    NAVIGATION_STATUS       = auto()  # NavigationAgent → Coordinator
    OBSTACLE_DETECTED       = auto()  # NavigationAgent → Coordinator
    REPLAN_REQUEST          = auto()  # Coordinator → NavigationAgent

    # ── Clarification ────────────────────────────────────────────────────────
    SPEECH_TRANSCRIPT_READY = auto()  # speech/audio pipeline → LanguageAgent
    CLARIFICATION_NEEDED    = auto()  # LanguageAgent → user (via Coordinator)
    CLARIFICATION_RESPONSE  = auto()  # user → LanguageAgent

    # ── Perception / Vision-Language ─────────────────────────────────────────
    PERCEPTION_REQUEST      = auto()  # Any → GroundingAgent
    PERCEPTION_RESULT       = auto()  # GroundingAgent → requester
    SCENE_OBSERVATION       = auto()  # GroundingAgent → Coordinator (proactive)

    # ── Contract-Net Protocol (legacy compatibility) ─────────────────────────
    TASK_CALL_FOR_PROPOSAL  = auto()
    TASK_BID_SUBMISSION     = auto()
    PERCEPTION_MEDICINE_ID  = auto()

    # ── System ───────────────────────────────────────────────────────────────
    AGENT_HEARTBEAT         = auto()
    SYSTEM_STATUS           = auto()


# Navigation status values used in NAVIGATION_STATUS payloads
class NavigationState(Enum):
    """Possible states reported by NavigationAgent."""
    PATH_PLANNED        = auto()
    NAVIGATION_STARTED  = auto()
    OBSTACLE_DETECTED   = auto()
    PATH_BLOCKED        = auto()
    REPLANNING          = auto()
    GOAL_REACHED        = auto()
    NAVIGATION_FAILED   = auto()


@dataclass
class AgentMessage:
    """Structured inter-agent communication envelope.

    Attributes:
        msg_id:     Globally unique message identifier.
        msg_type:   MessageType enum indicating content and intent.
        sender:     Agent identifier of the sender.
        receiver:   Target agent identifier ("broadcast" for all).
        payload:    Domain-specific payload dictionary.
        priority:   1 (critical/emergency) to 5 (background telemetry).
        timestamp:  Wall-clock creation time.
        in_reply_to: Optional msg_id this message is responding to.
    """
    msg_type: MessageType
    sender: str
    receiver: str = "broadcast"
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: int = 3
    msg_id: str = field(default_factory=lambda: f"MSG-{uuid.uuid4().hex[:8].upper()}")
    timestamp: float = field(default_factory=time.monotonic)
    in_reply_to: Optional[str] = None

    def is_broadcast(self) -> bool:
        """Return True if message is meant for all registered agents."""
        return self.receiver in ("broadcast", "*", "")

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict for logging and inspection."""
        return {
            "msg_id": self.msg_id,
            "msg_type": self.msg_type.name,
            "sender": self.sender,
            "receiver": self.receiver,
            "priority": self.priority,
            "timestamp": round(self.timestamp, 4),
            "in_reply_to": self.in_reply_to,
            "payload": self.payload,
        }

    def __repr__(self) -> str:
        return (
            f"AgentMessage({self.msg_id} | {self.msg_type.name} | "
            f"{self.sender} -> {self.receiver} | pri={self.priority})"
        )

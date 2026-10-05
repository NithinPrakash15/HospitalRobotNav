"""
HospitalRobotNav — Abstract Hospital Agent
=============================================
Base class for all autonomous agents in the hospital robot fleet.

Each agent wraps a ``Robot`` instance and a ``MissionExecutor``, providing
a common interface for the ``AgentCoordinator`` to discover capabilities,
request bids, assign tasks, and query status.

Agent State Machine::

    IDLE ──► BIDDING ──► ASSIGNED ──► EXECUTING ──► IDLE
      │                     │              │
      ▼                     ▼              ▼
    CHARGING             DECLINED       FAILED → IDLE

Architecture Note (ROS2):
    Each agent becomes its own ROS2 node:
        ros2 run hospital_robot delivery_agent
    Communication uses ROS2 action servers / services instead of the EventBus.
"""

from __future__ import annotations

import uuid
import time
from abc import ABC, abstractmethod
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from utilities.event_bus import EVENT_BUS, HospitalEvent
from utilities.logger import get_logger
from . import agent_config as cfg

log = get_logger(__name__)

GridPos = Tuple[int, int]


# ─── Agent States ────────────────────────────────────────────────────────────

class AgentState(Enum):
    """Operational state of a hospital agent."""
    IDLE       = auto()   # Available for new tasks
    BIDDING    = auto()   # Evaluating a contract-net call-for-proposals
    ASSIGNED   = auto()   # Task assigned, preparing execution
    EXECUTING  = auto()   # Actively running a mission
    RETURNING  = auto()   # Returning to dock / home position
    CHARGING   = auto()   # At dock, charging
    ERROR      = auto()   # Requires operator attention
    OFFLINE    = auto()   # Not responding


# ─── Agent Bid ───────────────────────────────────────────────────────────────

@dataclass
class AgentBid:
    """A bid submitted by an agent in response to a task broadcast.

    Attributes:
        agent_id:       Unique agent identifier.
        score:          Composite fitness score (0.0–1.0, higher is better).
        estimated_eta:  Estimated seconds to complete the mission.
        battery_pct:    Agent's current battery percentage.
        distance:       Grid distance from agent to first task waypoint.
        rationale:      Human-readable explanation of the bid.
    """
    agent_id: str = ""
    score: float = 0.0
    estimated_eta: float = 0.0
    battery_pct: float = 100.0
    distance: float = 0.0
    rationale: str = ""

    def __repr__(self) -> str:
        return (f"AgentBid({self.agent_id}, score={self.score:.2f}, "
                f"ETA={self.estimated_eta:.0f}s)")


# ─── Agent Status ────────────────────────────────────────────────────────────

@dataclass
class AgentStatus:
    """Heartbeat / status message broadcast by an agent."""
    agent_id: str = ""
    agent_type: str = ""
    state: AgentState = AgentState.IDLE
    position: Optional[GridPos] = None
    battery_pct: float = 100.0
    current_mission_id: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.monotonic)


# ─── Abstract Base Agent ────────────────────────────────────────────────────

class HospitalAgent(ABC):
    """Abstract base class for all hospital agents.

    Lifecycle:
        1. Instantiate with a unique ID and capability set.
        2. Register with ``AgentRegistry`` (auto-publishes heartbeats).
        3. Receive task broadcasts via ``evaluate_mission()``.
        4. If selected, execute via ``accept_mission()``.
        5. Report completion or failure via EventBus.
    """

    def __init__(
        self,
        agent_type: str,
        capabilities: FrozenSet[str],
        home_position: GridPos = (5, 5),
    ) -> None:
        self.agent_id: str = f"{agent_type[:3].upper()}-{uuid.uuid4().hex[:6].upper()}"
        self.agent_type: str = agent_type
        self.capabilities: FrozenSet[str] = capabilities
        self.home_position: GridPos = home_position

        # State
        self._state: AgentState = AgentState.IDLE
        self._position: GridPos = home_position
        self._battery_pct: float = 100.0
        self._current_mission_id: Optional[str] = None
        self._last_heartbeat: float = time.monotonic()

        # Statistics
        self._missions_completed: int = 0
        self._missions_failed: int = 0
        self._total_distance: float = 0.0

        log.info("Agent %s (%s) created at %s", self.agent_id, agent_type,
                 home_position)

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def position(self) -> GridPos:
        return self._position

    @property
    def battery_pct(self) -> float:
        return self._battery_pct

    @property
    def is_available(self) -> bool:
        """Agent can accept new tasks."""
        return self._state in (AgentState.IDLE, AgentState.RETURNING)

    @property
    def is_busy(self) -> bool:
        return self._state in (AgentState.EXECUTING, AgentState.ASSIGNED,
                               AgentState.BIDDING)

    # ── State Management ─────────────────────────────────────────────────────

    def set_state(self, new_state: AgentState) -> None:
        old = self._state
        self._state = new_state
        log.debug("Agent %s: %s → %s", self.agent_id, old.name, new_state.name)

    def set_position(self, pos: GridPos) -> None:
        self._position = pos

    def set_battery(self, pct: float) -> None:
        self._battery_pct = max(0.0, min(100.0, pct))

    # ── Heartbeat ────────────────────────────────────────────────────────────

    def heartbeat(self) -> AgentStatus:
        """Generate and publish a heartbeat status message."""
        status = AgentStatus(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            state=self._state,
            position=self._position,
            battery_pct=self._battery_pct,
            current_mission_id=self._current_mission_id,
            capabilities=list(self.capabilities),
        )
        self._last_heartbeat = time.monotonic()
        EVENT_BUS.publish(
            HospitalEvent.AGENT_REGISTERED,
            data={"status": status},
            source=self.agent_id,
        )
        return status

    # ── Contract-Net Interface ───────────────────────────────────────────────

    def has_capability(self, required: str) -> bool:
        """Check if this agent can handle a task requiring *required* capability."""
        return required in self.capabilities

    @abstractmethod
    def evaluate_mission(
        self,
        mission_type: str,
        destination: Optional[GridPos],
        priority: int,
    ) -> Optional[AgentBid]:
        """Evaluate a call-for-proposals and return a bid, or None to decline.

        Args:
            mission_type: The type of mission (e.g. 'MEDICINE_DELIVERY').
            destination:  First waypoint grid position.
            priority:     Mission priority (1=critical).

        Returns:
            An ``AgentBid`` if the agent wants the task, else ``None``.
        """
        ...

    @abstractmethod
    def accept_mission(self, mission_id: str, mission_data: Dict[str, Any]) -> bool:
        """Accept and begin executing an assigned mission.

        Args:
            mission_id:   Unique mission plan identifier.
            mission_data: Full mission details dictionary.

        Returns:
            True if mission execution started successfully.
        """
        ...

    @abstractmethod
    def abort_mission(self, reason: str = "") -> None:
        """Abort the currently executing mission and return to idle."""
        ...

    def report_completion(self, mission_id: str, success: bool = True) -> None:
        """Report mission completion/failure via EventBus."""
        event = HospitalEvent.MISSION_COMPLETE if success else HospitalEvent.MISSION_FAILED
        if success:
            self._missions_completed += 1
        else:
            self._missions_failed += 1
        self._current_mission_id = None
        self.set_state(AgentState.IDLE)

        EVENT_BUS.publish(event, data={
            "agent_id": self.agent_id,
            "mission_id": mission_id,
            "success": success,
        }, source=self.agent_id)

        log.info("Agent %s mission %s %s",
                 self.agent_id, mission_id,
                 "COMPLETED" if success else "FAILED")

    # ── Utility ──────────────────────────────────────────────────────────────

    def grid_distance(self, target: GridPos) -> float:
        """Manhattan distance from current position to target."""
        return abs(self._position[0] - target[0]) + abs(self._position[1] - target[1])

    def distance_to(self, target: GridPos) -> float:
        """Alias for grid_distance."""
        return self.grid_distance(target)

    def compute_bid_score(
        self,
        distance: float,
        priority: int,
        max_distance: float = 100.0,
    ) -> float:
        """Compute a normalised bid score (0–1).

        Score factors:
            - Proximity (closer → higher)
            - Battery level (more charge → higher)
            - Priority alignment
        """
        proximity_score = 1.0 - min(distance / max_distance, 1.0)
        battery_score   = self._battery_pct / 100.0
        priority_bonus  = max(0.0, (6 - priority) / 5.0)

        score = 0.5 * proximity_score + 0.3 * battery_score + 0.2 * priority_bonus
        return round(score, 4)

    def __repr__(self) -> str:
        return (f"{self.__class__.__name__}({self.agent_id}, "
                f"state={self._state.name}, bat={self._battery_pct:.0f}%)")

"""
HospitalRobotNav — Event Bus (Observer Pattern)
================================================
A lightweight, type-safe publish/subscribe event bus for decoupled
communication between simulation modules.

Design Pattern:
    Observer (Publish/Subscribe)

    Publishers fire events without knowing who listens.
    Subscribers register handlers without knowing who fires.

    Example usage:
        # Publisher (event_controller.py)
        EVENT_BUS.publish(HospitalEvent.EMERGENCY_ALERT, {"room": "ICU"})

        # Subscriber (robot_controller.py)
        EVENT_BUS.subscribe(HospitalEvent.EMERGENCY_ALERT, on_emergency)

Architecture Justification:
    In a ROS2 system, this maps directly to the topic/subscriber model:
        Publisher  → rclpy.publisher.Publisher
        Subscriber → rclpy.subscription.Subscription
        EventType  → message type (e.g., std_msgs/String)

    The event bus allows simulation code to be structurally identical to
    ROS2 node code, easing migration.
"""

from __future__ import annotations

from collections import defaultdict
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

from utilities.logger import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Event Type Registry
# ─────────────────────────────────────────────────────────────────────────────

class HospitalEvent(Enum):
    """
    Enumeration of all hospital simulation events.

    Each event maps to a ROS2 topic in a deployed system.

    ROS2 Topic Equivalents:
        ROBOT_GOAL_REACHED    → /robot/goal_reached (std_msgs/Bool)
        OBSTACLE_DETECTED     → /robot/obstacle (geometry_msgs/Point)
        EMERGENCY_ALERT       → /hospital/emergency (std_msgs/String)
        BATTERY_LOW           → /robot/battery_low (std_msgs/Float32)
        PATH_PLANNED          → /robot/path (nav_msgs/Path)
        PATH_FAILED           → /robot/path_failed (std_msgs/String)
        REPLANNING_STARTED    → /robot/replanning (std_msgs/Bool)
        REPLANNING_COMPLETE   → /robot/replan_done (std_msgs/Bool)
        MISSION_STARTED       → /robot/mission_start (std_msgs/String)
        MISSION_COMPLETE      → /robot/mission_done (std_msgs/String)
        MISSION_FAILED        → /robot/mission_fail (std_msgs/String)
        DYNAMIC_OBSTACLE_ADD  → /sim/obstacle_add (geometry_msgs/Point)
        DYNAMIC_OBSTACLE_MOVE → /sim/obstacle_move (geometry_msgs/Point)
        CORRIDOR_BLOCKED      → /hospital/corridor_blocked (std_msgs/String)
        FIRE_ALARM            → /hospital/fire (std_msgs/String)
        POWER_FAILURE         → /hospital/power_fail (std_msgs/Bool)
        PATIENT_CROSSING      → /hospital/patient_cross (geometry_msgs/Point)
        ROBOT_CHARGING        → /robot/charging (std_msgs/Bool)
        ROBOT_CHARGED         → /robot/charged (std_msgs/Bool)
        SIMULATION_RESET      → /sim/reset (std_msgs/Bool)
        PLANNER_CHANGED       → /robot/planner (std_msgs/String)
        SPEED_CHANGED         → /sim/speed (std_msgs/Float32)
    """

    # ── Robot Navigation Events ───────────────────────────────────────────────
    ROBOT_GOAL_REACHED      = auto()
    ROBOT_STUCK             = auto()
    PATH_PLANNED            = auto()
    PATH_FAILED             = auto()
    REPLANNING_STARTED      = auto()
    REPLANNING_COMPLETE     = auto()

    # ── Mission Events ────────────────────────────────────────────────────────
    MISSION_STARTED         = auto()
    MISSION_COMPLETE        = auto()
    MISSION_FAILED          = auto()
    MISSION_QUEUED          = auto()

    # ── Obstacle Events ───────────────────────────────────────────────────────
    OBSTACLE_DETECTED       = auto()
    DYNAMIC_OBSTACLE_ADD    = auto()
    DYNAMIC_OBSTACLE_REMOVE = auto()
    DYNAMIC_OBSTACLE_MOVE   = auto()

    # ── Hospital Events ───────────────────────────────────────────────────────
    EMERGENCY_ALERT         = auto()
    CORRIDOR_BLOCKED        = auto()
    FIRE_ALARM              = auto()
    POWER_FAILURE           = auto()
    PATIENT_CROSSING        = auto()

    # ── Robot Status Events ───────────────────────────────────────────────────
    BATTERY_LOW             = auto()
    BATTERY_CRITICAL        = auto()
    ROBOT_CHARGING          = auto()
    ROBOT_CHARGED           = auto()

    # ── Simulation Control Events ─────────────────────────────────────────────
    SIMULATION_RESET        = auto()
    SIMULATION_PAUSED       = auto()
    SIMULATION_RESUMED      = auto()
    PLANNER_CHANGED         = auto()
    SPEED_CHANGED           = auto()

    # ── Multi-Agent Events ───────────────────────────────────────────────────
    AGENT_REGISTERED        = auto()
    AGENT_TASK_ASSIGNED     = auto()
    AGENT_COLLISION_RISK    = auto()
    AGENT_BID               = auto()
    AGENT_ASSIGNED          = auto()

    # ── Speech & Dialogue Events ──────────────────────────────────────────────
    WAKE_WORD_DETECTED      = auto()
    SPEECH_RECOGNIZED       = auto()
    SPEECH_STARTED          = auto()
    INTENT_PARSED           = auto()
    DIALOGUE_UPDATE         = auto()
    DIALOGUE_RESPONSE       = auto()

    # ── Mission Step & Medicine Events ────────────────────────────────────────
    MISSION_REQUESTED       = auto()
    MISSION_PLANNED         = auto()
    MISSION_STEP_STARTED    = auto()
    MISSION_STEP_COMPLETE   = auto()
    MEDICINE_COLLECTED      = auto()
    MEDICINE_DELIVERED      = auto()


# ─────────────────────────────────────────────────────────────────────────────
# Event Data
# ─────────────────────────────────────────────────────────────────────────────

class EventPayload:
    """
    Structured event payload carrying event metadata and arbitrary data.

    Attributes:
        event_type: The HospitalEvent enum value.
        data:       Dictionary of event-specific key-value pairs.
        source:     Optional string identifying the firing component.
    """

    __slots__ = ("event_type", "data", "source", "timestamp")

    def __init__(
        self,
        event_type: HospitalEvent,
        data: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
        timestamp: float = 0.0,
    ) -> None:
        self.event_type: HospitalEvent       = event_type
        self.data:       Dict[str, Any]      = data or {}
        self.source:     Optional[str]       = source
        self.timestamp:  float               = timestamp

    def __repr__(self) -> str:
        return (
            f"EventPayload({self.event_type.name}, "
            f"source={self.source!r}, data={self.data})"
        )

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __contains__(self, key: str) -> bool:
        return key in self.data


# ─────────────────────────────────────────────────────────────────────────────
# Event Bus
# ─────────────────────────────────────────────────────────────────────────────

EventHandler = Callable[[EventPayload], None]


class EventBus:
    """
    Global publish/subscribe event bus.

    Thread Safety:
        This implementation is NOT thread-safe. In a ROS2 deployment,
        use rclpy executor callbacks which are inherently single-threaded
        per executor.

    Usage:
        # Register a handler
        EVENT_BUS.subscribe(HospitalEvent.EMERGENCY_ALERT, my_handler)

        # Fire an event
        EVENT_BUS.publish(
            HospitalEvent.EMERGENCY_ALERT,
            data={"room": "ICU", "code": "RED"},
            source="event_controller"
        )

        # Unregister
        EVENT_BUS.unsubscribe(HospitalEvent.EMERGENCY_ALERT, my_handler)
    """

    def __init__(self) -> None:
        # Maps event type → list of handler callbacks
        self._handlers: Dict[HospitalEvent, List[EventHandler]] = defaultdict(list)
        # Event history (last N events per type)
        self._history:  Dict[HospitalEvent, List[EventPayload]] = defaultdict(list)
        self._history_limit: int = 100
        self._sim_time: float = 0.0
        self._total_events: int = 0

    # ── Subscription Management ───────────────────────────────────────────────

    def subscribe(
        self,
        event_type: HospitalEvent,
        handler: EventHandler,
    ) -> None:
        """
        Register `handler` to be called whenever `event_type` is published.

        Args:
            event_type: Event to listen for.
            handler:    Callable(EventPayload) → None.
        """
        handlers = self._handlers[event_type]
        if handler not in handlers:
            handlers.append(handler)
            log.debug("Subscribed %s to %s", handler.__name__, event_type.name)

    def unsubscribe(
        self,
        event_type: HospitalEvent,
        handler: EventHandler,
    ) -> None:
        """
        Remove `handler` from `event_type` subscriptions.

        Args:
            event_type: Event to stop listening for.
            handler:    Previously registered callable.
        """
        handlers = self._handlers[event_type]
        if handler in handlers:
            handlers.remove(handler)

    def unsubscribe_all(self, event_type: HospitalEvent) -> None:
        """Remove all handlers for `event_type`."""
        self._handlers[event_type].clear()

    # ── Publishing ────────────────────────────────────────────────────────────

    def publish(
        self,
        event_type: HospitalEvent,
        data: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
    ) -> int:
        """
        Publish an event to all registered subscribers.

        Handlers are called synchronously in registration order.
        Exceptions in individual handlers are caught and logged, preventing
        one bad handler from blocking others.

        Args:
            event_type: The event to publish.
            data:       Optional key-value payload dictionary.
            source:     Optional string name of the publishing component.

        Returns:
            Number of handlers invoked.
        """
        payload = EventPayload(
            event_type=event_type,
            data=data or {},
            source=source,
            timestamp=self._sim_time,
        )

        # Record in history
        history = self._history[event_type]
        history.append(payload)
        if len(history) > self._history_limit:
            history.pop(0)

        self._total_events += 1
        handlers = self._handlers.get(event_type, [])

        if not handlers:
            log.debug("Event %s published with no subscribers", event_type.name)
            return 0

        invoked = 0
        for handler in list(handlers):  # Copy to allow mid-loop unsubscription
            try:
                handler(payload)
                invoked += 1
            except Exception as exc:
                log.error(
                    "Handler %s raised %s for event %s: %s",
                    handler.__name__, type(exc).__name__, event_type.name, exc,
                )

        return invoked

    # ── Simulation Time ───────────────────────────────────────────────────────

    def set_sim_time(self, t: float) -> None:
        """Update the simulation time used for event timestamps."""
        self._sim_time = t

    # ── History & Diagnostics ─────────────────────────────────────────────────

    def get_history(
        self,
        event_type: HospitalEvent,
        limit: int = 10,
    ) -> List[EventPayload]:
        """Return the last `limit` events of `event_type`."""
        return self._history[event_type][-limit:]

    def get_subscriber_count(self, event_type: HospitalEvent) -> int:
        """Return number of subscribers for `event_type`."""
        return len(self._handlers.get(event_type, []))

    def get_total_events_fired(self) -> int:
        """Return total number of events published since initialization."""
        return self._total_events

    def set_sim_time(self, sim_time: float) -> None:
        """Update current simulation time for event timestamps."""
        self._sim_time = sim_time

    def reset(self) -> None:
        """Clear all handlers and history (used on simulation reset)."""
        self._handlers.clear()
        self._history.clear()
        self._total_events = 0
        self._sim_time = 0.0
        log.info("EventBus reset.")


    def __repr__(self) -> str:
        subscribed = sum(len(h) for h in self._handlers.values())
        return f"EventBus(subscriptions={subscribed}, total_events={self._total_events})"


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton — import and use everywhere
# ─────────────────────────────────────────────────────────────────────────────
EVENT_BUS = EventBus()

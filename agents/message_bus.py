"""
HospitalRobotNav — Agent Message Bus
=======================================
Central message routing infrastructure for inter-agent communication.

Provides point-to-point and broadcast message delivery between all agents
in the hospital robot fleet, with a full communication log for inspection
during demonstration and evaluation.

Design:
    Each agent has a named mailbox (FIFO queue). Messages are routed
    by receiver ID or broadcast to all registered mailboxes. The bus
    keeps an inspectable log of every message ever routed (bounded).

    In a ROS2 deployment, this maps to a combination of:
    - Topic subscriptions (broadcast messages)
    - Service calls (point-to-point request/response)
    - Action servers (long-running task assignments)

Thread Safety:
    Single-threaded; all calls happen within the simulation frame loop.
"""

from __future__ import annotations

import time
from collections import deque, defaultdict
from typing import Callable, Deque, Dict, List, Optional, Set

from agents.agent_messages import AgentMessage, MessageType
from utilities.logger import get_logger

log = get_logger(__name__)

# Type alias for message handler callbacks
MessageHandler = Callable[[AgentMessage], None]


class AgentMessageBus:
    """Central message routing bus for the multi-agent system.

    Usage::

        bus = AgentMessageBus()

        # Register agent mailboxes
        bus.register_agent("coordinator")
        bus.register_agent("language_agent")

        # Subscribe to specific message types
        bus.subscribe("coordinator", MessageType.MISSION_REQUEST, handler_fn)

        # Send a message
        bus.send(AgentMessage(
            msg_type=MessageType.MISSION_REQUEST,
            sender="language_agent",
            receiver="coordinator",
            payload={"mission_type": "medicine_delivery", ...}
        ))

        # Or poll messages
        msgs = bus.get_messages("coordinator")
    """

    MAX_LOG_SIZE = 500
    MAX_QUEUE_SIZE = 200

    def __init__(self) -> None:
        # Per-agent message queues (agent_id → deque of AgentMessage)
        self._queues: Dict[str, Deque[AgentMessage]] = {}

        # Per-agent subscription handlers (agent_id → {MessageType → [handlers]})
        self._subscriptions: Dict[str, Dict[MessageType, List[MessageHandler]]] = defaultdict(
            lambda: defaultdict(list)
        )

        # Set of registered agent IDs
        self._registered: Set[str] = set()

        # Global communication log (bounded)
        self._communication_log: Deque[Dict] = deque(maxlen=self.MAX_LOG_SIZE)

        # Statistics
        self.total_messages_sent: int = 0
        self.total_messages_delivered: int = 0
        self.total_broadcasts: int = 0

        log.info("AgentMessageBus initialised.")

    # ── Agent Registration ───────────────────────────────────────────────────

    def register_agent(self, agent_id: str) -> None:
        """Register an agent's mailbox on the bus."""
        if agent_id not in self._registered:
            self._queues[agent_id] = deque(maxlen=self.MAX_QUEUE_SIZE)
            self._registered.add(agent_id)
            log.debug("MessageBus: registered agent '%s'", agent_id)

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent's mailbox from the bus."""
        self._registered.discard(agent_id)
        self._queues.pop(agent_id, None)
        self._subscriptions.pop(agent_id, None)

    @property
    def registered_agents(self) -> Set[str]:
        return set(self._registered)

    # ── Subscriptions ────────────────────────────────────────────────────────

    def subscribe(
        self,
        agent_id: str,
        msg_type: MessageType,
        handler: MessageHandler,
    ) -> None:
        """Register a callback for a specific message type.

        The handler will be called when a message of this type is
        delivered to this agent (either point-to-point or broadcast).
        """
        self._subscriptions[agent_id][msg_type].append(handler)

    # ── Message Sending ──────────────────────────────────────────────────────

    def send(self, message: AgentMessage) -> int:
        """Route a message to its intended recipient(s).

        Args:
            message: The AgentMessage to send.

        Returns:
            Number of agents the message was delivered to.
        """
        self.total_messages_sent += 1

        # Log to communication log
        self._communication_log.append(message.to_dict())

        delivered_count = 0

        if message.is_broadcast():
            self.total_broadcasts += 1
            for agent_id in self._registered:
                if agent_id != message.sender:  # Don't broadcast to self
                    delivered_count += self._deliver_to(agent_id, message)
        else:
            # Point-to-point
            delivered_count = self._deliver_to(message.receiver, message)
            if delivered_count == 0:
                log.warning(
                    "MessageBus: receiver '%s' not registered (msg %s from %s)",
                    message.receiver, message.msg_type.name, message.sender,
                )

        self.total_messages_delivered += delivered_count

        log.debug(
            "MessageBus: %s | %s -> %s | delivered=%d",
            message.msg_type.name,
            message.sender,
            message.receiver,
            delivered_count,
        )

        return delivered_count

    def _deliver_to(self, agent_id: str, message: AgentMessage) -> int:
        """Deliver a message to a single agent's mailbox and fire handlers."""
        if agent_id not in self._registered:
            return 0

        # Enqueue
        self._queues[agent_id].append(message)

        # Fire subscription handlers
        handlers = self._subscriptions.get(agent_id, {}).get(message.msg_type, [])
        for handler in handlers:
            try:
                handler(message)
            except Exception as exc:
                log.error(
                    "MessageBus: handler error for %s on agent %s: %s",
                    message.msg_type.name, agent_id, exc,
                )

        return 1

    # ── Message Retrieval ────────────────────────────────────────────────────

    def get_messages(
        self,
        agent_id: str,
        msg_type: Optional[MessageType] = None,
    ) -> List[AgentMessage]:
        """Retrieve and drain all pending messages for an agent.

        Args:
            agent_id: The agent to retrieve messages for.
            msg_type: Optional filter — only return this message type.

        Returns:
            List of pending messages (removed from queue).
        """
        if agent_id not in self._queues:
            return []

        queue = self._queues[agent_id]
        if msg_type is None:
            # Drain all
            messages = list(queue)
            queue.clear()
            return messages

        # Filter by type — drain only matching, keep others
        matching = []
        remaining = deque(maxlen=self.MAX_QUEUE_SIZE)
        for msg in queue:
            if msg.msg_type == msg_type:
                matching.append(msg)
            else:
                remaining.append(msg)
        self._queues[agent_id] = remaining
        return matching

    def peek_messages(
        self,
        agent_id: str,
        msg_type: Optional[MessageType] = None,
    ) -> List[AgentMessage]:
        """Peek at pending messages without removing them."""
        if agent_id not in self._queues:
            return []
        if msg_type is None:
            return list(self._queues[agent_id])
        return [m for m in self._queues[agent_id] if m.msg_type == msg_type]

    def has_messages(self, agent_id: str) -> bool:
        """Check if an agent has pending messages."""
        return bool(self._queues.get(agent_id))

    # ── Communication Log ────────────────────────────────────────────────────

    def get_communication_log(self, limit: int = 50) -> List[Dict]:
        """Return the last `limit` communication log entries.

        Each entry is a serialised AgentMessage dict, suitable for
        display in the mission dashboard and evaluation reports.
        """
        entries = list(self._communication_log)
        return entries[-limit:]

    def get_communication_log_for_mission(self, mission_id: str) -> List[Dict]:
        """Return all log entries related to a specific mission."""
        return [
            entry for entry in self._communication_log
            if entry.get("payload", {}).get("mission_id") == mission_id
        ]

    # ── Diagnostics ──────────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        """Return bus statistics for monitoring."""
        return {
            "registered_agents": len(self._registered),
            "total_messages_sent": self.total_messages_sent,
            "total_messages_delivered": self.total_messages_delivered,
            "total_broadcasts": self.total_broadcasts,
            "log_size": len(self._communication_log),
            "queue_sizes": {
                aid: len(q) for aid, q in self._queues.items()
            },
        }

    def reset(self) -> None:
        """Clear all queues and logs (used on simulation reset)."""
        for q in self._queues.values():
            q.clear()
        self._communication_log.clear()
        self.total_messages_sent = 0
        self.total_messages_delivered = 0
        self.total_broadcasts = 0
        log.info("AgentMessageBus reset.")

    def __repr__(self) -> str:
        return (
            f"AgentMessageBus(agents={len(self._registered)}, "
            f"sent={self.total_messages_sent})"
        )


# Module-level singleton
MESSAGE_BUS = AgentMessageBus()

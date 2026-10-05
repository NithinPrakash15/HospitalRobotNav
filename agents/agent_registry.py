"""
HospitalRobotNav — Agent Registry
====================================
Manages agent discovery, lifecycle, heartbeat monitoring, and
provides lookup services for the ``AgentCoordinator``.

The registry is the central directory of all agents in the fleet.
It tracks which agents are online, their capabilities, and their
current state.

Architecture Note (ROS2):
    In a ROS2 deployment this maps to the Node Discovery mechanism
    (ros2 node list) combined with a custom /agent_registry service.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Set

from utilities.event_bus import EVENT_BUS, HospitalEvent
from utilities.logger import get_logger
from .agent_base import AgentState, AgentStatus, HospitalAgent
from . import agent_config as cfg

log = get_logger(__name__)


class AgentRegistry:
    """Central registry for all hospital agents.

    Provides:
        - Agent registration and deregistration
        - Heartbeat-based liveness detection
        - Capability-based agent lookup
        - Fleet status summary

    Usage::

        registry = AgentRegistry()
        registry.register(delivery_agent)
        registry.register(reception_agent)

        available = registry.get_available_agents()
        delivery  = registry.get_agents_by_capability("deliver")
    """

    def __init__(self) -> None:
        self._agents: Dict[str, HospitalAgent] = {}
        self._last_heartbeat: Dict[str, float] = {}
        self._offline_ids: Set[str] = set()

    # ── Registration ─────────────────────────────────────────────────────────

    def register(self, agent: HospitalAgent) -> None:
        """Register an agent with the fleet."""
        self._agents[agent.agent_id] = agent
        self._last_heartbeat[agent.agent_id] = time.monotonic()

        EVENT_BUS.publish(HospitalEvent.AGENT_REGISTERED, data={
            "agent_id": agent.agent_id,
            "agent_type": agent.agent_type,
            "capabilities": list(agent.capabilities),
        }, source="agent_registry")

        log.info("Registered agent %s (%s) — fleet size: %d",
                 agent.agent_id, agent.agent_type, len(self._agents))

    def deregister(self, agent_id: str) -> None:
        """Remove an agent from the fleet."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            self._last_heartbeat.pop(agent_id, None)
            self._offline_ids.discard(agent_id)
            log.info("Deregistered agent %s — fleet size: %d",
                     agent_id, len(self._agents))

    # ── Lookup ───────────────────────────────────────────────────────────────

    def get_agent(self, agent_id: str) -> Optional[HospitalAgent]:
        return self._agents.get(agent_id)

    def get_all_agents(self) -> List[HospitalAgent]:
        return list(self._agents.values())

    def get_available_agents(self) -> List[HospitalAgent]:
        """Return agents that are IDLE and not marked offline."""
        return [
            a for a in self._agents.values()
            if a.is_available and a.agent_id not in self._offline_ids
        ]

    def get_agents_by_capability(self, capability: str) -> List[HospitalAgent]:
        """Return agents that have the given capability."""
        return [
            a for a in self._agents.values()
            if a.has_capability(capability) and a.agent_id not in self._offline_ids
        ]

    def get_agents_by_type(self, agent_type: str) -> List[HospitalAgent]:
        return [a for a in self._agents.values() if a.agent_type == agent_type]

    # ── Heartbeat Monitoring ─────────────────────────────────────────────────

    def record_heartbeat(self, agent_id: str) -> None:
        """Record that an agent sent a heartbeat."""
        self._last_heartbeat[agent_id] = time.monotonic()
        self._offline_ids.discard(agent_id)

    def check_heartbeats(self) -> List[str]:
        """Check for agents that missed their heartbeat deadline.

        Returns:
            List of agent IDs that are newly offline.
        """
        now = time.monotonic()
        newly_offline: List[str] = []

        for agent_id, last_hb in self._last_heartbeat.items():
            if agent_id in self._offline_ids:
                continue
            if now - last_hb > cfg.AGENT_HEARTBEAT_TIMEOUT:
                self._offline_ids.add(agent_id)
                newly_offline.append(agent_id)
                log.warning("Agent %s missed heartbeat — marked OFFLINE", agent_id)

        return newly_offline

    # ── Fleet Status ─────────────────────────────────────────────────────────

    @property
    def fleet_size(self) -> int:
        return len(self._agents)

    @property
    def online_count(self) -> int:
        return self.fleet_size - len(self._offline_ids)

    @property
    def available_count(self) -> int:
        return len(self.get_available_agents())

    def get_fleet_summary(self) -> Dict[str, int]:
        """Return a summary of agent states across the fleet."""
        summary: Dict[str, int] = {}
        for agent in self._agents.values():
            state_name = agent.state.name
            summary[state_name] = summary.get(state_name, 0) + 1
        summary["OFFLINE"] = len(self._offline_ids)
        return summary

    def broadcast_heartbeats(self) -> None:
        """Request all agents to send a heartbeat."""
        for agent in self._agents.values():
            if agent.agent_id not in self._offline_ids:
                agent.heartbeat()
                self.record_heartbeat(agent.agent_id)

    def __repr__(self) -> str:
        return (f"AgentRegistry(fleet={self.fleet_size}, "
                f"online={self.online_count}, "
                f"available={self.available_count})")

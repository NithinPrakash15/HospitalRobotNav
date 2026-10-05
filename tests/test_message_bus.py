"""
Unit tests for Multi-Agent Message Bus and Typed Agent Messages.
"""

import pytest
from agents.message_bus import AgentMessageBus
from agents.agent_messages import AgentMessage, MessageType


def test_message_bus_send_and_subscribe():
    bus = AgentMessageBus()
    bus.register_agent("NAV-01")
    bus.register_agent("COORD-01")
    received = []

    def on_nav_request(msg: AgentMessage):
        received.append(msg)

    bus.subscribe("NAV-01", MessageType.NAVIGATION_REQUEST, on_nav_request)

    msg = AgentMessage(
        msg_type=MessageType.NAVIGATION_REQUEST,
        sender="COORD-01",
        receiver="NAV-01",
        payload={"destination": (10, 20)},
        priority=1,
    )
    delivered = bus.send(msg)

    assert delivered == 1
    assert len(received) == 1
    assert received[0].payload["destination"] == (10, 20)
    assert received[0].sender == "COORD-01"


def test_message_bus_history_and_broadcast():
    bus = AgentMessageBus()
    bus.register_agent("DEL-01")
    bus.register_agent("EME-01")

    msg = AgentMessage(
        msg_type=MessageType.MISSION_COMPLETED,
        sender="COORD-01",
        receiver="broadcast",
        payload={"mission_id": "M100"},
    )
    count = bus.send(msg)
    assert count == 2

    history = bus.get_communication_log(limit=10)
    assert len(history) >= 1
    assert history[-1]["msg_type"] == "MISSION_COMPLETED"


def test_message_bus_unregister_and_queue():
    bus = AgentMessageBus()
    bus.register_agent("EXE-01")

    msg = AgentMessage(
        msg_type=MessageType.TASK_ASSIGNED,
        sender="COORD-01",
        receiver="EXE-01",
        payload={"task": "pickup"},
    )
    bus.send(msg)

    messages = bus.get_messages("EXE-01")
    assert len(messages) == 1
    assert messages[0].payload["task"] == "pickup"

    bus.unregister_agent("EXE-01")
    assert "EXE-01" not in bus.registered_agents

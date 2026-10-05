"""
HospitalRobotNav — End-to-End Mission Pipeline Coordinator
============================================================
Coordinates the full Embodied AI pipeline:
Natural Language Instruction ──► NLU ──► Spatial Grounding ──► Multi-Agent Task planning ──► Motion Planning & Navigation ──► Execution ──► Completion.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from agents.message_bus import MESSAGE_BUS
from agents.agent_messages import AgentMessage, MessageType
from agents.agent_registry import AgentRegistry
from agents.coordinator import AgentCoordinator
from agents.language_agent import LanguageAgent
from agents.environment_grounding_agent import EnvironmentGroundingAgent
from agents.task_execution_agent import TaskExecutionAgent
from agents.navigation_agent import NavigationAgent
from agents.delivery_agent import DeliveryAgent
from world_state.hospital_world_state import HospitalWorldState
from utilities.logger import get_logger

log = get_logger(__name__)


class HospitalMissionPipeline:
    """
    End-to-End Mission Pipeline.
    
    Orchestrates agent instances, wires them via the MESSAGE_BUS,
    feeds them environmental references, and steps the execution loop.
    Supports headless simulation testing and active simulator integration.
    """

    def __init__(self, simulator: Optional[Any] = None) -> None:
        self.simulator = simulator
        
        # Core world state reference
        if simulator is not None:
            self.world_state = simulator.world_state
            self.registry = simulator.agent_registry
            self.coordinator = simulator.agent_coordinator
            self.medicine_manager = simulator.medicine_manager
            self.robot = simulator.robot
            self.occupancy_grid = simulator.occupancy_grid
        else:
            # Headless mock setup for standalone testing
            self.world_state = HospitalWorldState()
            self.registry = AgentRegistry()
            self.coordinator = AgentCoordinator(self.registry)
            self.medicine_manager = None
            self.robot = None
            self.occupancy_grid = None

        # ── Instantiate curating specialist agents ───────────────────────────
        
        # 1. Language Interaction Agent
        self.language_agent = LanguageAgent()
        self.registry.register(self.language_agent)

        # 2. Grounding Agent
        self.grounding_agent = EnvironmentGroundingAgent(self.world_state)
        self.registry.register(self.grounding_agent)

        # 3. Task Execution Agent
        self.task_execution_agent = TaskExecutionAgent(self.medicine_manager)
        self.registry.register(self.task_execution_agent)

        # 4. Navigation Agent
        self.navigation_agent = NavigationAgent(self.robot, self.occupancy_grid)
        self.registry.register(self.navigation_agent)

        # Legacy agent matching for Coordinator bidding compatibility
        # If Coordinator executes bidding, it looks for delivery/emergency agents
        if simulator is None:
            self.delivery_agent = DeliveryAgent()
            self.registry.register(self.delivery_agent)
        else:
            # Simulator already registers standard DeliveryAgent/ReceptionAgent/EmergencyAgent
            # We fetch them or wire them accordingly
            self.delivery_agent = self.registry.get_agents_by_type("delivery")[0]

        log.info("HospitalMissionPipeline initialized successfully with 5-agent core fleet.")

    def run_command(self, natural_language_command: str) -> str:
        """Inject a natural language instruction to start the pipeline."""
        log.info("Pipeline Injecting command: '%s'", natural_language_command)
        
        # Reset MESSAGE_BUS to clear any stale messages from previous runs
        MESSAGE_BUS.reset()

        # Build and route transcript ready message (simulating speech recogniser completion)
        transcript_msg = AgentMessage(
            msg_type=MessageType.SPEECH_TRANSCRIPT_READY,
            sender="user",
            receiver=self.language_agent.agent_id,
            payload={"text": natural_language_command}
        )
        MESSAGE_BUS.send(transcript_msg)
        
        # Find created mission request id
        pending_msgs = MESSAGE_BUS.peek_messages("coordinator", MessageType.MISSION_REQUEST)
        if pending_msgs:
            return pending_msgs[0].payload.get("mission_id", "")
        return ""

    def step(self, dt: float) -> None:
        """Step each active agent's frame update (called every frame)."""
        # Execute updates on agents that require internal timers or position monitoring
        self.grounding_agent.update(dt)
        self.task_execution_agent.update(dt)
        self.navigation_agent.update(dt)

        if hasattr(self.delivery_agent, "update"):
            self.delivery_agent.update(dt)

    def is_mission_active(self, mission_id: str) -> bool:
        """Check if Coordinator is currently processing the mission."""
        return mission_id in self.coordinator.active_missions

    def get_mission_status(self, mission_id: str) -> Optional[str]:
        """Get current step details for active mission."""
        ctx = self.coordinator.active_missions.get(mission_id)
        if not ctx:
            return None
        
        idx = ctx["current_step_idx"]
        steps = ctx["steps"]
        state = ctx["state"]
        
        if idx < len(steps):
            curr_step = steps[idx]
            return f"State: {state} | Step {idx+1}/{len(steps)}: {curr_step.description}"
        return "Finishing..."

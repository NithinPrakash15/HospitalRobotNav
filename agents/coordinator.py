"""
HospitalRobotNav — Agent Coordinator (Contract-Net + Mission Lifecycle Manager)
==================================================================================
Central coordinator managing multi-agent task allocation (Contract-Net Protocol)
and supervising the end-to-end task execution pipeline via the Agent Message Bus.
"""

from __future__ import annotations

import time
import uuid
import random
from typing import Any, Dict, List, Optional, Tuple

from utilities.event_bus import EVENT_BUS, HospitalEvent
from utilities.logger import get_logger
from agents.agent_base import AgentBid, AgentState, HospitalAgent
from agents.agent_registry import AgentRegistry
from agents.agent_messages import AgentMessage, MessageType, NavigationState
from agents.message_bus import MESSAGE_BUS
from language.command_resolver import MissionRequest, MissionType
from missions.mission_planner import MissionPlanner
from missions.mission_types import TaskStep, TaskType, MissionPlan
from . import agent_config as cfg

log = get_logger(__name__)

GridPos = Tuple[int, int]


class AgentCoordinator:
    """
    Coordinator and Task Allocator for the Multi-Agent System.
    
    1. Legacies/Demos: Performs Contract-Net Protocol auctions (broadcast_mission).
    2. Embodied AI Lifecycle: Decomposes mission requests into atomic steps, 
       manages grounding, navigation and execution transitions, tracks active mission state
       and coordinates dynamic recovery.
    """

    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry
        self._assignment_log: List[Dict[str, Any]] = []
        self._planner = MissionPlanner()
        self.active_missions: Dict[str, Dict[str, Any]] = {}
        self._db_engine: Optional[Any] = None

        # Register coordinator on message bus
        MESSAGE_BUS.register_agent("coordinator")
        
        # Subscribe to lifecycle messages
        MESSAGE_BUS.subscribe("coordinator", MessageType.MISSION_REQUEST, self.handle_mission_request)
        MESSAGE_BUS.subscribe("coordinator", MessageType.GROUNDING_RESULT, self.handle_grounding_result)
        MESSAGE_BUS.subscribe("coordinator", MessageType.NAVIGATION_STATUS, self.handle_navigation_status)
        MESSAGE_BUS.subscribe("coordinator", MessageType.TASK_COMPLETED, self.handle_task_completed)
        MESSAGE_BUS.subscribe("coordinator", MessageType.TASK_FAILED, self.handle_task_failed)
        MESSAGE_BUS.subscribe("coordinator", MessageType.OBSTACLE_DETECTED, self.handle_obstacle_detected)
        
        log.info("AgentCoordinator registered on MESSAGE_BUS.")

    def set_db_engine(self, engine: Any) -> None:
        """Connect the hospital database query engine.
        
        Args:
            engine: DBQueryEngine instance.
        """
        self._db_engine = engine
        log.info("AgentCoordinator: Database query engine connected.")

    # ─── Legacy / Integration Bidding Auction ──────────────────────────────────

    def broadcast_mission(
        self,
        mission_type: str,
        mission_id: str,
        destination: Optional[GridPos],
        priority: int,
        mission_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[HospitalAgent], Optional[AgentBid]]:
        """Broadcast a call-for-proposals and select the best agent."""
        agents = self._registry.get_available_agents()
        if not agents:
            log.warning("No agents available for mission %s", mission_id)
            return None, None

        log.info("Broadcasting mission %s (%s, pri=%d) to %d agents",
                 mission_id, mission_type, priority, len(agents))

        # Collect bids
        bids: List[Tuple[HospitalAgent, AgentBid]] = []
        for agent in agents:
            bid = agent.evaluate_mission(mission_type, destination, priority)
            if bid and bid.score >= cfg.MIN_BID_CONFIDENCE:
                bids.append((agent, bid))
                log.debug("  Bid from %s: score=%.3f", agent.agent_id, bid.score)

        if not bids:
            log.warning("No bids received for mission %s", mission_id)
            EVENT_BUS.publish(HospitalEvent.MISSION_FAILED, data={
                "mission_id": mission_id,
                "reason": "no_bids",
            }, source="coordinator")
            return None, None

        # Select winner
        winner_agent, winner_bid = self._select_winner(bids)

        # Assign
        data = mission_data or {}
        data["mission_id"] = mission_id
        data["mission_type"] = mission_type
        data["destination_pos"] = destination
        data["priority"] = priority

        accepted = winner_agent.accept_mission(mission_id, data)
        if not accepted:
            log.warning("Winner %s declined after selection", winner_agent.agent_id)
            return None, None

        self._assignment_log.append({
            "mission_id": mission_id,
            "agent_id": winner_agent.agent_id,
            "bid_score": winner_bid.score,
            "timestamp": time.monotonic(),
            "total_bids": len(bids),
        })

        EVENT_BUS.publish(HospitalEvent.AGENT_TASK_ASSIGNED, data={
            "mission_id": mission_id,
            "agent_id": winner_agent.agent_id,
            "bid_score": winner_bid.score,
        }, source="coordinator")

        log.info("Mission %s assigned to %s (score=%.3f, ETA=%.0fs)",
                 mission_id, winner_agent.agent_id,
                 winner_bid.score, winner_bid.estimated_eta)

        return winner_agent, winner_bid

    def _select_winner(
        self,
        bids: List[Tuple[HospitalAgent, AgentBid]],
    ) -> Tuple[HospitalAgent, AgentBid]:
        """Select the winning bid with tie-breaking."""
        bids.sort(key=lambda ab: ab[1].score, reverse=True)
        top_score = bids[0][1].score

        # Collect ties
        tied = [(a, b) for a, b in bids if abs(b.score - top_score) < 1e-4]

        if len(tied) == 1:
            return tied[0]

        # Tie-break
        strategy = cfg.TIE_BREAK_STRATEGY
        if strategy == "nearest":
            tied.sort(key=lambda ab: ab[1].distance)
        elif strategy == "highest_battery":
            tied.sort(key=lambda ab: ab[1].battery_pct, reverse=True)
        elif strategy == "random":
            random.shuffle(tied)

        return tied[0]

    # ─── Multi-Agent Lifecycle Coordination ────────────────────────────────────

    def handle_mission_request(self, message: AgentMessage) -> None:
        """Process natural-language request and trigger multi-step decomposition."""
        payload = message.payload
        mission_id = payload.get("mission_id", f"MSN-{uuid.uuid4().hex[:6].upper()}")
        mission_type_str = payload.get("mission_type", "NAVIGATE")
        raw_text = payload.get("raw_text", "")
        priority = payload.get("priority", 4)
        
        log.info("Coordinator processing MISSION_REQUEST: %s (%s)", mission_id, mission_type_str)

        # 1. Map string type to MissionType enum
        mission_enum = None
        for m in MissionType:
            if m.name == mission_type_str:
                mission_enum = m
                break
        
        if not mission_enum:
            mission_enum = MissionType.NAVIGATE

        # 2. Reconstruct high-level request
        req = MissionRequest(
            mission_type=mission_enum,
            item=payload.get("item"),
            quantity_num=payload.get("quantity_num", 1),
            priority=priority,
            raw_text=raw_text
        )
        
        # Populate locations
        locs = payload.get("locations", [])
        if locs:
            if len(locs) > 1:
                req.pickup_location = locs[0]
                req.delivery_location = locs[1]
            else:
                req.delivery_location = locs[0]

        # 3. Formulate sequence of atomic tasks
        self._planner.semantic_map = getattr(self._registry, "semantic_map", None)
        try:
            plan: MissionPlan = self._planner.plan(req)
        except Exception as e:
            log.exception("Coordinator failed to decompose mission request:")
            self._reply_mission_failed(mission_id, message.sender, f"Decomposition failed: {e}")
            return

        # 4. Bid auction for the physical robot execution (Delivery or Emergency)
        dest_pos = plan.steps[0].destination_pos if plan.steps else None
        assigned_agent, bid = self.broadcast_mission(
            mission_type_str, mission_id, dest_pos, priority, payload
        )

        if not assigned_agent:
            self._reply_mission_failed(mission_id, message.sender, "No suitable execution agent found.")
            return

        # 5. Store mission context
        self.active_missions[mission_id] = {
            "plan_id": plan.plan_id,
            "mission_id": mission_id,
            "mission_type": mission_type_str,
            "assigned_agent_id": assigned_agent.agent_id,
            "steps": plan.steps,
            "current_step_idx": 0,
            "sender_id": message.sender,
            "state": "RUNNING",
            "priority": priority,
            "payload": payload
        }

        # Accept request
        MESSAGE_BUS.send(AgentMessage(
            msg_type=MessageType.MISSION_ACCEPTED,
            sender="coordinator",
            receiver=message.sender,
            in_reply_to=message.msg_id,
            payload={"mission_id": mission_id}
        ))

        # Start execution loop
        self._execute_next_step(mission_id)

    def _execute_next_step(self, mission_id: str) -> None:
        """Process the active step index of the designated mission."""
        ctx = self.active_missions.get(mission_id)
        if not ctx:
            return

        idx = ctx["current_step_idx"]
        steps = ctx["steps"]

        if idx >= len(steps):
            # All steps completed successfully!
            self._complete_mission(mission_id)
            return

        step: TaskStep = steps[idx]
        log.info("Coordinator advancing mission %s to step %d/%d: %s", 
                 mission_id, idx + 1, len(steps), step.description)

        # State updates
        EVENT_BUS.publish(HospitalEvent.MISSION_STEP_STARTED, data={
            "mission_id": mission_id,
            "step_index": idx,
            "description": step.description
        }, source="coordinator")

        # 1. Check if spatial grounding is required
        if step.task_type in (TaskType.NAVIGATE, TaskType.ESCORT):
            # Check relative spatial expression or missing position
            is_relative = step.destination and any(
                keyword in step.destination.lower() 
                for keyword in ("nearest", "opposite", "next to", "between", "less congested")
            )
            
            if step.destination_pos is None or is_relative:
                # Dispatch GROUNDING_REQUEST to grounding agent
                ctx["state"] = "GROUNDING"
                grounding_msg = AgentMessage(
                    msg_type=MessageType.GROUNDING_REQUEST,
                    sender="coordinator",
                    receiver="GROUND-AGENT",  # Broadcast or direct if registered
                    payload={
                        "query": step.destination,
                        "mission_id": mission_id
                    }
                )
                
                # Check direct routing name
                g_agent = self._registry.get_agents_by_type("grounding")
                if g_agent:
                    grounding_msg.receiver = g_agent[0].agent_id
                    
                MESSAGE_BUS.send(grounding_msg)
                log.info("Coordinator triggered spatial grounding request for: '%s'", step.destination)
                return

        # 2. Proceed to dispatch the physical execution action
        self._dispatch_step_action(mission_id, step)

    def _dispatch_step_action(self, mission_id: str, step: TaskStep) -> None:
        """Route step action to appropriate navigation or task agent."""
        ctx = self.active_missions[mission_id]
        agent_id = ctx["assigned_agent_id"]

        if step.task_type in (TaskType.NAVIGATE, TaskType.ESCORT):
            ctx["state"] = "NAVIGATION"
            
            # Send NAVIGATION_REQUEST to NavigationAgent
            nav_agents = self._registry.get_agents_by_type("navigation")
            nav_receiver = nav_agents[0].agent_id if nav_agents else agent_id
            
            nav_msg = AgentMessage(
                msg_type=MessageType.NAVIGATION_REQUEST,
                sender="coordinator",
                receiver=nav_receiver,
                payload={
                    "destination_pos": step.destination_pos,
                    "destination_name": step.destination,
                    "mission_id": mission_id,
                    "priority": ctx["priority"],
                    "escort": step.task_type == TaskType.ESCORT
                }
            )
            MESSAGE_BUS.send(nav_msg)
            
        elif step.task_type in (TaskType.COLLECT, TaskType.DELIVER, TaskType.INTERACT, TaskType.ALERT):
            ctx["state"] = "EXECUTION"
            
            # Send TASK_ASSIGNED to TaskExecutionAgent
            exec_agents = self._registry.get_agents_by_type("execution")
            exec_receiver = exec_agents[0].agent_id if exec_agents else agent_id
            
            exec_msg = AgentMessage(
                msg_type=MessageType.TASK_ASSIGNED,
                sender="coordinator",
                receiver=exec_receiver,
                payload={
                    "task_type": step.task_type.name,
                    "item": step.item,
                    "quantity_num": ctx["payload"].get("quantity_num", 1),
                    "destination": step.destination,
                    "mission_id": mission_id
                }
            )
            MESSAGE_BUS.send(exec_msg)

    # ─── Message Bus Callback Receivers ───────────────────────────────────────

    def handle_grounding_result(self, message: AgentMessage) -> None:
        """Update step coordinates after grounding agent returns metrics."""
        payload = message.payload
        mission_id = payload.get("mission_id", "")
        success = payload.get("success", False)
        
        ctx = self.active_missions.get(mission_id)
        if not ctx or ctx["state"] != "GROUNDING":
            return

        if not success:
            reason = payload.get("reason", "Grounding resolution failed")
            self._handle_step_failure(mission_id, f"Grounding failed: {reason}")
            return

        resolved_pos = payload.get("resolved_position")
        idx = ctx["current_step_idx"]
        step: TaskStep = ctx["steps"][idx]
        
        log.info("Coordinator integrated grounded position %s for step '%s'", resolved_pos, step.destination)
        step.destination_pos = resolved_pos
        
        # Grounding complete: dispatch step action
        self._dispatch_step_action(mission_id, step)

    def handle_navigation_status(self, message: AgentMessage) -> None:
        """Transition steps based on NavigationAgent reports."""
        payload = message.payload
        mission_id = payload.get("mission_id", "")
        status_name = payload.get("status", "")
        
        ctx = self.active_missions.get(mission_id)
        if not ctx or ctx["state"] != "NAVIGATION":
            return

        log.debug("Coordinator received NavigationAgent report for %s: %s", mission_id, status_name)

        if status_name == NavigationState.GOAL_REACHED.name:
            self._complete_current_step(mission_id)
        elif status_name == NavigationState.NAVIGATION_FAILED.name:
            self._handle_step_failure(mission_id, "Navigation execution failed")

    def handle_task_completed(self, message: AgentMessage) -> None:
        """Advance mission index after TaskExecutionAgent success."""
        payload = message.payload
        mission_id = payload.get("mission_id", "")
        
        ctx = self.active_missions.get(mission_id)
        if not ctx or ctx["state"] != "EXECUTION":
            return

        self._complete_current_step(mission_id)

    def handle_task_failed(self, message: AgentMessage) -> None:
        """Coordinate fallback or fail mission."""
        payload = message.payload
        mission_id = payload.get("mission_id", "")
        reason = payload.get("reason", "Task step execution failed")
        
        self._handle_step_failure(mission_id, f"Execution failed: {reason}")

    def handle_obstacle_detected(self, message: AgentMessage) -> None:
        """Trigger replan warning when path blocked."""
        payload = message.payload
        mission_id = payload.get("mission_id", "")
        obstacle_pos = payload.get("position")
        
        ctx = self.active_missions.get(mission_id)
        if not ctx:
            return

        log.warning("Coordinator warned of dynamic obstacle at %s on mission %s", obstacle_pos, mission_id)
        EVENT_BUS.publish(HospitalEvent.OBSTACLE_DETECTED, data={
            "mission_id": mission_id,
            "position": obstacle_pos
        }, source="coordinator")

        # Command Navigation agent to replan
        nav_agents = self._registry.get_agents_by_type("navigation")
        if nav_agents:
            MESSAGE_BUS.send(AgentMessage(
                msg_type=MessageType.REPLAN_REQUEST,
                sender="coordinator",
                receiver=nav_agents[0].agent_id,
                payload={"mission_id": mission_id}
            ))

    # ─── Mission State Transitions ───────────────────────────────────────────

    def _complete_current_step(self, mission_id: str) -> None:
        """Advance the index and evaluate completion."""
        ctx = self.active_missions[mission_id]
        idx = ctx["current_step_idx"]
        step = ctx["steps"][idx]

        EVENT_BUS.publish(HospitalEvent.MISSION_STEP_COMPLETE, data={
            "mission_id": mission_id,
            "step_index": idx,
            "description": step.description
        }, source="coordinator")

        # Sync items to fleet robot if needed
        # (Legacies handle item sync in delivery_agent, we sync metadata here)
        if step.task_type == TaskType.COLLECT:
            # Tell DeliveryAgent we collected
            agent = self._registry.get_agent(ctx["assigned_agent_id"])
            if hasattr(agent, "pickup_item") and step.destination_pos:
                agent.pickup_item(step.item or "Paracetamol", step.destination_pos)

        elif step.task_type == TaskType.DELIVER:
            agent = self._registry.get_agent(ctx["assigned_agent_id"])
            if hasattr(agent, "deliver_item"):
                agent.deliver_item()

        ctx["current_step_idx"] += 1
        self._execute_next_step(mission_id)

    def _handle_step_failure(self, mission_id: str, reason: str) -> None:
        """Initiate dynamic recovery replanning or fail mission."""
        ctx = self.active_missions.get(mission_id)
        if not ctx:
            return

        log.warning("Coordinator handling step failure on mission %s: %s", mission_id, reason)
        
        # Dynamic recovery decision-making:
        # If nearest pharmacy navigation failed, check if there's an alternative pharmacy available
        idx = ctx["current_step_idx"]
        step: TaskStep = ctx["steps"][idx]

        if step.task_type == TaskType.NAVIGATE and step.destination and "pharmacy" in step.destination.lower():
            # Attempt to reroute to alternative pharmacy
            log.info("Recovery: attempting to reroute to alternative pharmacy.")
            sem_map = getattr(self._registry, "semantic_map", None)
            if sem_map is not None:
                # Find all pharmacies in room database
                from maps.hospital.room_definitions import RoomCategory
                robot_pos = (80, 11)  # Default
                # Find alternative
                all_phms = [r for r in sem_map.get_destination_list() if "pharmacy" in r[1].lower()]
                if len(all_phms) > 1:
                    # Choose different pharmacy center
                    current_center = step.destination_pos
                    alt_pos = None
                    alt_name = ""
                    for pid, label, entry in all_phms:
                        if entry != current_center:
                            alt_pos = entry
                            alt_name = label
                            break
                    if alt_pos:
                        log.info("Recovery: Rerouting mission %s to alternative: '%s' at %s", 
                                 mission_id, alt_name, alt_pos)
                        step.destination_pos = alt_pos
                        step.destination = alt_name
                        step.description = f"Collect {step.item} from {alt_name}"
                        # Notify interface
                        EVENT_BUS.publish(HospitalEvent.REPLANNING_STARTED, data={
                            "mission_id": mission_id,
                            "reason": "alternative_pharmacy"
                        }, source="coordinator")
                        # Dispatch navigation request again
                        self._dispatch_step_action(mission_id, step)
                        return

        # Fallback: Fail the entire mission
        self._fail_mission(mission_id, reason)

    def _complete_mission(self, mission_id: str) -> None:
        """Mark mission complete and notify systems."""
        ctx = self.active_missions.pop(mission_id)
        ctx["state"] = "COMPLETED"
        log.info("Coordinator: MISSION %s COMPLETED SUCCESSFULLY.", mission_id)

        # Notify assigned agent
        agent = self._registry.get_agent(ctx["assigned_agent_id"])
        if agent:
            agent.report_completion(mission_id, success=True)

        # Publish completed event
        EVENT_BUS.publish(HospitalEvent.MISSION_COMPLETE, data={
            "mission_id": mission_id,
            "agent_id": ctx["assigned_agent_id"]
        }, source="coordinator")

        # Send broadcast complete
        MESSAGE_BUS.send(AgentMessage(
            msg_type=MessageType.MISSION_COMPLETED,
            sender="coordinator",
            payload={"mission_id": mission_id}
        ))

    def _fail_mission(self, mission_id: str, reason: str) -> None:
        """Cancel execution states and broadcast failed."""
        ctx = self.active_missions.pop(mission_id, None)
        if not ctx:
            return
            
        ctx["state"] = "FAILED"
        log.error("Coordinator: MISSION %s FAILED (%s)", mission_id, reason)

        # Notify assigned agent
        agent = self._registry.get_agent(ctx["assigned_agent_id"])
        if agent:
            agent.report_completion(mission_id, success=False)

        # Publish failed event
        EVENT_BUS.publish(HospitalEvent.MISSION_FAILED, data={
            "mission_id": mission_id,
            "reason": reason
        }, source="coordinator")

        # Send broadcast fail
        MESSAGE_BUS.send(AgentMessage(
            msg_type=MessageType.MISSION_FAILED,
            sender="coordinator",
            payload={"mission_id": mission_id, "reason": reason}
        ))

    def _reply_mission_failed(self, mission_id: str, receiver: str, reason: str) -> None:
        """Direct reply to sender when request rejected."""
        MESSAGE_BUS.send(AgentMessage(
            msg_type=MessageType.MISSION_FAILED,
            sender="coordinator",
            receiver=receiver,
            payload={"mission_id": mission_id, "reason": reason}
        ))

    # ─── Diagnostics ──────────────────────────────────────────────────────────

    @property
    def total_assignments(self) -> int:
        return len(self._assignment_log)

    def get_assignment_log(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._assignment_log[-limit:]

    def get_fleet_summary(self) -> Dict[str, Any]:
        """Get a structured snapshot of all fleet agents and active missions."""
        agents_info = []
        for agent in self._registry.get_all_agents():
            agents_info.append({
                "agent_id": agent.agent_id,
                "agent_type": getattr(agent, "agent_type", "general"),
                "state": agent.state.name if hasattr(agent.state, "name") else str(agent.state),
                "battery": getattr(agent, "battery_pct", getattr(agent, "battery_level", 100.0)),
                "position": getattr(agent, "position", (0, 0)),
                "current_mission": getattr(agent, "_current_mission_id", None),
            })
        return {
            "total_agents": len(agents_info),
            "active_missions": len(self.active_missions),
            "agents": agents_info,
        }

    def __repr__(self) -> str:
        return f"AgentCoordinator(assignments={self.total_assignments}, active={len(self.active_missions)})"

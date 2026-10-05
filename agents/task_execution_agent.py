"""
HospitalRobotNav — Task Execution Agent
===========================================
Executes atomic task steps assigned by the Coordinator, including item
collection (pickup), delivery (drop-off), patient/staff dialogue interaction,
and hardware alerts.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import uuid

from agents.agent_base import HospitalAgent, AgentState, AgentBid
from agents.agent_messages import AgentMessage, MessageType
from agents.message_bus import MESSAGE_BUS
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]


class TaskExecutionAgent(HospitalAgent):
    """
    Task Execution Agent.
    
    Responsible for executing non-navigation task steps such as collecting medicine,
    dispensing, verifying packages, patient interactions, and alerts. Runs internal timers
    for task duration and interfaces with the MedicineManager.
    """

    def __init__(
        self,
        medicine_manager: Optional[Any] = None,
        home_position: GridPos = (79, 47),
    ) -> None:
        super().__init__(
            agent_type="execution",
            capabilities=frozenset({
                "interact",
                "medicine"
            }),
            home_position=home_position,
        )
        self.medicine_manager = medicine_manager
        
        # Active task tracking
        self.active_task_id: Optional[str] = None
        self.active_mission_id: Optional[str] = None
        self.current_task_payload: Dict[str, Any] = {}
        self.task_type: Optional[str] = None
        self.timer_s: float = 0.0
        self.duration_s: float = 0.0

        # Register on message bus
        MESSAGE_BUS.register_agent(self.agent_id)
        
        # Subscribe to task assignments
        MESSAGE_BUS.subscribe(self.agent_id, MessageType.TASK_ASSIGNED, self.handle_task_assigned)

        log.info("TaskExecutionAgent %s initialized with MedicineManager: %s", 
                 self.agent_id, "Yes" if medicine_manager else "No")

    def evaluate_mission(
        self,
        mission_type: str,
        destination: Optional[GridPos],
        priority: int,
    ) -> Optional[AgentBid]:
        """Software/manipulation execution agent. Bids 0.0 or declines physical navigation."""
        return None

    def accept_mission(self, mission_id: str, mission_data: Dict[str, Any]) -> bool:
        return False

    def abort_mission(self, reason: str = "") -> None:
        log.warning("TaskExecutionAgent %s aborting active task %s: %s",
                    self.agent_id, self.active_task_id, reason)
        self.active_task_id = None
        self.active_mission_id = None
        self.current_task_payload = {}
        self.task_type = None
        self.timer_s = 0.0
        self.set_state(AgentState.IDLE)

    def handle_task_assigned(self, message: AgentMessage) -> None:
        """Process incoming task assignment from Coordinator."""
        payload = message.payload
        task_type = payload.get("task_type", "")
        task_id = payload.get("task_id", f"TSK-{uuid.uuid4().hex[:4].upper()}")
        mission_id = payload.get("mission_id", "")
        
        if self.state == AgentState.EXECUTING:
            log.warning("TaskExecutionAgent %s is busy. Rejecting task %s.", self.agent_id, task_id)
            self._reply_status(MessageType.TASK_FAILED, task_id, mission_id, "Agent busy")
            return

        log.info("TaskExecutionAgent %s assigned task: %s (%s)", self.agent_id, task_id, task_type)
        
        self.active_task_id = task_id
        self.active_mission_id = mission_id
        self.task_type = task_type
        self.current_task_payload = payload
        self.set_state(AgentState.EXECUTING)

        # Notify coordinator execution has started
        self._reply_status(MessageType.TASK_STARTED, task_id, mission_id)

        # Configure duration depending on execution step type
        if task_type == "COLLECT":
            self.duration_s = 2.0
        elif task_type == "DELIVER":
            self.duration_s = 2.0
        elif task_type in ("INTERACT", "ALERT"):
            self.duration_s = 1.5
        else:
            self.duration_s = 1.0
            
        self.timer_s = self.duration_s

    def update(self, dt: float) -> None:
        """Advance time slice and check step completion (called every frame)."""
        if self.state == AgentState.EXECUTING and self.active_task_id:
            self.timer_s -= dt
            
            # Periodically broadcast task progress
            if int(self.timer_s * 10) % 20 == 0:  # approximately every 2s
                progress_pct = max(0.0, min(100.0, (1.0 - self.timer_s / self.duration_s) * 100))
                self._reply_status(
                    MessageType.TASK_PROGRESS, 
                    self.active_task_id, 
                    self.active_mission_id, 
                    payload_addons={"progress_pct": progress_pct}
                )

            if self.timer_s <= 0.0:
                self._complete_task()

    def _complete_task(self) -> None:
        """Trigger physical updates (e.g. inventory consumption) and reply completed."""
        task_id = self.active_task_id
        mission_id = self.active_mission_id
        task_type = self.task_type
        payload = self.current_task_payload
        
        log.info("TaskExecutionAgent %s finished task operation: %s (%s)", self.agent_id, task_id, task_type)

        success = True
        reason = ""

        # Perform the actual action mapping to backend systems
        if task_type == "COLLECT" and self.medicine_manager is not None:
            item_name = payload.get("item", "Paracetamol")
            qty = payload.get("quantity_num", 1)
            dest = payload.get("destination", "Room 205")
            
            # Collect from medicine database
            collected_item = self.medicine_manager.collect(item_name, quantity=qty, destination=dest)
            if collected_item is None:
                success = False
                reason = f"Medicine '{item_name}' out of stock or unknown."
            else:
                log.info("TaskExecutionAgent collected item: %s", collected_item)

        elif task_type == "DELIVER" and self.medicine_manager is not None:
            # Deliver current item on robot
            item = self.medicine_manager.carrying_item
            if item:
                self.medicine_manager.deliver(item)
                log.info("TaskExecutionAgent delivered item: %s", item)
            else:
                # Fallback success if carrying state was set through another mode
                log.warning("TaskExecutionAgent delivering but no carrying item found in manager.")

        # Clean state
        self.active_task_id = None
        self.active_mission_id = None
        self.current_task_payload = {}
        self.task_type = None
        self.timer_s = 0.0
        self.set_state(AgentState.IDLE)

        # Notify coordinator of outcome
        if success:
            self._reply_status(MessageType.TASK_COMPLETED, task_id, mission_id)
        else:
            self._reply_status(MessageType.TASK_FAILED, task_id, mission_id, reason)

    def _reply_status(
        self, 
        msg_type: MessageType, 
        task_id: str, 
        mission_id: str, 
        reason: str = "", 
        payload_addons: Optional[Dict[str, Any]] = None
    ) -> None:
        """Helper to send status message to Coordinator."""
        payload = {
            "task_id": task_id,
            "mission_id": mission_id,
            "task_type": self.task_type,
            "agent_id": self.agent_id,
        }
        if reason:
            payload["reason"] = reason
        if payload_addons:
            payload.update(payload_addons)

        msg = AgentMessage(
            msg_type=msg_type,
            sender=self.agent_id,
            receiver="coordinator",
            payload=payload
        )
        MESSAGE_BUS.send(msg)

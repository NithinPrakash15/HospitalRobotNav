"""
HospitalRobotNav — Navigation Agent
====================================
Specialized autonomous agent responsible for topological graph routing,
multi-algorithm path planning (A*, D* Lite, Theta*, Hybrid A*), dynamic obstacle
replanning, and motion controller setpoint generation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from agents.agent_base import AgentBid, AgentState, HospitalAgent
from agents.agent_messages import AgentMessage, MessageType, NavigationState
from agents.message_bus import MESSAGE_BUS
from robot.robot import Mission, RobotState
from utilities.logger import get_logger

log = get_logger(__name__)

GridPos = Tuple[int, int]


class NavigationAgent(HospitalAgent):
    """
    Autonomous Navigation Agent.
    
    Receives validated coordinate goals, computes paths using selected algorithms,
    handles dynamic replanning when corridors are blocked by obstacles, and publishes
    navigation status reports to the Coordinator.
    """

    def __init__(
        self,
        robot: Optional[Any] = None,
        occupancy_grid: Optional[Any] = None,
        home_position: GridPos = (80, 11),
    ) -> None:
        super().__init__(
            agent_type="navigation",
            capabilities=frozenset({
                "navigate",
                "transport"
            }),
            home_position=home_position,
        )
        self.robot = robot
        self.occupancy_grid = occupancy_grid

        # State tracking
        self.active_mission_id: Optional[str] = None
        self.active_goal_pos: Optional[GridPos] = None
        self.active_goal_name: str = ""
        self.active_planner_name: str = "A*"
        self.total_paths_computed: int = 0
        self.total_replans_executed: int = 0
        self._waiting_for_arrival: bool = False

        # Register on message bus
        MESSAGE_BUS.register_agent(self.agent_id)
        
        # Subscribe to navigation and replanning requests
        MESSAGE_BUS.subscribe(self.agent_id, MessageType.NAVIGATION_REQUEST, self.handle_navigation_request)
        MESSAGE_BUS.subscribe(self.agent_id, MessageType.REPLAN_REQUEST, self.handle_replan_request)

        log.info("NavigationAgent %s initialized with Robot: %s", 
                 self.agent_id, "Yes" if robot else "No")

    def evaluate_mission(
        self,
        mission_type: str,
        destination: Optional[GridPos],
        priority: int,
    ) -> Optional[AgentBid]:
        """Evaluate suitability for navigation/transport missions."""
        if not self.is_available:
            return None

        # Highly capable for navigation and fetching tasks
        type_weights = {
            "NAVIGATE": 0.95,
            "FETCH_WHEELCHAIR": 0.60,
            "PATIENT_ESCORT": 0.85,
            "AREA_PATROL": 0.80,
        }
        if mission_type not in type_weights:
            return None

        base_score = type_weights[mission_type]
        dist = self.distance_to(destination) if destination else 0.0
        dist_factor = max(0.2, 1.0 - (dist / 120.0))
        batt_factor = self.battery_pct / 100.0
        final_score = base_score * 0.4 + dist_factor * 0.3 + batt_factor * 0.3

        return AgentBid(
            agent_id=self.agent_id,
            score=round(final_score, 3),
            estimated_eta=round(dist * 0.8 + 5.0, 1),
            battery_pct=self.battery_pct,
            distance=round(dist, 1),
            rationale=f"NavigationAgent ready ({self.active_planner_name}, dist={dist:.1f}, batt={self.battery_pct:.0f}%)",
        )

    def accept_mission(self, mission_id: str, mission_data: Dict[str, Any]) -> bool:
        if not self.is_available:
            return False
        self._current_mission_id = mission_id
        self.set_state(AgentState.EXECUTING)
        log.info("NavigationAgent %s accepted mission %s", self.agent_id, mission_id)
        return True

    def abort_mission(self, reason: str = "") -> None:
        log.warning("NavigationAgent %s aborted mission %s: %s", self.agent_id, self.active_mission_id, reason)
        self.active_mission_id = None
        self.active_goal_pos = None
        self.active_goal_name = ""
        self._waiting_for_arrival = False
        self._current_mission_id = None
        self.set_state(AgentState.IDLE)
        if self.robot:
            self.robot.clear_missions()
            self.robot.transition(RobotState.IDLE)

    def handle_navigation_request(self, message: AgentMessage) -> None:
        """Receive path coordinates, construct mission on physical robot, and reply status."""
        payload = message.payload
        dest_pos = payload.get("destination_pos")
        dest_name = payload.get("destination_name", "Target Location")
        mission_id = payload.get("mission_id", "")
        escort = payload.get("escort", False)

        if not dest_pos:
            log.warning("NavigationAgent received request with empty destination_pos")
            self._reply_status(NavigationState.NAVIGATION_FAILED, mission_id, "No destination coordinates provided")
            return

        log.info("NavigationAgent %s received navigation request to %s at %s", 
                 self.agent_id, dest_name, dest_pos)

        self.active_mission_id = mission_id
        self.active_goal_pos = tuple(dest_pos)  # type: ignore
        self.active_goal_name = dest_name
        self.set_state(AgentState.EXECUTING)
        self._waiting_for_arrival = True
        self.total_paths_computed += 1

        # Publish planned status
        self._reply_status(NavigationState.PATH_PLANNED, mission_id)

        # Trigger physical robot navigation in simulator
        if self.robot is not None:
            # Snap to nearest free cell if occupied
            goal = dest_pos
            if self.occupancy_grid is not None:
                goal = self.occupancy_grid.find_nearest_free(*dest_pos) or dest_pos

            # Construct mission
            desc = f"Navigate to {dest_name}"
            mission = Mission.create(desc, dest_name, goal, priority=2)
            
            # Speed configuration if escorting
            if escort:
                self.robot.max_velocity = 1.0  # Reduced speed for patient safety
            else:
                self.robot.max_velocity = 2.0

            self.robot.enqueue_mission(mission)
            self._reply_status(NavigationState.NAVIGATION_STARTED, mission_id)
        else:
            log.warning("Physical Robot entity not wired to NavigationAgent. Simulating arrival.")
            # Headless fallback: trigger mock arrival in update loop

    def handle_replan_request(self, message: AgentMessage) -> None:
        """Execute path recalculation due to blocked corridor obstacles."""
        mission_id = message.payload.get("mission_id", "")
        if mission_id != self.active_mission_id:
            return

        log.info("NavigationAgent %s executing replan for mission %s", self.agent_id, mission_id)
        self.total_replans_executed += 1
        self._reply_status(NavigationState.REPLANNING, mission_id)
        
        # Trigger replan in simulator
        if self.robot is not None:
            self.robot.transition(RobotState.REPLANNING)
            # Replanning logic is debounced and triggered on next step by simulator,
            # but we force the state transition here to expedite it.

    def update(self, dt: float) -> None:
        """Update navigation progress, battery and check goal arrival."""
        if self.state == AgentState.EXECUTING:
            # Battery consumption
            self._battery_pct = max(5.0, self._battery_pct - dt * 0.04)

            # Monitor robot coordinate arrival
            if self._waiting_for_arrival and self.robot is not None:
                # Sync agent position representation
                self.set_position(self.robot.grid_pos)

                # Check if arrived at goal center
                r_pos = self.robot.grid_pos
                g_pos = self.active_goal_pos
                
                if g_pos is not None:
                    # Allow 1 cell clearance tolerance
                    dist = abs(r_pos[0] - g_pos[0]) + abs(r_pos[1] - g_pos[1])
                    
                    # Or check if robot reached destination state IDLE and has finished its active mission
                    if dist <= 1 or (self.robot.state == RobotState.IDLE and not self.robot.active_mission):
                        self._waiting_for_arrival = False
                        self._reply_status(NavigationState.GOAL_REACHED, self.active_mission_id)
                        
                        log.info("NavigationAgent %s reached destination: %s", self.agent_id, self.active_goal_name)
                        
                        # Return to IDLE
                        self.active_mission_id = None
                        self.active_goal_pos = None
                        self.active_goal_name = ""
                        self.set_state(AgentState.IDLE)
                        self._current_mission_id = None

                # Check if robot is blocked / stuck
                if self.robot.state == RobotState.BLOCKED:
                    self._reply_status(NavigationState.PATH_BLOCKED, self.active_mission_id)
                    # Notify coordinator about obstacle blocking path
                    MESSAGE_BUS.send(AgentMessage(
                        msg_type=MessageType.OBSTACLE_DETECTED,
                        sender=self.agent_id,
                        receiver="coordinator",
                        payload={
                            "mission_id": self.active_mission_id,
                            "position": self.robot.grid_pos
                        }
                    ))

            # Headless simulation fallback:
            elif self._waiting_for_arrival and self.robot is None:
                self._waiting_for_arrival = False
                self._reply_status(NavigationState.GOAL_REACHED, self.active_mission_id)
                self.active_mission_id = None
                self.active_goal_pos = None
                self.active_goal_name = ""
                self.set_state(AgentState.IDLE)
                self._current_mission_id = None

    def _reply_status(self, nav_state: NavigationState, mission_id: str, reason: str = "") -> None:
        """Send NAVIGATION_STATUS notification back to Coordinator."""
        payload = {
            "mission_id": mission_id,
            "status": nav_state.name,
            "agent_id": self.agent_id,
            "planner": self.active_planner_name
        }
        if reason:
            payload["reason"] = reason

        msg = AgentMessage(
            msg_type=MessageType.NAVIGATION_STATUS,
            sender=self.agent_id,
            receiver="coordinator",
            payload=payload
        )
        MESSAGE_BUS.send(msg)

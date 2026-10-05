"""
HospitalRobotNav — Main Simulation Loop
=========================================
Orchestrates all simulation components and drives the main loop.

Responsibilities:
    - Initialize all subsystems
    - Drive the per-frame update cycle
    - Coordinate robot controller, physics, obstacle manager
    - Handle user events from the UI
    - Maintain the event bus simulation time
"""

from __future__ import annotations

import math
import random
import time
from typing import Any, Dict, List, Optional, Tuple, Set

from config.settings import APP_SETTINGS
from config.hospital_config import HOSPITAL_CONFIG
from maps.hospital.hospital_map import HospitalMap
from environment.occupancy_grid import OccupancyGrid
from environment.navigation_graph import NavigationGraph
from environment.semantic_map import SemanticMap
from environment.obstacle_manager import ObstacleManager, ObstacleType
from robot.robot import Robot, Mission
from config.robot_config import RobotType
from robot.robot_state import RobotState
from planning.planner_factory import PlannerFactory, PlannerType
from algorithms.heuristics import HeuristicType
from navigation.path_smoother import PathSmoother
from navigation.collision_detector import CollisionDetector
from simulation.clock import SimClock
from simulation.physics import RobotPhysics
from metrics.performance_metrics import PerformanceMetrics
from speech.wake_word_detector import WakeWordDetector
from speech.speech_recognizer import SpeechRecognizer
from speech.tts_engine import TTSEngine
from speech.audio_capture import AudioCapture
from speech.speech_config import SPEECH_CONFIG
from language.dialogue_manager import DialogueManager
from language.intent_parser import IntentParser
from language.entity_extractor import EntityExtractor
from language.command_resolver import CommandResolver, MissionRequest, MissionType
from database.hospital_db import HospitalDatabase
from database.db_query_engine import DBQueryEngine
from missions.mission_planner import MissionPlanner
from missions.mission_executor import MissionExecutor
from missions.medicine_manager import MedicineManager
from agents.agent_registry import AgentRegistry
from agents.coordinator import AgentCoordinator
from agents.agent_base import AgentState
from agents.delivery_agent import DeliveryAgent
from agents.reception_agent import ReceptionAgent
from agents.emergency_agent import EmergencyAgent
from agents.navigation_agent import NavigationAgent
from agents.language_agent import LanguageAgent
from agents.environment_grounding_agent import EnvironmentGroundingAgent
from agents.task_execution_agent import TaskExecutionAgent
from agents.message_bus import MESSAGE_BUS
from agents.agent_messages import AgentMessage, MessageType
from agents.vision_agent import VisionAgent
from agents.speech_agent import SpeechAgent
from agents.task_allocation_agent import TaskAllocationAgent
from agents.object_detection_agent import ObjectDetectionAgent
from agents.patient_interaction_agent import PatientInteractionAgent
from agents.medicine_management_agent import MedicineManagementAgent
from agents.environment_monitor_agent import EnvironmentMonitorAgent
from agents.robot_health_agent import RobotHealthAgent
from agents.mission_planning_agent import MissionPlanningAgent
from environment.hospital_entities import HospitalEntityManager
from utilities.event_bus import EVENT_BUS, HospitalEvent
from utilities.logger import get_logger
from world_state import HospitalWorldState

log = get_logger(__name__)

class Simulator:
    """
    Master simulation orchestrator.

    Lifecycle:
        sim = Simulator()
        sim.initialize()
        # In pygame loop:
        sim.step()
        sim.render(renderer)

    Attributes:
        hospital_map:      The 100x100 grid.
        occupancy_grid:    Live grid with dynamic obstacles.
        nav_graph:         Hospital navigation graph.
        semantic_map:      Semantic label>coordinate resolver.
        obstacle_manager:  Dynamic obstacle manager.
        robot:             The hospital robot entity.
        planner_factory:   Algorithm selection + execution.
        clock:             Simulation time manager.
        physics:           Robot kinematics.
        metrics:           Performance metrics collector.
    """

    def __init__(self) -> None:
        self._initialized = False
        self._show_expansion = APP_SETTINGS.simulation.ANIMATE_EXPANSION
        self._expansion_frame = 0
        self._nodes_per_frame = APP_SETTINGS.simulation.NODES_PER_FRAME
        self._replan_cooldown = 0          # Steps since last replan
        self._replan_interval = 10         # Check replan every 10 frames
        self._last_replan_time = 0.0       # Wall-clock time of last replan (debounce)
        self._replan_debounce_sec = 1.0    # Minimum seconds between replan attempts
        self._demo_mission_seq = 0
        self._mission_agents: Dict[str, HospitalAgent] = {}
        self._last_assigned_agent: Optional[HospitalAgent] = None
        self._last_assignment_bid = None

        # Multi-robot physical fleet (map agent_id -> Robot)
        # Created lazily during initialize(); only selected agent types are
        # instantiated as full Robot entities to avoid heavy simulation cost.
        self.fleet_robots: Dict[str, Robot] = {}
        self.fleet_executors: Dict[str, Any] = {}
        self._multi_robot_types = ("delivery", "emergency")

        # Simple reservation overlay: maps cell -> {"robots": set(agent_ids), "expiry": float}
        # Also track which cells were added to occupancy_grid by reservations so we don't
        # remove genuine dynamic obstacles authored elsewhere.
        self._reservations: Dict[Tuple[int,int], Dict[str, object]] = {}
        self._reservation_added_cells: Set[Tuple[int,int]] = set()

    # --------------------------------------------------------------------------
    # Initialization
    # --------------------------------------------------------------------------

    def initialize(self) -> None:
        """Build all subsystems and prepare for simulation."""
        log.info("=" * 60)
        log.info("  Initializing Hospital Robot Navigation System")
        log.info("=" * 60)

        # -- Build hospital environment ---------------------------------------
        self.hospital_map = HospitalMap().build()
        self.occupancy_grid = OccupancyGrid(self.hospital_map)

        # -- Build navigation graph & semantic map ----------------------------
        self.nav_graph = NavigationGraph().build()
        self.semantic_map = SemanticMap(self.nav_graph)

        # -- Dynamic obstacles ------------------------------------------------
        self.obstacle_manager = ObstacleManager(self.occupancy_grid)
        self.obstacle_manager.spawn_random_obstacles(
            HOSPITAL_CONFIG.INITIAL_DYNAMIC_OBSTACLES
        )
        self.entity_manager = HospitalEntityManager(self.occupancy_grid, self.semantic_map)
        self.entity_manager.spawn_default_population(10)

        # -- Robot ------------------------------------------------------------
        dock_pos = self._find_robot_start()
        self.robot = Robot(start_pos=dock_pos)

        # -- Planners ---------------------------------------------------------
        self.planner_factory = PlannerFactory(
            self.occupancy_grid,
            default_planner=PlannerType.ASTAR,
            default_heuristic=HeuristicType.DIAGONAL,
        )

        # -- Support systems --------------------------------------------------
        self.path_smoother = PathSmoother(
            is_blocked_fn=lambda r, c: not self.occupancy_grid.is_free(r, c)
        )
        self.collision_detector = CollisionDetector(self.occupancy_grid)
        self.clock = SimClock()
        self.physics = RobotPhysics()
        self.metrics = PerformanceMetrics()
        self.world_state = HospitalWorldState()

        # -- Speech & Dialogue Subsystems -------------------------------------
        self.speech_recognizer = SpeechRecognizer()
        self.wake_word_detector = WakeWordDetector()
        self.tts_engine = TTSEngine()
        self.tts_engine.initialize()
        self.tts_engine.start()
        self.dialogue_manager = DialogueManager(self.semantic_map)
        self.intent_parser = IntentParser()
        self.entity_extractor = EntityExtractor()
        self.command_resolver = CommandResolver()
        self.command_resolver.set_semantic_resolver(self.semantic_map)
        self.hospital_db = HospitalDatabase()
        self.db_query_engine = DBQueryEngine(self.hospital_db)
        self.command_resolver.set_db_engine(self.db_query_engine)
        self.path_smoother.set_clearance_checker(self.collision_detector.get_clearance, min_clearance=1.0)
        self._medication_check_cooldown: int = 0
        self._medication_check_interval: int = 60
        self.mission_planner = MissionPlanner()
        self.medicine_manager = MedicineManager()

        # -- Multi-agent pipeline ----------------------------------------------
        self.agent_registry = AgentRegistry()
        self.coordinator = AgentCoordinator(self.agent_registry)

        self.language_agent = LanguageAgent()
        self.environment_grounding_agent = EnvironmentGroundingAgent(world_state=self.world_state)
        self.task_execution_agent = TaskExecutionAgent(medicine_manager=self.medicine_manager)

        self.agent_registry.register(self.language_agent)
        self.agent_registry.register(self.environment_grounding_agent)
        self.agent_registry.register(self.task_execution_agent)

        delivery_agent = DeliveryAgent(home_position=(12, 18))
        emergency_agent = EmergencyAgent(home_position=(18, 14))
        reception_agent = ReceptionAgent()
        navigation_agent = NavigationAgent(robot=self.robot, occupancy_grid=self.occupancy_grid)

        self.agent_registry.register(delivery_agent)
        self.agent_registry.register(emergency_agent)
        self.agent_registry.register(reception_agent)
        self.agent_registry.register(navigation_agent)

        # Register remaining standard agents for full fleet
        self.agent_registry.register(VisionAgent(home_position=(50, 50)))
        self.agent_registry.register(SpeechAgent(home_position=(2, 50)))
        self.agent_registry.register(TaskAllocationAgent(home_position=(50, 50)))
        self.agent_registry.register(ObjectDetectionAgent(home_position=(50, 50)))
        self.agent_registry.register(PatientInteractionAgent(home_position=(25, 20)))
        self.agent_registry.register(MedicineManagementAgent(home_position=(79, 47)))
        self.agent_registry.register(EnvironmentMonitorAgent(home_position=(50, 50)))
        self.agent_registry.register(RobotHealthAgent(home_position=self._find_robot_start()))
        self.agent_registry.register(MissionPlanningAgent(home_position=(50, 50)))

        # Mission executor for the canonical robot
        self.mission_executor = MissionExecutor(self, self.robot, self.medicine_manager)
        self._configure_mission_executor()

        # Create a lightweight physical fleet for selected logical agents.
        self.fleet_executors: Dict[str, Any] = {}
        self.fleet_robots: Dict[str, Robot] = {}
        self._mission_agents: Dict[str, Any] = {}

        for agent in (delivery_agent, emergency_agent):
            start = self._find_robot_start()
            phys = Robot(start_pos=start)
            phys.robot_id = f"{agent.agent_type.upper()}-{len(self.fleet_robots) + 1:02d}"
            self.fleet_robots[agent.agent_id] = phys
            exec_runner = MissionExecutor(self, phys, self.medicine_manager)

            def _fleet_on_navigate(destination: str, pos: Optional[Tuple[int,int]], _phys=phys):
                goal_pos = None
                if pos is not None:
                    goal_pos = self.occupancy_grid.find_nearest_free(*pos) or pos
                else:
                    goal_pos = self.semantic_map.resolve(destination)
                    if goal_pos is not None:
                        goal_pos = self.occupancy_grid.find_nearest_free(*goal_pos) or goal_pos

                if goal_pos is None:
                    log.warning("Fleet executor: unknown destination '%s' for robot %s", destination, _phys.robot_id)
                    return

                _phys.transition(RobotState.PLANNING)
                self._run_planner(_phys, _phys.grid_pos, goal_pos)
                if _phys.has_path():
                    self._reserve_path(_phys.robot_id, _phys.path, horizon=6, duration=6.0)

            def _fleet_collect(item: str, _phys=phys):
                _phys.carrying_item = item
                _phys.carrying_medicine = item
                EVENT_BUS.publish(
                    HospitalEvent.MEDICINE_COLLECTED,
                    data={"medicine": item, "robot_id": _phys.robot_id},
                    source="mission_executor",
                )

            def _fleet_deliver(item: str, _phys=phys):
                _phys.carrying_item = None
                _phys.carrying_medicine = None
                EVENT_BUS.publish(
                    HospitalEvent.MEDICINE_DELIVERED,
                    data={"medicine": item, "robot_id": _phys.robot_id},
                    source="mission_executor",
                )

            def _fleet_mission_complete(plan, _phys=phys):
                assigned_agent = self._mission_agents.pop(plan.plan_id, None)
                if assigned_agent is not None:
                    assigned_agent.report_completion(assigned_agent._current_mission_id or plan.plan_id)
                EVENT_BUS.publish(
                    HospitalEvent.MISSION_COMPLETE,
                    data={"mission_id": plan.plan_id, "robot_id": _phys.robot_id},
                    source="mission_executor",
                )

            exec_runner.on_navigate = _fleet_on_navigate
            exec_runner.on_collect = _fleet_collect
            exec_runner.on_deliver = _fleet_deliver
            exec_runner.on_mission_complete = _fleet_mission_complete
            self.fleet_executors[agent.agent_id] = exec_runner
            agent.set_position(phys.grid_pos)
            log.info("Instantiated physical robot for agent %s at %s", agent.agent_id, phys.grid_pos)

        # -- State ------------------------------------------------------------
        self.current_goal: Optional[GridPos] = None
        self.last_plan_result = None
        self.expansion_animation: List[GridPos] = []
        self._obstacle_changed_cells: List[GridPos] = []

        # -- Event subscriptions (must be after all subsystems are built) ----
        self._register_event_handlers()

        # Initialize speech pipeline (mic or text-input fallback)
        try:
            self.initialize_speech()
        except Exception:
            log.exception("Speech initialization failed; continuing without live audio.")

        self._initialized = True
        self.world_state.refresh(self)
        log.info("Simulator initialized successfully.")
        log.info("  Hospital: %s", self.hospital_map)
        log.info("  Graph:    %s", self.nav_graph)
        log.info("  Robot:    %s", self.robot)

    def _sync_agent_positions(self) -> None:
        """Keep the fleet visible in the 2D map and give each agent a stable home position."""
        if not hasattr(self, "agent_registry"):
            return

        positions = [
            (2, 50), (12, 72), (20, 20), (25, 64), (34, 44), (40, 22),
            (48, 62), (62, 74), (68, 38), (74, 58), (82, 40), (90, 68),
        ]
        for index, agent in enumerate(self.agent_registry.get_all_agents()):
            target = positions[index % len(positions)]
            if agent.state in (AgentState.IDLE, AgentState.RETURNING, AgentState.CHARGING):
                agent.set_position(target)
            elif agent.state == AgentState.EXECUTING:
                # Keep busy agents near the active mission area so the fleet remains visible.
                agent.set_position((target[0] + 1, target[1] + 1))
            else:
                agent.set_position(agent.home_position)

    def _configure_mission_executor(self) -> None:
        """Connect mission executor callbacks to simulator behavior."""
        self.mission_executor.on_navigate = self._executor_navigate
        self.mission_executor.on_collect = self._executor_collect
        self.mission_executor.on_deliver = self._executor_deliver
        self.mission_executor.on_speak = self._executor_speak
        self.mission_executor.on_mission_complete = self._executor_mission_complete

    def _executor_navigate(self, destination: str, pos: Optional[GridPos]) -> None:
        """Queue a visible robot navigation mission for a mission-plan step."""
        if pos is not None:
            goal = self.occupancy_grid.find_nearest_free(*pos) or pos
            mission = Mission.create(f"Go to {destination}", destination, goal, priority=2)
            self.robot.enqueue_mission(mission)
            return
        self.navigate_to(destination)

    def _executor_collect(self, item: str) -> None:
        """Simulate collecting an item and publish a dashboard event."""
        item_name = item or "medicine"
        self.robot.carrying_item = item_name
        self.robot.carrying_medicine = item_name
        EVENT_BUS.publish(
            HospitalEvent.MEDICINE_COLLECTED,
            data={"medicine": item_name},
            source="mission_executor",
        )

    def _executor_deliver(self, item: str) -> None:
        """Simulate delivery and publish a dashboard event."""
        item_name = item or self.robot.carrying_item or "medicine"
        self.robot.carrying_item = None
        self.robot.carrying_medicine = None
        EVENT_BUS.publish(
            HospitalEvent.MEDICINE_DELIVERED,
            data={"medicine": item_name, "room": "Room 205"},
            source="mission_executor",
        )

    def _executor_speak(self, text: str) -> None:
        """Emit speech text to the dashboard AND speak it aloud via TTS."""
        EVENT_BUS.publish(
            HospitalEvent.DIALOGUE_RESPONSE,
            data={"text": text},
            source="mission_executor",
        )
        if self.tts_engine is not None:
            self.tts_engine.speak(text, category="mission")

    def _executor_mission_complete(self, plan) -> None:
        """Publish mission completion and enqueue return-to-dock."""
        assigned_agent = self._mission_agents.pop(plan.plan_id, None)
        if assigned_agent is not None:
            assigned_agent.report_completion(assigned_agent._current_mission_id or plan.plan_id)
        EVENT_BUS.publish(
            HospitalEvent.MISSION_COMPLETE,
            data={"mission_id": plan.plan_id},
            source="mission_executor",
        )
        # If the mission plan did NOT end with a RETURN_TO_DOCK step,
        # enqueue an automatic return to the charging station.
        if plan.steps and plan.steps[-1].task_type.name != "RETURN_TO_DOCK":
            dock = self.semantic_map.get_nearest_charging_station(self.robot.grid_pos)
            if dock and dock != self.robot.grid_pos:
                mission = Mission.create(
                    "Return to Charging Dock", "Charging Station",
                    dock, priority=0
                )
                self.robot.enqueue_mission(mission)
                log.info("Auto-return to dock enqueued after mission %s", plan.plan_id)

    def _find_robot_start(self) -> GridPos:
        """Find a free starting position near the charging station."""
        # Default to near charging station CHG-01 entry
        default = (80, 11)
        if self.occupancy_grid.is_free(*default):
            return default
        snapped = self.occupancy_grid.find_nearest_free(*default)
        return snapped or (50, 50)

    # --------------------------------------------------------------------------
    # Main Step
    # --------------------------------------------------------------------------

    def step(self) -> None:
        """
        Advance simulation by one frame.

        Called once per pygame frame (~60 FPS).
        """
        if not self._initialized:
            return

        dt = self.clock.tick()
        if dt <= 0:
            return  # Paused or zero-time

        # Update event bus simulation time
        EVENT_BUS.set_sim_time(self.clock.sim_time_s)

        # -- Robot State Machine ----------------------------------------------
        self._update_robot(dt)
        self.mission_executor.update(dt)

        # -- Physics ----------------------------------------------------------
        if self.robot.state == RobotState.MOVING:
            # Prevent motion into blocked or unsafe cells before the robot steps
            # into them. Checking after the move can still let the robot penetrate
            # a wall or obstacle for one frame; this guard reduces that risk.
            waypoint = self.robot.get_next_waypoint()
            if waypoint is not None and not self.collision_detector.is_position_safe(*waypoint):
                self.robot.velocity = 0.0
                self.robot.transition(RobotState.REPLANNING)
                self._replan()
            else:
                self.physics.step(self.robot, dt)
                self._check_arrival()

        # -- Dynamic obstacles (move BEFORE collision check!) -----------------
        self._update_obstacles(dt)

        # -- Step physical fleet robots (if any) and sync their agent positions --
        if self.fleet_robots:
           for agent_id, phys_robot in list(self.fleet_robots.items()):
               # Simple physics stepping for fleet robots (they may be idle)
               try:
                   self.physics.step(phys_robot, dt)
               except Exception:
                   # Keep simulator robust if an individual robot physics fails
                   log.exception("Physics step failed for fleet robot %s", agent_id)

               # Collision safeguard: immediate stop if footprint unsafe
               if not self.collision_detector.is_position_safe(phys_robot.row, phys_robot.col):
                   phys_robot.velocity = 0.0
                   phys_robot.transition(RobotState.BLOCKED)

               # Sync logical agent position to the physical robot
               agent_obj = self.agent_registry.get_agent(agent_id)
               if agent_obj is not None:
                   agent_obj.set_position(phys_robot.grid_pos)

        # Cleanup any expired short-term reservations so occupancy grid stays up-to-date
        self._cleanup_reservations()

        # -- Collision detection (now sees latest obstacle positions) ---------
        if self.robot.state == RobotState.MOVING:
           self._check_collision()

        # -- Battery ----------------------------------------------------------
        self._update_battery(dt)
        self._sync_agent_positions()
        self.world_state.refresh(self)

        # -- Multi-Agent Pipeline: step rewired agents -------------------------
        self.task_execution_agent.update(dt)
        if hasattr(self, 'navigation_agent'):
            nav_agents = self.agent_registry.get_agents_by_type('navigation')
            for na in nav_agents:
                if hasattr(na, 'update'):
                    na.update(dt)

        # -- Audio processing (poll mic / text input) --------------------------
        try:
            self.process_audio()
        except Exception:
            log.exception("Audio processing failed this frame.")

        # -- Replanning check -------------------------------------------------
        self._replan_cooldown += 1
        if self._replan_cooldown >= self._replan_interval:
            self._replan_cooldown = 0
            self._check_replan()

        # -- Medication schedule check ----------------------------------------
        self._medication_check_cooldown += 1
        if self._medication_check_cooldown >= self._medication_check_interval:
            self._medication_check_cooldown = 0
            self._check_medication_schedules()

        # -- Metrics ----------------------------------------------------------
        self.metrics.update_live(
            speed=self.robot.velocity,
            dt=dt,
            dist_this_frame=self.robot.velocity * dt,
            energy_this_frame=self.robot.battery.total_energy_consumed_wh,
        )

        # -- Expansion animation frame ----------------------------------------
        if self.expansion_animation and self._show_expansion:
            self._expansion_frame = min(
                self._expansion_frame + self._nodes_per_frame,
                len(self.expansion_animation),
            )

    # --------------------------------------------------------------------------
    # Robot State Updates
    # --------------------------------------------------------------------------

    def _update_robot(self, dt: float) -> None:
        """Handle robot FSM transitions and procedural humanoid animations."""
        self.robot.update_animation(dt)
        state = self.robot.state

        if state == RobotState.IDLE:
            # Check mission queue
            if self.robot.mission_queue:
                mission = self.robot.start_next_mission()
                if mission and mission.goal_pos:
                    self._execute_mission(mission)

        elif state == RobotState.ARRIVED:
            # Reached a waypoint -- check if full path complete
            if not self.robot.has_path():
                self.robot.complete_current_mission(success=True)
                self.robot.transition(RobotState.COMPLETE)
                EVENT_BUS.publish(
                    HospitalEvent.ROBOT_GOAL_REACHED,
                    data={"robot_id": self.robot.robot_id, "goal": self.robot.current_goal},
                    source="simulator",
                )
                self.mission_executor.notify_arrival()
                log.info("Robot reached goal!")
            else:
                self.robot.transition(RobotState.MOVING)

        elif state == RobotState.COMPLETE:
            self.robot.transition(RobotState.IDLE)

    def _execute_mission(self, mission: Mission) -> None:
        """Plan path for a mission and start navigation."""
        self.robot.transition(RobotState.PLANNING)
        goal = mission.goal_pos
        if goal is None:
            log.error("Mission has no goal position: %s", mission)
            self.robot.transition(RobotState.IDLE)
            return

        self.current_goal = goal
        # Plan for the canonical robot
        self._run_planner(self.robot, self.robot.grid_pos, goal)

    def _run_planner(self, robot: Robot, start: GridPos, goal: GridPos) -> None:
        """Execute planning from `start` to `goal` and assign the path to `robot`.

        This generic planner supports both the canonical `self.robot` and
        physical fleet robots passed as `robot`.
        """
        log.info("Planning for robot %s: %s -> %s using %s", robot.robot_id, start, goal,
                 self.planner_factory.active_planner_name)

        result = self.planner_factory.plan(start, goal)
        self.last_plan_result = result

        if result.success and result.path:
            # Smooth the path
            smooth = self.path_smoother.smooth(result.path, method="bezier")
            # Convert back to integer grid positions
            grid_path = [(int(round(r)), int(round(c))) for r, c in smooth]
            robot.set_path(grid_path)
            robot.transition(RobotState.MOVING)

            # Store expansion animation (only for canonical planner view)
            planner = self.planner_factory.active_planner
            if hasattr(planner, "expansion_order"):
                self.expansion_animation = planner.expansion_order
            else:
                self.expansion_animation = list(result.closed_set)
            self._expansion_frame = 0

            # Record metrics
            self.metrics.record_run(
                planner_metrics=result.metrics,
                start=start,
                goal=goal,
                success=True,
            )

            EVENT_BUS.publish(
                HospitalEvent.PATH_PLANNED,
                data={"path_len": len(result.path), "planner": result.metrics.planner_name, "robot_id": robot.robot_id},
                source="simulator",
            )
        else:
            log.warning("Planning failed: %s", result.status.name)
            robot.transition(RobotState.BLOCKED)
            EVENT_BUS.publish(HospitalEvent.PATH_FAILED, source="simulator")

    def _check_medication_schedules(self) -> None:
        """Check for pending medication schedules in the hospital database."""
        if not hasattr(self, "hospital_db") or not self.hospital_db:
            return
        try:
            pending = self.hospital_db.get_pending_medications()
            if pending:
                EVENT_BUS.publish(
                    HospitalEvent.MISSION_REQUESTED,
                    data={"pending_count": len(pending), "next_patient": pending[0].get("patient_id")},
                    source="medication_scheduler",
                )
        except Exception:
            log.debug("Medication schedule check skipped.")

    # --------------------------------------------------------------------------
    # Collision & Replanning
    # --------------------------------------------------------------------------

    def _check_collision(self) -> None:
        """Check for upcoming collisions and react appropriately.

        Two checks:
        1. Path ahead blocked (lookahead 6 waypoints) → replan.
        2. Dynamic obstacle too close to the robot → slow down
           (creep) instead of replanning.  Replanning on mere
           proximity causes constant replan thrashing and jerky
           stop-start movement.
        """
        obstacle_positions = self.obstacle_manager.get_obstacle_positions()

        # Immediate emergency stop: if the robot's current footprint is already
        # occupying a blocked cell or is inside a dynamic obstacle radius, do not
        # allow any further motion until a replan or obstacle clear event resolves it.
        if not self.collision_detector.is_position_safe(self.robot.row, self.robot.col):
            self.robot.velocity = 0.0
            self.robot.transition(RobotState.BLOCKED)
            return

        # Check 1: only treat a future waypoint as blocked when an obstacle is
        # genuinely close to the current corridor.  A loose proximity check on a
        # future waypoint causes repeated replanning thrash around moving people.
        blocked = self.collision_detector.check_path_ahead(
            self.robot.path,
            self.robot.path_index,
            lookahead=8,
            obstacle_positions=obstacle_positions,
        )
        if blocked:
            now = time.monotonic()
            if self.robot.state == RobotState.REPLANNING and (now - self._last_replan_time) < self._replan_debounce_sec:
                return
            if (now - self._last_replan_time) < self._replan_debounce_sec:
                if self.robot.state == RobotState.REPLANNING:
                    self.robot.transition(RobotState.MOVING if self.robot.has_path() else RobotState.BLOCKED)
                return
            log.info("Obstacle detected ahead at %s -- replanning", blocked)
            self.robot.transition(RobotState.REPLANNING)
            replan_succeeded = self._replan()
            if not replan_succeeded and self.robot.state == RobotState.REPLANNING:
                fallback_state = RobotState.MOVING if self.robot.has_path() else RobotState.BLOCKED
                self.robot.transition(fallback_state)
            return

        # Check 2: Dynamic obstacle near robot position → slow down only.
        # Do NOT replan here: a nearby (but not blocking) obstacle should
        # reduce speed, not trigger a full path recomputation.
        near_obs = self.collision_detector.is_near_dynamic_obstacle(
            self.robot.row, self.robot.col, obstacle_positions
        )
        if near_obs:
            # Creep: cap velocity to a slow crawl while near an obstacle.
            # This keeps the robot moving smoothly without replanning.
            creep_speed = getattr(self, "_creep_speed_cells", 0.35)
            if self.robot.velocity > creep_speed:
                self.robot.velocity = max(creep_speed, self.robot.velocity * 0.9)
                log.debug("Near dynamic obstacle -- slowing to %.2f", self.robot.velocity)

    def _check_replan(self) -> None:
        """Periodically check if path needs updating (D* Lite).

        Only triggers a replan if:
            - The robot is currently MOVING
            - A goal is set
            - Obstacle cells have changed since last check
            - Enough time has elapsed since the last replan (debounce)
              so we don't thrash while a moving obstacle crosses the path.
        """
        if (self.robot.state == RobotState.MOVING and
                self.current_goal is not None and
                self._obstacle_changed_cells and
                time.monotonic() - self._last_replan_time >= self._replan_debounce_sec):
            self._replan()
            self._obstacle_changed_cells.clear()

    def _replan(self) -> bool:
        """Execute replanning and update robot path (time-debounced).

        Returns:
            True if a replan was actually executed, False if it was
            suppressed by the debounce gate (too soon since last replan).
        """
        if self.current_goal is None:
            return False

        # Time-based debounce: never replan more often than every
        # _replan_debounce_sec seconds.  Prevents thrashing when a
        # dynamic obstacle hovers near the robot's path.
        now = time.monotonic()
        if now - self._last_replan_time < self._replan_debounce_sec:
            log.debug("Replan suppressed by debounce (%.2fs elapsed)",
                      now - self._last_replan_time)
            return False
        self._last_replan_time = now

        EVENT_BUS.publish(HospitalEvent.REPLANNING_STARTED, source="simulator")

        self.planner_factory.notify_obstacle_change(
            self._obstacle_changed_cells,
            self.robot.grid_pos,
        )
        result = self.planner_factory.replan(self.robot.grid_pos, self.current_goal)

        if result.success and result.path:
            # Keep the existing path when the replan degenerates into a useless
            # one-step or duplicate route; otherwise we get thrashing and a robot
            # that alternates between tiny corrections without making progress.
            if len(result.path) <= 2 and self.robot.has_path():
                log.debug("Replan returned a degenerate path; keeping current route.")
                self.robot.transition(RobotState.MOVING)
                EVENT_BUS.publish(HospitalEvent.REPLANNING_COMPLETE, source="simulator")
                return True

            self.robot.set_path(result.path)
            self.robot.total_replans += 1
            self.robot.transition(RobotState.MOVING)
            EVENT_BUS.publish(HospitalEvent.REPLANNING_COMPLETE, source="simulator")
            return True

        if self.robot.has_path():
            # If a route is still viable, hold the current path instead of getting
            # permanently stuck in the BLOCKED state during a transient obstacle.
            log.warning("Replanning failed; continuing with current route.")
            self.robot.transition(RobotState.MOVING)
            return False

        log.warning("Replanning failed and no valid route remains.")
        self.robot.transition(RobotState.BLOCKED)
        return False

    # --------------------------------------------------------------------------
    # Arrival & Battery
    # --------------------------------------------------------------------------

    def _check_arrival(self) -> None:
        """Check if robot reached goal."""
        if self.current_goal and not self.robot.has_path():
            self.robot.transition(RobotState.ARRIVED)

    def _update_battery(self, dt: float) -> None:
        """Update battery model each frame."""
        if self.robot.state == RobotState.MOVING:
            self.robot.battery.discharge_moving(dt, self.robot.velocity)
        elif self.robot.state == RobotState.CHARGING:
            done = self.robot.battery.charge_step(dt)
            if done:
                self.robot.transition(RobotState.IDLE)
        else:
            self.robot.battery.discharge_idle(dt)

        # Auto-return to dock if battery is low
        if (self.robot.battery.is_low() and
                self.robot.state not in (RobotState.RETURNING, RobotState.CHARGING, RobotState.DOCKED)):
            self._return_to_dock()

    def _return_to_dock(self) -> None:
        """Plan path to nearest charging station."""
        dock = self.semantic_map.get_nearest_charging_station(self.robot.grid_pos)
        if dock and dock != self.robot.grid_pos:
            mission = Mission.create("Return to charge", "Charging Station", dock, priority=0)
            self.robot.enqueue_mission(mission)
            self.robot.transition(RobotState.RETURNING)
            log.info("Low battery -- returning to charging station at %s", dock)

    # --------------------------------------------------------------------------
    # Obstacle Updates
    # --------------------------------------------------------------------------

    def _update_obstacles(self, dt: float) -> None:
        """Move dynamic obstacles and NPC entities and collect changed cells."""
        moves = self.obstacle_manager.step(dt=dt)
        for old_pos, new_pos in moves:
            self._obstacle_changed_cells.extend([old_pos, new_pos])
        if hasattr(self, "entity_manager") and self.entity_manager is not None:
            self.entity_manager.update(dt, self.robot.grid_pos)

    # --------------------------------------------------------------------------
    # Event Handlers
    # --------------------------------------------------------------------------

    def _register_event_handlers(self) -> None:
        """Subscribe to relevant hospital events."""
        EVENT_BUS.subscribe(HospitalEvent.DYNAMIC_OBSTACLE_MOVE, self._on_obstacle_move)
        EVENT_BUS.subscribe(HospitalEvent.BATTERY_LOW, self._on_battery_low)
        # Listen for agent task assignments so physical fleet robots can execute them
        EVENT_BUS.subscribe(HospitalEvent.AGENT_TASK_ASSIGNED, self._on_agent_task_assigned)

    def _on_obstacle_move(self, payload) -> None:
        """Track changed cells for incremental D* Lite replanning."""
        old_pos = payload.data.get("old_pos")
        new_pos = payload.data.get("new_pos")
        if old_pos:
            self._obstacle_changed_cells.append(old_pos)
        if new_pos:
            self._obstacle_changed_cells.append(new_pos)

    # --------------------------------------------------------------------------
    # Reservation helpers (short-term time-space reservations for multi-robot)
    # --------------------------------------------------------------------------

    def _reserve_path(self, robot_id: str, path: List[GridPos], horizon: int = 6, duration: float = 5.0) -> None:
        """Reserve the first `horizon` cells of `path` for `robot_id` for `duration` seconds.

        This implements a simple short-term reservation by temporarily adding dynamic
        obstacles for the reserved cells so other planners see them as blocked.
        Reservations are recorded in self._reservations and cleaned up when expired.
        """
        if not path:
            return
        now = time.monotonic()
        expiry = now + duration
        to_reserve = path[:horizon]
        dyn = self.occupancy_grid.get_dynamic_obstacles()
        for cell in to_reserve:
            # Normalize tuple
            r, c = int(cell[0]), int(cell[1])
            key = (r, c)
            entry = self._reservations.get(key)
            if entry is None:
                entry = {"robots": set(), "expiry": expiry}
                self._reservations[key] = entry
            entry["robots"].add(robot_id)
            # extend expiry if this reservation is later
            entry["expiry"] = max(entry["expiry"], expiry)
            # If the cell is not already a dynamic obstacle, add it and remember we added it.
            if key not in dyn and key not in self._reservation_added_cells:
                added = self.occupancy_grid.add_dynamic_obstacle(r, c)
                if added:
                    self._reservation_added_cells.add(key)
        log.debug("Reserved %d cells for robot %s (expires in %.1fs)", len(to_reserve), robot_id, duration)

    def _cleanup_reservations(self) -> None:
        """Remove expired reservations and clean up any dynamic obstacles we added."""
        if not self._reservations:
            return
        now = time.monotonic()
        to_remove = []
        for cell, info in list(self._reservations.items()):
            if info["expiry"] <= now:
                to_remove.append(cell)
        for cell in to_remove:
            robots_set = self._reservations[cell]["robots"]
            # remove reservation record
            del self._reservations[cell]
            # If we were the ones to add the dynamic obstacle, and no other reservation remains, remove it
            if cell in self._reservation_added_cells:
                # only remove if occupancy_grid still reports it and no other reservation exists for the cell
                if cell not in self._reservations and cell in self.occupancy_grid.get_dynamic_obstacles():
                    r, c = cell
                    try:
                        self.occupancy_grid.remove_dynamic_obstacle(r, c)
                    except Exception:
                        log.debug("Failed to remove reservation-added dynamic obstacle at %s", cell)
                self._reservation_added_cells.discard(cell)
        # Optionally we can shrink far-future expiries, but that's enough for now.

    def _on_battery_low(self, payload) -> None:
        log.warning("Battery low event received!")

    def _on_agent_task_assigned(self, payload) -> None:
        """Handle Agent task assignments and forward to any physical robot.

        Expected payload.data:
            {"mission_id": str, "agent_id": str, ...other mission_data}
        """
        data = payload.data or {}
        agent_id = data.get("agent_id")
        mission_id = data.get("mission_id")
        if not agent_id or mission_id is None:
            log.debug("AGENT_TASK_ASSIGNED missing agent_id/mission_id: %s", data)
            return

        phys = self.fleet_robots.get(agent_id)
        if phys is None:
            # Not a physical robot — nothing to do here
            log.debug("Assigned agent %s has no physical robot to execute mission", agent_id)
            return

        # Build a Mission for the physical robot using available fields
        dest = data.get("destination_pos") or data.get("destination")
        if dest is None:
            log.warning("No destination provided for mission %s assigned to %s", mission_id, agent_id)
            return

        # Snap to nearest free if necessary
        goal = self.occupancy_grid.find_nearest_free(*dest) or tuple(dest)
        desc = data.get("description") or f"Assigned mission {mission_id}"
        priority = int(data.get("priority", 2))
        mission = Mission.create(desc, mission_id, goal, priority=priority)

        phys.enqueue_mission(mission)
        log.info("Enqueued mission %s on physical robot %s -> %s", mission_id, agent_id, goal)

        # Immediately begin mission planning & start navigation for this physical robot
        try:
            self._start_physical_robot_mission(phys, mission)
        except Exception as exc:
            log.exception("Failed to start mission on physical robot %s: %s", agent_id, exc)

    def _start_physical_robot_mission(self, phys: Robot, mission: Mission) -> None:
        """Plan and start a mission for a physical Robot instance."""
        phys.transition(RobotState.PLANNING)
        goal = mission.goal_pos
        if goal is None:
            log.error("Mission has no goal position for robot %s: %s", phys.robot_id, mission)
            phys.transition(RobotState.IDLE)
            return

        # Plan from the robot's current grid position and assign path to that robot
        self._run_planner(phys, phys.grid_pos, goal)

        # Reserve the near-term waypoints so other robots avoid the immediate corridor
        if phys.has_path():
            self._reserve_path(phys.robot_id, phys.path, horizon=6, duration=6.0)

        EVENT_BUS.publish(
            HospitalEvent.MISSION_STARTED,
            data={"mission_id": mission.description or mission.label, "robot_id": phys.robot_id},
            source="simulator",
        )

    # --------------------------------------------------------------------------
    # User Commands (called from UI)
    # --------------------------------------------------------------------------

    def navigate_to(self, destination: str) -> bool:
        """
        Navigate robot to a semantic destination.

        Args:
            destination: Room name or ID (e.g., "ICU", "Pharmacy").

        Returns:
            True if navigation was initiated.
        """
        goal_pos = self.semantic_map.resolve(destination)
        if goal_pos is None:
            log.warning("Unknown destination: '%s'", destination)
            return False

        goal_pos = self.occupancy_grid.find_nearest_free(*goal_pos) or goal_pos
        mission = Mission.create(f"Go to {destination}", destination, goal_pos)
        self.robot.enqueue_mission(mission)
        log.info("Mission queued: %s -> %s", destination, goal_pos)
        return True

    def navigate_to_pos(self, row: int, col: int) -> bool:
        """Navigate to specific grid coordinates."""
        goal = self.occupancy_grid.find_nearest_free(row, col)
        if goal is None:
            return False
        mission = Mission.create(f"Go to ({row},{col})", f"({row},{col})", goal)
        self.robot.enqueue_mission(mission)
        return True

    def set_planner(self, planner_type: PlannerType) -> None:
        """Switch path planner at runtime."""
        self.planner_factory.set_planner(planner_type)
        EVENT_BUS.publish(
            HospitalEvent.PLANNER_CHANGED,
            data={"planner": planner_type.name},
            source="simulator",
        )

    def set_heuristic(self, heuristic_type: HeuristicType) -> None:
        """Change heuristic at runtime."""
        self.planner_factory.set_heuristic(heuristic_type)

    def spawn_obstacle(self) -> None:
        """Spawn a random dynamic obstacle."""
        self.obstacle_manager.spawn_random_obstacles(1)
        EVENT_BUS.publish(HospitalEvent.DYNAMIC_OBSTACLE_ADD, source="ui")

    def dispatch_demo_medicine_delivery(self):
        """Dispatch a repeat-safe professor-demo medicine delivery mission.

        Returns:
            ``(winner, bid, message)`` where winner/bid are ``None`` when the
            delivery robot is already busy or no capable robot is available.
        """
        delivery_agents = self.agent_registry.get_agents_by_type("delivery")
        if not delivery_agents:
            return None, None, "No delivery robot is registered"


        available_delivery = [agent for agent in delivery_agents if agent.is_available]
        if not available_delivery:
            busy = ", ".join(
                f"{agent.agent_id}:{agent.state.name}" for agent in delivery_agents
            )
            return None, None, f"Delivery robot busy ({busy})"

        # Resolve destinations from the semantic map so the demo works on any layout.
        pickup_pos = self.semantic_map.resolve("Pharmacy") or self.occupancy_grid.find_nearest_free(22, 59)
        delivery_pos = self.semantic_map.resolve("Room 205") or self.occupancy_grid.find_nearest_free(103, 36)
        request = MissionRequest(
            mission_type=MissionType.MEDICINE_DELIVERY,
            pickup_location="Pharmacy",
            delivery_location="Room 205",
            item="Paracetamol",
            priority=3,
            raw_text="Hey Arogya deliver Paracetamol to Room 205",
            resolved_pickup=pickup_pos,
            resolved_delivery=delivery_pos,
        )
        if not self.submit_mission_request(request):
            return None, None, "No capable delivery robot is available"
        winner = self._last_assigned_agent
        return winner, self._last_assignment_bid, "Medicine delivery dispatched"

    def dispatch_demo_emergency(self):
        """Dispatch a repeat-safe professor-demo emergency mission."""
        emergency_agents = self.agent_registry.get_agents_by_type("emergency")
        available_emergency = [agent for agent in emergency_agents if agent.is_available]
        if emergency_agents and not available_emergency:
            busy = ", ".join(
                f"{agent.agent_id}:{agent.state.name}" for agent in emergency_agents
            )
            return None, None, f"Emergency robot busy ({busy})"

        self._demo_mission_seq += 1
        mission_id = f"DEMO-EMG-{self._demo_mission_seq:03d}-{int(time.monotonic() * 1000) % 10000:04d}"
        return (*self.coordinator.broadcast_mission(
            mission_type="EMERGENCY_RESPONSE",
            mission_id=mission_id,
            destination=(80, 25),
            priority=1,
            mission_data={"room": "ICU"},
        ), "Emergency mission dispatched")

    def submit_mission_request(self, request: MissionRequest) -> bool:
        """Convert a resolved command into an executable visible mission plan."""
        if not request.is_valid:
            EVENT_BUS.publish(
                HospitalEvent.DIALOGUE_RESPONSE,
                data={"text": request.validation_error or "I could not understand that command."},
                source="simulator",
            )
            return False

        if request.mission_type == MissionType.MEDICINE_DELIVERY:
            request.resolved_pickup = request.resolved_pickup or self.semantic_map.resolve("Pharmacy") or (63, 12)
            request.resolved_delivery = request.resolved_delivery or (35, 60)
        elif request.delivery_location and request.resolved_delivery is None:
            request.resolved_delivery = self.semantic_map.resolve(request.delivery_location)

        self._demo_mission_seq += 1
        assignment_id = f"MSN-{self._demo_mission_seq:04d}-{int(time.monotonic() * 1000) % 10000:04d}"
        winner, bid = self.coordinator.broadcast_mission(
            mission_type=request.mission_type.name,
            mission_id=assignment_id,
            destination=request.resolved_delivery or request.resolved_pickup,
            priority=request.priority,
            mission_data={
                "item": request.item,
                "destination_pos": request.resolved_delivery,
                "pickup": request.pickup_location,
                "destination_label": request.delivery_location,
                "raw_text": request.raw_text,
            },
        )
        if winner is None:
            self._last_assigned_agent = None
            self._last_assignment_bid = None
            return False

        plan = self.mission_planner.plan(request)
        self._last_assigned_agent = winner
        self._last_assignment_bid = bid
        self._mission_agents[plan.plan_id] = winner

        # If the assigned agent has a physical robot, submit the plan to that robot's executor
        phys_exec = self.fleet_executors.get(winner.agent_id)
        if phys_exec is not None:
            phys_robot = self.fleet_robots.get(winner.agent_id)
            if phys_robot is not None:
                phys_robot.current_mission_plan = plan
            phys_exec.submit(plan)
            self.world_state.record_message({
                "message_type": "TASK_ASSIGNED",
                "sender": "coordinator_agent",
                "receiver": winner.agent_id,
                "priority": request.priority,
                "payload": {"mission_id": plan.plan_id, "mission_type": request.mission_type.name},
            })
            self.world_state.refresh(self)
            log.info("Submitted mission plan %s to fleet robot executor %s", plan.plan_id, winner.agent_id)
            # MissionExecutor for fleet robot will publish mission start when it begins the first step
            return True

        # Fallback: assign to canonical robot executor
        self.robot.current_mission_plan = plan
        self.mission_executor.submit(plan)
        self.world_state.record_message({
            "message_type": "TASK_ASSIGNED",
            "sender": "coordinator_agent",
            "receiver": winner.agent_id,
            "priority": request.priority,
            "payload": {"mission_id": plan.plan_id, "mission_type": request.mission_type.name},
        })
        self.world_state.refresh(self)
        EVENT_BUS.publish(
            HospitalEvent.MISSION_STARTED,
            data={"mission_id": plan.plan_id, "description": plan.description},
            source="simulator",
        )
        return True

    # --------------------------------------------------------------------------
    # Speech Initialization & Audio Polling
    # --------------------------------------------------------------------------

    def initialize_speech(self) -> None:
        """
        Start microphone capture and wire dialogue callbacks to TTS/mission.

        Call once after ``initialize()``.  Enables the live wake-word ->
        spoken-greeting pipeline in the legacy Pygame simulator.
        """
        # Wire dialogue manager speech -> TTS engine
        self.dialogue_manager.on_robot_speak = lambda text: (
            self.tts_engine.speak(text, category="dialogue")
            if self.tts_engine is not None else None
        )

        # Wire dialogue manager mission request -> simulator mission submit
        self.dialogue_manager.on_mission_request = self._on_dialogue_mission

        # Initialize the speech recognizer (Vosk or simulated fallback)
        self.speech_recognizer.initialize()

        # Wake-activated listening window: when the wake word is detected,
        # the robot "opens its ears" for COMMAND_TIMEOUT_SEC seconds.
        # During this window, any final STT transcript is processed as a
        # command.  Outside this window, only transcripts that *contain*
        # a wake word are processed (prevents phantom commands from
        # background noise being misrecognised as speech).
        self._wake_activated_at: float = 0.0

        # Start microphone capture (falls back gracefully if no mic or under tests)
        try:
            import sys
            from speech.audio_capture import TextInputCapture

            # Explicit FORCE_TEXT_INPUT in settings overrides live audio capture
            if APP_SETTINGS.simulation.FORCE_TEXT_INPUT:
                self.audio_capture = TextInputCapture()
                self.audio_capture.start()
                log.info("FORCE_TEXT_INPUT enabled — using TextInputCapture for audio.")

            # In test environments prefer the text-input capture to avoid PortAudio issues
            elif 'pytest' in sys.modules:
                self.audio_capture = TextInputCapture()
                self.audio_capture.start()
                log.info("Pytest detected — using TextInputCapture fallback for audio.")
            else:
                self.audio_capture = AudioCapture()
                try:
                    started = self.audio_capture.start()
                except Exception:
                    log.exception("AudioCapture.start() raised an exception — falling back to text input.")
                    started = False
                if started:
                    log.info("AudioCapture started — wake word 'Hey Arogya' active.")
                else:
                    log.info("No microphone available or failed to start -- using text-input mode.")
                    self.audio_capture = TextInputCapture()
                    self.audio_capture.start()
        except Exception:
            log.exception("Failed to initialize audio capture; continuing without live audio.")
            self.audio_capture = None

    def _on_dialogue_mission(self, intent, entities) -> None:
        """Convert a dialogue-confirmed intent/entities into a mission."""
        request = self.command_resolver.resolve(intent, entities)
        if request and request.is_valid:
            self.submit_mission_request(request)
        else:
            log.info("Dialogue mission request was not valid: %s",
                     getattr(request, "validation_error", "unknown"))

    def process_audio(self) -> None:
        """
        Poll microphone audio chunks and detect wake word / commands.

        Call once per frame.  Safe no-op when no microphone is available.
        Only processes chunks classified as speech by VAD (voice activity
        detection) to avoid phantom voice detections from background noise.

        This method also handles the TextInputCapture fallback: when the
        capture backend provides typed text (has_pending/consume_text),
        process it immediately as a final command so typing triggers the
        same wake-word/command pipeline used for microphone input.
        """
        cap = getattr(self, "audio_capture", None)
        if cap is None or not getattr(cap, "is_running", False):
            return

        # TextInputCapture handling: if a typed command is pending, consume and process it.
        # This ensures typed input triggers the same pipeline as microphone speech.
        if hasattr(cap, "has_pending") and callable(getattr(cap, "has_pending")):
            try:
                if cap.has_pending():
                    txt = None
                    # consume_text() returns the submitted text (or None)
                    if hasattr(cap, "consume_text") and callable(getattr(cap, "consume_text")):
                        txt = cap.consume_text()
                    if txt:
                        # Treat typed input as a final spoken command
                        self.process_spoken_command(txt)
                        # Do not additionally process audio chunks this frame
                        return
            except Exception:
                log.exception("TextInputCapture handling failed")

        # Read a chunk (non-blocking-ish, 0.05s timeout)
        chunk = None
        try:
            chunk = cap.read_chunk(timeout=0.05)
        except Exception:
            log.debug("Audio capture read_chunk failed or unsupported for this backend")
            return

        if chunk is None:
            return

        # VAD: Only process chunks that have speech energy.
        # This prevents background noise from triggering phantom commands.
        if not getattr(chunk, "is_speech", False):
            return

        # Feed to speech recognizer (streaming Vosk or simulated fallback)
        result = self.speech_recognizer.feed_chunk(chunk.data)
        if result is None:
            return

        # Wake word detection on partial results -> speak greeting
        if not result.is_final:
            match = self.wake_word_detector.check_partial(result.text)
            if match:
                EVENT_BUS.publish(
                    HospitalEvent.WAKE_WORD_DETECTED,
                    data={"phrase": match.phrase},
                    source="speech_input",
                )
                if self.tts_engine is not None:
                    greeting = self.wake_word_detector.get_greeting()
                    self.tts_engine.speak_greeting(greeting)
            return

        # Final transcript -> full command pipeline.
        # Gate on confidence and text length to reject phantom detections
        # from background noise that pass the VAD energy check.
        min_conf = SPEECH_CONFIG.recognizer.MIN_CONFIDENCE
        min_len  = SPEECH_CONFIG.recognizer.MIN_TEXT_LENGTH
        if not result.is_empty and len(result.text.strip()) >= min_len:
            # Only trust final results with a meaningful confidence score.
            # Vosk reports -1.0 when word confidence is unavailable, so treat
            # -1.0 as "trust the transcript" but reject low-confidence noise.
            conf = result.confidence
            if conf < 0.0 or conf >= min_conf:
                self.process_spoken_command(result.text)
            else:
                log.debug("STT result rejected (low confidence %.2f): %s",
                          conf, result.text)

    def process_spoken_command(self, text: str) -> bool:
        """Process a wake-word command from microphone, console, or test input.

        When a wake word is detected, the current mission is cancelled so
        the new command takes effect immediately (preemption behavior).
        """
        cleaned = text.strip()
        if not cleaned:
            return False

        # Reject overly short transcripts (phantom noise that slips past VAD).
        # Real commands are at least MIN_TEXT_LENGTH chars; anything shorter
        # is almost certainly noise.
        min_len = SPEECH_CONFIG.recognizer.MIN_TEXT_LENGTH
        if len(cleaned) < min_len:
            log.debug("Spoken command rejected (too short): %r", cleaned)
            return False

        EVENT_BUS.publish(
            HospitalEvent.SPEECH_RECOGNIZED,
            data={"text": cleaned},
            source="speech_input",
        )

        wake_match = self.wake_word_detector.check_text(cleaned)
        if wake_match:
            EVENT_BUS.publish(
                HospitalEvent.WAKE_WORD_DETECTED,
                data={"phrase": wake_match.phrase},
                source="speech_input",
            )
            # Speak the wake-word greeting aloud so the robot audibly
            # acknowledges the activation.
            if self.tts_engine is not None:
                greeting = self.wake_word_detector.get_greeting()
                self.tts_engine.speak_greeting(greeting)

            # Cancel current mission and clear queue so new command preempts
            if self.mission_executor.is_busy:
                self.mission_executor.cancel()
            self.robot.mission_queue.clear()
            self.robot.current_mission = None
            self.robot.current_mission_plan = None
            self.current_goal = None
            self.robot.clear_path()
            if self.robot.state in (RobotState.MOVING, RobotState.PLANNING,
                                    RobotState.REPLANNING, RobotState.BLOCKED):
                self.robot.transition(RobotState.IDLE)

            command = self.wake_word_detector.strip_wake_word(cleaned)
        else:
            command = cleaned

        response = self.dialogue_manager.on_user_input(command)
        EVENT_BUS.publish(
            HospitalEvent.DIALOGUE_RESPONSE,
            data={"text": response},
            source="dialogue_manager",
        )

        intent = self.intent_parser.parse(command)
        entities = self.entity_extractor.extract(command)
        request = self.command_resolver.resolve(intent, entities)

        return self.submit_mission_request(request)

    def trigger_event(self, event_name: str) -> None:
        """Trigger a named hospital event."""
        event_map = {
            "emergency":        HospitalEvent.EMERGENCY_ALERT,
            "fire":             HospitalEvent.FIRE_ALARM,
            "power_failure":    HospitalEvent.POWER_FAILURE,
            "corridor_blocked": HospitalEvent.CORRIDOR_BLOCKED,
            "patient_crossing": HospitalEvent.PATIENT_CROSSING,
        }
        event = event_map.get(event_name.lower())
        if event:
            EVENT_BUS.publish(event, data={"triggered_by": "ui"}, source="user")
            self.obstacle_manager.spawn_event_obstacle(event_name)

    def pause(self) -> None:
        """Pause the simulation."""
        self.clock.pause()
        self.robot.transition(RobotState.PAUSED)
        EVENT_BUS.publish(HospitalEvent.SIMULATION_PAUSED, source="simulator")

    def resume(self) -> None:
        """Resume the simulation."""
        self.clock.resume()
        if self.robot.state == RobotState.PAUSED:
            self.robot.transition(RobotState.MOVING if self.robot.has_path() else RobotState.IDLE)
        EVENT_BUS.publish(HospitalEvent.SIMULATION_RESUMED, source="simulator")

    def reset(self) -> None:
        """Reset simulation to initial state."""
        self.mission_executor.cancel()
        self.mission_executor.mission_queue.clear()
        self._mission_agents.clear()
        self._last_assigned_agent = None
        self._last_assignment_bid = None
        self.robot.reset(self._find_robot_start())
        self.obstacle_manager.clear_all()
        self.obstacle_manager.spawn_random_obstacles(HOSPITAL_CONFIG.INITIAL_DYNAMIC_OBSTACLES)
        self.current_goal = None
        self.last_plan_result = None
        self.expansion_animation = []
        self._expansion_frame = 0
        self._obstacle_changed_cells.clear()
        for agent in self.agent_registry.get_all_agents():
            if agent.is_busy:
                agent.abort_mission()
            elif agent.state != AgentState.IDLE:
                agent.set_state(AgentState.IDLE)
        # Reset any physical fleet robots to their home positions
        for aid, phys in list(self.fleet_robots.items()):
            agent_obj = self.agent_registry.get_agent(aid)
            home = agent_obj.home_position if agent_obj is not None else phys.grid_pos
            phys.reset(home)
            if agent_obj is not None:
                agent_obj.set_position(phys.grid_pos)

        self.clock.reset()
        self.metrics.reset_session()
        self._last_replan_time = 0.0   # Allow immediate replan after reset
        EVENT_BUS.publish(HospitalEvent.SIMULATION_RESET, source="simulator")
        log.info("Simulation reset.")

    def set_speed(self, index: int) -> None:
        """Set simulation speed by index."""
        self.clock.set_speed_index(index)
        EVENT_BUS.publish(
            HospitalEvent.SPEED_CHANGED,
            data={"speed": self.clock.speed},
            source="simulator",
        )

    # --------------------------------------------------------------------------
    # Rendering Data
    # --------------------------------------------------------------------------

    def get_expansion_visible(self):
        """Return currently visible expansion nodes for animation."""
        return self.expansion_animation[:self._expansion_frame]

    def get_open_set(self):
        """Return open set from last plan."""
        if self.last_plan_result:
            return self.last_plan_result.open_set
        return set()

    def get_closed_set(self):
        """Return closed set from last plan."""
        if self.last_plan_result:
            return self.last_plan_result.closed_set
        return set()

    @property
    def is_initialized(self) -> bool:
        return self._initialized

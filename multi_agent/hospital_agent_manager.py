"""
HospitalRobotNav & Isaac Sim Hospital — Multi-Agent Coordination Manager
========================================================================
Orchestrates Contract-Net Protocol bidding, dynamic task allocation, and
emergency preemption between specialized hospital agents:
    - CoordinatorAgent : Fleet manager, auction supervisor, priority scheduler
    - DeliveryAgent    : Medicine transport, pharmacy dispatch, bedside delivery
    - ReceptionAgent   : Patient triage, visitor escort, information assistance
    - EmergencyAgent   : Code Blue responder, trauma resupply, task preemption
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure repository root is on sys.path
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from agents.agent_base import AgentBid, AgentState, HospitalAgent
from agents.agent_registry import AgentRegistry
from agents.coordinator import AgentCoordinator
from agents.delivery_agent import DeliveryAgent
from agents.reception_agent import ReceptionAgent
from agents.emergency_agent import EmergencyAgent
from agents.support_agent import SupportAgent
from agents.message_bus import MESSAGE_BUS
from utilities.logger import get_logger

from ai_reasoning.mission_understander import EmbodiedMissionSpec

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Preempted Task Context
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PreemptedTaskContext:
    """State saved when an ongoing task is preempted by a high-priority emergency."""
    mission_spec: EmbodiedMissionSpec
    assigned_agent_id: str
    robot_position: Tuple[float, float, float]
    current_waypoint_idx: int
    total_waypoints: int
    remaining_waypoints: List[Any]
    saved_timestamp: float = field(default_factory=time.time)


# ─────────────────────────────────────────────────────────────────────────────
# Declarative Capability Registry (Section 13)
# ─────────────────────────────────────────────────────────────────────────────

FLEET_CAPABILITY_REGISTRY: Dict[str, Dict[str, Any]] = {
    "Arogya_Delivery": {
        "capabilities": {"MEDICINE_TRANSPORT", "LOCKABLE_STORAGE", "BEDSIDE_DELIVERY", "SCHEDULED_RUNS"},
        "payload_capacity_kg": 25.0,
        "max_speed_mps": 1.2,
    },
    "Mitra_Reception": {
        "capabilities": {"VISITOR_ESCORT", "WAYFINDING", "TRIAGE_CHECKIN", "INSPECTION", "AUDIO_ANNOUNCEMENT"},
        "payload_capacity_kg": 10.0,
        "max_speed_mps": 1.0,
    },
    "Garuda_Emergency": {
        "capabilities": {"CODE_BLUE", "TRAUMA_RESPONSE", "DEFIBRILLATOR_CARRIER", "EMERGENCY_OVERRIDE", "RAPID_TRANSIT"},
        "payload_capacity_kg": 35.0,
        "max_speed_mps": 1.8,
    },
    "Sahayak_Support": {
        "capabilities": {"EQUIPMENT_HAULING", "PATHOLOGY_TRANSPORT", "HEAVY_PAYLOAD", "GENERAL_LOGISTICS", "UV_C_DISINFECTION"},
        "payload_capacity_kg": 60.0,
        "max_speed_mps": 1.1,
    },
}

MISSION_CAPABILITY_REQUIREMENTS: Dict[str, Dict[str, Any]] = {
    "EMERGENCY_RESPONSE": {
        "primary": {"CODE_BLUE", "TRAUMA_RESPONSE", "EMERGENCY_OVERRIDE"},
        "secondary": {"RAPID_TRANSIT"},
    },
    "MEDICINE_DELIVERY": {
        "primary": {"MEDICINE_TRANSPORT", "BEDSIDE_DELIVERY"},
        "secondary": {"GENERAL_LOGISTICS", "LOCKABLE_STORAGE"},
    },
    "PATIENT_GUIDANCE": {
        "primary": {"VISITOR_ESCORT", "WAYFINDING"},
        "secondary": {"TRIAGE_CHECKIN", "AUDIO_ANNOUNCEMENT"},
    },
    "RECEPTION_GUIDE": {
        "primary": {"VISITOR_ESCORT", "WAYFINDING"},
        "secondary": {"TRIAGE_CHECKIN", "AUDIO_ANNOUNCEMENT"},
    },
    "EQUIPMENT_TRANSPORT": {
        "primary": {"EQUIPMENT_HAULING", "HEAVY_PAYLOAD"},
        "secondary": {"GENERAL_LOGISTICS"},
    },
    "SPECIMEN_TRANSPORT": {
        "primary": {"PATHOLOGY_TRANSPORT"},
        "secondary": {"EQUIPMENT_HAULING", "GENERAL_LOGISTICS"},
    },
    "NURSE_ALERT": {
        "primary": {"AUDIO_ANNOUNCEMENT", "WAYFINDING"},
        "secondary": {"VISITOR_ESCORT"},
    },
    "RETURN_TO_DOCK": {
        "primary": set(),
        "secondary": set(),
    },
}


def compute_capability_score(robot_name: str, mission_type: str, priority: int = 3) -> Tuple[float, str]:
    """Compute declarative capability match score and explainable description."""
    norm_type = mission_type.upper()
    req = None
    for k, v in MISSION_CAPABILITY_REQUIREMENTS.items():
        if k in norm_type or norm_type in k:
            req = v
            break

    if req is None or not req["primary"]:
        return 1.0, "Universal capability"

    robot_spec = FLEET_CAPABILITY_REGISTRY.get(robot_name, {})
    caps = robot_spec.get("capabilities", set())

    # Check primary capability match
    matched_primary = caps.intersection(req["primary"])
    if matched_primary:
        return 1.0, f"Primary capability match: {', '.join(sorted(matched_primary))}"

    # Check secondary fallback capability match
    matched_secondary = caps.intersection(req["secondary"])
    if matched_secondary:
        return 0.85, f"Secondary fallback capability match: {', '.join(sorted(matched_secondary))}"

    # Penalty for robot lacking specific hardware/capability
    if priority == 1 or "EMERGENCY" in norm_type:
        return 0.35, "Lacks emergency life-support hardware"
    elif "DELIVER" in norm_type:
        return 0.40, "Lacks dedicated secure medication payload compartment"
    elif "GUIDE" in norm_type or "ESCORT" in norm_type:
        return 0.45, "Lacks interactive visitor guidance display"
    else:
        return 0.50, "General fallback utility"


# ─────────────────────────────────────────────────────────────────────────────
# Hospital Agent Manager
# ─────────────────────────────────────────────────────────────────────────────

class HospitalAgentManager:
    """
    Manages the fleet of embodied AI agents operating inside Isaac Sim.
    
    Provides:
        1. Contract-Net Protocol auctions for clinical missions.
        2. Dynamic task allocation based on agent capabilities and proximity.
        3. Real-time Emergency Preemption with state preservation and recovery.
        4. Fleet monitoring and message bus integration.
    """

    def __init__(self) -> None:
        self.registry = AgentRegistry()

        # Instantiate specialized clinical agents
        # Coordinate space mapped to hospital zones
        self.delivery_agent = DeliveryAgent(home_position=(10, 10), pharmacy_position=(25, 20))
        self.reception_agent = ReceptionAgent(home_position=(15, 30))
        self.emergency_agent = EmergencyAgent(home_position=(30, 30))
        self.support_agent = SupportAgent(home_position=(40, 33), storage_position=(40, 30))

        # Register agents in fleet directory
        self.registry.register(self.delivery_agent)
        self.registry.register(self.reception_agent)
        self.registry.register(self.emergency_agent)
        self.registry.register(self.support_agent)

        # Instantiate central coordinator
        self.coordinator = AgentCoordinator(self.registry)

        # Preemption stack for emergency interruption
        self.preemption_stack: List[PreemptedTaskContext] = []
        self.active_mission_context: Optional[Dict[str, Any]] = None
        self.last_allocation: Optional[Dict[str, Any]] = None

        # Subscribe to emergency events from DB and system
        try:
            from utilities.event_bus import EVENT_BUS, HospitalEvent
            EVENT_BUS.subscribe(HospitalEvent.EMERGENCY_ALERT, self._on_emergency_alert_received)
        except Exception:
            pass

        log.info(
            "[HospitalAgentManager] Multi-Agent fleet online: %d agents registered (Delivery, Reception, Emergency, Support).",
            len(self.registry.get_all_agents())
        )

    def _on_emergency_alert_received(self, event_data: Any) -> None:
        """Handle real-time Code Blue emergency alerts from hospital database or UI."""
        payload_dict = event_data.data if hasattr(event_data, "data") and isinstance(event_data.data, dict) else (event_data if isinstance(event_data, dict) else {})
        patient_id = payload_dict.get("patient_id", "P003")
        room = payload_dict.get("room", "EMR-01")
        condition = payload_dict.get("condition", "Critical Code Blue Emergency")

        log.warning(
            "[HospitalAgentManager] EMERGENCY ALERT: Patient %s in %s (%s). Triggering fleet preemption!",
            patient_id, room, condition
        )

        try:
            from isaac_sim_hospital.ai_reasoning.mission_understander import EmbodiedMissionSpec
            em_spec = EmbodiedMissionSpec(
                mission_id=f"EMR-{patient_id}-{int(time.time())}",
                raw_text=f"Emergency Code Blue patient {patient_id} in {room}: {condition}",
                language="en",
                task_type="EMERGENCY_RESPONSE",
                item="Crash Cart / Defibrillator",
                quantity=1,
                source_dept="EMR-01",
                dest_dept=room,
                target_bed=None,
                priority_level=1,
                priority_label="CRITICAL_EMERGENCY",
                urgency_string="STAT",
                confidence=1.0,
                spoken_response_en=f"Emergency Code Blue alert in {room}. Garuda Emergency dispatched immediately.",
                spoken_response_hi=f"{room} में आपातकालीन कोड ब्लू अलर्ट।",
                is_emergency=True,
            )
            # Execute preemption
            self.preempt_active_task_for_emergency(
                emergency_spec=em_spec,
                current_robot_pos=(0.0, 0.0, 0.0),
                current_waypoint_idx=0,
                total_waypoints=1,
                remaining_waypoints=[],
            )

            # Record in Explainable Decision Engine
            try:
                from ai_reasoning.decision_engine import DECISION_ENGINE
                DECISION_ENGINE.reason_emergency_preemption(
                    emergency_patient_id=patient_id,
                    emergency_room=room,
                    preempted_robot="Arogya_Delivery",
                    dispatched_robot="Garuda_Emergency",
                )
            except Exception:
                pass
        except Exception as e:
            log.error("[HospitalAgentManager] Failed to handle emergency alert: %s", e)

    def allocate_mission(
        self,
        mission_spec: EmbodiedMissionSpec,
        robot_grid_pos: Tuple[int, int] = (10, 10),
    ) -> Tuple[Optional[HospitalAgent], Optional[AgentBid], str]:
        """
        Execute Contract-Net Protocol bidding for a parsed mission.
        
        Args:
            mission_spec: Parsed EmbodiedMissionSpec from MissionUnderstander.
            robot_grid_pos: Current robot grid position for proximity scoring.
            
        Returns:
            Tuple of (winning_agent, winning_bid, reasoning_explanation)
        """
        mission_type = mission_spec.task_type
        priority = mission_spec.priority_level

        log.info(
            "[HospitalAgentManager] Bidding initiated for Mission %s (Type: %s, Priority: %d)",
            mission_spec.mission_id, mission_type, priority
        )

        # Query all available agents for bids
        available_agents = self.registry.get_available_agents()
        bids: List[Tuple[HospitalAgent, AgentBid]] = []

        for agent in available_agents:
            bid = agent.evaluate_mission(mission_type, destination=robot_grid_pos, priority=priority)
            if bid:
                bids.append((agent, bid))
                log.info(
                    "  -> Agent %s submitted bid: score=%.3f, ETA=%.1fs, distance=%.1f",
                    agent.agent_id, bid.score, bid.estimated_eta, bid.distance
                )

        if not bids:
            # Fallback based on task type if standard bids are empty
            if mission_spec.is_emergency:
                winner = self.emergency_agent
                bid = AgentBid(agent_id=winner.agent_id, mission_id=mission_spec.mission_id, score=1.0)
            elif "DELIVERY" in mission_type:
                winner = self.delivery_agent
                bid = AgentBid(agent_id=winner.agent_id, mission_id=mission_spec.mission_id, score=0.9)
            else:
                winner = self.reception_agent
                bid = AgentBid(agent_id=winner.agent_id, mission_id=mission_spec.mission_id, score=0.85)

            explanation = f"Direct allocation to {winner.agent_id} based on specialized capability match for {mission_type}."
            self._record_assignment(winner, mission_spec, bid)
            return winner, bid, explanation

        # Sort bids: highest score wins
        bids.sort(key=lambda item: item[1].score, reverse=True)
        winner_agent, winner_bid = bids[0]

        explanation = (
            f"Contract awarded to {winner_agent.agent_id} ({winner_agent.agent_type}) "
            f"with top bid score {winner_bid.score:.3f} among {len(bids)} bidding agents."
        )

        self._record_assignment(winner_agent, mission_spec, winner_bid)

        # Record explainable decision (Phase 6)
        try:
            from ai_reasoning.decision_engine import DECISION_ENGINE
            candidates_dict = {
                a.agent_id: {"battery": getattr(a, "battery_pct", 100), "dist": b.distance, "score": b.score}
                for a, b in bids
            } if bids else {winner_agent.agent_id: {"battery": 100, "dist": 0, "score": 1.0}}
            DECISION_ENGINE.reason_task_allocation(
                mission_type=mission_type,
                destination=mission_spec.dest_dept or "Hospital Department",
                candidates=candidates_dict,
                winner_robot_name=winner_agent.agent_id,
                winning_reason=explanation,
            )
        except Exception:
            pass

        return winner_agent, winner_bid, explanation

    def _record_assignment(
        self,
        agent: HospitalAgent,
        mission_spec: EmbodiedMissionSpec,
        bid: Optional[AgentBid],
    ) -> None:
        """Update active mission tracking state."""
        self.active_mission_context = {
            "mission_spec": mission_spec,
            "agent_id": agent.agent_id,
            "agent_type": agent.agent_type,
            "bid_score": bid.score if bid else 1.0,
            "start_time": time.time(),
        }

    def preempt_active_task_for_emergency(
        self,
        emergency_spec: EmbodiedMissionSpec,
        current_robot_pos: Tuple[float, float, float],
        current_waypoint_idx: int,
        total_waypoints: int,
        remaining_waypoints: List[Any],
    ) -> Tuple[HospitalAgent, str]:
        """
        Execute real-time emergency preemption:
        1. Save active mission state onto the preemption stack.
        2. Assign emergency mission directly to EmergencyAgent.
        3. Emit emergency alert over AgentMessageBus.
        """
        if self.active_mission_context:
            active_spec: EmbodiedMissionSpec = self.active_mission_context["mission_spec"]
            context = PreemptedTaskContext(
                mission_spec=active_spec,
                assigned_agent_id=self.active_mission_context["agent_id"],
                robot_position=current_robot_pos,
                current_waypoint_idx=current_waypoint_idx,
                total_waypoints=total_waypoints,
                remaining_waypoints=remaining_waypoints,
            )
            self.preemption_stack.append(context)
            log.warning(
                "[HospitalAgentManager] TASK PREEMPTED! Mission %s paused at waypoint %d/%d for Code Blue emergency.",
                active_spec.mission_id, current_waypoint_idx, total_waypoints
            )

        # Dispatch EmergencyAgent
        self.emergency_agent.set_state(AgentState.EXECUTING)
        explanation = (
            f"CRITICAL EMERGENCY PREEMPTION: Code Blue alert in {emergency_spec.dest_dept}! "
            f"All non-emergency tasks suspended. EmergencyAgent dispatched with Priority 1."
        )

        self.active_mission_context = {
            "mission_spec": emergency_spec,
            "agent_id": self.emergency_agent.agent_id,
            "agent_type": "emergency",
            "bid_score": 1.0,
            "start_time": time.time(),
        }

        return self.emergency_agent, explanation

    def resume_preempted_task(self) -> Optional[PreemptedTaskContext]:
        """
        Restore the most recently preempted clinical mission from the stack.
        Returns PreemptedTaskContext if one was waiting, else None.
        """
        if not self.preemption_stack:
            log.info("[HospitalAgentManager] No preempted tasks waiting in queue.")
            return None

        saved_context = self.preemption_stack.pop()
        log.info(
            "[HospitalAgentManager] RESUMING PREEMPTED MISSION: %s (Target: %s, Resuming at waypoint %d/%d)",
            saved_context.mission_spec.mission_id,
            saved_context.mission_spec.dest_dept,
            saved_context.current_waypoint_idx,
            saved_context.total_waypoints,
        )

        self.active_mission_context = {
            "mission_spec": saved_context.mission_spec,
            "agent_id": saved_context.assigned_agent_id,
            "start_time": time.time(),
        }
        return saved_context

    def get_fleet_status_summary(self) -> Dict[str, Any]:
        """Return fleet health, battery levels, and operational states."""
        summary = {}
        for agent_id, agent in self.registry._agents.items():
            summary[agent_id] = {
                "type": agent.agent_type,
                "state": agent.state.name,
                "battery": agent.battery_pct,
                "is_available": agent.is_available,
            }
        summary["preempted_queue_depth"] = len(self.preemption_stack)
        return summary

    def recover_low_battery_mission(
        self,
        failing_robot: Any,
        fleet_robots: Dict[str, Any],
        hospital_env: Any = None,
        collision_guard: Any = None,
        battery_threshold: float = 30.0,
    ) -> Optional[Tuple[Any, str]]:
        """
        Autonomous fleet self-healing: Reassigns active missions when an AMR drops below
        battery_threshold during transit. Dispatches low-battery robot to CHG-01 dock.
        """
        if not getattr(failing_robot, "mission_active", False):
            return None
        if getattr(failing_robot, "battery_level", 100.0) >= battery_threshold:
            return None

        r_name = getattr(failing_robot, "name", "AMR")
        m_id = getattr(failing_robot, "current_mission_id", "MSN-UNKNOWN")
        dest = getattr(failing_robot, "destination_name", "None")
        task_desc = getattr(failing_robot, "current_task_description", "Active task")
        pri = getattr(failing_robot, "priority_level", 3)

        # Find eligible healthy candidate robot
        candidates = [
            r for name, r in fleet_robots.items()
            if name != r_name and getattr(r, "battery_level", 0.0) >= 45.0 and not getattr(r, "mission_active", False)
        ]

        if not candidates:
            # No immediate peer available: push to preemption stack for later resumption
            from isaac_sim_hospital.ai_reasoning.mission_understander import EmbodiedMissionSpec
            m_spec = EmbodiedMissionSpec(
                mission_id=m_id,
                raw_text=task_desc,
                task_type="MEDICINE_DELIVERY" if "deliver" in task_desc.lower() else "PATIENT_GUIDANCE",
                dest_dept=dest,
                priority_level=pri,
            )
            rem_wps = list(getattr(failing_robot, "waypoints", []))[getattr(failing_robot, "current_waypoint_idx", 0):]
            ctx_obj = PreemptedTaskContext(
                mission_spec=m_spec,
                assigned_agent_id=r_name,
                robot_position=(failing_robot.x, failing_robot.y, getattr(failing_robot, "z", 0.0)),
                current_waypoint_idx=0,
                total_waypoints=len(rem_wps),
                remaining_waypoints=rem_wps,
            )
            self.preemption_stack.append(ctx_obj)
            expl = f"FLEET ALERT: {r_name} battery critical ({failing_robot.battery_level:.1f}%). Mission {m_id} queued to preemption stack."
            log.warning(expl)
            if hasattr(failing_robot, "_evaluate_post_mission_policy"):
                failing_robot._evaluate_post_mission_policy()
            return None, expl

        # Select candidate with highest battery
        candidates.sort(key=lambda r: getattr(r, "battery_level", 0.0), reverse=True)
        peer = candidates[0]

        # Plan route from peer to destination
        peer_route = []
        try:
            from isaac_sim_hospital.navigation.route_planner import plan_hospital_route
            if hospital_env and collision_guard:
                peer_route = plan_hospital_route(peer.get_position(), dest, hospital_env, collision_guard)
        except Exception:
            pass

        if not peer_route:
            peer_route = list(getattr(failing_robot, "waypoints", []))[getattr(failing_robot, "current_waypoint_idx", 0):]

        peer.assign_mission(
            waypoints=peer_route,
            task_description=f"Handoff from {r_name}: {task_desc}",
            destination_name=dest,
            priority_level=pri,
            mission_id=m_id,
        )

        expl = (
            f"FLEET SELF-HEALING: {r_name} battery depleted ({failing_robot.battery_level:.1f}% < {battery_threshold}%). "
            f"Active mission {m_id} to {dest} successfully handed off to {peer.name} (Battery: {peer.battery_level:.1f}%)."
        )
        log.warning(expl)

        # Clear active mission and send failing robot to charger
        failing_robot.mission_active = False
        if hasattr(failing_robot, "_evaluate_post_mission_policy"):
            failing_robot._evaluate_post_mission_policy()

        return peer, expl

    def allocate_fleet_mission(
        self,
        mission_type: str,
        destination_dept: str,
        priority: int,
        robots: Dict[str, Any],
        destination_coords: Tuple[float, float],
    ) -> Tuple[Any, float, str, List[Dict[str, Any]]]:
        """
        Dynamic Contract-Net Protocol auction across the live physical robot fleet.
        
        Evaluates each robot on:
        - Capability match (40%)
        - Availability (30%)
        - Proximity to destination (15%)
        - Battery level (15%)
        With emergency priority preemption bonus.
        
        Returns:
            (winning_robot, top_score, allocation_reasoning, bid_breakdowns)
        """
        import numpy as np

        print(f"\n[COORDINATOR] ==============================================================")
        print(f"[COORDINATOR] New Mission Tender: {mission_type} -> {destination_dept}")
        print(f"[COORDINATOR] Priority Level: {priority} (1=Emergency, 3=Normal, 5=Dock)")
        print(f"[COORDINATOR] Calling for bids across {len(robots)} hospital robots...")

        bids: List[Tuple[Any, float, Dict[str, Any]]] = []

        for name, robot in robots.items():
            # 1. Capability Score via Declarative Registry
            role = getattr(robot, "role", "UNKNOWN")
            cap_score, cap_fit_desc = compute_capability_score(name, mission_type, priority=priority)

            # 2. Availability Score
            state = getattr(robot.state_machine, "state", None)
            is_idle = state and (robot.state_machine.is_idle() or robot.state_machine.is_complete())
            if is_idle:
                avail_score = 1.0
            elif getattr(robot, "is_charging", False):
                avail_score = 0.20
            elif getattr(robot, "mission_active", False):
                # If incoming mission is emergency priority 1, can preempt active task
                avail_score = 0.65 if priority == 1 else 0.0
            else:
                avail_score = 0.80

            # 3. Proximity Score
            dist = float(np.hypot(robot.x - destination_coords[0], robot.y - destination_coords[1]))
            prox_score = max(0.05, 1.0 - (dist / 60.0))

            # 4. Battery Score
            batt_pct = getattr(robot, "battery_level", 100.0)
            batt_score = max(0.0, min(1.0, batt_pct / 100.0))

            # Total weighted bid
            total_score = (
                cap_score * 0.40
                + avail_score * 0.30
                + prox_score * 0.15
                + batt_score * 0.15
            )

            # Emergency surge boost for Emergency AMR
            if priority == 1 and role == "EMERGENCY":
                total_score += 0.25

            breakdown = {
                "robot": name,
                "robot_name": name,
                "role": role,
                "capability": round(cap_score, 2),
                "capability_fit": cap_fit_desc,
                "availability": round(avail_score, 2),
                "proximity": round(prox_score, 2),
                "distance_m": round(dist, 1),
                "battery": round(batt_pct, 1),
                "total_score": round(total_score, 3),
            }

            bids.append((robot, total_score, breakdown))

            # Visible agent communication log
            print(
                f"[FLEET BID] [ROBOT] {name:16s} ({role:9s}) -> Bid Score: {total_score:.3f} "
                f"| Cap: {cap_score:.2f} ({cap_fit_desc}) | Dist: {dist:4.1f}m | Battery: {batt_pct:3.0f}% | State: {state.name if state else 'IDLE'}"
            )

        # Sort descending by bid score
        bids.sort(key=lambda item: item[1], reverse=True)
        winner_robot, winning_score, winner_breakdown = bids[0]

        reasoning = (
            f"Coordinator selected {winner_robot.name} ({winner_breakdown['role']}) "
            f"with top bid score {winning_score:.3f} (Fit: {winner_breakdown['capability_fit']}, "
            f"Cap: {winner_breakdown['capability']}, Dist: {winner_breakdown['distance_m']}m, Batt: {winner_breakdown['battery']}%)."
        )

        print(f"[COORDINATOR] [OK] Awarded to: {winner_robot.name}")
        print(f"[COORDINATOR] [RATIONALE] {reasoning}")
        print(f"[{winner_robot.name}] Assignment acknowledged. Calculating collision-free corridor trajectory.")
        print(f"[COORDINATOR] ==============================================================\n")

        all_breakdowns = [b[2] for b in bids]
        self.last_explainable_trace = (
            winner_robot.name,
            round(winning_score, 3),
            reasoning,
            all_breakdowns,
            winner_breakdown["capability_fit"],
        )
        self.last_allocation = {
            "mission_type": mission_type,
            "destination": destination_dept,
            "priority": priority,
            "winner": winner_robot.name,
            "winner_score": round(winning_score, 3),
            "reasoning": reasoning,
            "bids": all_breakdowns,
            "explainable_trace": self.last_explainable_trace,
            "timestamp": time.time(),
        }
        return winner_robot, winning_score, reasoning, all_breakdowns

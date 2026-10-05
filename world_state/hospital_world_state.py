"""Read-mostly shared state for the multi-agent hospital runtime.

Agents receive snapshots from this object and report changes through their
coordinator/event interfaces.  It deliberately does not expose the simulator's
mutable robot, map, or obstacle objects for agents to edit directly.
"""

from __future__ import annotations

import time
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Tuple

from agents.message_bus import MESSAGE_BUS

class HospitalWorldState:
    """Controlled, serialisable view of the hospital's current state."""

    def __init__(self) -> None:
        self._state: Dict[str, Any] = {
            "robot": {},
            "agents": {},
            "mission": {},
            "task_queue": [],
            "obstacles": [],
            "locations": {},
            "medicine_inventory": {},
            "patient_locations": {},
            "emergency": {"active": False},
            "navigation": {},
            "communication": [],
            "updated_at": time.monotonic(),
        }
        self.semantic_map: Optional[Any] = None
        self.occupancy_grid: Optional[Any] = None

    def refresh(self, simulator: Any) -> None:
        """Atomically refresh the public snapshot from authoritative systems."""
        self.semantic_map = getattr(simulator, "semantic_map", None)
        self.occupancy_grid = getattr(simulator, "occupancy_grid", None)

        robot = simulator.robot
        # Prefer showing an active plan from any fleet executor (physical robots)
        plan = None
        executor_for_plan = None
        if hasattr(simulator, "fleet_executors") and simulator.fleet_executors:
            for ex in simulator.fleet_executors.values():
                if getattr(ex, "active_plan", None) is not None:
                    plan = ex.active_plan
                    executor_for_plan = ex
                    break
        if plan is None:
            plan = simulator.mission_executor.active_plan
            executor_for_plan = simulator.mission_executor

        agents = simulator.agent_registry.get_all_agents()
        self._state["robot"] = {
            "id": robot.robot_id,
            "position": tuple(robot.grid_pos),
            "state": robot.state.name,
            "battery_pct": robot.battery.soc_percent,
            "carrying_item": getattr(robot, "carrying_item", None),
        }
        self._state["agents"] = {
            agent.agent_id: {
                "type": agent.agent_type,
                "state": agent.state.name,
                "position": tuple(agent.position),
                "battery_pct": agent.battery_pct,
                "mission_id": agent._current_mission_id,
            }
            for agent in agents
        }
        self._state["mission"] = {
            "plan_id": plan.plan_id if plan else None,
            "description": plan.description if plan else None,
            "progress_pct": (executor_for_plan.progress_percent if executor_for_plan is not None else simulator.mission_executor.progress_percent),
            "current_task": (executor_for_plan.current_step_description if executor_for_plan is not None else simulator.mission_executor.current_step_description),
        }
        # Use the canonical mission executor queue for the task queue listing
        self._state["task_queue"] = [p.plan_id for p in simulator.mission_executor.mission_queue]
        self._state["obstacles"] = [tuple(o.position) for o in simulator.obstacle_manager.get_all_obstacles()]
        self._state["locations"] = {
            room.room_id: tuple(room.center)
            for room in simulator.hospital_map.rooms
        }
        self._state["medicine_inventory"] = {
            name: slot.stock
            for name, slot in simulator.medicine_manager.inventory.items()
        }
        self._state["navigation"] = {
            "goal": tuple(simulator.current_goal) if simulator.current_goal else None,
            "robot_state": robot.state.name,
            "path_length": len(robot.path),
        }
        # Synchronise communication log from MESSAGE_BUS
        self._state["communication"] = MESSAGE_BUS.get_communication_log(50)

        # Synchronise Hospital Database state if available
        if hasattr(simulator, "hospital_db") and simulator.hospital_db:
            try:
                active_pts = simulator.hospital_db.get_active_patients()
                pending_meds = simulator.hospital_db.get_pending_medications()
                pending_tasks = simulator.hospital_db.get_pending_tasks()
                self._state["hospital_database"] = {
                    "active_patients": active_pts,
                    "pending_medications": pending_meds,
                    "pending_tasks": pending_tasks,
                }
                self._state["patient_locations"] = {
                    p["patient_id"]: p.get("room_id") for p in active_pts
                }
            except Exception:
                pass

        self._state["updated_at"] = time.monotonic()

    def record_message(self, message: Dict[str, Any]) -> None:
        """Append a structured communication record with bounded retention (delegates to MESSAGE_BUS)."""
        MESSAGE_BUS._communication_log.append(message)
        self._state["communication"] = MESSAGE_BUS.get_communication_log(50)

    def snapshot(self) -> Dict[str, Any]:
        """Return an isolated snapshot safe for agent/UI consumption."""
        return deepcopy(self._state)

    # ─── Clean getters / reading interfaces ─────────────────────────────────

    def get_active_patients(self) -> List[Dict[str, Any]]:
        return self._state.get("hospital_database", {}).get("active_patients", [])

    def get_pending_medications(self) -> List[Dict[str, Any]]:
        return self._state.get("hospital_database", {}).get("pending_medications", [])

    def get_pending_tasks(self) -> List[Dict[str, Any]]:
        return self._state.get("hospital_database", {}).get("pending_tasks", [])

    def get_patient_room(self, patient_id: str) -> Optional[str]:
        return self._state.get("patient_locations", {}).get(patient_id)

    def get_robot_position(self) -> Tuple[int, int]:
        return self._state["robot"].get("position", (0, 0))

    def get_robot_state(self) -> str:
        return self._state["robot"].get("state", "IDLE")

    def get_robot_battery(self) -> float:
        return self._state["robot"].get("battery_pct", 100.0)

    def get_agent_states(self) -> Dict[str, Dict[str, Any]]:
        return self._state["agents"]

    def get_mission_state(self) -> Dict[str, Any]:
        return self._state["mission"]

    def get_task_queue(self) -> List[str]:
        return self._state["task_queue"]

    def get_obstacles(self) -> List[Tuple[int, int]]:
        return self._state["obstacles"]

    def get_medicine_inventory(self) -> Dict[str, int]:
        return self._state["medicine_inventory"]

    def get_navigation_state(self) -> Dict[str, Any]:
        return self._state["navigation"]

    def get_communication_log(self) -> List[Dict[str, Any]]:
        return self._state["communication"]

    # ─── Updating interfaces ────────────────────────────────────────────────

    def update_agent_state(self, agent_id: str, state_name: str, position: Optional[Tuple[int, int]] = None, battery_pct: Optional[float] = None) -> None:
        if agent_id not in self._state["agents"]:
            self._state["agents"][agent_id] = {}
        self._state["agents"][agent_id]["state"] = state_name
        if position is not None:
            self._state["agents"][agent_id]["position"] = position
        if battery_pct is not None:
            self._state["agents"][agent_id]["battery_pct"] = battery_pct
        self._state["updated_at"] = time.monotonic()

    def update_mission_state(self, plan_id: Optional[str], description: Optional[str], progress_pct: float, current_task: Optional[str]) -> None:
        self._state["mission"] = {
            "plan_id": plan_id,
            "description": description,
            "progress_pct": progress_pct,
            "current_task": current_task,
        }
        self._state["updated_at"] = time.monotonic()

    # ─── SemanticMap Query Delegation ───────────────────────────────────────

    def find_location(self, query: str) -> Optional[Tuple[int, int]]:
        """Resolve a natural language room query/department (e.g. 'ICU', 'Pharmacy') to coordinates."""
        if self.semantic_map is None:
            return None
        return self.semantic_map.resolve(query)

    def find_room(self, room_number: str) -> Optional[Tuple[int, int]]:
        """Resolve a room number (e.g. '205') to grid coordinates."""
        if self.semantic_map is None:
            return None
        # Add Room prefix if needed
        q = f"Room {room_number}" if not room_number.lower().startswith("room") else room_number
        return self.semantic_map.resolve(q)

    def find_nearest(self, category_or_name: str, from_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """Find nearest location of category or query to starting position."""
        if self.semantic_map is None:
            return None
        from maps.hospital.room_definitions import RoomCategory
        # Check if category matches
        for cat in RoomCategory:
            if cat.name.lower() in category_or_name.lower():
                return self.semantic_map.find_nearest_room_of_category(cat, from_pos)
        # Otherwise resolve directly
        return self.semantic_map.resolve(category_or_name)

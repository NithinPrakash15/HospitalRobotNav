"""
Real-Time Status Dashboard for Multi-Agent Hospital Robot Fleet
===============================================================
Prints a rich, color-coded console HUD every N simulation steps showing:
- Fleet-wide status table for all 4 AMRs (Arogya, Mitra, Garuda, Sahayak)
- Dynamic auto-focus on the currently active AMR (eliminating hardcoded robot display)
- Robot FSM state, real battery level, real position coordinates
- Current waypoint / total waypoints with visual progress bar
- Active clinical task description, destination, and priority level
- Dynamic obstacle count and emergency preemption stack depth
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


# ANSI color codes for Windows console (works in Windows Terminal)
class Color:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    CYAN    = "\033[96m"
    MAGENTA = "\033[95m"
    WHITE   = "\033[97m"
    BLUE    = "\033[94m"
    DIM     = "\033[2m"


# State -> color mapping
STATE_COLORS: dict = {
    "IDLE":               Color.DIM + Color.WHITE,
    "MISSION_ANALYSIS":   Color.BLUE,
    "TASK_ASSIGNED":      Color.CYAN,
    "PLANNING":           Color.YELLOW,
    "NAVIGATING":         Color.GREEN + Color.BOLD,
    "EXECUTING_TASK":     Color.MAGENTA + Color.BOLD,
    "AVOIDING_OBSTACLE":  Color.YELLOW + Color.BOLD,
    "REPLANNING":         Color.YELLOW + Color.BOLD,
    "BLOCKED":            Color.YELLOW + Color.BOLD,
    "EMERGENCY_OVERRIDE": Color.RED + Color.BOLD,
    "CHARGING":           Color.CYAN,
    "PAUSED":             Color.YELLOW,
    "MISSION_COMPLETE":   Color.GREEN + Color.BOLD,
}


def _colorize_state(state_name: str, width: int = 18) -> str:
    color = STATE_COLORS.get(state_name, Color.WHITE)
    return f"{color}{state_name:<{width}}{Color.RESET}"


def _battery_bar(pct: float, width: int = 10) -> str:
    """Render a compact ASCII battery bar."""
    pct = max(0.0, min(100.0, float(pct)))
    filled = int(round(pct / 100.0 * width))
    bar = "#" * filled + "." * (width - filled)
    color = Color.GREEN if pct > 60 else (Color.YELLOW if pct > 25 else Color.RED)
    return f"{color}[{bar}]{Color.RESET} {pct:.0f}%"


class StatusDashboard:
    """
    Prints a real-time status HUD to the simulation console.
    Monitors all 4 robots in the fleet and dynamically tracks the active AMR.
    """

    def __init__(self, print_every_n_steps: int = 60) -> None:
        self.print_every = print_every_n_steps
        self._sim_start_time = time.monotonic()

    def tick(
        self,
        step: int,
        robots_or_arogya: Any,
        companion_or_mitra: Any = None,
        dynamic_obstacles: Any = None,
        agent_manager: Any = None,
        *args,
    ) -> None:
        """
        Call every simulation step — prints every N steps.
        Supports both dict of fleet robots or positional robot arguments.
        """
        if step % self.print_every != 0:
            return

        # Resolve robots dictionary
        fleet: Dict[str, Any] = {}
        dyn_obs = dynamic_obstacles
        mgr = agent_manager

        if isinstance(robots_or_arogya, dict):
            fleet = robots_or_arogya
            dyn_obs = companion_or_mitra
            mgr = dynamic_obstacles
        else:
            if hasattr(robots_or_arogya, "name"):
                fleet[robots_or_arogya.name] = robots_or_arogya
            if companion_or_mitra and hasattr(companion_or_mitra, "name"):
                fleet[companion_or_mitra.name] = companion_or_mitra
            for arg in args:
                if hasattr(arg, "name"):
                    fleet[arg.name] = arg

        self._print(step, fleet, dyn_obs, mgr)

    @staticmethod
    def get_active_robot(fleet_robots: Dict[str, Any]) -> Any:
        """Identify currently active AMR (highest priority or mission active)."""
        active_robot = None
        for r in fleet_robots.values():
            if getattr(r, "mission_active", False):
                if active_robot is None or getattr(r, "priority_level", 99) < getattr(active_robot, "priority_level", 99):
                    active_robot = r
        if active_robot is None:
            active_robot = next(iter(fleet_robots.values())) if fleet_robots else None
        return active_robot

    def _print(
        self,
        step: int,
        fleet_robots: Dict[str, Any],
        dynamic_obstacles: Any,
        agent_manager: Any,
    ) -> None:
        elapsed = time.monotonic() - self._sim_start_time
        active_robot = self.get_active_robot(fleet_robots)

        # Preemption depth
        preempt_depth = 0
        try:
            if agent_manager:
                preempt_depth = len(getattr(agent_manager, "preemption_stack", []))
        except Exception:
            pass

        # Obstacle count
        obstacle_count = 0
        try:
            if dynamic_obstacles:
                obstacle_count = len(dynamic_obstacles.get_obstacle_positions())
        except Exception:
            pass

        print(flush=True)
        print(f"{Color.CYAN}{'=' * 88}{Color.RESET}", flush=True)
        print(
            f"  {Color.BOLD}AROGYA HOSPITAL ROBOTICS CONTROL CENTER — FLEET TELEMETRY{Color.RESET}  "
            f"Step: {Color.WHITE}{step:>5d}{Color.RESET}  "
            f"Elapsed: {Color.DIM}{elapsed:>6.1f}s{Color.RESET}",
            flush=True
        )
        print(f"{Color.CYAN}{'-' * 88}{Color.RESET}", flush=True)

        # 1. Fleet-wide summary table (all 4 AMRs)
        print(
            f"  {Color.BOLD}{'ROBOT ID':<18} {'ROLE':<10} {'STATE':<20} {'BATT':<16} {'POS (X,Y)':<14} {'CURRENT TASK'}{Color.RESET}",
            flush=True
        )
        print(f"  {'-' * 84}", flush=True)

        for name, r in fleet_robots.items():
            st_name = getattr(r.state_machine, "state_name", "IDLE")
            role = getattr(r, "role", "AMR")
            batt = getattr(r, "battery_level", 100.0)
            pos = r.get_position() if hasattr(r, "get_position") else (getattr(r, "x", 0.0), getattr(r, "y", 0.0))
            task = getattr(r, "current_task_description", "Standing by in IDLE") or "Standing by in IDLE"
            is_cur_active = (r == active_robot and getattr(r, "mission_active", False))

            marker = f"{Color.YELLOW}►{Color.RESET} " if is_cur_active else "  "
            colored_name = f"{Color.BOLD}{name:<16}{Color.RESET}" if is_cur_active else f"{name:<16}"
            print(
                f"{marker}{colored_name} {role:<10} {_colorize_state(st_name, 19)} {_battery_bar(batt, 7):<15} "
                f"({pos[0]:>5.1f},{pos[1]:>5.1f})  {task[:24]}",
                flush=True
            )

        print(f"{Color.CYAN}{'-' * 88}{Color.RESET}", flush=True)

        # 2. Active Robot Focused Telemetry Ribbon
        if active_robot:
            act_name = active_robot.name
            act_state = getattr(active_robot.state_machine, "state_name", "IDLE")
            act_pos = active_robot.get_position() if hasattr(active_robot, "get_position") else (active_robot.x, active_robot.y)
            act_wp_cur = getattr(active_robot, "current_waypoint_idx", 0) + 1
            act_wp_tot = max(1, len(getattr(active_robot, "waypoints", [])))
            act_dest = getattr(active_robot, "destination_name", "N/A")
            act_task = getattr(active_robot, "current_task_description", "None")
            act_prio = getattr(active_robot, "priority_level", 3)
            pri_labels = {1: "P1-CRITICAL", 2: "P2-URGENT", 3: "P3-SCHEDULED", 4: "P4-ESCORT", 5: "P5-DOCK"}
            pri_label = pri_labels.get(act_prio, f"P{act_prio}")

            prog_width = 16
            filled = int(round((act_wp_cur / act_wp_tot) * prog_width)) if act_wp_tot > 0 else 0
            prog_bar = "#" * filled + "-" * (prog_width - filled)

            rem_dist = active_robot.get_remaining_distance() if hasattr(active_robot, "get_remaining_distance") else 0.0

            print(
                f"  {Color.BOLD}ACTIVE FOCUS:{Color.RESET} {Color.CYAN}{act_name}{Color.RESET}  "
                f"State: {_colorize_state(act_state, 14)} "
                f"Prio: {Color.YELLOW}{pri_label}{Color.RESET}  "
                f"Dest: {Color.WHITE}{act_dest}{Color.RESET}",
                flush=True
            )
            print(
                f"  Position: X={act_pos[0]:>6.2f}m, Y={act_pos[1]:>6.2f}m  "
                f"Waypoints: [{prog_bar}] {act_wp_cur}/{act_wp_tot}  "
                f"Dist Rem: {rem_dist:>5.1f}m  "
                f"Blocked: {Color.RED if getattr(active_robot, 'is_blocked', False) else Color.GREEN}"
                f"{'YES' if getattr(active_robot, 'is_blocked', False) else 'NO'}{Color.RESET}",
                flush=True
            )
            act_reason = getattr(active_robot.state_machine, "current_reason", "Normal Operation")
            act_action = getattr(active_robot.state_machine, "current_action", "Tracking Waypoints")
            print(
                f"  Nav Reason: {Color.WHITE}{act_reason}{Color.RESET}  |  "
                f"Nav Action: {Color.CYAN}{act_action}{Color.RESET}",
                flush=True
            )

        print(
            f"  Dynamic Obstacles: {obstacle_count} active agents  |  "
            f"Emergency Preemption Stack: {Color.RED if preempt_depth > 0 else ''}{preempt_depth}{Color.RESET}",
            flush=True
        )
        print(f"{Color.CYAN}{'=' * 88}{Color.RESET}", flush=True)
        print(flush=True)

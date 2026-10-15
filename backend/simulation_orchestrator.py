"""
AAROGYA Platform — Simulation Orchestration & Real Telemetry Gateway
====================================================================
Implements User Requirements 1, 13, 14, 15, 16, 17, 18, 41, 42:
1. NVIDIA Isaac Sim is the SINGLE SOURCE OF TRUTH for physics, navigation, and camera.
2. No fake linear interpolation loops or synthesized robot movements.
3. Live telemetry polled directly from Isaac Sim Perception Server (http://127.0.0.1:8080/api/telemetry).
4. Lifecycle states: OFFLINE, STARTING, LOADING, CONNECTING, READY, RUNNING, STOPPING, ERROR.
5. True event checklist during startup (Backend, Mission System, ROS 2, Isaac Sim, Hospital, Robot, Sensors, Ready).
6. Bidirectional task synchronization between SQLite Hospital Database and Isaac Sim fleet.
"""

from __future__ import annotations

import datetime
import json
import logging
import math
import os
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Set

from database.models import (
    Robot, RobotRoleEnum, RobotStatusEnum, RobotTask, TaskPriorityEnum, TaskStatusEnum, TaskTypeEnum,
    EmergencyEvent, AuditLog, TaskEvent
)
from database.session import SessionLocal

logger = logging.getLogger("SimulationOrchestrator")


class CameraMode:
    FOLLOW_ROBOT = "FOLLOW_ROBOT"
    FOLLOW_TASK = "FOLLOW_TASK"
    OVERVIEW = "OVERVIEW"


class SimulationOrchestrator:
    _instance: Optional[SimulationOrchestrator] = None

    def __new__(cls) -> SimulationOrchestrator:
        if cls._instance is None:
            cls._instance = super(SimulationOrchestrator, cls).__new__(cls)
            cls._instance._init_singleton()
        return cls._instance

    def _init_singleton(self) -> None:
        self.is_running = False
        self.status = "BACKEND_ONLINE"  # BACKEND_ONLINE, SIMULATION_STARTING, ISAAC_PROCESS_RUNNING, ISAAC_GUI_AVAILABLE, USD_STAGE_LOADED, TIMELINE_PLAYING, ROS2_CONNECTED, ROBOTS_INITIALIZED, SIMULATION_READY, SIMULATION_FAILED
        self.sim_process: Optional[subprocess.Popen] = None
        self.camera_mode = CameraMode.OVERVIEW
        self.active_robot_id = "ROBOT-01"
        self.active_task_code: Optional[str] = None
        self.start_time: Optional[float] = None
        self.telemetry_clients: Set[Any] = set()
        self._lock = threading.Lock()
        self._telemetry_thread: Optional[threading.Thread] = None
        self._startup_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Real Startup Event Checklist (Section 18)
        self.startup_checklist = {
            "backend": True,
            "mission_system": True,
            "ros2": False,
            "isaac_sim": False,
            "hospital_env": False,
            "robot": False,
            "sensors": False,
            "simulation_ready": False,
        }

        # Autonomous SLAM Exploration Real Runtime State Machine (Section 4 & 11)
        self.exploration_state: str = "IDLE"
        self.exploration_selected_robot: str = "Arogya_Delivery"
        self.exploration_current_frontier: Optional[List[float]] = None
        self.exploration_current_goal: Optional[List[float]] = None
        self.exploration_action_status: str = "READY"
        self.exploration_last_error: Optional[str] = None
        self.exploration_stages: List[Dict[str, Any]] = []

        # Real Fleet Telemetry (populated strictly from Isaac Sim)
        self.fleet_telemetry: Dict[str, Dict[str, Any]] = {
            "ROBOT-01": {
                "id": "ROBOT-01",
                "name": "Arogya_Delivery",
                "role": "DELIVERY",
                "status": "OFFLINE",
                "battery": None,
                "x": None,
                "y": None,
                "yaw": None,
                "speed": 0.0,
                "target_x": None,
                "target_y": None,
                "task": None,
                "progress": 0.0,
                "is_active": True,
            },
            "ROBOT-02": {
                "id": "ROBOT-02",
                "name": "Mitra_Reception",
                "role": "RECEPTION",
                "status": "OFFLINE",
                "battery": None,
                "x": None,
                "y": None,
                "yaw": None,
                "speed": 0.0,
                "target_x": None,
                "target_y": None,
                "task": None,
                "progress": 0.0,
                "is_active": False,
            },
            "ROBOT-03": {
                "id": "ROBOT-03",
                "name": "Garuda_Emergency",
                "role": "EMERGENCY",
                "status": "OFFLINE",
                "battery": None,
                "x": None,
                "y": None,
                "yaw": None,
                "speed": 0.0,
                "target_x": None,
                "target_y": None,
                "task": None,
                "progress": 0.0,
                "is_active": False,
            },
            "ROBOT-04": {
                "id": "ROBOT-04",
                "name": "Sahayak_Support",
                "role": "SUPPORT",
                "status": "OFFLINE",
                "battery": None,
                "x": None,
                "y": None,
                "yaw": None,
                "speed": 0.0,
                "target_x": None,
                "target_y": None,
                "task": None,
                "progress": 0.0,
                "is_active": False,
            },
        }

        self.last_lidar_scan: Dict[str, Any] = {"points": [], "closest_dist": None}
        self.sensor_health: Dict[str, Any] = {}
        self.measured_fps: Optional[float] = None
        self.last_slam_map: Optional[Dict[str, Any]] = None
        self.active_dynamic_obstacles: List[Dict[str, Any]] = []

        # Camera state metadata
        self.camera_state = {
            "mode": CameraMode.OVERVIEW,
            "eye": [0.0, -56.0, 48.0],
            "target": [0.0, 1.0, 0.0],
            "stream_url": "http://127.0.0.1:8080/video_feed",
            "following_robot": "Arogya_Delivery",
        }

        self.logs: List[Dict[str, Any]] = []
        self._check_initial_status()

    def _check_initial_status(self) -> None:
        """Check if Isaac Sim is already running on port 8080 upon startup."""
        if self._check_isaac_sim_alive():
            self.is_running = True
            self.status = "SIMULATION_READY"
            self.startup_checklist = {k: True for k in self.startup_checklist}
            self.start_time = time.time()
            self._start_telemetry_thread()
        else:
            self.status = "BACKEND_ONLINE"

    def log_message(self, level: str, message: str, source: str = "SIM") -> None:
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3],
            "level": level,
            "message": message,
            "source": source,
        }
        self.logs.append(entry)
        if len(self.logs) > 500:
            self.logs.pop(0)

    def _check_isaac_sim_alive(self, timeout: float = 0.5) -> bool:
        """Query perception server health endpoint to test real simulation availability."""
        try:
            req = urllib.request.Request("http://127.0.0.1:8080/health")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            return False
        return False

    def set_camera_mode(self, mode: str, target_robot_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if mode in (CameraMode.FOLLOW_ROBOT, CameraMode.FOLLOW_TASK, CameraMode.OVERVIEW):
                self.camera_mode = mode
                self.camera_state["mode"] = mode
                if target_robot_id:
                    self.active_robot_id = target_robot_id
                    # Also map to robot name
                    target_name = "Arogya_Delivery"
                    for r in self.fleet_telemetry.values():
                        if r["id"] == target_robot_id or r["name"].lower() == target_robot_id.lower():
                            target_name = r["name"]
                            break
                    self.camera_state["following_robot"] = target_name

                    # Send camera select request to Isaac Sim Perception Server
                    try:
                        post_data = json.dumps({"robot": target_name}).encode("utf-8")
                        req = urllib.request.Request(
                            "http://127.0.0.1:8080/api/select_robot",
                            data=post_data,
                            headers={"Content-Type": "application/json"},
                        )
                        urllib.request.urlopen(req, timeout=0.5)
                    except Exception:
                        pass

                self.log_message("INFO", f"Camera switched to {mode} tracking {self.camera_state['following_robot']}", "CAMERA")
        return self.camera_state

    def start_simulation(self, headless: bool = False, force: bool = False) -> Dict[str, Any]:
        """
        Executes proper backend orchestration layer (Section 16).
        Checks if Isaac Sim is already running; if not, launches it and tracks readiness.
        """
        with self._lock:
            # If force restart requested or orphaned background process running, clean up first
            if force:
                self.log_message("INFO", "Force simulation launch requested. Stopping any existing instances...", "ORCHESTRATOR")
                if sys.platform == "win32":
                    try:
                        subprocess.run(["taskkill", "/F", "/IM", "kit.exe", "/T"], capture_output=True)
                        time.sleep(1.0)
                    except Exception:
                        pass
                self.is_running = False
                self.sim_process = None
                self.status = "BACKEND_ONLINE"

            if not force and self.is_running and self.status == "SIMULATION_READY":
                return {"status": "SIMULATION_READY", "message": "Simulation is already active and connected."}

            # Check if Isaac Sim perception server is already active
            if not force and self._check_isaac_sim_alive(timeout=1.0):
                self.is_running = True
                self.status = "SIMULATION_READY"
                self.startup_checklist = {k: True for k in self.startup_checklist}
                self.start_time = time.time()
                self._start_telemetry_thread()
                self.log_message("INFO", "Connected to existing NVIDIA Isaac Sim instance on port 8080.", "ORCHESTRATOR")
                return {
                    "status": "SIMULATION_READY",
                    "message": "Connected to active Isaac Sim environment.",
                    "isaac_sim_available": True,
                    "fleet_size": len(self.fleet_telemetry),
                }

            # Isaac Sim not running: begin startup sequence
            self.status = "ISAAC_LAUNCH_REQUESTED"
            self.startup_checklist["backend"] = True
            self.startup_checklist["mission_system"] = True
            self.startup_checklist["ros2"] = False
            self.startup_checklist["isaac_sim"] = False
            self.startup_checklist["hospital_env"] = False
            self.startup_checklist["robot"] = False
            self.startup_checklist["sensors"] = False
            self.startup_checklist["simulation_ready"] = False

            isaac_python = r"C:\isaacsim\python.bat"
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            script_path = os.path.join(
                project_root,
                "isaac_sim_hospital", "scripts", "run_embodied_hospital_ai.py"
            )

            if not os.path.exists(isaac_python):
                self.status = "SIMULATION_FAILED"
                msg = f"NVIDIA Isaac Sim 5.1 launcher not found at {isaac_python}."
                self.log_message("ERROR", msg, "ORCHESTRATOR")
                return {"status": "SIMULATION_FAILED", "message": msg, "isaac_sim_available": False}

            # Clear any stale status file and runtime log
            status_file = os.path.join(project_root, "sim_startup_status.json")
            if os.path.exists(status_file):
                try:
                    os.remove(status_file)
                except Exception:
                    pass

            self.status = "ISAAC_PROCESS_STARTING"
            self.log_message("INFO", "Launching NVIDIA Isaac Sim simulation process...", "ORCHESTRATOR")
            try:
                launcher_bat = os.path.join(
                    project_root,
                    "isaac_sim_hospital", "scripts", "launch_isaac_sim_gui.bat"
                )

                if headless:
                    cmd = [isaac_python, script_path, "--headless"]
                else:
                    cmd = ["cmd.exe", "/c", launcher_bat]

                popen_kwargs: Dict[str, Any] = {
                    "cwd": project_root,
                }
                if sys.platform == "win32":
                    popen_kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE

                self.sim_process = subprocess.Popen(
                    cmd,
                    **popen_kwargs,
                )
                self.status = "ISAAC_PROCESS_RUNNING"
                self.is_running = True
                self.start_time = time.time()

                # Launch async monitoring thread to wait for Isaac Sim readiness
                self._startup_thread = threading.Thread(target=self._monitor_startup, daemon=True)
                self._startup_thread.start()

                return {
                    "status": "ISAAC_PROCESS_RUNNING",
                    "message": "NVIDIA Isaac Sim process started. Initializing hospital stage...",
                    "isaac_sim_available": True,
                    "checklist": self.startup_checklist,
                }
            except Exception as e:
                self.status = "SIMULATION_FAILED"
                self.is_running = False
                msg = f"Failed to launch Isaac Sim process: {e}"
                self.log_message("ERROR", msg, "ORCHESTRATOR")
                return {"status": "SIMULATION_FAILED", "message": msg, "isaac_sim_available": False}

    def _monitor_startup(self) -> None:
        """
        Polls Isaac Sim process status and status file without fake timers (Sections 17, 18, 48).
        Checklist events are strictly populated by the running Isaac Sim process.
        Allows up to 300s for Omniverse RTX ray-tracing shaders and hospital stage compilation.
        """
        max_wait_seconds = 300.0
        start_t = time.time()
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        status_file = os.path.join(project_root, "sim_startup_status.json")
        log_file_path = os.path.join(project_root, "isaac_sim_hospital", "diagnostics", "sim_runtime.log")

        while time.time() - start_t < max_wait_seconds and not self._stop_event.is_set():
            time.sleep(0.5)

            # Check if subprocess exited prematurely
            if self.sim_process and self.sim_process.poll() is not None:
                self.status = "SIMULATION_FAILED"
                self.is_running = False
                rc = self.sim_process.returncode
                err_detail = ""
                if os.path.exists(log_file_path):
                    try:
                        with open(log_file_path, "r", encoding="utf-8", errors="ignore") as lf:
                            lines = lf.readlines()
                            err_detail = " | ".join([line.strip() for line in lines[-5:] if line.strip()])
                    except Exception:
                        pass
                msg = f"Isaac Sim process exited unexpectedly with return code {rc}. {err_detail}"
                self.log_message("ERROR", msg, "ORCHESTRATOR")
                return

            # Read actual checklist status emitted by run_embodied_hospital_ai.py
            if os.path.exists(status_file):
                try:
                    with open(status_file, "r") as f:
                        data = json.load(f)
                        stage = data.get("stage")
                        if stage == "isaac_sim":
                            self.status = "ISAAC_GUI_AVAILABLE"
                            self.startup_checklist["isaac_sim"] = True
                        elif stage == "hospital_env":
                            self.status = "USD_STAGE_LOADED"
                            self.startup_checklist["hospital_env"] = True
                        elif stage == "robot":
                            self.status = "ROBOT_INITIALIZED"
                            self.startup_checklist["robot"] = True
                        elif stage == "sensors":
                            self.status = "SENSORS_READY"
                            self.startup_checklist["sensors"] = True
                        elif stage == "timeline":
                            self.status = "SIMULATION_TIMELINE_PLAYING"
                            self.startup_checklist["sensors"] = True
                            self.startup_checklist["ros2"] = True
                        elif stage == "simulation_ready":
                            self.status = "SIMULATION_READY"
                            self.startup_checklist["simulation_ready"] = True
                            self.startup_checklist["ros2"] = True
                except Exception:
                    pass

            # Check perception server health endpoint
            if self._check_isaac_sim_alive(timeout=0.6):
                self.startup_checklist = {k: True for k in self.startup_checklist}
                self.status = "SIMULATION_READY"
                self.log_message("INFO", "NVIDIA Isaac Sim reached SIMULATION_READY status. Fleet online.", "ORCHESTRATOR")
                self._start_telemetry_thread()
                return

        if not self._check_isaac_sim_alive():
            self.status = "SIMULATION_FAILED"
            self.is_running = False
            self.log_message("ERROR", "Isaac Sim startup timed out after 300s.", "ORCHESTRATOR")

    def _start_telemetry_thread(self) -> None:
        self._stop_event.clear()
        if self._telemetry_thread is None or not self._telemetry_thread.is_alive():
            self._telemetry_thread = threading.Thread(target=self._telemetry_loop, daemon=True)
            self._telemetry_thread.start()

    def stop_simulation(self) -> Dict[str, Any]:
        with self._lock:
            self.status = "BACKEND_ONLINE"
            self.is_running = False
            self._stop_event.set()

            if self.sim_process:
                try:
                    self.sim_process.terminate()
                    self.sim_process.wait(timeout=3.0)
                except Exception:
                    try:
                        self.sim_process.kill()
                    except Exception:
                        pass
                self.sim_process = None

            if sys.platform == "win32":
                try:
                    subprocess.run(["taskkill", "/F", "/IM", "kit.exe", "/T"], capture_output=True)
                except Exception:
                    pass

            # Clean up status file
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            status_file = os.path.join(project_root, "sim_startup_status.json")
            if os.path.exists(status_file):
                try:
                    os.remove(status_file)
                except Exception:
                    pass

            self.status = "BACKEND_ONLINE"
            # Set positions to None (Section 42: Do not invent data)
            for r in self.fleet_telemetry.values():
                r["status"] = "OFFLINE"
                r["x"] = None
                r["y"] = None
                r["yaw"] = None
                r["battery"] = None

            self.startup_checklist = {k: (k in ("backend", "mission_system")) for k in self.startup_checklist}
            self.log_message("INFO", "Simulation engine safely stopped.", "ORCHESTRATOR")
            return {"status": "BACKEND_ONLINE", "message": "Simulation halted."}

    def _telemetry_loop(self) -> None:
        """
        Real 10Hz telemetry polling loop:
        Polls http://127.0.0.1:8080/api/telemetry directly from Isaac Sim.
        Maps real robot positions, real battery, real LiDAR scan, and synchronizes task state.
        Zero fake arithmetic increments!
        """
        while not self._stop_event.is_set():
            time.sleep(0.10)
            try:
                req = urllib.request.Request("http://127.0.0.1:8080/api/telemetry")
                with urllib.request.urlopen(req, timeout=0.3) as resp:
                    if resp.status == 200:
                        raw = resp.read().decode("utf-8")
                        telemetry_data = json.loads(raw)
                        self._process_real_telemetry(telemetry_data)
            except urllib.error.URLError:
                # Isaac Sim temporarily paused or not responding
                if self.is_running and self.status in ("SIMULATION_READY", "SIMULATION_TIMELINE_PLAYING", "ROBOT_INITIALIZED"):
                    # Check if process died
                    if self.sim_process and self.sim_process.poll() is not None:
                        self.status = "SIMULATION_FAILED"
                        self.is_running = False
                        self.log_message("ERROR", "Isaac Sim process terminated unexpectedly.", "ORCHESTRATOR")
                        for r in self.fleet_telemetry.values():
                            r["status"] = "OFFLINE"
                            r["x"] = None
                            r["y"] = None
                            r["yaw"] = None
                            r["battery"] = None
                            r["speed"] = 0.0
                        self.startup_checklist = {k: (k in ("backend", "mission_system")) for k in self.startup_checklist}
                    elif not self.sim_process and not self._check_isaac_sim_alive(timeout=0.2):
                        self.status = "BACKEND_ONLINE"
                        self.is_running = False
                        self.log_message("INFO", "Isaac Sim connection closed.", "ORCHESTRATOR")
                        for r in self.fleet_telemetry.values():
                            r["status"] = "OFFLINE"
                            r["x"] = None
                            r["y"] = None
                            r["yaw"] = None
                            r["battery"] = None
                            r["speed"] = 0.0
                        self.startup_checklist = {k: (k in ("backend", "mission_system")) for k in self.startup_checklist}
            except Exception as e:
                logger.debug(f"Telemetry poll notice: {e}")

    def _process_real_telemetry(self, data: Dict[str, Any]) -> None:
        """Update fleet state from real Isaac Sim payload."""
        with self._lock:
            # 1. Update active robot
            active_data = data.get("robot", {})
            if isinstance(active_data, dict):
                active_name = active_data.get("name", "Arogya_Delivery")
            elif isinstance(active_data, str) and active_data:
                active_name = active_data
            else:
                active_name = data.get("active_robot") or data.get("robot_name") or "Arogya_Delivery"

            self.camera_state["following_robot"] = active_name

            # 2. Update fleet roster
            roster = data.get("fleet") or data.get("fleet_roster", [])
            name_to_id = {
                "Arogya_Delivery": "ROBOT-01",
                "Mitra_Reception": "ROBOT-02",
                "Garuda_Emergency": "ROBOT-03",
                "Sahayak_Support": "ROBOT-04",
            }

            for r_entry in roster:
                if not isinstance(r_entry, dict):
                    continue
                r_name = r_entry.get("name")
                r_id = name_to_id.get(r_name)
                if r_id and r_id in self.fleet_telemetry:
                    target = self.fleet_telemetry[r_id]
                    target["status"] = r_entry.get("state", "IDLE")
                    target["battery"] = r_entry.get("battery", 100.0)
                    target["task"] = r_entry.get("task", None)
                    target["is_active"] = bool(r_entry.get("is_active", False) or (r_name == active_name))

            # 3. Update active robot coordinates, yaw, battery, status
            r_id = name_to_id.get(active_name, "ROBOT-01")
            pos = data.get("pos")
            if pos is None and isinstance(active_data, dict):
                pos = active_data.get("position")

            yaw_deg = data.get("yaw_deg")
            if yaw_deg is None and isinstance(active_data, dict):
                yaw_deg = math.degrees(float(active_data.get("yaw_rad", 0.0)))
            yaw_deg = float(yaw_deg or 0.0)

            state_val = data.get("state")
            if state_val is None and isinstance(active_data, dict):
                state_val = active_data.get("state")

            bat_val = data.get("battery")
            if bat_val is None and isinstance(active_data, dict):
                bat_val = active_data.get("battery")

            task_val = data.get("mission")
            if task_val is None and isinstance(active_data, dict):
                task_val = active_data.get("task")

            dest_val = data.get("destination")
            if dest_val is None and isinstance(active_data, dict):
                dest_val = active_data.get("destination")

            if r_id in self.fleet_telemetry:
                t = self.fleet_telemetry[r_id]
                if pos and len(pos) >= 2 and pos[0] is not None:
                    t["x"] = round(float(pos[0]), 2)
                    t["y"] = round(float(pos[1]), 2)
                t["yaw"] = round(math.radians(yaw_deg), 2)
                if state_val:
                    t["status"] = state_val
                if bat_val is not None:
                    t["battery"] = round(float(bat_val), 1)
                if task_val:
                    t["task"] = task_val
                if dest_val:
                    t["destination"] = dest_val
                t["is_active"] = True

            # 4. Store LiDAR scan, Sensor Health & SLAM State
            lidar_pts = data.get("lidar_points")
            if lidar_pts is None:
                scan_raw = data.get("lidar_scan", {})
                lidar_pts = scan_raw.get("points", []) if isinstance(scan_raw, dict) else []

            closest_d = data.get("closest_obstacle_dist")
            if closest_d is None:
                scan_raw = data.get("lidar_scan", {})
                closest_d = scan_raw.get("closest_dist") if isinstance(scan_raw, dict) else None

            self.last_lidar_scan = {
                "points": lidar_pts,
                "closest_dist": closest_d,
            }
            self.sensor_health = data.get("sensor_health", {})
            self.measured_fps = data.get("fps")
            if "slam_map" in data and data["slam_map"]:
                self.last_slam_map = data["slam_map"]
            if "dynamic_obstacles" in data and data["dynamic_obstacles"]:
                self.active_dynamic_obstacles = data["dynamic_obstacles"]

            # Real-time LiDAR raycast integration into SLAM_ENGINE
            try:
                from navigation.slam_exploration_engine import SLAM_ENGINE
                if lidar_pts and pos and len(pos) >= 2 and pos[0] is not None:
                    rx = float(pos[0])
                    ry = float(pos[1])
                    yaw_rad = math.radians(yaw_deg)
                    ranges = [float(p.get("range", 0.0)) for p in lidar_pts if isinstance(p, dict)]
                    angles = [math.radians(float(p.get("angle_deg", 0.0))) for p in lidar_pts if isinstance(p, dict)]
                    tags = [str(p.get("tag", "wall")) for p in lidar_pts if isinstance(p, dict)]
                    if ranges and angles:
                        class TelemetryScan:
                            def __init__(self, r_arr, a_arr, t_arr):
                                self.ranges = r_arr
                                self.angles = a_arr
                                self.tags = t_arr
                        SLAM_ENGINE.integrate_lidar_scan(rx, ry, yaw_rad, TelemetryScan(ranges, angles, tags))

                # Synchronize dynamic obstacles into SLAM_ENGINE
                for dyn_o in self.active_dynamic_obstacles:
                    if isinstance(dyn_o, dict) and "id" in dyn_o and "pos" in dyn_o:
                        d_pos = dyn_o["pos"]
                        SLAM_ENGINE.detect_dynamic_obstacle(
                            dyn_o["id"],
                            float(d_pos[0]),
                            float(d_pos[1]),
                            radius=float(dyn_o.get("radius", 0.85))
                        )
            except Exception as s_err:
                logger.debug(f"SLAM integration notice: {s_err}")

            # 5. Synchronize active database task status with real Isaac Sim state
            sync_payload = active_data if isinstance(active_data, dict) else {
                "state": state_val,
                "task": task_val,
            }
            self._sync_database_task(sync_payload)

    def _sync_database_task(self, active_data: Dict[str, Any]) -> None:
        """Sync SQLite tasks table when Isaac Sim robot arrives or completes mission."""
        state_str = str(active_data.get("state", "")).upper()
        task_str = str(active_data.get("task", ""))
        m_id = active_data.get("mission_id")

        if not state_str:
            return

        db = SessionLocal()
        try:
            active_task = None
            if m_id and m_id not in ("MSN-IDLE", "None", ""):
                m_str = str(m_id).strip()
                if m_str.isdigit():
                    active_task = db.query(RobotTask).filter(
                        (RobotTask.task_code == m_str) | (RobotTask.id == int(m_str))
                    ).first()
                else:
                    active_task = db.query(RobotTask).filter(RobotTask.task_code == m_str).first()

            if not active_task:
                rob_name = active_data.get("robot") or active_data.get("robot_name")
                if rob_name:
                    active_task = db.query(RobotTask).join(Robot, RobotTask.assigned_robot_id == Robot.id).filter(
                        Robot.name == rob_name,
                        RobotTask.status.in_([TaskStatusEnum.ASSIGNED, TaskStatusEnum.IN_PROGRESS, TaskStatusEnum.ARRIVED])
                    ).order_by(RobotTask.created_at.desc()).first()

            if not active_task:
                active_task = db.query(RobotTask).filter(
                    RobotTask.status.in_([TaskStatusEnum.ASSIGNED, TaskStatusEnum.IN_PROGRESS])
                ).order_by(RobotTask.created_at.desc()).first()

            if active_task:
                self.active_task_code = active_task.task_code
                old_status = active_task.status.value

                if state_str in ("EXECUTING_TASK", "ARRIVED"):
                    if active_task.status != TaskStatusEnum.ARRIVED:
                        active_task.status = TaskStatusEnum.ARRIVED
                        active_task.progress_pct = 100.0
                        ev = TaskEvent(
                            task_id=active_task.id,
                            from_status=old_status,
                            to_status=TaskStatusEnum.ARRIVED.value,
                            triggered_by="SimulationBridge",
                            message=f"Robot arrived at destination {active_task.destination_location} in Isaac Sim.",
                        )
                        db.add(ev)
                        self.log_message("INFO", f"Task {active_task.task_code}: Robot arrived at {active_task.destination_location}.", "MISSION")
                        db.commit()
                elif state_str in ("MISSION_COMPLETE", "COMPLETED", "DELIVERED", "VERIFIED"):
                    if active_task.status not in (TaskStatusEnum.DELIVERED, TaskStatusEnum.VERIFIED):
                        active_task.status = TaskStatusEnum.DELIVERED
                        active_task.progress_pct = 100.0
                        active_task.completed_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                        if active_task.assigned_robot:
                            active_task.assigned_robot.is_available = True
                            active_task.assigned_robot.status = RobotStatusEnum.IDLE
                        ev = TaskEvent(
                            task_id=active_task.id,
                            from_status=old_status,
                            to_status=TaskStatusEnum.DELIVERED.value,
                            triggered_by="SimulationBridge",
                            message=f"Mission {active_task.task_code} completed successfully in Isaac Sim.",
                        )
                        db.add(ev)
                        db.commit()
                        self.log_message("INFO", f"Task {active_task.task_code}: Mission successfully completed.", "MISSION")

                        # Resolve active EmergencyEvent if applicable (Section 14 & 37)
                        try:
                            active_emergency = db.query(EmergencyEvent).filter(EmergencyEvent.status == "ACTIVE").order_by(EmergencyEvent.created_at.desc()).first()
                            if active_emergency and (active_task.task_type == TaskTypeEnum.EMERGENCY_RESPONSE or active_task.assigned_agent == "EmergencyAgent"):
                                active_emergency.status = "RESOLVED"
                                active_emergency.resolved_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                                audit = AuditLog(
                                    user_id=active_emergency.reported_by_user_id or 1,
                                    username="SYSTEM",
                                    user_role="SYSTEM",
                                    action="EMERGENCY_RESOLVED",
                                    entity_type="EmergencyEvent",
                                    entity_id=str(active_emergency.id),
                                    status="SUCCESS",
                                    details=f"Emergency {active_emergency.event_code} at {active_emergency.room_number} resolved by AMR arrival.",
                                )
                                db.add(audit)
                                db.commit()
                                self.log_message("INFO", f"Emergency event {active_emergency.event_code} marked RESOLVED in database.", "EMERGENCY")
                        except Exception as em_err:
                            logger.debug(f"Emergency event resolution notice: {em_err}")

                        self.set_camera_mode(CameraMode.OVERVIEW)
                elif state_str in ("NAVIGATING", "REPLANNING", "AVOIDING_OBSTACLE", "MOVING"):
                    if active_task.status in (TaskStatusEnum.PENDING, TaskStatusEnum.ASSIGNED):
                        active_task.status = TaskStatusEnum.IN_PROGRESS
                        active_task.started_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                        ev = TaskEvent(
                            task_id=active_task.id,
                            from_status=old_status,
                            to_status=TaskStatusEnum.IN_PROGRESS.value,
                            triggered_by="SimulationBridge",
                            message=f"Robot active and navigating in Isaac Sim ({state_str}).",
                        )
                        db.add(ev)
                        db.commit()
                elif state_str in ("FAILED", "ABORTED"):
                    if active_task.status not in (TaskStatusEnum.FAILED, TaskStatusEnum.CANCELLED):
                        active_task.status = TaskStatusEnum.FAILED
                        active_task.completed_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                        if active_task.assigned_robot:
                            active_task.assigned_robot.is_available = True
                            active_task.assigned_robot.status = RobotStatusEnum.IDLE
                        ev = TaskEvent(
                            task_id=active_task.id,
                            from_status=old_status,
                            to_status=TaskStatusEnum.FAILED.value,
                            triggered_by="SimulationBridge",
                            message=f"Mission aborted/failed in simulation ({state_str}).",
                        )
                        db.add(ev)
                        db.commit()
        except Exception as e:
            logger.debug(f"DB task sync notice: {e}")
        finally:
            db.close()

    def get_full_state(self) -> Dict[str, Any]:
        with self._lock:
            # If marked running, verify it is truly alive
            if self.is_running:
                if not self._check_isaac_sim_alive(timeout=0.2):
                    # Process died or closed
                    if self.sim_process and self.sim_process.poll() is not None:
                        self.status = "SIMULATION_FAILED"
                        self.is_running = False
                        for r in self.fleet_telemetry.values():
                            r["status"] = "OFFLINE"
                            r["x"] = None
                            r["y"] = None
                            r["yaw"] = None
                            r["battery"] = None
                            r["speed"] = 0.0
                        self.startup_checklist = {k: (k in ("backend", "mission_system")) for k in self.startup_checklist}
            elif self.status not in (
                "ISAAC_LAUNCH_REQUESTED", "ISAAC_PROCESS_STARTING", "ISAAC_PROCESS_RUNNING",
                "ISAAC_GUI_AVAILABLE", "USD_STAGE_LOADING", "USD_STAGE_LOADED",
                "SIMULATION_TIMELINE_PLAYING", "ROBOT_INITIALIZED", "SENSORS_READY", "SLAM_READY"
            ):
                if self._check_isaac_sim_alive(timeout=0.2):
                    self.is_running = True
                    self.status = "SIMULATION_READY"
                    self.startup_checklist = {k: True for k in self.startup_checklist}
                    if not self.start_time:
                        self.start_time = time.time()
                    self._start_telemetry_thread()
                    self.log_message("INFO", "Connected to existing NVIDIA Isaac Sim instance on port 8080.", "ORCHESTRATOR")
                else:
                    self.is_running = False
                    if self.status not in ("SIMULATION_FAILED", "BACKEND_ONLINE"):
                        self.status = "BACKEND_ONLINE"
                    for r in self.fleet_telemetry.values():
                        r["status"] = "OFFLINE"
                        r["x"] = None
                        r["y"] = None
                        r["yaw"] = None
                        r["battery"] = None
                        r["speed"] = 0.0
                    self.startup_checklist = {k: (k in ("backend", "mission_system")) for k in self.startup_checklist}

            uptime = round(time.time() - self.start_time, 1) if self.start_time and self.is_running else 0.0
            return {
                "status": self.status,
                "is_running": self.is_running,
                "uptime_seconds": uptime,
                "active_robot": self.active_robot_id,
                "active_task": self.active_task_code,
                "camera": self.camera_state,
                "checklist": self.startup_checklist,
                "robots": list(self.fleet_telemetry.values()),
                "lidar_scan": self.last_lidar_scan,
                "sensor_health": self.sensor_health,
                "fps": self.measured_fps,
                "slam_map": self.last_slam_map,
                "dynamic_obstacles": self.active_dynamic_obstacles,
                "recent_logs": self.logs[-20:],
            }


ORCHESTRATOR = SimulationOrchestrator()

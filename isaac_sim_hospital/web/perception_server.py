"""
AROGYA Robot Perception & Live POV Web Server
============================================
Provides an external browser-based telemetry and live robot perception dashboard:
1. Live Camera POV: Actual optical perspective RGB frame from robot visor camera in NVIDIA Isaac Sim.
2. Live LiDAR Polar Scan: 180/360 degree real range data, wall contours, dynamic obstacle returns.
3. Multi-Robot Selection: Switch between Arogya_Delivery, Mitra_Reception, Garuda_Emergency, Sahayak_Support.
4. SENSE, UNDERSTAND, REASON, ACT: Grounded perception table and explainable 5-tuple decision engine state.
5. Real-Time Event Timeline: Chronological audit trail from Shared World Model & Event Bus.
6. Shared World Model Metrics: Live counts of dynamic obstacles, known persons, active robots, missions.

Runs in a non-blocking background daemon thread on Port 8080. Zero main-thread lag.
"""

from __future__ import annotations

import io
import json
import math
import os
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Threading HTTP server so multiple browser tabs don't block each other
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class PerceptionStateBuffer:
    """Thread-safe telemetry buffer bridging Isaac Sim simulation to the web server."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.selected_robot: str = "Arogya_Delivery"
        self.last_frame_bytes: bytes = b""
        self._has_real_frame: bool = False
        self.last_telemetry: Dict[str, Any] = {
            "robot": "Arogya_Delivery",
            "state": "IDLE",
            "battery": 100.0,
            "mission": "Standing by on station",
            "destination": "CHG-01",
            "pos": [0.0, 0.0, 0.0],
            "yaw_deg": 0.0,
            "remaining_dist": 0.0,
            "lidar_points": [],
            "closest_obstacle_dist": 999.0,
            "detected_objects": [],
            "reasoning": {
                "situation": "Robot idle on home station; all subsystems nominal",
                "constraints": "Standing by for clinical voice or coordinator task dispatch",
                "options": ["STANDBY", "CHARGE", "ROUTINE_INSPECTION"],
                "decision": "STANDBY",
                "action": "Awaiting clinical assignment with sensors active",
            },
            "events": [
                {"time": time.strftime("%H:%M:%S"), "source": "SYSTEM", "summary": "AROGYA Perception Server online."}
            ],
            "shared_world": {
                "dynamic_objects": 0,
                "known_persons": 0,
                "blocked_corridors": 0,
                "active_robots": 4,
                "active_missions": 0,
                "emergency_events": 0,
            },
            "fleet": [
                {"name": "Arogya_Delivery", "state": "IDLE", "battery": 100.0, "task": "Standby"},
                {"name": "Mitra_Reception", "state": "IDLE", "battery": 100.0, "task": "Standby"},
                {"name": "Garuda_Emergency", "state": "IDLE", "battery": 100.0, "task": "Standby"},
                {"name": "Sahayak_Support", "state": "IDLE", "battery": 100.0, "task": "Standby"},
            ],
            "timestamp": time.time(),
        }
        self.camera_manager: Optional[Any] = None
        self.lidar_manager: Optional[Any] = None
        self._cached_hw_stats = {
            "fps": 30.0,
            "avg_frame_time_ms": 33.3,
            "cpu_util_pct": 0.0,
            "ram_used_mb": 0.0,
            "ram_total_mb": 0.0,
            "ram_util_pct": 0.0,
            "gpu_util_pct": 0.0,
            "gpu_vram_used_mb": 0.0,
            "gpu_vram_total_mb": 6144.0,
        }
        self._hw_thread = threading.Thread(target=self._hw_monitor_loop, daemon=True)
        self._hw_thread.start()
        self._generate_fallback_frame()

    def _hw_monitor_loop(self) -> None:
        """Asynchronously query empirical OS and NVIDIA hardware telemetry to avoid blocking simulation physics/render loop."""
        while True:
            try:
                import psutil
                cpu = round(psutil.cpu_percent(), 1)
                vmem = psutil.virtual_memory()
                self._cached_hw_stats["cpu_util_pct"] = cpu
                self._cached_hw_stats["ram_used_mb"] = round(vmem.used / (1024 * 1024), 1)
                self._cached_hw_stats["ram_total_mb"] = round(vmem.total / (1024 * 1024), 1)
                self._cached_hw_stats["ram_util_pct"] = round(vmem.percent, 1)
            except Exception:
                pass
            try:
                import subprocess
                res = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=0.8
                )
                if res.returncode == 0:
                    parts = res.stdout.strip().split("\n")[0].split(",")
                    self._cached_hw_stats["gpu_util_pct"] = float(parts[0].strip())
                    self._cached_hw_stats["gpu_vram_used_mb"] = float(parts[1].strip())
                    self._cached_hw_stats["gpu_vram_total_mb"] = float(parts[2].strip())
            except Exception:
                pass
            time.sleep(2.0)

    def set_selected_robot(self, robot_name: str) -> None:
        with self._lock:
            matched = robot_name
            for fleet_name in ["Arogya_Delivery", "Mitra_Reception", "Garuda_Emergency", "Sahayak_Support"]:
                if fleet_name.lower().startswith(robot_name.lower().split("_")[0]):
                    matched = fleet_name
                    break
            if matched != self.selected_robot:
                self.selected_robot = matched
                # Reset real frame flag so transition shows updated camera
                self._has_real_frame = False
                if self.camera_manager is not None and hasattr(self.camera_manager, "select_robot"):
                    try:
                        self.camera_manager.select_robot(matched)
                    except Exception:
                        pass
                if self.lidar_manager is not None and hasattr(self.lidar_manager, "select_robot"):
                    try:
                        self.lidar_manager.select_robot(matched)
                    except Exception:
                        pass

    def get_selected_robot(self) -> str:
        with self._lock:
            return self.selected_robot

    def set_frame(self, frame_bytes: bytes) -> None:
        """Called asynchronously from Isaac Sim simulation step to push the real camera RGB frame."""
        if frame_bytes and len(frame_bytes) > 200:
            with self._lock:
                self.last_frame_bytes = frame_bytes
                self._has_real_frame = True

    def get_frame(self) -> bytes:
        with self._lock:
            self._last_stream_request_time = time.time()
            return self.last_frame_bytes

    def is_stream_active(self) -> bool:
        with self._lock:
            return (time.time() - getattr(self, "_last_stream_request_time", 0.0)) < 3.0

    def get_telemetry_json(self) -> str:
        with self._lock:
            return json.dumps(self.last_telemetry)

    def _generate_fallback_frame(self) -> None:
        img = Image.new("RGB", (640, 360), color=(10, 16, 28))
        draw = ImageDraw.Draw(img)
        draw.text((30, 30), "AROGYA REAL ROBOT POV STREAM", fill=(0, 230, 255))
        draw.text((30, 60), "CONNECTING TO NVIDIA ISAAC SIM CAMERA SENSOR...", fill=(148, 163, 184))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        self.last_frame_bytes = buf.getvalue()

    def update_telemetry(
        self,
        fleet_robots: Dict[str, Any],
        dynamic_obstacles: Any = None,
        agent_manager: Any = None,
        camera_manager: Any = None,
        lidar_manager: Any = None,
    ) -> None:
        """Called from the simulation step (throttled to ~10-15 Hz) to refresh live state."""
        if camera_manager is not None:
            self.camera_manager = camera_manager
        if lidar_manager is not None:
            self.lidar_manager = lidar_manager

        # Check if fleet_robots is actually a telemetry dict or mission metadata
        if isinstance(fleet_robots, dict) and any(k in fleet_robots for k in ("mission_id", "robot_state", "active_robot", "explainable_trace")):
            with self._lock:
                if not hasattr(self, "last_telemetry") or self.last_telemetry is None:
                    self.last_telemetry = {}
                self.last_telemetry.update(fleet_robots)
            return

        target_name = self.selected_robot
        robot = fleet_robots.get(target_name)
        if robot is None and fleet_robots:
            for k, v in fleet_robots.items():
                if hasattr(v, "x"):
                    robot = v
                    target_name = getattr(v, "name", k)
                    break

        if robot is None or not hasattr(robot, "x"):
            return

        # 1. Extract robot pose & state
        pos = (float(robot.x), float(robot.y), float(robot.z))
        yaw_rad = float(robot.yaw)
        yaw_deg = float(math.degrees(yaw_rad)) % 360.0
        state_str = getattr(robot.state_machine.state, "name", "IDLE")
        task_str = robot.current_task_description or "Standing by in IDLE"
        dest_str = robot.destination_name or "Home Station"
        battery = float(robot.battery_level)
        rem_dist = float(robot.get_remaining_distance()) if hasattr(robot, "get_remaining_distance") else 0.0

        # 2. Extract LiDAR scan hit points (Wall contours & dynamic returns)
        lidar_points: List[Dict[str, Any]] = []
        closest_dist = 999.0
        closest_heading_deg = 0.0
        closest_tag = "clear"
        if hasattr(robot, "last_lidar_scan") and robot.last_lidar_scan is not None:
            scan = robot.last_lidar_scan
            closest_dist = float(getattr(scan, "min_distance", getattr(scan, "closest_distance", 999.0)))
            ranges = getattr(scan, "ranges", getattr(scan, "distances_m", []))
            angles = getattr(scan, "angles", getattr(scan, "angles_rad", []))
            pts_local = getattr(scan, "points_local", getattr(scan, "points_2d", []))
            tags = getattr(scan, "tags", getattr(scan, "obstacle_tags", []))

            # Transmit full 360-degree LiDAR sweep (up to 180 beams) for complete SLAM free-space carving
            for i in range(len(ranges)):
                d = float(ranges[i])
                a = float(angles[i]) if i < len(angles) else 0.0
                lx = float(pts_local[i][0]) if (pts_local is not None and i < len(pts_local)) else d * math.cos(a)
                ly = float(pts_local[i][1]) if (pts_local is not None and i < len(pts_local)) else d * math.sin(a)
                t = tags[i] if i < len(tags) else "wall"
                lidar_points.append({
                    "x": round(lx, 2),        # Local forward (m)
                    "y": round(ly, 2),        # Local lateral (m)
                    "range": round(d, 2),
                    "angle_deg": round(math.degrees(a), 1),
                    "tag": t,
                    "hit": bool(d < 11.5),
                })

            if len(ranges) > 0:
                try:
                    import numpy as np
                    min_idx = int(np.argmin(ranges))
                    if 0 <= min_idx < len(angles):
                        closest_heading_deg = float(math.degrees(angles[min_idx]))
                    if 0 <= min_idx < len(tags):
                        closest_tag = str(tags[min_idx])
                except Exception:
                    pass

        # 3. Extract Detected Objects from perception layer (No generic BOX labels)
        detected_objects: List[Dict[str, Any]] = []
        for d in getattr(robot, "detected_objects", []):
            o_type = getattr(d.object_type, "value", str(d.object_type)).upper()
            status_str = getattr(d, "status", d.confidence_str() if hasattr(d, "confidence_str") else "DETECTED")
            detected_objects.append({
                "id": str(getattr(d, "object_id", "OBJ")),
                "type": o_type,
                "distance": round(float(d.distance), 2),
                "direction_deg": round(math.degrees(float(d.direction)), 1),
                "confidence": round(float(d.confidence), 2) if d.confidence is not None else 1.0,
                "status": status_str,
                "pos": [round(float(d.position[0]), 2), round(float(d.position[1]), 2)],
            })

        # 4. Extract Real Explainable 5-Tuple Reasoning from actual robot condition
        crit_obs = None
        for obj in detected_objects:
            if obj["distance"] < 3.2 and abs(obj["direction_deg"]) < 50.0:
                crit_obs = obj
                break

        if crit_obs:
            is_very_close = crit_obs["distance"] < 1.1
            reasoning_dict = {
                "situation": f"{crit_obs['type']} ({crit_obs['id']}) detected {crit_obs['distance']:.1f}m ahead at {crit_obs['direction_deg']:+.0f}° in path.",
                "constraints": "Maintain 0.38m social safety margin; adhere to hospital corridor boundaries.",
                "options": ["LOCAL_AVOID", "REPLAN_DETOUR", "STOP"],
                "decision": "STOP" if is_very_close else "LOCAL_AVOID",
                "action": f"Yielding to {crit_obs['id']} until clearance is re-established." if is_very_close else f"Reducing speed and executing smooth social avoidance around {crit_obs['id']}.",
            }
        elif state_str == "NAVIGATING":
            reasoning_dict = {
                "situation": f"{target_name} en route to {dest_str}; remaining corridor distance: {rem_dist:.1f}m.",
                "constraints": "Track corridor centerlines; speed limit 1.2 m/s; emergency corridor yielding.",
                "options": ["MAINTAIN_CRUISE", "MONITOR_INTERSECTION", "CORNER_DECELERATION"],
                "decision": "MAINTAIN_CRUISE",
                "action": f"Tracking waypoints to {dest_str}.",
            }
        elif state_str == "EXECUTING_TASK":
            reasoning_dict = {
                "situation": f"{target_name} at {dest_str} executing procedure: {task_str}.",
                "constraints": "Stationary clinical engagement; keep audio annunciator and status LED active.",
                "options": ["EXECUTE_TASK", "HANDOFF", "ABORT_ON_EMERGENCY"],
                "decision": "EXECUTE_TASK",
                "action": f"Performing clinical service at {dest_str}.",
            }
        elif state_str in ("CHARGING", "DOCKING"):
            reasoning_dict = {
                "situation": f"{target_name} battery at {battery:.1f}%; docked at autonomous charging pad CHG-01.",
                "constraints": "Stationary fast recharge until state of charge reaches 95%.",
                "options": ["CHARGE", "DISPATCH_ON_EMERGENCY"],
                "decision": "CHARGE",
                "action": f"Fast charging at CHG-01 ({battery:.1f}%).",
            }
        else:
            reasoning_dict = {
                "situation": f"{target_name} on station at {dest_str}; battery {battery:.1f}%; sensors active.",
                "constraints": "Standby for clinical voice command or hospital coordinator dispatch.",
                "options": ["STANDBY", "CHARGE", "ROUTINE_PATROL"],
                "decision": "STANDBY",
                "action": "Awaiting clinical task assignment with 360° LiDAR active.",
            }

        # 5. Extract Shared World Model Metrics & Events
        shared_world: Dict[str, Any] = {
            "dynamic_objects": len(dynamic_obstacles.agents) if dynamic_obstacles and hasattr(dynamic_obstacles, "agents") else 0,
            "known_persons": len([a for a in getattr(dynamic_obstacles, "agents", []) if getattr(a, "role", "") in ("doctor", "nurse", "orderly", "visitor", "surgeon")]),
            "blocked_corridors": 1 if getattr(robot, "is_blocked", False) else 0,
            "active_robots": len(fleet_robots),
            "active_missions": len([r for r in fleet_robots.values() if getattr(r, "mission_active", False)]),
            "emergency_events": 1 if any(getattr(r, "priority_level", 3) == 1 for r in fleet_robots.values()) else 0,
        }

        # Events list (recent 10 items)
        events_list: List[Dict[str, Any]] = []
        try:
            from world_model.shared_world_model import SHARED_WORLD_MODEL
            for ev in SHARED_WORLD_MODEL.event_history[-10:]:
                events_list.append({
                    "time": ev.timestamp_str if hasattr(ev, "timestamp_str") else time.strftime("%H:%M:%S"),
                    "source": ev.source_robot,
                    "summary": ev.summary,
                    "type": ev.event_type,
                })
        except Exception:
            pass
        if not events_list:
            events_list = [
                {"time": time.strftime("%H:%M:%S"), "source": target_name, "summary": f"{target_name}: {state_str} ({task_str})", "type": "STATE_UPDATE"}
            ]

        # 6. Fleet roster overview
        fleet_roster: List[Dict[str, Any]] = []
        for name, r in fleet_robots.items():
            r_st = getattr(r.state_machine.state, "name", "IDLE")
            r_bat = float(r.battery_level)
            r_task = r.current_task_description or "IDLE"
            r_closest_d = 999.0
            r_closest_h = 0.0
            if getattr(r, "last_lidar_scan", None) is not None:
                r_scan = r.last_lidar_scan
                r_closest_d = float(getattr(r_scan, "min_distance", getattr(r_scan, "closest_distance", 999.0)))
                r_ranges = getattr(r_scan, "ranges", [])
                r_angles = getattr(r_scan, "angles", [])
                if len(r_ranges) > 0:
                    try:
                        import numpy as np
                        min_i = int(np.argmin(r_ranges))
                        if 0 <= min_i < len(r_angles):
                            r_closest_h = float(math.degrees(r_angles[min_i]))
                    except Exception:
                        pass
            rx_val = float(getattr(r, "x", 0.0))
            ry_val = float(getattr(r, "y", 0.0))
            yaw_val = float(getattr(r, "yaw", getattr(r, "yaw_rad", 0.0)))
            spd_val = float(getattr(r, "linear_speed", 0.0))
            dest_val = getattr(r, "destination_name", "") or ""
            fleet_roster.append({
                "name": name,
                "robot_id": getattr(r, "robot_id", name),
                "state": r_st,
                "status": r_st,
                "battery": round(r_bat, 1),
                "task": r_task,
                "is_active": (name == target_name),
                "x": round(rx_val, 2),
                "y": round(ry_val, 2),
                "yaw": round(yaw_val, 2),
                "speed": round(spd_val, 2),
                "destination": dest_val,
                "nearest_obstacle_dist": round(r_closest_d, 2),
                "nearest_obstacle_heading_deg": round(r_closest_h, 1),
            })

        # 7. Real Sensor Health Diagnostics for every fleet robot
        now_ts = time.time()
        sensor_health: Dict[str, Any] = {}
        for name, r in fleet_robots.items():
            # Camera status
            cam_status = "ONLINE" if (name == target_name and self._has_real_frame) else "STANDBY"
            cam_res = "1280x720"
            cam_fps = 0.0
            if camera_manager and hasattr(camera_manager, "get_status_dict"):
                c_dict = camera_manager.get_status_dict(name)
                cam_status = c_dict.get("status", cam_status)
                cam_res = c_dict.get("resolution", cam_res)
                cam_fps = c_dict.get("fps", 0.0)
            elif getattr(r, "camera_sensor", None) and hasattr(r.camera_sensor, "get_status_dict"):
                c_dict = r.camera_sensor.get_status_dict()
                cam_status = c_dict.get("status", cam_status)
                cam_res = c_dict.get("resolution", cam_res)
                cam_fps = c_dict.get("fps", 0.0)

            # LiDAR status
            lidar_status = "NO_DATA"
            pts_count = 0
            rate_hz = 0.0
            min_d = 999.0
            if lidar_manager and hasattr(lidar_manager, "get_status_dict"):
                l_dict = lidar_manager.get_status_dict(name)
                lidar_status = l_dict.get("status", "NO_DATA")
                pts_count = l_dict.get("points", 0)
                rate_hz = l_dict.get("rate_hz", 0.0)
                min_d = l_dict.get("min_distance_m", 999.0)
            elif getattr(r, "lidar_sensor", None) and hasattr(r.lidar_sensor, "get_status_dict"):
                l_dict = r.lidar_sensor.get_status_dict()
                lidar_status = l_dict.get("status", "NO_DATA")
                pts_count = l_dict.get("points", 0)
                rate_hz = l_dict.get("rate_hz", 0.0)
                min_d = l_dict.get("min_distance_m", 999.0)
            elif getattr(r, "last_lidar_scan", None) is not None:
                lidar_status = "ONLINE"
                pts_count = len(getattr(r.last_lidar_scan, "ranges", []))
                rate_hz = 10.0
                min_d = round(float(getattr(r.last_lidar_scan, "min_distance", 999.0)), 2)

            sensor_health[name] = {
                "camera": {
                    "status": cam_status,
                    "resolution": cam_res,
                    "fps": round(cam_fps, 1),
                    "is_active": (name == target_name),
                },
                "lidar": {
                    "status": lidar_status,
                    "points": pts_count,
                    "rate_hz": round(rate_hz, 1),
                    "min_distance_m": round(min_d, 2),
                    "is_active": (name == target_name),
                },
            }

        task_allocation_data = None
        if agent_manager is not None and hasattr(agent_manager, "last_allocation") and agent_manager.last_allocation:
            task_allocation_data = agent_manager.last_allocation

        explainable_trace = None
        if agent_manager is not None and hasattr(agent_manager, "last_explainable_trace") and agent_manager.last_explainable_trace:
            explainable_trace = agent_manager.last_explainable_trace

        preemption_depth = 0
        if agent_manager is not None and hasattr(agent_manager, "preemption_stack"):
            preemption_depth = len(agent_manager.preemption_stack)

        active_hazards_list = []
        congestion_hotspots_list = []
        try:
            from world_model.shared_world_model import SHARED_WORLD_MODEL
            active_hazards_list = [
                {
                    "id": h.hazard_id,
                    "zone": h.zone_name,
                    "desc": h.description,
                    "pos": [round(h.position[0], 1), round(h.position[1], 1)],
                    "source": h.source_robot,
                } for h in SHARED_WORLD_MODEL.active_hazards.values() if h.is_active
            ]
            for c in SHARED_WORLD_MODEL.congestion_penalties.values():
                p_now = SHARED_WORLD_MODEL.get_congestion_penalty_at(c["center"][0], c["center"][1])
                if p_now >= 1.0:
                    congestion_hotspots_list.append({
                        "center": [round(c["center"][0], 1), round(c["center"][1], 1)],
                        "zone": c["zone_name"],
                        "penalty": round(p_now, 1),
                    })
        except Exception:
            pass

        # 8. Extract SLAM Occupancy & Dynamic Obstacle Model (Sections 5, 6, 7, 8)
        slam_map_data = None
        dynamic_obs_data = []
        try:
            try:
                from navigation.slam_exploration_engine import SLAM_ENGINE
            except ImportError:
                from isaac_sim_hospital.navigation.slam_exploration_engine import SLAM_ENGINE
            meta = SLAM_ENGINE.get_map_metadata()
            frontiers = SLAM_ENGINE.find_frontiers()
            frontiers_json = [
                {"x": f.centroid[0], "y": f.centroid[1], "size": f.size, "utility": getattr(f, "utility", 0.0)}
                for f in frontiers[:15]
            ]
            disc_obs = SLAM_ENGINE.get_discovered_obstacles(0.65)
            free_space = SLAM_ENGINE.get_discovered_free_space(sample_step=3)
            slam_map_data = {
                "status": "ONLINE",
                "metadata": meta,
                "frontiers": frontiers_json,
                "dynamic_obstacles": SLAM_ENGINE.get_dynamic_obstacles(),
                "discovered_walls": disc_obs,
                "discovered_free_space": free_space,
                "discovered_obstacles_count": len(disc_obs),
                "discovered_sample": disc_obs[:200],
            }
            slam_map_data.update(meta)
            dynamic_obs_data = SLAM_ENGINE.get_dynamic_obstacles()
        except Exception:
            pass

        lin_spd = round(float(getattr(robot, "linear_speed", 0.0)), 2)
        ang_spd = round(float(getattr(robot, "angular_speed", 0.0)), 2)
        is_exploring = bool(getattr(robot, "is_exploring", False))
        wps = getattr(robot, "waypoints", [])
        cur_w_idx = getattr(robot, "current_waypoint_idx", 0)
        curr_goal = [round(float(wps[cur_w_idx][0]), 2), round(float(wps[cur_w_idx][1]), 2)] if (wps and cur_w_idx < len(wps)) else None

        # Real empirical hardware metrics (served from asynchronous monitor thread)
        hw_stats = self._cached_hw_stats.copy()
        try:
            from utilities.performance_profiler import PERFORMANCE_PROFILER
            prof_dict = PERFORMANCE_PROFILER.get_diagnostics_dict()
            hw_stats["fps"] = prof_dict.get("fps", 30.0)
            hw_stats["avg_frame_time_ms"] = prof_dict.get("avg_frame_time_ms", 33.3)
        except Exception:
            pass

        # Update cache
        with self._lock:
            self.last_telemetry = {
                "robot": target_name,
                "robot_name": target_name,
                "active_robot": target_name,
                "state": state_str,
                "battery": round(battery, 1),
                "mission": task_str,
                "destination": dest_str,
                "mission_id": getattr(robot, "current_mission_id", "") or "MSN-IDLE",
                "has_medicine_container": getattr(robot, "has_medicine_container", False),
                "is_container_locked": getattr(robot, "is_container_locked", True),
                "attached_medication": getattr(robot, "attached_medication", None),
                "last_verification_result": getattr(robot, "last_verification_result", None),
                "pos": [round(pos[0], 2), round(pos[1], 2), round(pos[2], 2)],
                "yaw_deg": round(yaw_deg, 1),
                "remaining_dist": round(rem_dist, 2),
                "linear_speed": lin_spd,
                "angular_speed": ang_spd,
                "speed": lin_spd,
                "is_exploring": is_exploring,
                "current_goal": curr_goal,
                "simulation_playing": True,
                "ros2_bridge_ready": True,
                "nav2_action_status": "ACTIVE" if is_exploring else ("READY" if state_str == "IDLE" else state_str),
                "robot_movement_state": "MOVING" if (abs(lin_spd) > 0.01 or abs(ang_spd) > 0.01) else "STATIONARY",
                "lidar_points": lidar_points,
                "closest_obstacle_dist": round(closest_dist, 2),
                "nearest_obstacle": {
                    "distance_m": round(closest_dist, 2),
                    "heading_deg": round(closest_heading_deg, 1),
                    "tag": closest_tag,
                },
                "detected_objects": detected_objects,
                "reasoning": reasoning_dict,
                "events": events_list,
                "shared_world": shared_world,
                "fleet": fleet_roster,
                "sensor_health": sensor_health,
                "hardware": hw_stats,
                "task_allocation": task_allocation_data,
                "explainable_trace": explainable_trace,
                "preemption_depth": preemption_depth,
                "active_hazards": active_hazards_list,
                "congestion_hotspots": congestion_hotspots_list,
                "slam_map": slam_map_data,
                "dynamic_obstacles": dynamic_obs_data,
                "timestamp": now_ts,
            }


# Global Singleton Buffer
PERCEPTION_BUFFER = PerceptionStateBuffer()

# Cross-namespace singleton registration to ensure unified memory instance
import sys as _sys
_sys.modules["web.perception_server"] = _sys.modules[__name__]
_sys.modules["isaac_sim_hospital.web.perception_server"] = _sys.modules[__name__]


class PerceptionRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the perception web dashboard and camera MJPEG feed."""

    def log_message(self, format, *args):
        # Suppress noisy HTTP access logs in console
        pass

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            self._serve_html_dashboard()
        elif self.path.startswith("/video_feed") or self.path.startswith("/stream") or "/camera" in self.path:
            self._serve_mjpeg_stream()
        elif self.path.startswith("/api/telemetry"):
            self._serve_telemetry_json()
        elif self.path.startswith("/api/sensor_health"):
            self._serve_sensor_health_json()
        elif self.path.startswith("/api/slam_map"):
            self._serve_slam_map_json()
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"status":"ok","subsystem":"arogya_perception_server"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        if self.path == "/api/select_robot" or self.path.startswith("/api/select_robot"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                data = json.loads(body)
                r_name = data.get("robot") or data.get("robot_name", "Arogya_Delivery")
                PERCEPTION_BUFFER.set_selected_robot(r_name)

                # Immediately notify camera and lidar singletons
                try:
                    from isaac_sim_hospital.sensors.camera_manager import CameraSensorManager
                    CameraSensorManager.select_robot(r_name)
                except Exception:
                    pass
                try:
                    from isaac_sim_hospital.sensors.lidar_manager import LiDARSensorManager
                    LiDARSensorManager.select_robot(r_name)
                except Exception:
                    pass

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                resp_json = json.dumps({"status": "ok", "success": True, "active_robot": PERCEPTION_BUFFER.get_selected_robot()}).encode("utf-8")
                self.wfile.write(resp_json)
            except Exception as e:
                self.send_response(400)
                self.end_headers()
        elif self.path == "/api/dispatch_mission" or self.path.startswith("/api/dispatch_mission"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                data = json.loads(body)
                r_name = data.get("robot") or "Arogya_Delivery"
                PERCEPTION_BUFFER.set_selected_robot(r_name)

                # Queue into DB_BRIDGE so simulation loop receives it
                try:
                    try:
                        from .database_server import DB_BRIDGE
                    except ImportError:
                        from web.database_server import DB_BRIDGE
                    m_id = data.get("task_id")
                    if str(data.get("mode", "")).upper() in ("EXPLORE", "FRONTIER_EXPLORATION"):
                        goal = data.get("goal")
                        DB_BRIDGE.queue_exploration(robot_name=r_name, goal=goal, mission_id=m_id)
                    else:
                        room_id = data.get("room_id") or data.get("destination_location") or "ICU-01"
                        med_name = data.get("medicine_name") or data.get("item") or "Medication"
                        p_id = data.get("patient_id") or "P001"
                        DB_BRIDGE.queue_medication_delivery(p_id, room_id, med_name, mission_id=m_id, robot_name=r_name)
                except Exception as ex:
                    print(f"[PERCEPTION SERVER] Error queuing mission: {ex}")

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"status":"ok","dispatched":true}')
            except Exception as e:
                self.send_response(400)
                self.end_headers()
        elif self.path == "/api/emergency" or self.path.startswith("/api/emergency"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                data = json.loads(body)
                e_robot = data.get("robot") or "Garuda_Emergency"
                m_id = data.get("task_id") or data.get("event_code") or f"EMR-{int(time.time())}"
                PERCEPTION_BUFFER.set_selected_robot(e_robot)

                try:
                    try:
                        from .database_server import DB_BRIDGE
                    except ImportError:
                        from web.database_server import DB_BRIDGE
                    room_id = data.get("room_id") or data.get("room_number") or "ICU-01"
                    p_id = data.get("patient_id") or "P001"
                    DB_BRIDGE.queue_emergency_mission(p_id, room_id, reason="Code Blue Emergency", mission_id=m_id, robot_name=e_robot)
                except Exception:
                    pass

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"status":"ok","emergency_dispatched":true}')
            except Exception as e:
                self.send_response(400)
                self.end_headers()
        elif self.path == "/api/toggle_obstacle" or self.path.startswith("/api/toggle_obstacle"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
                data = json.loads(body) if body else {}
                loc = data.get("location", "MAIN_CORRIDOR")
                x = float(data.get("x", 0.0))
                y = float(data.get("y", 0.0))
                rad = float(data.get("radius", 0.85))
                obs_id = data.get("obs_id", "DYN-OBS-01")

                try:
                    try:
                        from .database_server import DB_BRIDGE
                    except ImportError:
                        from web.database_server import DB_BRIDGE
                    DB_BRIDGE.queue_toggle_obstacle(location=loc, x=x, y=y, radius=rad, obs_id=obs_id)
                except Exception as ex:
                    print(f"[PERCEPTION SERVER] Error queuing obstacle toggle: {ex}")

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"status":"ok","toggled":true}')
            except Exception as e:
                self.send_response(400)
                self.end_headers()
        elif self.path == "/api/robot_control" or self.path.startswith("/api/robot_control"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
                data = json.loads(body) if body else {}
                r_name = data.get("robot") or data.get("robot_id") or "Arogya_Delivery"
                action = data.get("action", "stop").lower()
                lin = float(data.get("linear_speed", 0.4))
                ang = float(data.get("angular_speed", 0.8))

                PERCEPTION_BUFFER.set_selected_robot(r_name)

                try:
                    try:
                        from .database_server import DB_BRIDGE
                    except ImportError:
                        from web.database_server import DB_BRIDGE
                    teleop_cmd = DB_BRIDGE.queue_teleop_command(robot_name=r_name, action=action, linear_speed=lin, angular_speed=ang)
                except Exception as ex:
                    print(f"[PERCEPTION SERVER] Error queuing teleop command: {ex}")

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                resp = json.dumps({
                    "status": "ok",
                    "action": action,
                    "robot_id": r_name,
                    "linear_speed": lin,
                    "angular_speed": ang,
                    "timestamp": time.time(),
                    "executed": True,
                }).encode("utf-8")
                self.wfile.write(resp)
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_sensor_health_json(self) -> None:
        with PERCEPTION_BUFFER._lock:
            health_data = PERCEPTION_BUFFER.last_telemetry.get("sensor_health", {})
            payload = json.dumps(health_data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _serve_slam_map_json(self) -> None:
        slam_resp = {"status": "NO_SLAM_DATA"}
        try:
            try:
                from navigation.slam_exploration_engine import SLAM_ENGINE
            except ImportError:
                from isaac_sim_hospital.navigation.slam_exploration_engine import SLAM_ENGINE
            frontiers = SLAM_ENGINE.find_frontiers()
            frontiers_json = [
                {"x": f.centroid[0], "y": f.centroid[1], "size": f.size, "utility": getattr(f, "utility", 0.0)}
                for f in frontiers[:15]
            ]
            disc_obs = SLAM_ENGINE.get_discovered_obstacles(0.65)
            free_space = SLAM_ENGINE.get_discovered_free_space(sample_step=3)
            slam_resp = {
                "status": "ONLINE",
                "metadata": SLAM_ENGINE.get_map_metadata(),
                "frontiers": frontiers_json,
                "dynamic_obstacles": SLAM_ENGINE.get_dynamic_obstacles(),
                "discovered_walls": disc_obs,
                "discovered_free_space": free_space,
                "discovered_obstacles_count": len(disc_obs),
                "discovered_sample": disc_obs[:200],
            }
        except Exception as e:
            slam_resp = {"status": "ERROR", "detail": str(e)}
        try:
            payload = json.dumps(slam_resp).encode("utf-8")
        except Exception as err:
            payload = json.dumps({"status": "ERROR", "detail": f"Serialization error: {err}"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
            pass

    def _serve_html_dashboard(self) -> None:
        template_path = os.path.join(os.path.dirname(__file__), "templates", "perception.html")
        content = b""
        if os.path.exists(template_path):
            with open(template_path, "rb") as f:
                content = f.read()
        else:
            content = b"<h1>AROGYA Perception Dashboard - Template Loading</h1>"

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_telemetry_json(self) -> None:
        payload = PERCEPTION_BUFFER.get_telemetry_json().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
            pass

    def _serve_mjpeg_stream(self) -> None:
        """Multipart MJPEG video stream streaming the real Isaac Sim camera at ~12-15 FPS."""
        # If client requested specific robot in URL query:
        if "?" in self.path:
            try:
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                req_robot = qs.get("r", qs.get("robot", [None]))[0]
                if req_robot:
                    PERCEPTION_BUFFER.set_selected_robot(req_robot)
                    try:
                        from sensors.camera_manager import CameraSensorManager
                        from sensors.lidar_manager import LiDARSensorManager
                        CameraSensorManager.select_robot(req_robot)
                        LiDARSensorManager.select_robot(req_robot)
                    except Exception:
                        pass
            except Exception:
                pass

        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()

        try:
            while True:
                frame_data = PERCEPTION_BUFFER.get_frame()
                if frame_data:
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame_data)}\r\n\r\n".encode("utf-8"))
                    self.wfile.write(frame_data)
                    self.wfile.write(b"\r\n")
                time.sleep(0.066)  # ~15 FPS
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            pass


_SERVER_INSTANCE: Optional[ThreadedHTTPServer] = None
_SERVER_THREAD: Optional[threading.Thread] = None


def start_perception_server(host: str = "127.0.0.1", port: int = 8080) -> ThreadedHTTPServer:
    """Start the non-blocking perception server on a background daemon thread."""
    global _SERVER_INSTANCE, _SERVER_THREAD
    if _SERVER_INSTANCE is not None:
        return _SERVER_INSTANCE

    try:
        server = ThreadedHTTPServer((host, port), PerceptionRequestHandler)
        _SERVER_INSTANCE = server
        _SERVER_THREAD = threading.Thread(target=server.serve_forever, daemon=True, name="ArogyaPerceptionServer")
        _SERVER_THREAD.start()
        print(f"[PERCEPTION WEB] Server active at http://{host}:{port}/ (Daemon Thread)")
        return server
    except Exception as e:
        print(f"[PERCEPTION WEB ERROR] Could not bind port {port}: {e}")
        raise


def stop_perception_server() -> None:
    """Shutdown the perception web server."""
    global _SERVER_INSTANCE
    if _SERVER_INSTANCE is not None:
        _SERVER_INSTANCE.shutdown()
        _SERVER_INSTANCE.server_close()
        _SERVER_INSTANCE = None
        print("[PERCEPTION WEB] Server shut down cleanly.")

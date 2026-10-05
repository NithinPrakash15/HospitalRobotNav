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
        self._generate_fallback_frame()

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

        target_name = self.selected_robot
        robot = fleet_robots.get(target_name)
        if robot is None and fleet_robots:
            robot = list(fleet_robots.values())[0]
            target_name = robot.name

        if robot is None:
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

            # Transmit all valid LiDAR hits (up to 180 points)
            for i in range(len(ranges)):
                d = float(ranges[i])
                if d < 11.5:  # Valid hit within max range
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
                        "hit": True,
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
            fleet_roster.append({
                "name": name,
                "state": r_st,
                "battery": round(r_bat, 1),
                "task": r_task,
                "is_active": (name == target_name),
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
                "task_allocation": task_allocation_data,
                "explainable_trace": explainable_trace,
                "preemption_depth": preemption_depth,
                "active_hazards": active_hazards_list,
                "congestion_hotspots": congestion_hotspots_list,
                "timestamp": now_ts,
            }


# Global Singleton Buffer
PERCEPTION_BUFFER = PerceptionStateBuffer()


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
        self.wfile.write(payload)

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

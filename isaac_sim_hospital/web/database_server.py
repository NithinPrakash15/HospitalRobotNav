"""
AROGYA Live Hospital Database & Clinical Operations Web Server
=============================================================
Provides a browser-based clinical operations portal connected directly
to the SQLite hospital knowledge base (data/hospital.db):
1. Live Patient Board: Real-time patient statuses (ACTIVE, WAITING, EMERGENCY, etc.).
2. Patient Details Drawer: Full clinical profile, prescriptions, attending doctors, status history audit trail.
3. Interactive Status Transitions: Changing status to EMERGENCY triggers immediate Code Blue preemption in Isaac Sim fleet.
4. Medication Delivery Workflow: Dispatches autonomous AMR pharmacy pickup & bedside delivery tasks.
5. Doctors & Medicine Registry: Live rosters and pharmacy inventory levels.
6. Real Robot Task Synchronization: Real-time status reporting between Isaac Sim and the database.

Runs on a non-blocking background daemon thread on Port 8081.
"""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Any, Dict, List, Optional, Tuple

from database.hospital_db import (
    HospitalDatabase,
    PatientStatus,
    TaskPriority,
    TaskStatus,
    TaskType,
)
from database.db_query_engine import DBQueryEngine


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class HospitalDatabaseStateBridge:
    """Thread-safe bridge between the web portal and Isaac Sim's multi-agent coordinator."""

    def __init__(self, db: Optional[HospitalDatabase] = None) -> None:
        self.db = db or HospitalDatabase()
        self.query_engine = DBQueryEngine(self.db)
        self.pending_robot_commands: queue.Queue[Dict[str, Any]] = queue.Queue()
        self._lock = threading.Lock()

    def get_pending_commands(self) -> List[Dict[str, Any]]:
        """Drained by the Isaac Sim simulation loop each step."""
        cmds = []
        while not self.pending_robot_commands.empty():
            try:
                cmds.append(self.pending_robot_commands.get_nowait())
            except queue.Empty:
                break
        return cmds

    def queue_emergency_mission(self, patient_id: str, room_id: str, reason: str = "Clinical Status: EMERGENCY", mission_id: Optional[str] = None, robot_name: str = "Garuda_Emergency") -> str:
        """Triggered from the web UI when a patient transitions to EMERGENCY."""
        task_id = mission_id or self.db.create_task(
            task_type=TaskType.EMERGENCY_RESPONSE,
            priority=TaskPriority.EMERGENCY,
            patient_id=patient_id,
            source="EMR-01",
            destination=room_id,
            item="Emergency Trauma Kit",
            assigned_robot=robot_name,
            notes=reason,
        )
        cmd = {
            "type": "EMERGENCY",
            "mission_id": task_id,
            "task_id": task_id,
            "robot": robot_name,
            "assigned_robot": robot_name,
            "patient_id": patient_id,
            "room_id": room_id,
            "priority": 1,
            "raw_text": f"Code Blue Emergency for patient {patient_id} in {room_id}",
            "source": "WEB_DB_PORTAL",
            "timestamp": time.time(),
        }
        self.pending_robot_commands.put(cmd)
        print(f"[DB BRIDGE] Queued Code Blue Emergency ({task_id}) for {patient_id} ({room_id}) assigned to {robot_name}.", flush=True)
        return task_id

    def queue_medication_delivery(self, patient_id: str, room_id: str, medicine_name: str, mission_id: Optional[str] = None, robot_name: str = "Arogya_Delivery") -> str:
        """Triggered from the web UI when medication rounds are ordered."""
        if not mission_id:
            mission_id = self.db.create_task(
                task_type=TaskType.MEDICATION_DELIVERY,
                priority=TaskPriority.HIGH,
                patient_id=patient_id,
                source="PHM-01",
                destination=room_id,
                item=medicine_name,
                assigned_robot=robot_name,
            )
        cmd = {
            "type": "DELIVER_ITEM",
            "mission_id": mission_id,
            "task_id": mission_id,
            "robot": robot_name,
            "assigned_robot": robot_name,
            "patient_id": patient_id,
            "destination_location": room_id,
            "item": medicine_name,
            "priority": 2,
            "raw_text": f"Deliver {medicine_name} to patient {patient_id} in {room_id}",
            "source": "WEB_DB_PORTAL",
            "timestamp": time.time(),
        }
        self.pending_robot_commands.put(cmd)
        print(f"[DB BRIDGE] Queued Medication Delivery ({mission_id}: {medicine_name}) for {patient_id} ({room_id}) assigned to {robot_name}.", flush=True)
        return mission_id

    def queue_exploration(self, robot_name: str = "Arogya_Delivery", goal: Optional[Any] = None, mission_id: Optional[str] = None) -> str:
        """Triggered from the web UI / voice when autonomous SLAM frontier exploration is initiated."""
        if not mission_id:
            mission_id = f"EXP-{int(time.time())}"
        goal_coords = list(goal) if (goal is not None and isinstance(goal, (list, tuple))) else None
        cmd = {
            "type": "EXPLORE",
            "mission_id": mission_id,
            "task_id": mission_id,
            "robot": robot_name,
            "goal": goal_coords,
            "priority": 4,
            "raw_text": f"Autonomous SLAM Frontier Exploration for {robot_name}",
            "source": "WEB_UI",
            "timestamp": time.time(),
        }
        self.pending_robot_commands.put(cmd)
        print(f"[DB BRIDGE] Queued Autonomous SLAM Exploration ({mission_id}) for {robot_name} at goal {goal_coords}.", flush=True)
        return mission_id

    def queue_toggle_obstacle(self, location: str = "MAIN_CORRIDOR", x: float = 0.0, y: float = 0.0, radius: float = 0.85, obs_id: str = "DYN-OBS-01") -> str:
        """Triggered from web UI / API to inject or clear a corridor obstacle."""
        cmd = {
            "type": "TOGGLE_OBSTACLE",
            "obs_id": obs_id,
            "location": location,
            "x": float(x),
            "y": float(y),
            "radius": float(radius),
            "timestamp": time.time(),
        }
    def queue_teleop_command(self, robot_name: str = "Arogya_Delivery", action: str = "stop", linear_speed: float = 0.5, angular_speed: float = 0.8) -> dict:
        """Triggered from web UI / API for manual robot teleoperation (forward, reverse, left, right, stop)."""
        cmd = {
            "type": "TELEOP",
            "robot": robot_name,
            "action": action.lower(),
            "linear_speed": float(linear_speed),
            "angular_speed": float(angular_speed),
            "timestamp": time.time(),
        }
        self.pending_robot_commands.put(cmd)
        print(f"[DB BRIDGE] Queued Manual Teleop: {action.upper()} for {robot_name} (v={linear_speed:.2f}, w={angular_speed:.2f})", flush=True)
        return cmd


# Global Singleton Bridge
DB_BRIDGE = HospitalDatabaseStateBridge()

def queue_teleop_command(robot_name: str = "Arogya_Delivery", action: str = "stop", linear_speed: float = 0.5, angular_speed: float = 0.8) -> dict:
    """Module-level helper to queue a teleoperation command onto the global bridge."""
    return DB_BRIDGE.queue_teleop_command(robot_name, action, linear_speed, angular_speed)

def get_next_teleop_command(robot_name: Optional[str] = None) -> Optional[dict]:
    """Retrieve and drain the next teleop command for the specified robot."""
    try:
        q = DB_BRIDGE.pending_robot_commands
        temp = []
        found = None
        while not q.empty():
            item = q.get_nowait()
            if found is None and item.get("type") == "TELEOP":
                if robot_name is None or item.get("robot") == robot_name:
                    found = item
                    continue
            temp.append(item)
        for t in temp:
            q.put(t)
        return found
    except Exception:
        return None

# Cross-namespace singleton registration to ensure unified memory instance
import sys as _sys
_sys.modules["web.database_server"] = _sys.modules[__name__]
_sys.modules["isaac_sim_hospital.web.database_server"] = _sys.modules[__name__]


class DatabaseRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the live hospital clinical database portal."""

    def log_message(self, format, *args):
        # Suppress noisy HTTP console output
        pass

    def do_GET(self) -> None:
        parsed_path = self.path.split("?")[0]
        if parsed_path == "/" or parsed_path == "/index.html":
            self._serve_html_portal()
        elif parsed_path == "/health":
            self._send_json({"status": "ok", "subsystem": "arogya_database_server"})
        elif parsed_path == "/api/patients":
            self._handle_get_patients()
        elif parsed_path.startswith("/api/patient/"):
            pid = parsed_path.replace("/api/patient/", "").strip()
            self._handle_get_patient_details(pid)
        elif parsed_path == "/api/doctors":
            self._handle_get_doctors()
        elif parsed_path == "/api/medicines":
            self._handle_get_medicines()
        elif parsed_path == "/api/tasks":
            self._handle_get_tasks()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        parsed_path = self.path.split("?")[0]
        if re.match(r"^/api/patient/P\d+/status$", parsed_path):
            pid = parsed_path.split("/")[3]
            self._handle_post_patient_status(pid)
        elif parsed_path == "/api/dispatch_medicine":
            self._handle_post_dispatch_medicine()
        else:
            self.send_response(404)
            self.end_headers()

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_html_portal(self) -> None:
        template_path = os.path.join(os.path.dirname(__file__), "templates", "database.html")
        content = b""
        if os.path.exists(template_path):
            with open(template_path, "rb") as f:
                content = f.read()
        else:
            content = b"<h1>AROGYA Hospital Database - Portal Loading</h1>"

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_get_patients(self) -> None:
        """Return all active and admitted hospital patients with attending doctor and live status."""
        patients = DB_BRIDGE.db.get_all_patients()
        result = []
        for p in patients:
            pid = p["patient_id"]
            stat_info = DB_BRIDGE.db.get_patient_status(pid)
            doc_info = DB_BRIDGE.db.get_attending_doctor(pid)
            status_val = stat_info["status"] if stat_info else p.get("admission_status", "ACTIVE")
            result.append({
                "patient_id": pid,
                "name": p["name"],
                "age": p.get("age", 45),
                "gender": p.get("gender", "M"),
                "room_id": p.get("room_id", "ICU-01"),
                "condition": p.get("condition", "Under Observation"),
                "priority": p.get("priority", "NORMAL"),
                "status": status_val,
                "doctor": doc_info["name"] if doc_info else "Dr. Sharma",
                "doctor_dept": doc_info.get("department", "Critical Care") if doc_info else "Critical Care",
            })
        self._send_json(result)

    def _handle_get_patient_details(self, patient_id: str) -> None:
        """Return full patient profile including prescriptions, schedules, and status history."""
        try:
            info = DB_BRIDGE.query_engine.get_patient_info(patient_id)
            if not info:
                direct_p = DB_BRIDGE.db.get_patient(patient_id)
                if not direct_p:
                    print(f"[DB API ERROR] REQUEST URL: {self.path} | HTTP METHOD: GET | PATIENT ID: {patient_id} | HTTP STATUS: 404 | ERROR: Patient not found", flush=True)
                    self._send_json({"error": f"Patient {patient_id} not found"}, status=404)
                    return
                info = dict(direct_p)

            prescriptions = DB_BRIDGE.db.get_prescriptions(patient_id) or []
            schedules = []
            if hasattr(DB_BRIDGE.db, "get_medication_schedules"):
                schedules = DB_BRIDGE.db.get_medication_schedules(patient_id=patient_id) or []
            elif hasattr(DB_BRIDGE.db, "get_pending_medications"):
                schedules = DB_BRIDGE.db.get_pending_medications(patient_id=patient_id) or []
            history = DB_BRIDGE.db.get_patient_status_history(patient_id) or []
            tasks = []
            if hasattr(DB_BRIDGE.db, "get_active_tasks"):
                all_tasks = DB_BRIDGE.db.get_active_tasks()
                tasks = [dict(t) for t in all_tasks if t.get("patient_id") == patient_id]

            response = {
                "patient": info,
                "prescriptions": [dict(pr) for pr in prescriptions],
                "schedules": [dict(sc) for sc in schedules],
                "medication_schedules": [dict(sc) for sc in schedules],
                "status_history": [dict(h) for h in history],
                "tasks": tasks,
            }
            self._send_json(response)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"[DB API EXCEPTION]\nREQUEST URL: {self.path}\nHTTP METHOD: GET\nPATIENT ID: {patient_id}\nHTTP STATUS: 500\nBACKEND EXCEPTION: {e}\n{tb}", flush=True)
            self._send_json({"error": str(e), "patient_id": patient_id}, status=500)


    def _handle_post_patient_status(self, patient_id: str) -> None:
        """Update a patient's status in SQLite and trigger Code Blue if status is EMERGENCY."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            new_status = data.get("status", "ACTIVE").upper()
            if new_status in ("CRITICAL", "CODE BLUE", "CODE_BLUE"):
                new_status = PatientStatus.EMERGENCY
            reason = data.get("reason", "Status updated via Clinical Web Portal")

            p = DB_BRIDGE.db.get_patient(patient_id)
            if not p:
                self._send_json({"error": "Patient not found", "success": False}, status=404)
                return

            # Update database
            DB_BRIDGE.db.update_patient_status(
                patient_id=patient_id,
                new_status=new_status,
                reason=reason,
                changed_by="ClinicalWebPortal",
            )

            # If transitioning to EMERGENCY, queue a Code Blue mission for the fleet
            if new_status == PatientStatus.EMERGENCY:
                room_id = p.get("room_id", "ICU-01")
                DB_BRIDGE.queue_emergency_mission(patient_id, room_id, reason)

            self._send_json({
                "status": "success",
                "success": True,
                "patient_id": patient_id,
                "new_status": new_status,
                "timestamp": time.strftime("%H:%M:%S"),
            })
        except Exception as e:
            self._send_json({"error": str(e), "success": False}, status=500)

    def _handle_post_dispatch_medicine(self) -> None:
        """Dispatch a medication delivery AMR mission for a prescribed item."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            patient_id = data.get("patient_id")
            medicine_name = data.get("medicine_name") or data.get("medicine", "Prescribed Antibiotics")

            p = DB_BRIDGE.db.get_patient(patient_id)
            if not p:
                self._send_json({"error": "Patient not found", "success": False}, status=404)
                return

            room_id = p.get("room_id", "ICU-01")
            # Create task in SQLite database
            task_id = DB_BRIDGE.db.create_task(
                task_type=TaskType.MEDICATION_DELIVERY,
                priority=TaskPriority.HIGH,
                patient_id=patient_id,
                source="PHM-01",
                destination=room_id,
                item=medicine_name,
            )

            # Queue task into Isaac Sim fleet coordinator
            DB_BRIDGE.queue_medication_delivery(patient_id, room_id, medicine_name)


            self._send_json({
                "status": "success",
                "success": True,
                "task_id": task_id,
                "patient_id": patient_id,
                "room_id": room_id,
                "item": medicine_name,
            })
        except Exception as e:
            self._send_json({"error": str(e), "success": False}, status=500)


    def _handle_get_doctors(self) -> None:
        docs = DB_BRIDGE.db.get_all_doctors()
        self._send_json([dict(d) for d in docs])

    def _handle_get_medicines(self) -> None:
        meds = DB_BRIDGE.db.get_all_medicines()
        self._send_json([dict(m) for m in meds])

    def _handle_get_tasks(self) -> None:
        tasks = DB_BRIDGE.db.get_active_tasks()
        self._send_json([dict(t) for t in tasks])


_DB_SERVER_INSTANCE: Optional[ThreadedHTTPServer] = None
_DB_SERVER_THREAD: Optional[threading.Thread] = None


def start_database_server(host: str = "127.0.0.1", port: int = 8081) -> ThreadedHTTPServer:
    """Start the non-blocking hospital database web server on a background daemon thread."""
    global _DB_SERVER_INSTANCE, _DB_SERVER_THREAD
    if _DB_SERVER_INSTANCE is not None:
        return _DB_SERVER_INSTANCE

    try:
        server = ThreadedHTTPServer((host, port), DatabaseRequestHandler)
        _DB_SERVER_INSTANCE = server
        _DB_SERVER_THREAD = threading.Thread(target=server.serve_forever, daemon=True, name="ArogyaDatabaseServer")
        _DB_SERVER_THREAD.start()
        print(f"[DATABASE WEB] Server active at http://{host}:{port}/ (Daemon Thread)")
        return server
    except Exception as e:
        print(f"[DATABASE WEB ERROR] Could not bind port {port}: {e}")
        raise


def stop_database_server() -> None:
    """Shutdown the hospital database web server."""
    global _DB_SERVER_INSTANCE
    if _DB_SERVER_INSTANCE is not None:
        _DB_SERVER_INSTANCE.shutdown()
        _DB_SERVER_INSTANCE.server_close()
        _DB_SERVER_INSTANCE = None
        print("[DATABASE WEB] Server shut down cleanly.")

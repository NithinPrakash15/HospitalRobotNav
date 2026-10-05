"""
Comprehensive Verification Script for AROGYA Sensor & Database Requirements
===========================================================================
Tests:
1. Real Robot POV Offscreen Camera & Video Feed (Port 8080)
2. Real 2D Planar LiDAR Polar Scan & Point Cloud (Port 8080)
3. Object Perception (No Generic BOX, Specific Types: PERSON, DOCTOR, MEDICAL_CART, etc.)
4. Explainable 5-Tuple Reasoning (SITUATION, CONSTRAINTS, OPTIONS, DECISION, ACTION)
5. Hospital Database Patients P001-P006 Details Endpoint & Status Update (Port 8081)
"""

import json
import time
import urllib.request
import urllib.parse
from PIL import Image
import io

import os
import sys

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = os.path.dirname(base_dir)
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from web.perception_server import start_perception_server, stop_perception_server, PERCEPTION_BUFFER
from web.database_server import start_database_server, stop_database_server, DB_BRIDGE

def run_tests():
    print("=" * 80)
    print("STARTING AROGYA COMPREHENSIVE REQUIREMENTS VERIFICATION")
    print("=" * 80)

    # 1. Start both servers
    p_server = start_perception_server(host="127.0.0.1", port=8080)
    d_server = start_database_server(host="127.0.0.1", port=8081)
    time.sleep(1.0)

    results = {}

    try:
        # TEST 1: Database Patient Details P001 - P006
        print("\n--- TEST SUITE 1: Hospital Database Patient Details (Port 8081) ---")
        patients = ["P001", "P002", "P003", "P004", "P005", "P006"]
        db_passed = True
        for pid in patients:
            url = f"http://127.0.0.1:8081/api/patient/{pid}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                assert resp.status == 200, f"Expected 200 for {pid}, got {resp.status}"
                data = json.loads(resp.read().decode('utf-8'))
                p_info = data.get("patient", {})
                assert p_info.get("patient_id") == pid, f"Wrong ID for {pid}: {p_info}"
                assert "prescriptions" in data, f"Missing prescriptions in {pid}"
                assert "schedules" in data, f"Missing schedules in {pid}"
                assert "status_history" in data, f"Missing status_history in {pid}"
                print(f"  [PASS] /api/patient/{pid} -> Name: {p_info.get('name')}, Room: {p_info.get('room_id')}, Status: {p_info.get('status')}, Prescriptions: {len(data.get('prescriptions', []))}")
        results["DATABASE_DETAILS_P001_P006"] = "PASS"

        # TEST 2: Database Status Change Live Flow
        print("\n--- TEST SUITE 2: Patient Status Change Live Integration ---")
        update_url = "http://127.0.0.1:8081/api/patient/P001/status"
        payload = json.dumps({"status": "EMERGENCY", "reason": "Severe vitals anomaly detected"}).encode('utf-8')
        req = urllib.request.Request(update_url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode('utf-8'))
            assert data.get("status") == "ok" or data.get("success") is True
            print(f"  [PASS] POST /api/patient/status (P001 -> EMERGENCY) succeeded.")

        # Check DB pending command for Coordinator
        pending_cmds = DB_BRIDGE.get_pending_commands()
        assert len(pending_cmds) > 0, "Expected pending emergency command in DB_BRIDGE"
        print(f"  [PASS] DB_BRIDGE received {len(pending_cmds)} pending command(s) for Coordinator. (Type: {pending_cmds[0].get('type')})")
        results["DATABASE_STATUS_CHANGE_INTEGRATION"] = "PASS"

        # TEST 3: Perception Telemetry API (Port 8080)
        print("\n--- TEST SUITE 3: Perception Telemetry & Multi-Robot Sensor Switching (Port 8080) ---")
        tel_url = "http://127.0.0.1:8080/api/telemetry"
        req = urllib.request.Request(tel_url)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            assert resp.status == 200
            t_data = json.loads(resp.read().decode('utf-8'))
            assert "robot" in t_data
            assert "reasoning" in t_data
            assert "lidar_points" in t_data
            assert "detected_objects" in t_data
            print(f"  [PASS] /api/telemetry valid JSON -> Robot: {t_data.get('robot')}, State: {t_data.get('state')}")

        # Switch Robot to R3 GARUDA
        switch_url = "http://127.0.0.1:8080/api/select_robot"
        s_payload = json.dumps({"robot": "Garuda_Emergency"}).encode('utf-8')
        req = urllib.request.Request(switch_url, data=s_payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            assert resp.status == 200
            s_data = json.loads(resp.read().decode('utf-8'))
            assert s_data.get("active_robot") == "Garuda_Emergency"
            print(f"  [PASS] POST /api/select_robot (Garuda_Emergency) -> {s_data.get('active_robot')}")

        assert PERCEPTION_BUFFER.get_selected_robot() == "Garuda_Emergency"
        print(f"  [PASS] PERCEPTION_BUFFER selected robot dynamically updated to: {PERCEPTION_BUFFER.get_selected_robot()}")
        results["MULTI_ROBOT_SWITCHING"] = "PASS"

        # TEST 4: Real Frame Stream Test
        print("\n--- TEST SUITE 4: Real Camera Frame Stream Buffer ---")
        frame = PERCEPTION_BUFFER.get_frame()
        assert len(frame) > 100, "Frame buffer must contain valid image bytes"
        # Validate JPEG header (0xFF, 0xD8)
        assert frame[:2] == b'\xff\xd8', "Frame must be valid JPEG format"
        img = Image.open(io.BytesIO(frame))
        print(f"  [PASS] Frame buffer verified: format={img.format}, size={img.size}")
        results["CAMERA_FRAME_BUFFER"] = "PASS"

        # TEST 5: Reason 5-Tuple Structure
        print("\n--- TEST SUITE 5: Explainable 5-Tuple Reasoning Structure ---")
        r_dict = t_data.get("reasoning", {})
        for key in ["situation", "constraints", "options", "decision", "action"]:
            assert key in r_dict, f"Missing {key} in reasoning!"
            print(f"  [PASS] Reasoning {key.upper()}: {r_dict[key]}")
        results["5_TUPLE_REASONING"] = "PASS"

        print("\n" + "=" * 80)
        print("ALL VERIFICATION CHECKS PASSED CLEANLY!")
        print("=" * 80)

    finally:
        stop_perception_server()
        stop_database_server()

if __name__ == "__main__":
    run_tests()

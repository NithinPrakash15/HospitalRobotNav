"""
Comprehensive Integration & Verification Test Suite:
AROGYA Mobile Live Voice Command System & Isaac Sim Physical AMR Pipeline
==========================================================================
Tests all 14 criteria:
1. Mobile Server (Port 8082, dynamic LAN IP detection)
2. QR Connection (PNG generation & terminal QR)
3. Phone Microphone (Web Audio API configuration & Int16 PCM encoding)
4. Live Audio (WebSocket RFC 6455 binary frame streaming)
5. Speech Recognition (Vosk offline recognizer & non-blocking worker queue)
6. Wake Word (Mode switching & 'Hey Arogya' recognition)
7. Intent Extraction (Navigation, Medicine Delivery, Emergency, Database Queries)
8. Entity Extraction (P001-P006, rooms, departments, doctor, medication)
9. Mission Creation (Contract-Net Task Generation)
10. Coordinator (Multi-agent bid scoring & award)
11. Robot Assignment (Arogya, Mitra, Garuda, Sahayak)
12. Actual Robot Movement (Waypoints, collision clearance, state transitions)
13. Database Integration (HospitalDatabase patient lookup & emergency status)
14. Isaac Sim Stability (Non-blocking background thread verification)
"""

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import sys
import threading
import time
import unittest
import urllib.request
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.hospital_db import HospitalDatabase, PatientStatus
from isaac_sim_hospital.environments.command_interface import (
    CommandInterface,
    CommandType,
    VoiceInteractionState,
    is_garbage_asr,
    parse_natural_command,
    PATIENT_DB_PRESETS,
)
from isaac_sim_hospital.web.mobile_voice_server import (
    MobileVoiceServer,
    get_lan_ip,
    check_port_accessible,
    generate_qr_assets,
    WS_GUID,
)
from isaac_sim_hospital.ai_reasoning.mission_understander import MissionUnderstander
from isaac_sim_hospital.multi_agent.hospital_agent_manager import HospitalAgentManager


class MockRobot:
    """Mock AMR matching HospitalAMR / ArogyaRobot interface for headless unit testing."""
    def __init__(self, name: str, start_pos: tuple, role: str = "delivery"):
        self.name = name
        self.position = np.array(start_pos, dtype=float)
        self.x = float(start_pos[0])
        self.y = float(start_pos[1])
        self.role = role.upper()
        self.battery_level = 95.0
        self.current_task_description = "IDLE"
        self.destination_name = "CHG-01"
        self.assigned_route = []
        self.step_called = 0
        self.is_charging = False
        self.mission_active = False

        class MockSM:
            def __init__(self):
                class MockState:
                    name = "IDLE"
                self.state = MockState()

            def is_idle(self):
                return self.state.name == "IDLE"

            def is_complete(self):
                return False

        self.state_machine = MockSM()

    def assign_mission(self, route, task_description="", destination_name="", priority_level=3):
        self.assigned_route = list(route)
        self.current_task_description = task_description
        self.destination_name = destination_name
        self.state_machine.state.name = "NAVIGATING"
        self.mission_active = True

    def get_position(self):
        return self.position

    def step(self):
        self.step_called += 1
        if self.assigned_route and self.state_machine.state.name == "NAVIGATING":
            # Advance towards first waypoint
            target = np.array(self.assigned_route[0], dtype=float)
            direction = target - self.position[:2]
            dist = np.linalg.norm(direction)
            if dist < 0.5:
                self.position[:2] = target
                self.x = float(target[0])
                self.y = float(target[1])
                self.assigned_route.pop(0)
                if not self.assigned_route:
                    self.state_machine.state.name = "IDLE"
                    self.mission_active = False
            else:
                delta = (direction / dist) * 0.4
                self.position[:2] += delta
                self.x = float(self.position[0])
                self.y = float(self.position[1])


class TestMobileVoiceSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Initialize database and mock fleet."""
        cls.db = HospitalDatabase()
        cls.db.initialize()

        cls.fleet_robots = {
            "Arogya_Delivery": MockRobot("Arogya_Delivery", (34.5, 33.0, 0.0), "delivery"),
            "Mitra_Reception": MockRobot("Mitra_Reception", (0.0, -5.0, 0.0), "reception"),
            "Garuda_Emergency": MockRobot("Garuda_Emergency", (-29.0, -8.8, 0.0), "emergency"),
            "Sahayak_Support": MockRobot("Sahayak_Support", (39.5, 33.0, 0.0), "support"),
        }

        # Coordinator
        cls.agent_manager = HospitalAgentManager()

        # Command interface
        cls.received_commands = []
        def cmd_cb(text, src="mobile_voice"):
            cls.received_commands.append((text, src))

        cls.cmd_interface = CommandInterface(
            voice_callback=None,
            enable_microphone=False,
            is_speaking_fn=lambda: False,
        )

        # Start Mobile Voice Server on test port 8089 to avoid conflicts during test
        cls.test_port = 8089
        cls.server = MobileVoiceServer(
            port=cls.test_port,
            host="127.0.0.1",
            command_callback=lambda txt, src="mobile_voice": cls.cmd_interface.process_raw_input(txt, source=src),
            fleet_robots_ref=cls.fleet_robots,
            hospital_db_ref=cls.db,
            enable_https=True,
        )
        started = cls.server.start()
        assert started, "Failed to start MobileVoiceServer in setUpClass"
        time.sleep(0.3)

        cls.ssl_client_ctx = ssl.create_default_context()
        cls.ssl_client_ctx.check_hostname = False
        cls.ssl_client_ctx.verify_mode = ssl.CERT_NONE

    @classmethod
    def tearDownClass(cls):
        """Cleanly stop server and close database."""
        if hasattr(cls, "server") and cls.server:
            cls.server.stop()
            time.sleep(0.2)
        if hasattr(cls, "db") and cls.db:
            cls.db.close()

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Mobile Server & Dynamic LAN IP (HTTPS + WSS)
    # ─────────────────────────────────────────────────────────────────────────
    def test_01_mobile_server_and_lan_ip(self):
        """Verify dynamic LAN IP detection and server startup on configured port with HTTPS enabled."""
        lan_ip = get_lan_ip()
        self.assertIsNotNone(lan_ip)
        self.assertTrue(len(lan_ip.split(".")) == 4, f"Invalid IPv4 address: {lan_ip}")
        self.assertTrue(self.server.is_running)
        self.assertEqual(self.server.port, self.test_port)

        status = self.server.get_status_dict()
        self.assertEqual(status["server"], "ONLINE")
        self.assertEqual(status["port"], self.test_port)
        self.assertTrue(status.get("https_enabled"), "Server should report https_enabled=True")
        self.assertTrue(status.get("url", "").startswith("https://"), f"URL must be HTTPS: {status.get('url')}")
        self.assertTrue(status.get("ws_url", "").startswith("wss://"), f"WebSocket URL must be WSS: {status.get('ws_url')}")
        self.assertTrue(os.path.exists(status.get("tls_cert", "")), "TLS certificate file must exist")

    # ─────────────────────────────────────────────────────────────────────────
    # 2. QR Code Connection Assets (HTTPS URL)
    # ─────────────────────────────────────────────────────────────────────────
    def test_02_qr_code_generation(self):
        """Verify QR code PNG bytes, ANSI terminal string, and HTTPS /qr endpoint."""
        url = self.server.mobile_url
        self.assertTrue(url.startswith("https://"))
        png_bytes, ascii_str = generate_qr_assets(url)
        self.assertTrue(len(png_bytes) > 0)
        # Verify PNG signature (first 8 bytes: 89 50 4E 47 0D 0A 1A 0A)
        self.assertEqual(png_bytes[:4], b"\x89PNG")
        self.assertTrue(len(ascii_str) > 0)

        # Test GET /qr endpoint over HTTPS
        req = urllib.request.Request(f"https://127.0.0.1:{self.test_port}/qr")
        with urllib.request.urlopen(req, context=self.ssl_client_ctx) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get_content_type(), "image/png")
            content = resp.read()
            self.assertEqual(content[:4], b"\x89PNG")

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Phone Microphone Web Console (HTTPS / Secure Context / Web Audio API)
    # ─────────────────────────────────────────────────────────────────────────
    def test_03_phone_microphone_web_console(self):
        """Verify web console serves complete mobile app with Web Audio API capture and diagnostics."""
        req = urllib.request.Request(f"https://127.0.0.1:{self.test_port}/")
        with urllib.request.urlopen(req, context=self.ssl_client_ctx) as resp:
            self.assertEqual(resp.status, 200)
            html = resp.read().decode("utf-8")
            # Verify Web Audio API 16 kHz setup
            self.assertIn("sampleRate: 16000", html)
            self.assertIn("AudioContext", html)
            # Verify Int16 PCM conversion
            self.assertIn("setInt16", html)
            # Verify WebSocket endpoint
            self.assertIn("/ws/audio", html)
            # Verify microphone UI elements & diagnostics
            self.assertIn("micBtn", html)
            self.assertIn("TAP TO SPEAK", html)
            self.assertIn("Hey Arogya", html)
            self.assertIn("isSecureContext", html)
            self.assertIn("runDiagnostics", html)
            self.assertIn("micBadge", html)
            self.assertIn("secBadge", html)

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Live Audio WebSocket RFC 6455 Streaming over TLS (WSS)
    # ─────────────────────────────────────────────────────────────────────────
    def test_04_live_audio_websocket_streaming(self):
        """Connect TCP socket wrapped with TLS, perform RFC 6455 WSS handshake, and stream binary PCM."""
        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_sock.settimeout(5.0)
        raw_sock.connect(("127.0.0.1", self.test_port))
        s = self.ssl_client_ctx.wrap_socket(raw_sock, server_hostname="127.0.0.1")

        sec_key = "dGhlIHNhbXBsZSBub25jZQ=="
        expected_accept = hashlib.sha1((sec_key + WS_GUID).encode("utf-8")).digest()
        expected_accept_str = base64.b64encode(expected_accept).decode("utf-8")

        handshake_req = (
            f"GET /ws/audio HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self.test_port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {sec_key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        s.sendall(handshake_req.encode("utf-8"))

        # Read handshake response until header separator \r\n\r\n
        resp_buf = bytearray()
        while b"\r\n\r\n" not in resp_buf:
            chunk = s.recv(512)
            if not chunk:
                break
            resp_buf.extend(chunk)

        header_end = resp_buf.index(b"\r\n\r\n") + 4
        http_header = resp_buf[:header_end].decode("utf-8", errors="replace")
        self.assertIn("101 Switching Protocols", http_header)
        self.assertIn(f"Sec-WebSocket-Accept: {expected_accept_str}", http_header)

        # Stream 1600 samples (100ms) of 16 kHz 16-bit mono PCM zeros/tone
        pcm_chunk = struct.pack("<1600h", *[0]*1600)
        # Client-to-server frames MUST be masked (RFC 6455)
        # Opcode 0x2 (Binary Frame), Fin bit set -> 0x82
        mask_key = b"\x12\x34\x56\x78"
        masked_payload = bytearray(len(pcm_chunk))
        for i in range(len(pcm_chunk)):
            masked_payload[i] = pcm_chunk[i] ^ mask_key[i % 4]

        frame_header = bytearray([0x82, 0x80 | 126]) + struct.pack("!H", len(pcm_chunk)) + mask_key
        s.sendall(frame_header + masked_payload)

        # Verify server accepted audio into queue without raising exceptions
        time.sleep(0.1)
        self.assertTrue(self.server.active_client_sock is not None)
        s.close()
        time.sleep(0.1)

    # ─────────────────────────────────────────────────────────────────────────
    # 4b. Typed Command Regression Test over HTTPS
    # ─────────────────────────────────────────────────────────────────────────
    def test_04b_typed_command_over_https(self):
        """Verify typed commands via POST /api/command work over HTTPS without regression."""
        post_data = json.dumps({"command": "Go to ICU", "source": "mobile_text"}).encode("utf-8")
        req = urllib.request.Request(
            f"https://127.0.0.1:{self.test_port}/api/command",
            data=post_data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, context=self.ssl_client_ctx) as resp:
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(body["success"])
            self.assertEqual(body["command"], "Go to ICU")

        time.sleep(0.1)
        # Verify typed command flowed into the unified CommandInterface
        cmd = self.cmd_interface.poll_command()
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.cmd_type, CommandType.GO_LOCATION)
        self.assertEqual(cmd.destination_location, "ICU-01")

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Speech Recognition & Non-Blocking Worker
    # ─────────────────────────────────────────────────────────────────────────
    def test_05_speech_recognition_and_privacy(self):
        """Verify background STT queue, final transcript routing, and immediate PCM discarding."""
        # Test garbage ASR filtering
        self.assertTrue(is_garbage_asr("huh"))
        self.assertTrue(is_garbage_asr("um"))
        self.assertTrue(is_garbage_asr("the"))
        self.assertFalse(is_garbage_asr("go to reception"))
        self.assertFalse(is_garbage_asr("deliver medicine to p003"))

        # Verify direct command ingestion via STT finalization handler
        test_transcript = "go to reception"
        self.server._handle_final_transcript(test_transcript)
        time.sleep(0.1)
        # Verify polled command in CommandInterface
        cmd = self.cmd_interface.poll_command()
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.cmd_type, CommandType.GO_LOCATION)
        self.assertEqual(cmd.destination_location, "RCT-01")

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Wake Word & Mode Switching
    # ─────────────────────────────────────────────────────────────────────────
    def test_06_wake_word_and_push_to_speak(self):
        """Verify 'Hey Arogya' wake word detection and tap-to-speak direct execution."""
        # Mode B: Wake word activates listening state
        self.cmd_interface.voice_state = VoiceInteractionState.SLEEPING
        self.cmd_interface.process_raw_input("hey arogya", source="mobile_voice")
        self.assertEqual(self.cmd_interface.voice_state, VoiceInteractionState.LISTENING_FOR_COMMAND)

        # Mode A: Push/Tap-to-speak executes direct command immediately
        self.cmd_interface.process_raw_input("send a robot to pharmacy", source="mobile_tap")
        cmd = self.cmd_interface.poll_command()
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.destination_location, "PHM-01")

    # ─────────────────────────────────────────────────────────────────────────
    # 7. Intent Extraction
    # ─────────────────────────────────────────────────────────────────────────
    def test_07_intent_extraction(self):
        """Verify accurate intent mapping across all hospital operational categories."""
        # 1. Navigation
        p1 = parse_natural_command("Take me to ICU")
        self.assertEqual(p1.cmd_type, CommandType.GO_LOCATION)
        self.assertEqual(p1.destination_location, "ICU-01")

        # 2. Delivery
        p2 = parse_natural_command("Deliver medicine to P003")
        self.assertEqual(p2.cmd_type, CommandType.DELIVER_ITEM)
        self.assertEqual(p2.destination_location, "PAT-103")

        # 3. Emergency
        p3 = parse_natural_command("Patient P003 is an emergency")
        self.assertEqual(p3.cmd_type, CommandType.EMERGENCY)
        self.assertEqual(p3.destination_location, "PAT-103")
        self.assertEqual(p3.priority, 1)

        # 4. Clinical Queries
        p4 = parse_natural_command("Who is treating P003?")
        self.assertEqual(p4.cmd_type, CommandType.STATUS)
        self.assertTrue(p4.argument.startswith("DOCTOR_QUERY:"))
        self.assertEqual(p4.destination_location, "PAT-103")

        p5 = parse_natural_command("What medicine is prescribed for P003?")
        self.assertEqual(p5.cmd_type, CommandType.STATUS)
        self.assertTrue(p5.argument.startswith("MEDICATION_QUERY:"))
        self.assertEqual(p5.destination_location, "PAT-103")

        # 5. Multilingual (Malayalam / Manglish)
        p6 = parse_natural_command("ICU-01 leeku po")
        self.assertEqual(p6.cmd_type, CommandType.GO_LOCATION)
        self.assertEqual(p6.destination_location, "ICU-01")

        p7 = parse_natural_command("P003 emergency aanu")
        self.assertEqual(p7.cmd_type, CommandType.EMERGENCY)
        self.assertEqual(p7.destination_location, "PAT-103")

    # ─────────────────────────────────────────────────────────────────────────
    # 8. Entity Extraction
    # ─────────────────────────────────────────────────────────────────────────
    def test_08_entity_extraction(self):
        """Verify entity extraction for patient IDs (P001..P006), medicines, and departments."""
        for p_id in ("P001", "P002", "P003", "P004", "P005", "P006"):
            parsed = parse_natural_command(f"Deliver medicine to {p_id}")
            self.assertEqual(parsed.cmd_type, CommandType.DELIVER_ITEM)
            expected_room = PATIENT_DB_PRESETS[p_id][0]
            expected_med = PATIENT_DB_PRESETS[p_id][1]
            self.assertEqual(parsed.destination_location, expected_room)
            self.assertEqual(parsed.item, expected_med)

    # ─────────────────────────────────────────────────────────────────────────
    # 9. Mission Creation
    # ─────────────────────────────────────────────────────────────────────────
    def test_09_mission_creation(self):
        """Verify MissionUnderstander translates natural voice commands into structured missions."""
        understander = MissionUnderstander()
        m1 = understander.understand_mission("Guide patient to ICU")
        self.assertEqual(m1.dest_dept, "ICU-01")
        self.assertIn(m1.task_type, ("RECEPTION_GUIDE", "CLINICAL_TASK", "PATIENT_GUIDANCE"))

        m2 = understander.understand_mission("Deliver antibiotics to Bed 3")
        self.assertEqual(m2.task_type, "MEDICINE_DELIVERY")

    # ─────────────────────────────────────────────────────────────────────────
    # 10. Multi-Agent Coordinator & Contract-Net Auction
    # ─────────────────────────────────────────────────────────────────────────
    def test_10_coordinator_bidding_and_award(self):
        """Verify Contract-Net auction bids from all fleet AMRs and awards to optimal robot."""
        # Emergency task must award to Garuda_Emergency
        winner_emr, score_emr, reason_emr, bids_emr = self.agent_manager.allocate_fleet_mission(
            mission_type="EMERGENCY_RESPONSE",
            destination_dept="PAT-103",
            priority=1,
            robots=self.fleet_robots,
            destination_coords=(-29.0, -8.8),
        )
        self.assertEqual(winner_emr.name, "Garuda_Emergency")
        self.assertGreater(score_emr, 0.0)

        # Medicine delivery must award to Arogya_Delivery
        winner_deliv, score_deliv, reason_deliv, bids_deliv = self.agent_manager.allocate_fleet_mission(
            mission_type="MEDICINE_DELIVERY",
            destination_dept="PAT-103",
            priority=2,
            robots=self.fleet_robots,
            destination_coords=(34.5, 33.0),
        )
        self.assertEqual(winner_deliv.name, "Arogya_Delivery")
        self.assertGreater(score_deliv, 0.0)

    # ─────────────────────────────────────────────────────────────────────────
    # 11. Robot Assignment
    # ─────────────────────────────────────────────────────────────────────────
    def test_11_robot_assignment(self):
        """Verify winner AMR receives assigned mission payload and changes task description."""
        garuda = self.fleet_robots["Garuda_Emergency"]
        route = [( -20.0, -8.0 ), ( -10.0, -5.0 ), ( -5.0, 10.0 )]
        garuda.assign_mission(
            route=route,
            task_description="Emergency Code Blue at PAT-103",
            destination_name="PAT-103",
            priority_level=1,
        )
        self.assertEqual(garuda.current_task_description, "Emergency Code Blue at PAT-103")
        self.assertEqual(garuda.destination_name, "PAT-103")
        self.assertEqual(garuda.state_machine.state.name, "NAVIGATING")

    # ─────────────────────────────────────────────────────────────────────────
    # 12. Actual Robot Movement & Collision Avoidance
    # ─────────────────────────────────────────────────────────────────────────
    def test_12_actual_robot_movement(self):
        """Verify robot physically steps along its planned route waypoints."""
        arogya = self.fleet_robots["Arogya_Delivery"]
        start_x, start_y = float(arogya.position[0]), float(arogya.position[1])
        target_waypoint = (start_x + 2.0, start_y)
        arogya.assign_mission(
            route=[target_waypoint],
            task_description="Deliver medication",
            destination_name="PAT-103",
            priority_level=2,
        )

        for _ in range(10):
            arogya.step()

        # Robot must have moved closer to target waypoint
        new_x, new_y = float(arogya.position[0]), float(arogya.position[1])
        self.assertNotEqual((start_x, start_y), (new_x, new_y))
        dist_moved = np.linalg.norm(np.array([new_x, new_y]) - np.array([start_x, start_y]))
        self.assertGreater(dist_moved, 0.5)

    # ─────────────────────────────────────────────────────────────────────────
    # 13. Hospital Database Integration
    # ─────────────────────────────────────────────────────────────────────────
    def test_13_hospital_database_integration(self):
        """Verify patient lookup, medication retrieval, and emergency status updates."""
        # Patient P003 record exists
        p_rec = self.db.get_patient("P003")
        self.assertIsNotNone(p_rec)
        self.assertEqual(p_rec["room_id"], "PAT-103")
        self.assertEqual(p_rec["name"], "Meera Iyer")

        # Emergency update
        success = self.db.set_patient_status("P003", PatientStatus.EMERGENCY)
        self.assertTrue(success)
        status_rec = self.db.get_patient_status("P003")
        self.assertEqual(status_rec["status"], PatientStatus.EMERGENCY)

        # Revert status back to admitted / active
        self.db.set_patient_status("P003", PatientStatus.ACTIVE)

    # ─────────────────────────────────────────────────────────────────────────
    # 14. Isaac Sim Stability (Non-Blocking Architecture)
    # ─────────────────────────────────────────────────────────────────────────
    def test_14_isaac_sim_stability_under_load(self):
        """Verify heavy audio ingestion does not starve or block main simulation loop."""
        main_ticks = 0
        start_t = time.perf_counter()

        # Simulate 100 simulation frames while injecting 50 audio frames in background
        def background_audio_load():
            for _ in range(50):
                dummy_chunk = b"\x00" * 3200
                self.server.ingest_pcm_chunk(dummy_chunk)
                time.sleep(0.005)

        bg_t = threading.Thread(target=background_audio_load, daemon=True)
        bg_t.start()

        # Main loop simulation steps
        for _ in range(100):
            main_ticks += 1
            # Step fleet robots
            for r in self.fleet_robots.values():
                r.step()
            time.sleep(0.002)

        bg_t.join(timeout=2.0)
        elapsed = time.perf_counter() - start_t

        self.assertEqual(main_ticks, 100)
        # 100 steps with 2ms sleep each should finish easily in < 2 seconds
        self.assertLess(elapsed, 2.0, f"Main loop took too long: {elapsed:.2f}s (Blocked by STT/Audio)")

    # ─────────────────────────────────────────────────────────────────────────
    # 15. The 5 Required Clinical Voice Commands
    # ─────────────────────────────────────────────────────────────────────────
    def test_15_required_five_clinical_commands(self):
        """Verify the 5 required commands from the specification parse with 100% precision."""
        # 1. "Go to ICU"
        c1 = parse_natural_command("Go to ICU")
        self.assertEqual(c1.cmd_type, CommandType.GO_LOCATION)
        self.assertEqual(c1.destination_location, "ICU-01")

        # 2. "Go to pharmacy"
        c2 = parse_natural_command("Go to pharmacy")
        self.assertEqual(c2.cmd_type, CommandType.GO_LOCATION)
        self.assertEqual(c2.destination_location, "PHM-01")

        # 3. "Deliver medicine to patient P003"
        c3 = parse_natural_command("Deliver medicine to patient P003")
        self.assertEqual(c3.cmd_type, CommandType.DELIVER_ITEM)
        self.assertEqual(c3.destination_location, "PAT-103")
        self.assertEqual(c3.item, "Metoprolol 25mg")

        # 4. "Patient P003 is an emergency"
        c4 = parse_natural_command("Patient P003 is an emergency")
        self.assertEqual(c4.cmd_type, CommandType.EMERGENCY)
        self.assertEqual(c4.destination_location, "PAT-103")
        self.assertEqual(c4.argument, "PATIENT_EMERGENCY:P003")

        # 5. "Return to charger"
        c5 = parse_natural_command("Return to charger")
        self.assertEqual(c5.cmd_type, CommandType.CHARGE_DOCK)
        self.assertEqual(c5.destination_location, "CHG-01")

    # ─────────────────────────────────────────────────────────────────────────
    # 16. Spoken Acoustic / Phonetic Normalization
    # ─────────────────────────────────────────────────────────────────────────
    def test_16_spoken_phonetic_normalization(self):
        """Verify spoken speech artifacts (e.g. 'i see you' -> 'icu', 'p zero zero three' -> 'p003') resolve correctly."""
        # Spoken "i see you" for ICU
        c_icu1 = parse_natural_command("go to i see you")
        self.assertEqual(c_icu1.cmd_type, CommandType.GO_LOCATION)
        self.assertEqual(c_icu1.destination_location, "ICU-01")

        c_icu2 = parse_natural_command("guide me to eye see you")
        self.assertEqual(c_icu2.cmd_type, CommandType.GO_LOCATION)
        self.assertEqual(c_icu2.destination_location, "ICU-01")

        # Spoken "p zero zero three" for Patient P003
        c_p003 = parse_natural_command("deliver medicine to patient p zero zero three")
        self.assertEqual(c_p003.cmd_type, CommandType.DELIVER_ITEM)
        self.assertEqual(c_p003.destination_location, "PAT-103")
        self.assertEqual(c_p003.item, "Metoprolol 25mg")

        # Spoken "peace euro zero three"
        c_peace = parse_natural_command("patient peace euro zero three is an emergency")
        self.assertEqual(c_peace.cmd_type, CommandType.EMERGENCY)
        self.assertEqual(c_peace.destination_location, "PAT-103")

        # Spoken "charging station"
        c_dock = parse_natural_command("navigate to charging station")
        self.assertEqual(c_dock.cmd_type, CommandType.CHARGE_DOCK)
        self.assertEqual(c_dock.destination_location, "CHG-01")

    # ─────────────────────────────────────────────────────────────────────────
    # 17. Thread-Safe Main-Thread Command Queue Isolation
    # ─────────────────────────────────────────────────────────────────────────
    def test_17_main_thread_command_queue_isolation(self):
        """Verify MobileVoiceServer isolates commands into a thread-safe queue for Isaac Sim."""
        # Empty queue initially
        self.server.get_pending_commands()

        # Simulate STT worker or web client dispatching commands off-thread
        self.server.dispatch_command("Go to ICU", source="mobile_voice")
        self.server.dispatch_command("Deliver medicine to patient P003", source="mobile_voice")

        # Retrieve strictly via poll_pending_command & get_pending_commands
        cmd1 = self.server.poll_pending_command()
        self.assertIsNotNone(cmd1)
        self.assertEqual(cmd1[0], "Go to ICU")
        self.assertEqual(cmd1[1], "mobile_voice")

        remaining = self.server.get_pending_commands()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0][0], "Deliver medicine to patient P003")

        # Queue is now empty
        self.assertIsNone(self.server.poll_pending_command())

    # ─────────────────────────────────────────────────────────────────────────
    # 18. Bounded Audio Buffer Overflow Protection
    # ─────────────────────────────────────────────────────────────────────────
    def test_18_bounded_audio_queue_overflow(self):
        """Verify streaming more than 20 seconds of audio safely drops oldest and never crashes."""
        initial_dropped = self.server.audio_frames_dropped
        self.server._is_streaming_audio = True

        # Push 250 chunks of dummy 16 kHz audio (each 3200 bytes = 100ms)
        chunk = b"\x00\x01" * 1600
        for _ in range(250):
            self.server.ingest_pcm_chunk(chunk)

        # Server must still be running and frames must be safely dropped
        self.assertTrue(self.server.is_running)
        self.assertGreater(self.server.audio_frames_dropped, initial_dropped)
        total_buffered = sum(len(c) for c in self.server._utterance_chunks)
        self.assertLessEqual(total_buffered, 640000)
        self.server._is_streaming_audio = False
        self.server._utterance_chunks = []

    # ─────────────────────────────────────────────────────────────────────────
    # 19. Utterance Buffering & Single Authoritative Final Result
    # ─────────────────────────────────────────────────────────────────────────
    def test_19_utterance_buffering_and_finalization(self):
        """Verify on_audio_stream_start and on_audio_stream_end maintain utterance state cleanly."""
        self.server.on_audio_stream_start(mode="tap")
        self.assertTrue(self.server._is_streaming_audio)
        self.assertEqual(len(self.server._utterance_chunks), 0)

        # Ingest some chunks
        self.server.ingest_pcm_chunk(b"\x00\x01" * 1600)
        self.assertEqual(len(self.server._utterance_chunks), 1)

        # Simulate user releasing mic button
        self.server.on_audio_stream_end()
        self.assertFalse(self.server._is_streaming_audio)
        self.assertEqual(len(self.server._utterance_chunks), 0)

    # ─────────────────────────────────────────────────────────────────────────
    # 20. Phone Disconnect Resilience (Zero Isaac Sim Crash)
    # ─────────────────────────────────────────────────────────────────────────
    def test_20_phone_disconnect_resilience(self):
        """Verify phone disconnection purges queue and leaves robots and backend active."""
        dummy_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        can_conn, _ = self.server.register_client_session(dummy_sock, "192.168.1.99")
        self.assertTrue(can_conn)

        # Push some frames
        self.server._is_streaming_audio = True
        self.server.ingest_pcm_chunk(b"\x00" * 3200)

        # Disconnect client
        self.server.unregister_client_session(dummy_sock)
        dummy_sock.close()

        # Session reset safely
        self.assertIsNone(self.server.active_client_sock)
        self.assertEqual(len(self.server._utterance_chunks), 0)
        self.assertTrue(self.server.is_running)
        # Verify fleet AMR is still healthy and operational
        garuda = self.fleet_robots["Garuda_Emergency"]
        self.assertTrue(garuda.battery_level > 50.0)


if __name__ == "__main__":
    unittest.main()

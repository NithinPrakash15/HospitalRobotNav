"""
AROGYA Mobile Live Voice Server & WebSocket Audio Ingestion Engine
===================================================================
Project: "Multi-Agent Embodied AI Robot for Autonomous Hospital Assistance
          using Vision-Language Reasoning"

Enables the user's mobile phone to act as the primary live voice microphone
and mobile command console for AROGYA.

Architecture:
1. Dynamic Active LAN IP Detection:
   Auto-detects the host PC's Wi-Fi network address (e.g. 192.168.x.x) at runtime.
2. Single-Port Dual-Protocol Server (Port 8082):
   - Serves modern responsive mobile web console (GET /)
   - Serves dynamic runtime QR code image (GET /qr)
   - Serves live diagnostic & telemetry API (GET /status, GET /api/telemetry)
   - Handles text command fallback (POST /api/command)
   - Upgrades GET /ws/audio to RFC 6455 WebSocket for real-time 16 kHz PCM audio streaming
3. Non-Blocking STT Worker Thread:
   - Receives raw 16 kHz 16-bit mono PCM binary chunks from the smartphone microphone
   - Streams audio into Vosk offline Kaldi recognizer
   - Emits streaming partial transcripts and finalized transcripts back to the phone
   - Immediately purges raw audio chunks after recognition (zero persistent recording)
   - Zero Isaac Sim main-thread interference: runs completely off-thread
4. Unified Command Dispatch:
   - Transcripts flow directly into AROGYA's command pipeline (`cmd_interface.process_raw_input`)
   - Full support for natural clinical commands, database lookups (P003), and emergency alerts
   - Preserves running missions if phone disconnects
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import io
import ipaddress
import json
import os
import queue
import socket
import ssl
import struct
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Any, Callable, Dict, List, Optional, Tuple

from speech.stt_supervisor import STTSupervisor, STTSupervisorState

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# ─────────────────────────────────────────────────────────────────────────────
# Dynamic LAN IP Detection & Network Diagnostics
# ─────────────────────────────────────────────────────────────────────────────

def get_lan_ip() -> str:
    """
    Dynamically determine the PC's active LAN IPv4 address (e.g. 192.168.x.x).
    Uses a non-transmitting UDP probe against external routing table.
    Falls back to hostname resolution or 127.0.0.1.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 8.8.8.8:80 is used solely for routing table inspection; no packets are sent.
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def check_port_accessible(port: int, host: str = "0.0.0.0") -> Tuple[bool, str]:
    """Test whether the configured port can be bound without conflict."""
    test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        test_sock.bind((host, port))
        test_sock.close()
        return True, "Port available"
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# QR Code Generator (PNG Image + ANSI Terminal QR)
# ─────────────────────────────────────────────────────────────────────────────

def generate_qr_assets(url: str, output_png_path: Optional[str] = None) -> Tuple[bytes, str]:
    """
    Generate both a PNG byte buffer and an ANSI console string for the given URL.
    Returns (png_bytes, ascii_qr_str).
    """
    png_bytes = b""
    ascii_str = ""

    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=8,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)

        # 1. Generate PNG image
        img = qr.make_image(fill_color="#0284c7", back_color="#090d16")
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        png_bytes = bio.getvalue()

        if output_png_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_png_path)), exist_ok=True)
            with open(output_png_path, "wb") as f:
                f.write(png_bytes)

        # 2. Generate ASCII representation
        ascii_io = io.StringIO()
        qr.print_ascii(out=ascii_io, invert=True)
        ascii_str = ascii_io.getvalue()

    except Exception as ex:
        # Fallback if qrcode module fails
        ascii_str = f" [ Scan URL: {url} ]\n"

    return png_bytes, ascii_str


# ─────────────────────────────────────────────────────────────────────────────
# Local Development TLS Certificate Management (HTTPS + WSS)
# ─────────────────────────────────────────────────────────────────────────────

def _generate_self_signed_cert(cert_path: str, key_path: str, target_ip: str) -> None:
    """
    Generate a local development self-signed X.509 v3 certificate with SAN
    including target_ip, 127.0.0.1, localhost, and local hostname.
    """
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        raise RuntimeError("The 'cryptography' Python package is required to generate development TLS certificates.")

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, target_ip),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AROGYA Hospital Robotics"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Mobile Voice Terminal"),
    ])

    san_entries: List[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    try:
        san_entries.append(x509.IPAddress(ipaddress.ip_address(target_ip)))
    except Exception:
        pass
    try:
        hname = socket.gethostname()
        if hname and hname.lower() != "localhost":
            san_entries.append(x509.DNSName(hname))
    except Exception:
        pass

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    os.makedirs(os.path.dirname(os.path.abspath(cert_path)), exist_ok=True)
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))


def get_or_create_tls_certificate(
    cert_dir: Optional[str] = None,
    lan_ip: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Ensure a local TLS certificate exists with Subject Alternative Name (SAN)
    matching the host's active LAN IP, localhost, and 127.0.0.1.

    Returns:
        (cert_file_path, key_file_path)
    """
    if not cert_dir:
        curr_dir = os.path.dirname(os.path.abspath(__file__))
        cert_dir = os.path.abspath(os.path.join(curr_dir, "..", "..", "certificates"))

    os.makedirs(cert_dir, exist_ok=True)
    cert_path = os.path.join(cert_dir, "server.crt")
    key_path = os.path.join(cert_dir, "server.key")
    target_ip = lan_ip or get_lan_ip()

    needs_generation = True
    if os.path.exists(cert_path) and os.path.exists(key_path):
        try:
            from cryptography import x509
            with open(cert_path, "rb") as f:
                cert_bytes = f.read()
            cert = x509.load_pem_x509_certificate(cert_bytes)

            now_utc = datetime.datetime.now(datetime.timezone.utc)
            expiry_utc = cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc") else cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)
            if expiry_utc > now_utc + datetime.timedelta(days=1):
                try:
                    san_ext = cert.extensions.get_extension_for_oid(x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                    san_ips = san_ext.value.get_values_for_type(x509.IPAddress)
                    target_ip_obj = ipaddress.ip_address(target_ip)
                    if target_ip_obj in san_ips:
                        needs_generation = False
                        print(f"[MOBILE_VOICE] Reusing local TLS certificate for {target_ip}: {cert_path}")
                except Exception:
                    pass
        except Exception as e:
            print(f"[MOBILE_VOICE] Notice: Existing certificate check exception: {e}; regenerating.")

    if needs_generation:
        print(f"[MOBILE_VOICE] Generating new local development TLS certificate for LAN IP: {target_ip}...")
        _generate_self_signed_cert(cert_path, key_path, target_ip)
        print(f"[MOBILE_VOICE] TLS Certificate ready: {cert_path}")

    return cert_path, key_path


# ─────────────────────────────────────────────────────────────────────────────
# Threaded HTTP & WebSocket Server Implementation
# ─────────────────────────────────────────────────────────────────────────────

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Suppress noisy tracebacks from TLS handshake interruptions or plain HTTP probes."""
        exc_type = sys.exc_info()[0]
        if exc_type and issubclass(exc_type, (ssl.SSLError, ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


class MobileVoiceHTTPRequestHandler(BaseHTTPRequestHandler):
    """
    Handles both standard HTTP endpoints and upgrades /ws/audio requests
    to RFC 6455 WebSocket streaming.
    """
    protocol_version = "HTTP/1.1"

    # Reference to the parent MobileVoiceServer instance (injected at server startup)
    server_controller: Optional[MobileVoiceServer] = None

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress noisy request logs; errors and key events are logged explicitly."""
        return

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests from mobile browsers."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Sec-WebSocket-Key, Sec-WebSocket-Version, Upgrade")
        self.end_headers()

    def do_GET(self) -> None:
        ctrl = getattr(self.server, "controller", None) or MobileVoiceHTTPRequestHandler.server_controller

        # ── WebSocket Upgrade Request ────────────────────────────────────────
        if self.headers.get("Upgrade", "").lower() == "websocket":
            self.handle_websocket(ctrl)
            return

        # ── HTTP GET / (Mobile Web Console) ──────────────────────────────────
        if self.path in ("/", "/index.html") or self.path.startswith("/?"):
            html_content = ctrl.get_html_content() if ctrl else b"<h1>AROGYA Mobile Voice</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(html_content)
            return

        # ── HTTP GET /qr (QR Code Image) ─────────────────────────────────────
        if self.path == "/qr" or self.path.startswith("/qr?"):
            qr_bytes = ctrl.get_qr_png_bytes() if ctrl else b""
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(qr_bytes)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(qr_bytes)
            return

        # ── HTTP GET /status (Diagnostics & Server Health) ───────────────────
        if self.path == "/status" or self.path.startswith("/status?"):
            status_data = ctrl.get_status_dict() if ctrl else {"server": "OFFLINE"}
            body = json.dumps(status_data, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return

        # ── HTTP GET /api/telemetry (Live Fleet & Voice State) ───────────────
        if self.path == "/api/telemetry" or self.path.startswith("/api/telemetry?"):
            telem = ctrl.get_telemetry_dict() if ctrl else {}
            body = json.dumps(telem).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_error(404, f"Path '{self.path}' not found")

    def do_POST(self) -> None:
        ctrl = getattr(self.server, "controller", None) or MobileVoiceHTTPRequestHandler.server_controller

        # ── HTTP POST /api/command (Fallback Text Command Submission) ─────────
        if self.path == "/api/command":
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length)
            try:
                data = json.loads(raw_body.decode("utf-8"))
                cmd_text = data.get("command", "").strip()
                source = data.get("source", "mobile_text")
                if ctrl and cmd_text:
                    ctrl.dispatch_command(cmd_text, source=source)
                    resp = json.dumps({"success": True, "command": cmd_text}).encode("utf-8")
                else:
                    resp = json.dumps({"success": False, "error": "Empty command"}).encode("utf-8")
            except Exception as e:
                resp = json.dumps({"success": False, "error": str(e)}).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp)
            return

        self.send_error(404, "Not Found")

    # ── WebSocket RFC 6455 Handler ───────────────────────────────────────────

    def handle_websocket(self, ctrl: Optional[MobileVoiceServer]) -> None:
        """Upgrade HTTP socket to an RFC 6455 full-duplex WebSocket connection."""
        self.close_connection = True
        key = self.headers.get("Sec-WebSocket-Key", "")
        if not key:
            self.send_error(400, "Missing Sec-WebSocket-Key")
            return

        # Compute Sec-WebSocket-Accept token
        accept_str = base64.b64encode(hashlib.sha1((key + WS_GUID).encode("utf-8")).digest()).decode("utf-8")
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept_str)
        self.end_headers()

        sock = self.connection
        sock.settimeout(None)
        client_addr = self.client_address[0]

        # Enforce single active voice controller device lock (Requirement 32)
        if ctrl:
            can_connect, active_dev = ctrl.register_client_session(sock, client_addr)
            if not can_connect:
                print(f"[MOBILE_VOICE] Connection from {client_addr} rejected: Active controller is already {active_dev}")
                try:
                    self._send_ws_text(sock, json.dumps({
                        "type": "device_rejected",
                        "active_controller": active_dev,
                    }))
                    time.sleep(0.2)
                    sock.close()
                except Exception:
                    pass
                return

        print(f"\n[MOBILE_VOICE] Client connected: {client_addr}")
        if ctrl:
            ctrl.on_client_connected(client_addr)

        try:
            self._send_ws_text(sock, json.dumps({
                "type": "connected",
                "message": "Connected to AROGYA PC Voice Server",
                "client": client_addr,
            }))

            # Push current telemetry snapshot immediately
            if ctrl:
                telem = ctrl.get_telemetry_dict()
                telem["type"] = "telemetry"
                self._send_ws_text(sock, json.dumps(telem))

            while ctrl and ctrl.is_running:
                # Read 2-byte WebSocket frame header
                header = sock.recv(2)
                if not header or len(header) < 2:
                    break

                b1, b2 = header[0], header[1]
                fin = (b1 & 0x80) != 0
                opcode = b1 & 0x0F
                masked = (b2 & 0x80) != 0
                payload_len = b2 & 0x7F

                if opcode == 8:  # Close frame
                    break
                elif opcode == 9:  # Ping frame -> reply Pong
                    sock.sendall(bytes([0x8A, 0x00]))
                    continue
                elif opcode == 10:  # Pong frame
                    continue

                if payload_len == 126:
                    ext = sock.recv(2)
                    payload_len = struct.unpack("!H", ext)[0]
                elif payload_len == 127:
                    ext = sock.recv(8)
                    payload_len = struct.unpack("!Q", ext)[0]

                mask_key = sock.recv(4) if masked else b""

                # Read payload buffer
                payload = bytearray()
                while len(payload) < payload_len:
                    chunk = sock.recv(min(payload_len - len(payload), 65536))
                    if not chunk:
                        break
                    payload.extend(chunk)

                if masked and mask_key:
                    for i in range(len(payload)):
                        payload[i] ^= mask_key[i % 4]

                data = bytes(payload)

                # Opcode 2: Binary 16 kHz 16-Bit Mono PCM Audio Chunk
                if opcode == 2:
                    if ctrl:
                        ctrl.ingest_pcm_chunk(data)

                # Opcode 1: JSON Text Command / Client Handshake
                elif opcode == 1:
                    try:
                        text_msg = data.decode("utf-8", errors="replace")
                        json_msg = json.loads(text_msg)
                        msg_type = json_msg.get("type", "")

                        if msg_type == "device_handshake":
                            client_info = json_msg.get("client", "Mobile Device")
                            if ctrl:
                                ctrl.set_active_device_name(client_info)
                        elif msg_type == "audio_stream_start":
                            if ctrl:
                                ctrl.on_audio_stream_start(json_msg.get("mode", "tap"))
                        elif msg_type == "audio_stream_end":
                            if ctrl:
                                ctrl.on_audio_stream_end()
                        elif msg_type == "text_command":
                            cmd_str = json_msg.get("text", "")
                            if ctrl and cmd_str:
                                ctrl.dispatch_command(cmd_str, source="mobile_text")
                    except Exception as ex:
                        print(f"[MOBILE_VOICE] Error parsing text frame: {ex}")

        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass
        except Exception as e:
            print(f"[MOBILE_VOICE] WebSocket session exception: {e}")
        finally:
            print(f"[MOBILE_VOICE] Client disconnected: {client_addr}")
            if ctrl:
                ctrl.unregister_client_session(sock)


    def _send_ws_text(self, sock: socket.socket, text: str) -> None:
        """Send a UTF-8 text frame over the WebSocket."""
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        length = len(payload)
        if length <= 125:
            header.append(length)
        elif length <= 65535:
            header.append(126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(127)
            header.extend(struct.pack("!Q", length))
        sock.sendall(header + payload)


# ─────────────────────────────────────────────────────────────────────────────
# Mobile Voice Server Controller
# ─────────────────────────────────────────────────────────────────────────────

class MobileVoiceServer:
    """
    Master controller for AROGYA Mobile Live Voice Command System:
    - Hosts dual-protocol HTTP + WebSocket server on port 8082
    - Off-thread STT worker transcribing 16 kHz PCM chunks with Vosk
    - Feeds transcripts into CommandInterface
    - Broadcasts live fleet & mission updates to the mobile UI
    """

    def __init__(
        self,
        port: int = 8082,
        host: str = "0.0.0.0",
        command_callback: Optional[Callable[[str, str], None]] = None,
        vosk_model_path: Optional[str] = None,
        fleet_robots_ref: Optional[Dict[str, Any]] = None,
        hospital_db_ref: Optional[Any] = None,
        enable_https: bool = True,
        cert_dir: Optional[str] = None,
        stt_port: int = 8095,
        stt_model: str = "small",
        stt_device: str = "cpu",
    ) -> None:
        self.port = port
        self.host = host
        self.lan_ip = get_lan_ip()
        self.enable_https = enable_https
        self.cert_dir = cert_dir
        self.cert_path: Optional[str] = None
        self.key_path: Optional[str] = None
        self.https_ready = False

        if self.enable_https:
            try:
                self.cert_path, self.key_path = get_or_create_tls_certificate(
                    cert_dir=self.cert_dir,
                    lan_ip=self.lan_ip,
                )
                self.https_ready = True
                self.mobile_url = f"https://{self.lan_ip}:{self.port}"
                self.ws_url = f"wss://{self.lan_ip}:{self.port}/ws/audio"
            except Exception as e:
                print(f"\n[MOBILE_VOICE ERROR] TLS Certificate preparation failed: {e}")
                print("Mobile Voice: HTTPS unavailable. Microphone: Unavailable until HTTPS is enabled.")
                print("AROGYA system remains running with text command fallback.\n")
                self.enable_https = False
                self.https_ready = False
                self.mobile_url = f"http://{self.lan_ip}:{self.port}"
                self.ws_url = f"ws://{self.lan_ip}:{self.port}/ws/audio"
        else:
            self.mobile_url = f"http://{self.lan_ip}:{self.port}"
            self.ws_url = f"ws://{self.lan_ip}:{self.port}/ws/audio"

        self.command_callback = command_callback
        self.fleet_robots = fleet_robots_ref or {}
        self.hospital_db = hospital_db_ref
        self.is_running = False

        # State tracking
        self.active_client_sock: Optional[socket.socket] = None
        self.active_client_ip: Optional[str] = None
        self.active_device_name: str = "Unknown"
        self._lock = threading.Lock()

        # Telemetry & History
        self.last_transcript: str = ""
        self.last_intent: str = "STANDBY"
        self.last_destination: str = "NONE"
        self.last_assigned_robot: str = "GARUDA"
        self.last_status: str = "IDLE"
        self.command_history: List[Dict[str, Any]] = []

        # Thread-safe Command Queue for Isaac Sim Main-Thread Consumption
        self._pending_commands: queue.Queue[Tuple[str, str]] = queue.Queue()

        # STT Worker Supervisor (Runs faster-whisper in an isolated external process)
        self.stt_supervisor: Optional[STTSupervisor] = None
        self._init_stt_supervisor(stt_port=stt_port, model=stt_model, device=stt_device)
        self._utterance_chunks: List[bytes] = []
        self._is_streaming_audio: bool = False
        self._server_thread: Optional[threading.Thread] = None
        self._httpd: Optional[ThreadedHTTPServer] = None

        # Real-Time Diagnostics & Performance Metrics
        self.audio_frames_received: int = 0
        self.audio_frames_dropped: int = 0
        self.stt_latency_ms: float = 0.0
        self.current_rms: float = 0.0
        self.vad_state: str = "SILENCE"
        self.sample_rate: int = 16000
        self.channels: int = 1

        # Template & Assets
        self._html_content = b""
        self._qr_png_bytes = b""
        self._ascii_qr = ""
        self._load_templates_and_qr()

    def _init_stt_supervisor(self, stt_port: int = 8095, model: str = "small", device: str = "cpu") -> None:
        """Initialize the external faster-whisper STT worker process supervisor."""
        try:
            self.stt_supervisor = STTSupervisor(
                port=stt_port,
                host="127.0.0.1",
                model=model,
                device=device,
            )
            print(f"[MOBILE_VOICE] STT Initialized with faster-whisper ({model} on {device}) via Supervisor")
        except Exception as e:
            print(f"[MOBILE_VOICE] STT Supervisor initialization notice: {e}")

    def _load_templates_and_qr(self) -> None:
        """Load mobile_voice.html and generate dynamic runtime QR code."""
        # 1. HTML template
        curr_dir = os.path.dirname(os.path.abspath(__file__))
        tmpl_path = os.path.join(curr_dir, "templates", "mobile_voice.html")
        if os.path.exists(tmpl_path):
            with open(tmpl_path, "rb") as f:
                self._html_content = f.read()
        else:
            self._html_content = b"<html><body><h1>AROGYA Mobile Voice Ready</h1></body></html>"

        # 2. QR code PNG & ASCII
        project_root = os.path.abspath(os.path.join(curr_dir, "..", ".."))
        qr_png_path = os.path.join(project_root, "isaac_sim_hospital", "textures", "mobile_voice_qr.png")
        self._qr_png_bytes, self._ascii_qr = generate_qr_assets(self.mobile_url, qr_png_path)

    def _init_speech_engine(self, custom_path: Optional[str] = None) -> None:
        """Initialize Vosk speech recognizer in a thread-safe manner."""
        try:
            import vosk
            vosk.SetLogLevel(-1)

            # Find model
            candidates = []
            if custom_path:
                candidates.append(custom_path)
            curr_dir = os.path.dirname(os.path.abspath(__file__))
            repo_root = os.path.abspath(os.path.join(curr_dir, "..", ".."))
            candidates.extend([
                os.path.join(repo_root, "models", "vosk-model-small-en-us-0.15"),
                os.path.join(repo_root, "models", "vosk-model-small-hi-in-0.4"),
                os.path.join(repo_root, "models", "vosk-model-small-ml-in-0.2"),
            ])

            model_dir = None
            for p in candidates:
                if os.path.exists(p) and os.path.isdir(p):
                    model_dir = p
                    break

            if model_dir:
                self._vosk_model = vosk.Model(model_dir)
                self._recognizer = vosk.KaldiRecognizer(self._vosk_model, 16000)
                print(f"[MOBILE_VOICE] STT Initialized with Vosk model: {os.path.basename(model_dir)}")
            else:
                print("[MOBILE_VOICE] Notice: Vosk acoustic model directory not found; text fallback active.")
        except Exception as e:
            print(f"[MOBILE_VOICE] Speech recognizer initialization notice: {e}")

    def start(self) -> bool:
        """Start the background HTTP+WebSocket server and external STT worker supervisor."""
        if self.is_running:
            return True

        is_avail, reason = check_port_accessible(self.port, self.host)
        if not is_avail:
            print(f"\n[MOBILE_VOICE WARNING] Port {self.port} may be blocked or in use: {reason}")
            print(f"Windows Firewall Diagnostic: If inaccessible from phone, allow TCP Port {self.port} in Windows Defender Firewall.\n")

        self.is_running = True

        # Start external STT worker process supervisor
        if self.stt_supervisor:
            self.stt_supervisor.start()

        # Start HTTP / HTTPS server
        try:
            MobileVoiceHTTPRequestHandler.server_controller = self
            self._httpd = ThreadedHTTPServer((self.host, self.port), MobileVoiceHTTPRequestHandler)
            setattr(self._httpd, "controller", self)

            # Wrap socket with TLS if HTTPS is enabled
            if self.enable_https and self.cert_path and self.key_path:
                try:
                    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                    ssl_ctx.load_cert_chain(certfile=self.cert_path, keyfile=self.key_path)
                    self._httpd.socket = ssl_ctx.wrap_socket(self._httpd.socket, server_side=True)
                    self.https_ready = True
                except Exception as ssl_err:
                    print(f"\n[MOBILE_VOICE ERROR] Failed to bind TLS/SSL context to port {self.port}: {ssl_err}")
                    print("HTTPS startup failed. Existing AROGYA system remains running.\n")
                    self.https_ready = False

            self._server_thread = threading.Thread(
                target=self._httpd.serve_forever,
                name="ArogyaMobileVoiceHTTPThread",
                daemon=True,
            )
            self._server_thread.start()

            # Print Startup Banner
            self._print_startup_banner()
            return True

        except Exception as e:
            print(f"[MOBILE_VOICE ERROR] Failed to start Mobile Voice Server: {e}")
            self.is_running = False
            return False

    def _print_startup_banner(self) -> None:
        """Print clear startup banner with detected LAN IP, HTTPS URL, and ASCII QR code."""
        proto_str = "HTTPS (Secure TLS) + WSS" if (self.enable_https and self.https_ready) else "HTTP (Insecure) + WS"
        print()
        print("=" * 68)
        print("     AROGYA SECURE MOBILE LIVE VOICE TERMINAL (HTTPS + WSS)")
        print("=" * 68)
        print(f" Voice Server      : ONLINE")
        print(f" Protocol          : {proto_str}")
        print(f" Port              : {self.port}")
        print(f" Detected LAN IP   : {self.lan_ip}")
        print(f" Mobile HTTPS URL  : {self.mobile_url}")
        print(f" WebSocket Stream  : {self.ws_url}")
        if self.enable_https and self.cert_path:
            print(f" TLS Certificate   : {self.cert_path}")
            print(f" SAN Hostnames/IPs : {self.lan_ip}, 127.0.0.1, localhost")
            print()
            print(" [MOBILE BROWSER SETUP - FIRST TIME VISIT]:")
            print(" 1. Scan the QR code below or open the Mobile HTTPS URL on your phone.")
            print(" 2. Because this is a local LAN certificate, Chrome/Safari may display:")
            print("    'Your connection is not private' or 'Not Secure'.")
            print(" 3. Tap 'Advanced' -> 'Proceed to ... (unsafe)' to trust this LAN session.")
            print(" 4. Once loaded over HTTPS, browser microphone access is fully UNLOCKED!")
        print()
        print(" Connect your phone to the SAME Wi-Fi network and scan:")
        print()
        if self._ascii_qr and hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
            try:
                if hasattr(sys.stdout, "reconfigure"):
                    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
                print(self._ascii_qr)
            except Exception:
                print(f" [ Mobile Terminal Link: {self.mobile_url} ]")
        else:
            print(f" [ Mobile Terminal Link: {self.mobile_url} ]")
        print(f" Direct Link       : {self.mobile_url}")
        print("=" * 68)
        print()

    def stop(self) -> None:
        """Stop server cleanly."""
        self.is_running = False
        if self.stt_supervisor:
            try:
                self.stt_supervisor.stop()
            except Exception:
                pass
        if self._httpd:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
        print("[MOBILE_VOICE] Voice Server stopped.")

    # ── Client Session Management ────────────────────────────────────────────

    def register_client_session(self, sock: socket.socket, ip: str) -> Tuple[bool, str]:
        with self._lock:
            if self.active_client_sock is not None and self.active_client_sock != sock:
                # Single active controller policy (Requirement 32)
                return False, self.active_client_ip or "Another Phone"
            self.active_client_sock = sock
            self.active_client_ip = ip
            return True, ip

    def unregister_client_session(self, sock: socket.socket) -> None:
        """Handle client disconnection safely without interrupting running missions."""
        with self._lock:
            if self.active_client_sock == sock:
                self.active_client_sock = None
                self.active_client_ip = None
                self.active_device_name = "None"
        self._is_streaming_audio = False
        self._utterance_chunks = []
        self.vad_state = "SILENCE"
        print("[MOBILE_VOICE] Client session cleaned up safely. Simulation and missions remain ACTIVE.")

    def on_client_connected(self, ip: str) -> None:
        pass

    def set_active_device_name(self, name: str) -> None:
        self.active_device_name = name

    def broadcast_to_client(self, msg_dict: Dict[str, Any]) -> None:
        """Send a JSON message to the connected phone."""
        with self._lock:
            sock = self.active_client_sock
        if not sock:
            return
        try:
            payload = json.dumps(msg_dict).encode("utf-8")
            header = bytearray([0x81])
            length = len(payload)
            if length <= 125:
                header.append(length)
            elif length <= 65535:
                header.append(126)
                header.extend(struct.pack("!H", length))
            else:
                header.append(127)
                header.extend(struct.pack("!Q", length))
            sock.sendall(header + payload)
        except Exception:
            pass

    # ── Live Audio Ingestion & faster-whisper Utterance Buffering ─────────────

    def ingest_pcm_chunk(self, pcm_bytes: bytes) -> None:
        """
        Receive raw 16 kHz 16-bit mono PCM chunks from WebSocket.
        Enforces bounded memory buffer and computes live RMS/VAD for visual meter.
        """
        if not self.is_running or not pcm_bytes:
            return

        # Calculate RMS energy for speech/silence determination
        try:
            import numpy as np
            samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
            if len(samples) > 0:
                rms = float(np.sqrt(np.mean(np.square(samples))))
                self.current_rms = rms
                self.vad_state = "SPEECH" if rms > 320.0 else "SILENCE"
                self.audio_frames_received += len(samples)
        except Exception:
            pass

        # Buffer speech while streaming (cap at 20 seconds = 640,000 bytes)
        if self._is_streaming_audio:
            current_bytes = sum(len(c) for c in self._utterance_chunks)
            if current_bytes + len(pcm_bytes) <= 640000:
                self._utterance_chunks.append(pcm_bytes)
            else:
                self.audio_frames_dropped += len(pcm_bytes) // 2

    def on_audio_stream_start(self, mode: str) -> None:
        """Client started microphone streaming (Push-to-Talk or Wake Word)."""
        print(f"[MOBILE_VOICE] Audio stream started (mode: {mode})")
        self._is_streaming_audio = True
        self._utterance_chunks = []
        self.broadcast_to_client({
            "type": "voice_status",
            "status": "listening",
            "mode": mode,
        })

    def on_audio_stream_end(self) -> None:
        """
        Utterance ended (user released Tap-to-Speak button).
        Dispatches complete utterance to faster-whisper STT worker process.
        """
        print("[MOBILE_VOICE] Audio stream ended. Dispatching complete utterance to faster-whisper...")
        self._is_streaming_audio = False
        self.broadcast_to_client({
            "type": "voice_status",
            "status": "processing",
        })

        complete_pcm = b"".join(self._utterance_chunks)
        self._utterance_chunks = []

        if not complete_pcm or len(complete_pcm) < 3200:
            # Less than 100ms: treat as tap cancellation
            self.broadcast_to_client({
                "type": "voice_status",
                "status": "ready",
            })
            return

        def _do_transcribe() -> None:
            t0 = time.time()
            if not self.stt_supervisor:
                print("[MOBILE_VOICE ERROR] STT supervisor is not available")
                self.broadcast_to_client({"type": "voice_status", "status": "ready"})
                return

            res = self.stt_supervisor.transcribe(
                complete_pcm,
                sample_rate=16000,
                channels=1,
                language=None,  # Auto-detects English, Hindi, and Malayalam natively
                timeout=12.0,
            )
            self.stt_latency_ms = (time.time() - t0) * 1000.0

            if res.get("success"):
                transcript = res.get("transcript", "").strip()
                if transcript:
                    self._handle_final_transcript(transcript)
                else:
                    self.broadcast_to_client({
                        "type": "voice_status",
                        "status": "ready",
                    })
            else:
                err = res.get("error", "Unknown STT error")
                print(f"[MOBILE_VOICE] STT Error: {err}")
                self.broadcast_to_client({
                    "type": "voice_status",
                    "status": "error",
                    "message": "Voice service temporarily unavailable.",
                })
                time.sleep(1.5)
                self.broadcast_to_client({
                    "type": "voice_status",
                    "status": "ready",
                })

        threading.Thread(target=_do_transcribe, name="ArogyaSTTInferenceDispatch", daemon=True).start()

    def _handle_final_transcript(self, text: str) -> None:
        """
        Process finalized speech transcript and route into thread-safe command queue.
        """
        print(f'\n[STT] Final transcript: "{text}"')
        self.last_transcript = text

        # Emit authoritative final transcript to phone
        self.broadcast_to_client({
            "type": "transcript_final",
            "text": text,
        })

        # Filter single-token noise or garbage ASR (e.g. "huh", "um")
        from isaac_sim_hospital.environments.command_interface import is_garbage_asr
        if is_garbage_asr(text):
            print(f'[ASR FILTER] Discarded ambient noise token: "{text}"')
            self.broadcast_to_client({
                "type": "voice_status",
                "status": "ready",
            })
            return

        # Pass to authoritative AROGYA command dispatcher (thread-safe queue)
        self.dispatch_command(text, source="mobile_voice")

    def dispatch_command(self, cmd_text: str, source: str = "mobile_voice") -> None:
        """
        Enqueue command for safe processing on the Isaac Sim main thread.
        Never calls omni.ui or Isaac Sim directly from this worker thread.
        """
        if not cmd_text:
            return

        print(f"[MOBILE_VOICE] Enqueuing command for Isaac Sim main thread: '{cmd_text}' (source: {source})")
        self._pending_commands.put((cmd_text, source))

        self.broadcast_to_client({
            "type": "voice_status",
            "status": "command_detected",
            "command": cmd_text,
        })

        # Also invoke command_callback if provided (e.g. for standalone tests)
        if self.command_callback:
            try:
                self.command_callback(cmd_text, source)
            except Exception as e:
                print(f"[MOBILE_VOICE] Command callback notice: {e}")

    def poll_pending_command(self) -> Optional[Tuple[str, str]]:
        """
        Thread-safe retrieval of next command.
        MUST be called exclusively from Isaac Sim main simulation loop.
        """
        try:
            return self._pending_commands.get_nowait()
        except queue.Empty:
            return None

    def get_pending_commands(self) -> List[Tuple[str, str]]:
        """
        Thread-safe retrieval of all pending commands.
        MUST be called exclusively from Isaac Sim main simulation loop.
        """
        cmds = []
        while True:
            try:
                cmds.append(self._pending_commands.get_nowait())
            except queue.Empty:
                break
        return cmds

    # ── Notification & Telemetry Handlers ────────────────────────────────────

    def notify_mission_update(
        self,
        raw_text: str,
        intent: str,
        destination: str,
        assigned_robot: str,
        status: str,
        is_emergency: bool = False,
    ) -> None:
        """Called by runner / coordinator when a mission is created and assigned."""
        self.last_intent = intent
        self.last_destination = destination
        self.last_assigned_robot = assigned_robot
        self.last_status = status

        record = {
            "type": "mission_update",
            "raw_text": raw_text,
            "intent": intent,
            "destination": destination,
            "assigned_robot": assigned_robot,
            "status": status,
            "is_emergency": is_emergency,
            "timestamp": time.strftime("%H:%M:%S"),
        }
        self.command_history.insert(0, record)
        if len(self.command_history) > 25:
            self.command_history.pop()

        self.broadcast_to_client(record)

    def get_html_content(self) -> bytes:
        return self._html_content

    def get_qr_png_bytes(self) -> bytes:
        return self._qr_png_bytes

    def get_status_dict(self) -> Dict[str, Any]:
        return {
            "server": "ONLINE" if self.is_running else "OFFLINE",
            "https_enabled": self.enable_https and self.https_ready,
            "lan_ip": self.lan_ip,
            "port": self.port,
            "url": self.mobile_url,
            "ws_url": self.ws_url,
            "tls_cert": self.cert_path,
            "client_connected": self.active_client_sock is not None,
            "active_client_ip": self.active_client_ip,
            "active_device": self.active_device_name,
            "last_transcript": self.last_transcript,
            "stt_engine": f"faster-whisper ({self.stt_supervisor.model} on {self.stt_supervisor.device})" if self.stt_supervisor else "Text Mode",
            "stt_service": self.stt_supervisor.get_status() if self.stt_supervisor else {},
            "audio_diagnostics": {
                "sample_rate": self.sample_rate,
                "channels": self.channels,
                "frames_received": self.audio_frames_received,
                "frames_dropped": self.audio_frames_dropped,
                "vad_state": self.vad_state,
                "rms_level": round(self.current_rms, 1),
                "stt_latency_ms": round(self.stt_latency_ms, 1),
            }
        }

    def get_telemetry_dict(self) -> Dict[str, Any]:
        robots_data = {}
        for name, r in self.fleet_robots.items():
            state_str = getattr(r.state_machine.state, "name", "IDLE") if hasattr(r, "state_machine") else "IDLE"
            dest_str = getattr(r, "destination_name", "CHG-01") or "CHG-01"
            bat = float(getattr(r, "battery_level", 100.0))
            robots_data[name] = {
                "state": state_str,
                "destination": dest_str,
                "battery": bat,
            }

        return {
            "type": "telemetry",
            "robots": robots_data,
            "assigned_robot": self.last_assigned_robot,
            "intent": self.last_intent,
            "destination": self.last_destination,
            "status": self.last_status,
            "history": self.command_history[:10],
            "audio_diagnostics": {
                "sample_rate": self.sample_rate,
                "channels": self.channels,
                "frames_received": self.audio_frames_received,
                "frames_dropped": self.audio_frames_dropped,
                "vad_state": self.vad_state,
                "rms_level": round(self.current_rms, 1),
                "stt_latency_ms": round(self.stt_latency_ms, 1),
            }
        }

"""
HospitalRobotNav — Standalone STT Worker Process
================================================
Independent process hosting faster-whisper inference via a lightweight
localhost HTTP IPC interface.

Architecture:
1. Completely isolated process: If Whisper/CTranslate2 encounters a native crash,
   CUDA OOM, or memory leak, only this worker process terminates.
2. Model is loaded once on startup and stays memory-resident.
3. Thread-safe request queue / single-request lock to prevent VRAM/CPU contention.
4. Exposes GET /health, POST /transcribe, and POST /shutdown on 127.0.0.1:<port>.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Any, Dict, Optional

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from speech.audio_processor import AudioProcessor
from speech.whisper_engine import WhisperEngine


class STTWorkerState:
    STARTING = "STARTING"
    READY = "READY"
    PROCESSING = "PROCESSING"
    ERROR = "ERROR"


class STTWorkerController:
    """Manages worker state, concurrency lock, and model inference."""

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: Optional[str] = None,
    ) -> None:
        self.state = STTWorkerState.STARTING
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.start_time = time.time()
        self._lock = threading.Lock()
        self.audio_processor = AudioProcessor(target_sample_rate=16000)
        self.whisper_engine: Optional[WhisperEngine] = None
        self.error_message: Optional[str] = None

        # Load model in background thread so HTTP server starts listening immediately
        threading.Thread(target=self._load_model_async, name="ArogyaWhisperAsyncLoader", daemon=True).start()

    def _load_model_async(self) -> None:
        try:
            print(f"[STT WORKER] Loading faster-whisper model '{self.model_size}' on {self.device}...", flush=True)
            self.whisper_engine = WhisperEngine(
                model_size=self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            self.state = STTWorkerState.READY
            print(f"[STT WORKER] Model ready! STT service is now active and READY.", flush=True)
        except Exception as e:
            self.state = STTWorkerState.ERROR
            self.error_message = str(e)
            print(f"[STT WORKER ERROR] Model initialization failed: {e}", flush=True)

    def get_health_dict(self) -> Dict[str, Any]:
        return {
            "status": self.state,
            "model": self.model_size,
            "device": self.device,
            "compute_type": self.compute_type or ("float16" if self.device == "cuda" else "int8"),
            "uptime_sec": round(time.time() - self.start_time, 1),
            "error": self.error_message,
        }

    def transcribe(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        channels: int = 1,
        language: Optional[str] = "en",
    ) -> Dict[str, Any]:
        """
        Process audio with faster-whisper under single-request concurrency lock.
        """
        if self.state == STTWorkerState.ERROR:
            return {"success": False, "error": f"Worker in ERROR state: {self.error_message}"}

        if not self._lock.acquire(blocking=False):
            # One request at a time policy (Requirement 36)
            return {"success": False, "error": "STT_BUSY", "code": 429}

        self.state = STTWorkerState.PROCESSING
        try:
            audio_float32, fmt_info = self.audio_processor.to_float32_16khz(
                audio_bytes,
                source_rate=sample_rate,
                source_channels=channels,
            )
            result = self.whisper_engine.transcribe(audio_float32, language=language)
            return result
        except Exception as e:
            print(f"[STT WORKER ERROR] Transcription failure: {e}")
            return {"success": False, "error": str(e), "transcript": ""}
        finally:
            self.state = STTWorkerState.READY
            self._lock.release()


class STTWorkerHTTPHandler(BaseHTTPRequestHandler):
    """Localhost HTTP request handler for the STT worker."""

    controller: Optional[STTWorkerController] = None

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard HTTP logging."""
        return

    def do_GET(self) -> None:
        ctrl = STTWorkerHTTPHandler.controller
        if self.path == "/health":
            data = ctrl.get_health_dict() if ctrl else {"status": "OFFLINE"}
            body = json.dumps(data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        ctrl = STTWorkerHTTPHandler.controller
        if not ctrl:
            self.send_error(503, "Controller not ready")
            return

        if self.path == "/transcribe":
            content_length = int(self.headers.get("Content-Length", 0))
            raw_audio = self.rfile.read(content_length)

            sample_rate = int(self.headers.get("X-Audio-Rate", 16000))
            channels = int(self.headers.get("X-Audio-Channels", 1))
            language = self.headers.get("X-Audio-Language", "en")
            if language == "auto" or not language:
                language = None

            res = ctrl.transcribe(
                raw_audio,
                sample_rate=sample_rate,
                channels=channels,
                language=language,
            )

            status_code = 200
            if not res.get("success") and res.get("error") == "STT_BUSY":
                status_code = 429
            elif not res.get("success"):
                status_code = 500

            body = json.dumps(res).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/shutdown":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            resp = json.dumps({"status": "shutting_down"}).encode("utf-8")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

            # Trigger shutdown in separate thread so response can complete
            def _delayed_exit():
                time.sleep(0.3)
                os._exit(0)

            threading.Thread(target=_delayed_exit, daemon=True).start()
            return

        self.send_error(404, "Not Found")


class ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def run_worker_server(
    host: str = "127.0.0.1",
    port: int = 8095,
    model_size: str = "small",
    device: str = "cpu",
    compute_type: Optional[str] = None,
) -> None:
    """Launch the STT worker server."""
    print("=" * 60)
    print("     AROGYA FASTER-WHISPER STANDALONE STT WORKER")
    print("=" * 60)
    print(f"[STT] Worker started (PID: {os.getpid()})")
    print(f"[STT] Listening on http://{host}:{port}")

    ctrl = STTWorkerController(
        model_size=model_size,
        device=device,
        compute_type=compute_type,
    )
    STTWorkerHTTPHandler.controller = ctrl

    httpd = ThreadedServer((host, port), STTWorkerHTTPHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        print("[STT] Worker stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AROGYA faster-whisper Standalone STT Worker")
    parser.add_argument("--host", default="127.0.0.1", help="Host IP to bind to")
    parser.add_argument("--port", type=int, default=8095, help="Port to listen on")
    parser.add_argument("--model", default="small", help="Whisper model size: small, turbo, base")
    parser.add_argument("--device", default="cpu", help="Inference device: cpu or cuda")
    parser.add_argument("--compute_type", default=None, help="Compute type: int8, float16, etc.")
    args = parser.parse_args()

    run_worker_server(
        host=args.host,
        port=args.port,
        model_size=args.model,
        device=args.device,
        compute_type=args.compute_type,
    )

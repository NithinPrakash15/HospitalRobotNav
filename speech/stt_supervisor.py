"""
HospitalRobotNav — STT Worker Process Supervisor
================================================
Monitors, manages, and restarts the standalone faster-whisper STT worker process.

Key Guarantees:
1. Total Isolation: The parent application (Isaac Sim / AROGYA) never imports
   CTranslate2 or faster-whisper.
2. Non-Blocking Startup: Isaac Sim simulation starts immediately while the STT
   worker loads asynchronously in the background.
3. Resilient Auto-Recovery: If the worker process crashes (CUDA error, VRAM exhaustion,
   segfault), the supervisor detects it, sets state to RESTARTING, and restarts the
   worker with exponential backoff.
4. Clean IPC: Uses structured JSON messages over localhost HTTP (127.0.0.1:8095).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple


class STTSupervisorState:
    STARTING = "STARTING"
    READY = "READY"
    PROCESSING = "PROCESSING"
    ERROR = "ERROR"
    RESTARTING = "RESTARTING"
    OFFLINE = "OFFLINE"


class STTSupervisor:
    """
    Supervisor daemon running inside the main application to oversee
    the external STT worker process.
    """

    def __init__(
        self,
        port: int = 8095,
        host: str = "127.0.0.1",
        model: str = "small",
        device: str = "cpu",
        compute_type: Optional[str] = None,
        python_exe: Optional[str] = None,
    ) -> None:
        self.port = port
        self.host = host
        self.model = model
        self.device = device
        self.compute_type = compute_type
        self.base_url = f"http://{self.host}:{self.port}"

        self.state = STTSupervisorState.STARTING
        self._process: Optional[subprocess.Popen] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._is_running = False
        self._lock = threading.Lock()

        # Crash backoff tracking
        self._restart_count = 0
        self._last_restart_time = 0.0
        self._max_rapid_restarts = 5
        self._backoff_window_sec = 60.0

        # Locate Python executable for STT worker
        self.python_exe = python_exe or self._discover_stt_python()

    def _discover_stt_python(self) -> str:
        """Find the dedicated virtual environment Python executable."""
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        candidates = [
            os.path.join(project_root, "stt_env", "Scripts", "python.exe"),
            os.path.join(project_root, ".venv_stt", "Scripts", "python.exe"),
            os.path.join(project_root, "stt_env", "bin", "python"),
            sys.executable,
        ]
        for p in candidates:
            if os.path.exists(p) and os.path.isfile(p):
                return p
        return sys.executable

    def start(self) -> bool:
        """Start the supervisor and spawn the worker process in the background."""
        if self._is_running:
            return True

        self._is_running = True
        self.state = STTSupervisorState.STARTING
        print(f"[STT SUPERVISOR] Starting STT service on {self.base_url} (Worker Python: {self.python_exe})")

        # Spawn worker
        self._spawn_worker()

        # Start supervisor health monitor thread
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="ArogyaSTTSupervisorMonitor",
            daemon=True,
        )
        self._monitor_thread.start()
        return True

    def _spawn_worker(self) -> None:
        """Spawn the STT worker subprocess with clean environment isolation."""
        cmd = [
            self.python_exe,
            "-u",
            "-m", "speech.stt_worker",
            "--host", self.host,
            "--port", str(self.port),
            "--model", self.model,
            "--device", self.device,
        ]
        if self.compute_type:
            cmd.extend(["--compute_type", self.compute_type])

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        try:
            # Creation flag to detach process safely on Windows without flashing console
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

            # CRITICAL: Clean environment to prevent Isaac Sim / Kit Python contamination
            # Isaac Sim sets PYTHONHOME and kit-specific PYTHONPATH which causes standard venvs
            # to crash with "AssertionError: SRE module mismatch".
            env = os.environ.copy()
            for var in ["PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE"]:
                env.pop(var, None)
            env["PYTHONPATH"] = project_root
            env["PYTHONUNBUFFERED"] = "1"

            # Prepend STT virtual environment Scripts to PATH
            stt_scripts = os.path.join(project_root, "stt_env", "Scripts")
            if os.path.exists(stt_scripts):
                env["PATH"] = stt_scripts + os.pathsep + env.get("PATH", "")

            # Log worker output to logs/stt_worker.log
            log_dir = os.path.join(project_root, "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "stt_worker.log")
            if hasattr(self, "_log_file") and self._log_file is not None and not self._log_file.closed:
                try:
                    self._log_file.close()
                except Exception:
                    pass
            self._log_file = open(log_path, "ab")

            self._process = subprocess.Popen(
                cmd,
                cwd=project_root,
                env=env,
                stdout=self._log_file,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
            print(f"[STT SUPERVISOR] Worker process spawned (PID: {self._process.pid}, log: {log_path})", flush=True)
        except Exception as e:
            print(f"[STT SUPERVISOR ERROR] Failed to spawn STT worker: {e}", flush=True)
            self.state = STTSupervisorState.ERROR

    def _monitor_loop(self) -> None:
        """Continually checks worker health and triggers auto-recovery on failure."""
        while self._is_running:
            time.sleep(1.0)
            if not self._is_running:
                break

            # 1. Check if subprocess terminated
            if self._process is not None:
                ret = self._process.poll()
                if ret is not None:
                    print(f"\n[STT WARNING] Worker process (PID {self._process.pid}) exited with code {ret}!")
                    self._process = None  # Clear process handle so we don't spin on dead process
                    self._handle_worker_crash()
                    continue

            # 2. Check health endpoint via HTTP (direct localhost socket)
            try:
                import http.client
                conn = http.client.HTTPConnection(self.host, self.port, timeout=1.0)
                conn.request("GET", "/health")
                resp = conn.getresponse()
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    worker_status = data.get("status", "")
                    if worker_status == "READY":
                        if self.state != STTSupervisorState.READY:
                            print(f"[STT SUPERVISOR] Worker is READY: Model={data.get('model')} on {data.get('device')}")
                        self.state = STTSupervisorState.READY
                        self._restart_count = 0  # Reset restart count upon successful recovery
                    elif worker_status == "PROCESSING":
                        self.state = STTSupervisorState.PROCESSING
                    elif worker_status == "STARTING":
                        self.state = STTSupervisorState.STARTING
                    elif worker_status == "ERROR":
                        self.state = STTSupervisorState.ERROR
                conn.close()
            except Exception:
                # If in ERROR state and no worker process is alive, periodically attempt recovery
                if self.state == STTSupervisorState.ERROR and self._process is None:
                    if time.time() - self._last_restart_time > 15.0:
                        print("[STT SUPERVISOR] Attempting periodic auto-recovery for STT worker...")
                        self._restart_count = 0
                        self._spawn_worker()

    def _handle_worker_crash(self) -> None:
        """Handle worker exit, apply backoff, and restart worker."""
        self.state = STTSupervisorState.RESTARTING
        now = time.time()

        if now - self._last_restart_time < self._backoff_window_sec:
            self._restart_count += 1
        else:
            self._restart_count = 1
        self._last_restart_time = now

        if self._restart_count > self._max_rapid_restarts:
            print(f"[STT SUPERVISOR ERROR] Rapid restart limit exceeded ({self._restart_count} crashes). Halting rapid restarts (will retry periodically).")
            self.state = STTSupervisorState.ERROR
            return

        backoff = min(1.0 * (2 ** (self._restart_count - 1)), 8.0)
        print(f"[STT SUPERVISOR] Restarting STT worker in {backoff:.1f}s (Attempt {self._restart_count}/{self._max_rapid_restarts})...")
        time.sleep(backoff)

        if self._is_running:
            self._spawn_worker()

    def get_status(self) -> Dict[str, Any]:
        """Expose current supervisor and worker state."""
        return {
            "status": self.state,
            "port": self.port,
            "model": self.model,
            "device": self.device,
            "pid": self._process.pid if self._process else None,
            "restarts": self._restart_count,
        }

    def transcribe(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        channels: int = 1,
        language: str = "en",
        timeout: float = 12.0,
    ) -> Dict[str, Any]:
        """
        Send audio to worker for transcription over localhost HTTP IPC.
        """
        import http.client

        # If in ERROR or RESTARTING, perform a quick 0.5s health probe before rejecting
        if self.state not in (STTSupervisorState.READY, STTSupervisorState.PROCESSING):
            try:
                conn = http.client.HTTPConnection(self.host, self.port, timeout=0.8)
                conn.request("GET", "/health")
                resp = conn.getresponse()
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("status") == "READY":
                        self.state = STTSupervisorState.READY
                        self._restart_count = 0
                conn.close()
            except Exception:
                pass

        if self.state not in (STTSupervisorState.READY, STTSupervisorState.PROCESSING):
            return {
                "success": False,
                "transcript": "",
                "error": f"STT Service currently {self.state}",
            }

        headers = {
            "Content-Type": "application/octet-stream",
            "X-Audio-Rate": str(sample_rate),
            "X-Audio-Channels": str(channels),
            "X-Audio-Language": language or "en",
        }

        try:
            conn = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
            conn.request("POST", "/transcribe", body=audio_bytes, headers=headers)
            resp = conn.getresponse()
            raw_data = resp.read()
            conn.close()
            data = json.loads(raw_data.decode("utf-8"))
            return data
        except Exception as ex:
            return {"success": False, "transcript": "", "error": str(ex)}

    def stop(self) -> None:
        """Clean shutdown of worker and supervisor."""
        self._is_running = False
        self.state = STTSupervisorState.OFFLINE

        # Attempt graceful HTTP shutdown
        try:
            req = urllib.request.Request(f"{self.base_url}/shutdown", data=b"{}", method="POST")
            with urllib.request.urlopen(req, timeout=1.0):
                pass
        except Exception:
            pass

        # Terminate process if still alive
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=2.0)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

        if hasattr(self, "_log_file") and self._log_file is not None and not self._log_file.closed:
            try:
                self._log_file.close()
            except Exception:
                pass

        print("[STT SUPERVISOR] STT Service stopped.")

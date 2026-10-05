"""
Tests STT Worker Subprocess, Supervisor, IPC, and Crash-Recovery
===============================================================
Verifies:
1. STT worker starts as an independent subprocess.
2. Supervisor monitors health over localhost HTTP (127.0.0.1:8095).
3. Transcribes audio over IPC and returns clean transcript.
4. Independent restart: If STT worker process is killed, supervisor detects
   it, restarts the worker process, and restores READY state.
5. Post-restart transcription succeeds.
"""

import os
import sys
import time
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from speech.stt_supervisor import STTSupervisor, STTSupervisorState


class TestSTTProcessAndSupervisor(unittest.TestCase):

    def setUp(self):
        # Use port 8097 to avoid conflicts
        self.supervisor = STTSupervisor(
            port=8097,
            host="127.0.0.1",
            model="small",
            device="cpu",
        )
        self.supervisor.start()

        # Wait up to 10 seconds for worker to be READY
        for _ in range(50):
            if self.supervisor.state == STTSupervisorState.READY:
                break
            time.sleep(0.2)

        self.assertEqual(self.supervisor.state, STTSupervisorState.READY, "Supervisor failed to become READY")

    def tearDown(self):
        self.supervisor.stop()

    def test_transcribe_over_ipc(self):
        wav_path = os.path.join(PROJECT_ROOT, "tests", "audio", "test_01.wav")
        self.assertTrue(os.path.exists(wav_path))

        with open(wav_path, "rb") as f:
            raw_audio = f.read()

        result = self.supervisor.transcribe(raw_audio, sample_rate=22050, channels=1, language="en")
        self.assertTrue(result.get("success"), f"Transcription failed: {result}")
        transcript = result.get("transcript", "").lower()
        print(f"[TEST IPC] Received transcript: '{result.get('transcript')}' (latency: {result.get('latency_ms')}ms)")
        self.assertIn("go to icu", transcript)

    def test_worker_crash_and_auto_recovery(self):
        """Simulate worker crash (segfault/kill) and verify supervisor restarts it."""
        orig_pid = self.supervisor._process.pid
        print(f"\n[TEST CRASH] Force-killing STT worker (PID: {orig_pid})...")

        # Terminate worker abruptly to simulate crash
        self.supervisor._process.kill()

        # Wait for supervisor monitor to detect exit and restart
        restarted = False
        for _ in range(60):
            time.sleep(0.3)
            if self.supervisor.state == STTSupervisorState.READY and self.supervisor._process.pid != orig_pid:
                restarted = True
                break

        self.assertTrue(restarted, "Supervisor failed to restart worker after crash!")
        new_pid = self.supervisor._process.pid
        print(f"[TEST CRASH] Worker recovered successfully with new PID: {new_pid}!")

        # Verify transcription works after crash recovery
        wav_path = os.path.join(PROJECT_ROOT, "tests", "audio", "test_02.wav")
        with open(wav_path, "rb") as f:
            raw_audio = f.read()

        res = self.supervisor.transcribe(raw_audio, sample_rate=22050, channels=1, language="en")
        self.assertTrue(res.get("success"), f"Post-crash transcription failed: {res}")
        print(f"[TEST CRASH] Post-crash transcript: '{res.get('transcript')}'")
        self.assertIn("pharmacy", res.get("transcript", "").lower())


if __name__ == "__main__":
    unittest.main()

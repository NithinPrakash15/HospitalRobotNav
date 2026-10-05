"""
AROGYA Autonomous Hospital Robot Fleet — Headless Control Stub
==============================================================
This module previously hosted a Tkinter-based standalone GUI window.

Tkinter (_tkinter C-extension) is NOT available inside Isaac Sim Kit Python.
All GUI functionality has been migrated to the native omni.ui HUD:
    environments/in_viewport_hud.py  ->  HospitalViewportHUD

This file is now a PURE HEADLESS STUB that provides:
  - A no-op ArogyaControlWindow class so existing import lines don't crash.
  - Thread-safe add_log() / start() / stop() methods that route messages
    to standard output so logs are still visible in the Isaac Sim console.

DO NOT import tkinter here — it is intentionally absent.
"""

from __future__ import annotations

import queue
import time
import threading
from typing import Any, Callable, Dict, List, Optional


class ArogyaControlWindow:
    """
    Headless (no-op) replacement for the old Tkinter fleet control window.

    All visual controls now live in HospitalViewportHUD (omni.ui).
    This stub keeps the API surface identical so call-sites in
    run_embodied_hospital_ai.py that reference control_window.add_log(...)
    continue to work without crashing.
    """

    def __init__(
        self,
        cmd_interface: Any = None,
        fleet_robots: Optional[Dict[str, Any]] = None,
        agent_manager: Any = None,
        on_command_submit: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.cmd_interface     = cmd_interface
        self.fleet_robots      = fleet_robots or {}
        self.agent_manager     = agent_manager
        self.on_command_submit = on_command_submit
        self._running          = False
        self._log_queue: queue.Queue = queue.Queue()

        # Connect as voice listener if command interface available
        if self.cmd_interface and hasattr(self.cmd_interface, "add_voice_listener"):
            self.cmd_interface.add_voice_listener(self._on_voice_event)

        print("[ControlWindow] Headless stub mode — GUI is handled by omni.ui HospitalViewportHUD.")

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """No-op: GUI is handled by omni.ui viewport HUD."""
        self._running = True
        print("[ControlWindow] start() called — using omni.ui HUD (no Tkinter window).")

    def stop(self) -> None:
        """No-op shutdown."""
        self._running = False

    # ── Logging ───────────────────────────────────────────────────────────────

    def add_log(self, message: str) -> None:
        """Print log message to Isaac Sim console (no GUI needed)."""
        timestamp = time.strftime("%H:%M:%S")
        safe = _strip_emoji(message)
        print(f"[ControlLog][{timestamp}] {safe}", flush=True)
        self._log_queue.put(f"[{timestamp}] {safe}\n")

    # ── Voice event forwarding ────────────────────────────────────────────────

    def _on_voice_event(self, info: dict) -> None:
        """Receive voice-pipeline updates — log to console."""
        if info.get("transcript"):
            self.add_log(f"[VOICE] Speech: \"{info['transcript']}\" -> Intent: {info.get('intent', 'N/A')}")


def _strip_emoji(text: str) -> str:
    """Remove non-ASCII characters so Isaac Sim console doesn't show garbled output."""
    return "".join(c if 32 <= ord(c) <= 126 else " " for c in str(text)).strip()

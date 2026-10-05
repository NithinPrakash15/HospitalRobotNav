"""
AROGYA Autonomous Web Interface Launcher & Background Service Manager
====================================================================
Orchestrates the background execution of:
1. Perception & POV Web Server (Port 8080)
2. Live Hospital Database Web Server (Port 8081)

Features:
- Completely non-blocking background daemon thread startup
- Health check polling before browser tab invocation
- Strict singleton guard against duplicate browser window/tab launches
- Clean teardown hooks for graceful simulation exit
"""

from __future__ import annotations

import logging
import threading
import time
import urllib.request
import webbrowser
from typing import Optional

from .perception_server import start_perception_server, stop_perception_server
from .database_server import start_database_server, stop_database_server

logger = logging.getLogger("ArogyaBrowserLauncher")

_already_launched: bool = False
_launcher_lock = threading.Lock()


def _check_server_healthy(url: str, timeout_seconds: float = 3.0) -> bool:
    """Poll health endpoint until HTTP 200 or timeout."""
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ArogyaHealthCheck/1.0"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.1)
    return False


def _launcher_worker(open_browser: bool = True) -> None:
    """Background worker that spins up servers and conditionally opens browser tabs."""
    global _already_launched

    try:
        # 1. Start Perception Server (Port 8080)
        start_perception_server(host="127.0.0.1", port=8080)
    except Exception as e:
        logger.error(f"Failed to start Perception Server on port 8080: {e}")

    try:
        # 2. Start Hospital Database Server (Port 8081)
        start_database_server(host="127.0.0.1", port=8081)
    except Exception as e:
        logger.error(f"Failed to start Hospital Database Server on port 8081: {e}")

    if not open_browser:
        logger.info("[AROGYA WEB] Headless mode: Browser launch suppressed.")
        return

    with _launcher_lock:
        if _already_launched:
            logger.info("[AROGYA WEB] Browser tabs already launched once in this session. Skipping duplicate.")
            return
        _already_launched = True

    # 3. Wait for endpoints to become responsive
    p_healthy = _check_server_healthy("http://127.0.0.1:8080/health", timeout_seconds=4.0)
    d_healthy = _check_server_healthy("http://127.0.0.1:8081/health", timeout_seconds=4.0)

    if not p_healthy:
        logger.warning("[AROGYA WEB] Perception server did not respond to /health in time.")
    if not d_healthy:
        logger.warning("[AROGYA WEB] Database server did not respond to /health in time.")

    # 4. Open default browser tabs
    try:
        logger.info("[AROGYA WEB] Opening Perception Dashboard at http://127.0.0.1:8080")
        webbrowser.open_new_tab("http://127.0.0.1:8080")
        time.sleep(0.4)
        logger.info("[AROGYA WEB] Opening Live Hospital Database at http://127.0.0.1:8081")
        webbrowser.open_new_tab("http://127.0.0.1:8081")
    except Exception as e:
        logger.error(f"[AROGYA WEB] Exception opening browser tabs: {e}")


def launch_web_interfaces(headless: bool = False, open_browser: bool = True) -> threading.Thread:
    """
    Launch Perception and Database web interfaces on background daemon threads.
    If headless is True, browser tabs will NOT be opened automatically.
    """
    should_open = open_browser and not headless
    t = threading.Thread(target=_launcher_worker, args=(should_open,), daemon=True, name="ArogyaBrowserLauncherThread")
    t.start()
    return t


def stop_web_interfaces() -> None:
    """Shut down both background web servers cleanly."""
    stop_perception_server()
    stop_database_server()

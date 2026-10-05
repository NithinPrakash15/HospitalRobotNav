"""
Milestone 3 -- Full-Scale ROS 2 Digital Twin Hospital (60m x 60m)
==================================================================
Directly executes the Unified Multi-Agent Embodied AI Hospital Robot system:
    - 26 Clinical Departments with Solid Perimeter Enclosure
    - Event-Driven Interactive Command Terminal (keyboard + Vosk ASR mic)
    - Multi-Agent Contract-Net Protocol (Coordinator, Delivery, Reception, Emergency)
    - Triple-Layer Collision Guard (100% wall-safe navigation through doorways)
    - Bilingual Voice: English + Hindi (Windows SAPI synthesis)
    - Real-Time Status Dashboard
    - Dynamic Obstacles: Doctors, Nurses, Stretchers patrolling corridors
    - Pure IDLE start: Zero automated movement and zero automated speech

Run Command:
    C:\\isaacsim\\python.bat scripts\\milestone_3_hospital_expanded.py
"""

import os
import sys

# Configure UTF-8 console output for Windows CP1252 compatibility
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Forward execution to the unified Multi-Agent Embodied AI master script
runner_path = os.path.join(os.path.dirname(__file__), "run_embodied_hospital_ai.py")
with open(runner_path, "r", encoding="utf-8") as f:
    code = f.read()

exec(compile(code, runner_path, "exec"))

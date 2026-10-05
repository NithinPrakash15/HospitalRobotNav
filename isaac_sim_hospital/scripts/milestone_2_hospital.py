"""
Hospital Simulation Launcher — Multi-Agent Embodied AI Robot v2.0
==================================================================
Entry point for the complete 60m x 60m ROS 2 Digital Twin Hospital:
- 24 Clinical Departments & Full Corridor Network
- Arogya Service AMR + Companion Logistics AMR
- Event-Driven Interactive Command Terminal (type commands to start robot)
- Multi-Agent Contract-Net Protocol (Coordinator, Delivery, Reception, Emergency)
- Triple-Layer Collision Guard (100% wall-safe navigation)
- Bilingual Voice: English + Hindi (Windows SAPI synthesis)
- Real-Time Status Dashboard
- 9-State Robot State Machine with 5 Priority Levels
- Dynamic Obstacles: Doctors, Nurses, Stretchers patrolling corridors

Run Commands:
    Interactive  : C:\\isaacsim\\python.bat scripts\\milestone_2_hospital.py
    With mic ASR : C:\\isaacsim\\python.bat scripts\\milestone_2_hospital.py --mic
    Headless test: C:\\isaacsim\\python.bat scripts\\milestone_2_hospital.py --headless
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

# Forward to the complete Multi-Agent Embodied AI demonstration script
runner_path = os.path.join(os.path.dirname(__file__), "run_embodied_hospital_ai.py")
with open(runner_path, "r", encoding="utf-8") as f:
    code = f.read()

exec(compile(code, runner_path, "exec"))


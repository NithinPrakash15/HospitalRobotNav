"""
Stage 5 Diagnostic: Isaac Sim with Full Hospital + All 4 Fleet Robots
=====================================================================
Tests whether Isaac Sim 5.1 can load the full Hospital Environment,
instantiate all 4 specialized AMRs:
  1. Arogya_Delivery  (DeliveryAMR,   CHG-01, (34.5, 33.0, 0.0))
  2. Mitra_Reception  (ReceptionAMR,  RCT-01, (0.0, -5.0, 0.0))
  3. Garuda_Emergency (EmergencyAMR,  EMR-01, (-29.0, -8.8, 0.0))
  4. Sahayak_Support  (SupportAMR,    CHG-01, (39.5, 33.0, 0.0))
step the simulation loop for 100 frames, and verify VRAM / fleet stability.
"""

import os
import sys
import time
import subprocess
import traceback

_this_dir = os.path.dirname(os.path.abspath(__file__))
_isaac_dir = os.path.dirname(_this_dir)
_repo_root = os.path.dirname(_isaac_dir)

for p in [_repo_root, _isaac_dir]:
    if p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, _repo_root)
sys.path.insert(0, _isaac_dir)

def log_msg(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [STAGE 5] {msg}"
    print(line, flush=True)
    with open("logs/isaac_sim/stage5_full_fleet.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")

def get_vram_info():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.free,memory.total", "--format=csv,nounits,noheader"],
            universal_newlines=True
        ).strip()
        used, free, total = [int(x.strip()) for x in out.split(",")]
        return f"VRAM Used: {used} MiB / Free: {free} MiB / Total: {total} MiB"
    except Exception as e:
        return f"VRAM check failed: {e}"

def main():
    os.makedirs("logs/isaac_sim", exist_ok=True)
    with open("logs/isaac_sim/stage5_full_fleet.log", "w", encoding="utf-8") as f:
        f.write("=== Stage 5: Hospital + Full Fleet (4 Robots) Stability Test ===\n")

    log_msg("Starting Stage 5 Diagnostic...")
    log_msg(f"Initial GPU Memory: {get_vram_info()}")

    headless = "--gui" not in sys.argv
    log_msg(f"Headless mode: {headless}")

    log_msg("Step 5.1: Launching SimulationApp...")
    t0 = time.time()
    try:
        from isaacsim import SimulationApp
        app_config = {
            "headless": headless,
            "width": 1280,
            "height": 720,
            "anti_aliasing": 0,
            "renderer": "RayTracedLighting",
            "max_bounces": 1,
            "max_specular_transmission_bounces": 0,
            "denoiser": True,
            "subdiv_refinement_level": 0,
        }
        app = SimulationApp(app_config)
        log_msg(f"SimulationApp initialized in {time.time() - t0:.2f}s")
    except Exception as e:
        log_msg(f"CRITICAL ERROR initializing SimulationApp: {e}")
        log_msg(traceback.format_exc())
        return 1

    log_msg("Step 5.2: Initializing World & HospitalEnvironment...")
    t1 = time.time()
    try:
        from isaacsim.core.api import World
        from environments.hospital_env import HospitalEnvironment

        world = World(physics_dt=1.0/60.0, rendering_dt=1.0/30.0, stage_units_in_meters=1.0)
        env = HospitalEnvironment()
        log_msg("Building 88m x 76m Grand Hospital digital twin...")
        env.build_all()
        log_msg(f"Hospital environment built in {time.time() - t1:.2f}s")
    except Exception as e:
        log_msg(f"CRITICAL ERROR building HospitalEnvironment: {e}")
        log_msg(traceback.format_exc())
        app.close()
        return 2

    log_msg("Step 5.3: Instantiating Full 4-Robot Fleet...")
    t2 = time.time()
    try:
        from robots.arogya_robot import (
            DeliveryAMR, ReceptionAMR, EmergencyAMR, SupportAMR
        )
        import numpy as np

        robot_configs = [
            ("Arogya_Delivery", (34.5, 33.0, 0.0), -np.pi / 2, DeliveryAMR, np.array([0.0, 0.85, 0.95]), "CHG-01"),
            ("Mitra_Reception", (0.0, -5.0, 0.0), -np.pi / 2, ReceptionAMR, np.array([0.0, 0.85, 0.45]), "RCT-01"),
            ("Garuda_Emergency", (-29.0, -8.8, 0.0), 0.0, EmergencyAMR, np.array([0.95, 0.15, 0.15]), "EMR-01"),
            ("Sahayak_Support", (39.5, 33.0, 0.0), -np.pi / 2, SupportAMR, np.array([0.95, 0.70, 0.10]), "CHG-01"),
        ]

        robots = []
        for name, pos, yaw, cls, color, home in robot_configs:
            r = cls(
                prim_path=f"/World/Robots/{name}",
                name=name,
                start_position=pos,
                start_yaw=yaw,
                accent_color=color,
                home_station=home,
            )
            robots.append(r)
            log_msg(f"  Spawned {name} ({cls.__name__}) at {pos}")

        log_msg(f"All 4 fleet robots instantiated in {time.time() - t2:.2f}s")
        log_msg(f"GPU Memory after fleet spawn: {get_vram_info()}")
    except Exception as e:
        log_msg(f"CRITICAL ERROR instantiating fleet: {e}")
        log_msg(traceback.format_exc())
        app.close()
        return 3

    log_msg("Step 5.4: Stepping simulation loop for 100 frames with full fleet...")
    try:
        world.reset()
        for frame in range(1, 101):
            for r in robots:
                r.step_autonomous(dt=1.0/60.0)
            world.step(render=not headless)
            if frame % 25 == 0:
                states = [f"{r.name}:{r.state_machine.state.name}" for r in robots]
                log_msg(f"  Frame {frame}/100 stepped successfully. [{', '.join(states)}] {get_vram_info()}")
        log_msg("100 frames completed successfully with Hospital + All 4 Fleet Robots.")
    except Exception as e:
        log_msg(f"CRITICAL ERROR during simulation stepping: {e}")
        log_msg(traceback.format_exc())
        app.close()
        return 4

    log_msg("Step 5.5: Closing SimulationApp...")
    try:
        app.close()
        log_msg("SimulationApp closed cleanly.")
        log_msg(f"Final GPU Memory: {get_vram_info()}")
        log_msg(">>> STAGE 5 PASSED: Hospital + Full Fleet (4 Robots) is 100% STABLE. <<<")
        return 0
    except Exception as e:
        log_msg(f"Error during SimulationApp close: {e}")
        log_msg(traceback.format_exc())
        return 5

if __name__ == "__main__":
    sys.exit(main())

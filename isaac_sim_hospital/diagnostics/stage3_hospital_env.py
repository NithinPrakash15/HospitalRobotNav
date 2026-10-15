"""
Stage 3 Diagnostic: Isaac Sim with Full Hospital Environment
============================================================
Tests whether Isaac Sim 5.1 can load the full 88m x 76m Hospital Environment
(20+ clinical departments, walls, furniture, cutaway signage, lighting),
step the simulation loop for 100 frames, and verify VRAM / stability.
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
    line = f"[{ts}] [STAGE 3] {msg}"
    print(line, flush=True)
    with open("logs/isaac_sim/stage3_hospital.log", "a", encoding="utf-8") as f:
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
    with open("logs/isaac_sim/stage3_hospital.log", "w", encoding="utf-8") as f:
        f.write("=== Stage 3: Hospital Environment Stability Test ===\n")

    log_msg("Starting Stage 3 Diagnostic...")
    log_msg(f"Initial GPU Memory: {get_vram_info()}")

    headless = "--gui" not in sys.argv
    log_msg(f"Headless mode: {headless}")

    log_msg("Step 3.1: Launching SimulationApp...")
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

    log_msg("Step 3.2: Initializing World & HospitalEnvironment...")
    t1 = time.time()
    try:
        from isaacsim.core.api import World
        from environments.hospital_env import HospitalEnvironment

        world = World(physics_dt=1.0/60.0, rendering_dt=1.0/30.0, stage_units_in_meters=1.0)
        env = HospitalEnvironment()
        log_msg("Building 88m x 76m Grand Hospital digital twin...")
        env.build_all()
        log_msg(f"Hospital environment built in {time.time() - t1:.2f}s")
        log_msg(f"Collision boxes registered: {len(env.collision_boxes)}")
        log_msg(f"GPU Memory after hospital build: {get_vram_info()}")
    except Exception as e:
        log_msg(f"CRITICAL ERROR building HospitalEnvironment: {e}")
        log_msg(traceback.format_exc())
        app.close()
        return 2

    log_msg("Step 3.3: Stepping simulation loop for 100 frames with full hospital...")
    try:
        world.reset()
        for frame in range(1, 101):
            world.step(render=not headless)
            if frame % 25 == 0:
                log_msg(f"  Frame {frame}/100 stepped successfully. {get_vram_info()}")
        log_msg("100 frames completed successfully with full procedural hospital digital twin.")
    except Exception as e:
        log_msg(f"CRITICAL ERROR during simulation stepping: {e}")
        log_msg(traceback.format_exc())
        app.close()
        return 3

    log_msg("Step 3.4: Closing SimulationApp...")
    try:
        app.close()
        log_msg("SimulationApp closed cleanly.")
        log_msg(f"Final GPU Memory: {get_vram_info()}")
        log_msg(">>> STAGE 3 PASSED: Full Hospital Digital Twin is 100% STABLE. <<<")
        return 0
    except Exception as e:
        log_msg(f"Error during SimulationApp close: {e}")
        log_msg(traceback.format_exc())
        return 4

if __name__ == "__main__":
    sys.exit(main())

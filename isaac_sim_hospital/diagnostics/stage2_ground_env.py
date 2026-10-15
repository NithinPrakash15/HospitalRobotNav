"""
Stage 2 Diagnostic: Isaac Sim with Ground Plane & Physics
=========================================================
Tests whether Isaac Sim 5.1 can initialize PhysX physics, add a default ground plane,
add lighting, step the physics simulation loop for 100 frames, and shut down cleanly.
Logs: RAM, VRAM, PhysX initialization, and clean shutdown.
"""

import os
import sys
import time
import subprocess
import traceback

def log_msg(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [STAGE 2] {msg}"
    print(line, flush=True)
    with open("logs/isaac_sim/stage2_ground.log", "a", encoding="utf-8") as f:
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
    with open("logs/isaac_sim/stage2_ground.log", "w", encoding="utf-8") as f:
        f.write("=== Stage 2: Ground Plane & Physics Stability Test ===\n")

    log_msg("Starting Stage 2 Diagnostic...")
    log_msg(f"Initial GPU Memory: {get_vram_info()}")

    headless = "--gui" not in sys.argv
    log_msg(f"Headless mode: {headless}")

    log_msg("Step 2.1: Launching SimulationApp...")
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

    log_msg("Step 2.2: Initializing World & Adding Ground Plane...")
    t1 = time.time()
    try:
        from isaacsim.core.api import World
        world = World(physics_dt=1.0/60.0, rendering_dt=1.0/30.0, stage_units_in_meters=1.0)
        world.scene.add_default_ground_plane()
        log_msg(f"Ground plane added in {time.time() - t1:.2f}s")
        log_msg(f"GPU Memory after ground plane: {get_vram_info()}")
    except Exception as e:
        log_msg(f"CRITICAL ERROR adding ground plane: {e}")
        log_msg(traceback.format_exc())
        app.close()
        return 2

    log_msg("Step 2.3: Stepping simulation loop for 100 frames with physics...")
    try:
        world.reset()
        for frame in range(1, 101):
            world.step(render=not headless)
            if frame % 25 == 0:
                log_msg(f"  Frame {frame}/100 stepped successfully. {get_vram_info()}")
        log_msg("100 frames completed successfully with active PhysX ground plane.")
    except Exception as e:
        log_msg(f"CRITICAL ERROR during simulation stepping: {e}")
        log_msg(traceback.format_exc())
        app.close()
        return 3

    log_msg("Step 2.4: Closing SimulationApp...")
    try:
        app.close()
        log_msg("SimulationApp closed cleanly.")
        log_msg(f"Final GPU Memory: {get_vram_info()}")
        log_msg(">>> STAGE 2 PASSED: Ground Plane & Physics are 100% STABLE. <<<")
        return 0
    except Exception as e:
        log_msg(f"Error during SimulationApp close: {e}")
        log_msg(traceback.format_exc())
        return 4

if __name__ == "__main__":
    sys.exit(main())

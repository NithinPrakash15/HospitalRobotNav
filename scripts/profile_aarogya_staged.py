"""
AAROGYA — Staged Performance Profiler (Phase 1 Baseline)
======================================================
Measures and records performance across the 9 required stages:
1. Empty Isaac Sim scene
2. Hospital environment without robots
3. Hospital environment with one robot
4. Robot with physics enabled
5. Robot with camera enabled
6. Robot with LiDAR enabled
7. ROS2 integration enabled
8. SLAM enabled
9. Full AAROGYA application

Collects:
- FPS & frame rendering time
- GPU utilization & VRAM usage (via pynvml / nvidia-smi)
- CPU utilization & System RAM usage (via psutil)
- Component times: physics, rendering, camera, LiDAR, ROS2, SLAM
"""

import os
import sys
import time
import json
import math
import psutil
import numpy as np

# Path configuration
script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(script_dir)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
isaac_hospital_dir = os.path.join(repo_root, "isaac_sim_hospital")
if isaac_hospital_dir not in sys.path:
    sys.path.insert(0, isaac_hospital_dir)

import importlib.util

def _protect_config_module():
    global sys
    sys.path = [p for p in sys.path if not (p.replace("\\", "/").rstrip("/").endswith("/cv2"))]
    for p in [repo_root, isaac_hospital_dir]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)
    config_init = os.path.join(repo_root, "config", "__init__.py")
    if os.path.exists(config_init) and ("config" not in sys.modules or not hasattr(sys.modules["config"], "__path__")):
        spec = importlib.util.spec_from_file_location("config", config_init, submodule_search_locations=[os.path.dirname(config_init)])
        mod = importlib.util.module_from_spec(spec)
        sys.modules["config"] = mod
        spec.loader.exec_module(mod)

_protect_config_module()

def get_gpu_info():
    """Query GPU util and VRAM using nvidia-smi."""
    try:
        import subprocess
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=1.5
        )
        if res.returncode == 0:
            parts = res.stdout.strip().split("\n")[0].split(",")
            return {
                "gpu_util_pct": float(parts[0].strip()),
                "gpu_vram_used_mb": float(parts[1].strip()),
                "gpu_vram_total_mb": float(parts[2].strip()),
            }
    except Exception:
        pass
    return {"gpu_util_pct": 0.0, "gpu_vram_used_mb": 0.0, "gpu_vram_total_mb": 6141.0}

def get_sys_info():
    mem = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=None)
    return {
        "cpu_util_pct": cpu,
        "ram_used_mb": round((mem.total - mem.available) / (1024 * 1024), 1),
        "ram_total_mb": round(mem.total / (1024 * 1024), 1),
        "ram_util_pct": mem.percent,
    }

print("=" * 80)
print("  AAROGYA PHASE 1: STAGED PERFORMANCE PROFILER & BASELINE BENCHMARK")
print("=" * 80)

# Import Isaac Sim SimulationApp
from isaacsim import SimulationApp
from configs.simulation_config import get_app_config, AROGYA_FEATURES

app_config = get_app_config(headless=True)
simulation_app = SimulationApp(app_config)
_protect_config_module()

from isaacsim.core.api import World
from environments.hospital_env import HospitalEnvironment
from robots.arogya_robot import DeliveryAMR
from multi_agent.ros2_bridge import IsaacSimROS2Bridge
from navigation.slam_exploration_engine import SLAM_ENGINE
from sensors.camera_manager import CameraSensorManager
from sensors.lidar_manager import LiDARSensorManager

results = {}

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1: Empty Scene
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BENCHMARK] Stage 1: Empty Isaac Sim Scene...")
world = World(stage_units_in_meters=1.0)
world.reset()

times = []
for _ in range(35):
    t0 = time.perf_counter()
    world.step(render=False)
    times.append(time.perf_counter() - t0)

dt_arr = times[5:]  # Discard warmup
fps = 1.0 / np.mean(dt_arr)
results["Stage 1: Empty Scene"] = {
    "fps": round(fps, 1),
    "frame_time_ms": round(float(np.mean(dt_arr) * 1000), 2),
    **get_gpu_info(),
    **get_sys_info(),
}
print(f"  -> FPS: {fps:.1f} | Frame Time: {np.mean(dt_arr)*1000:.2f} ms")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2: Hospital Environment without robots
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BENCHMARK] Stage 2: Hospital Environment without robots...")
hospital_env = HospitalEnvironment(wall_height=1.30, wall_thickness=0.22, door_width=2.0)
hospital_env.build_all()
collision_guard = hospital_env.get_collision_guard(robot_radius=0.38)
world.reset()

times = []
for _ in range(35):
    t0 = time.perf_counter()
    world.step(render=False)
    times.append(time.perf_counter() - t0)

dt_arr = times[5:]
fps = 1.0 / np.mean(dt_arr)
results["Stage 2: Hospital Scene (No Robots)"] = {
    "fps": round(fps, 1),
    "frame_time_ms": round(float(np.mean(dt_arr) * 1000), 2),
    **get_gpu_info(),
    **get_sys_info(),
}
print(f"  -> FPS: {fps:.1f} | Frame Time: {np.mean(dt_arr)*1000:.2f} ms")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 3: Hospital Environment with 1 robot
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BENCHMARK] Stage 3: Hospital Environment with 1 robot...")
robot1 = DeliveryAMR(
    prim_path="/World/Robots/Arogya_Delivery",
    start_position=(34.5, 33.0, 0.0),
    start_yaw=-np.pi / 2,
    name="Arogya_Delivery",
)
robot1.set_collision_guard(collision_guard)
robot1.set_hospital_env(hospital_env)
fleet = {"Arogya_Delivery": robot1}
world.reset()

times = []
for _ in range(35):
    t0 = time.perf_counter()
    world.step(render=False)
    times.append(time.perf_counter() - t0)

dt_arr = times[5:]
fps = 1.0 / np.mean(dt_arr)
results["Stage 3: Hospital + 1 Robot"] = {
    "fps": round(fps, 1),
    "frame_time_ms": round(float(np.mean(dt_arr) * 1000), 2),
    **get_gpu_info(),
    **get_sys_info(),
}
print(f"  -> FPS: {fps:.1f} | Frame Time: {np.mean(dt_arr)*1000:.2f} ms")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 4: Robot with Physics & Autonomous Kinematics Enabled
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BENCHMARK] Stage 4: Robot with Physics & Autonomous Kinematics...")
times = []
physics_times = []
nav_times = []

for _ in range(35):
    t0 = time.perf_counter()
    t_p0 = time.perf_counter()
    world.step(render=False)
    t_p = time.perf_counter() - t_p0

    t_n0 = time.perf_counter()
    robot1.step_autonomous(dt=0.016)
    t_n = time.perf_counter() - t_n0

    times.append(time.perf_counter() - t0)
    physics_times.append(t_p)
    nav_times.append(t_n)

dt_arr = times[5:]
fps = 1.0 / np.mean(dt_arr)
results["Stage 4: Robot with Physics"] = {
    "fps": round(fps, 1),
    "frame_time_ms": round(float(np.mean(dt_arr) * 1000), 2),
    "physics_time_ms": round(float(np.mean(physics_times[5:]) * 1000), 2),
    "kinematics_time_ms": round(float(np.mean(nav_times[5:]) * 1000), 2),
    **get_gpu_info(),
    **get_sys_info(),
}
print(f"  -> FPS: {fps:.1f} | Frame Time: {np.mean(dt_arr)*1000:.2f} ms (Physics: {np.mean(physics_times[5:])*1000:.2f}ms, Nav: {np.mean(nav_times[5:])*1000:.2f}ms)")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 5: Robot with Camera Enabled
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BENCHMARK] Stage 5: Robot with Camera Enabled...")
camera_mgr = CameraSensorManager(stage=world.stage, resolution=(640, 360))
camera_mgr.register_robot_camera("Arogya_Delivery", robot1.prim_path)
camera_mgr.select_robot("Arogya_Delivery")

times = []
camera_times = []
for _ in range(35):
    t0 = time.perf_counter()
    world.step(render=True)
    robot1.step_autonomous(dt=0.016)
    t_c0 = time.perf_counter()
    camera_mgr.update_all(fleet)
    frame_bytes = camera_mgr.capture_frame()
    t_c = time.perf_counter() - t_c0

    times.append(time.perf_counter() - t0)
    camera_times.append(t_c)

dt_arr = times[5:]
fps = 1.0 / np.mean(dt_arr)
results["Stage 5: Robot with Camera"] = {
    "fps": round(fps, 1),
    "frame_time_ms": round(float(np.mean(dt_arr) * 1000), 2),
    "camera_time_ms": round(float(np.mean(camera_times[5:]) * 1000), 2),
    **get_gpu_info(),
    **get_sys_info(),
}
print(f"  -> FPS: {fps:.1f} | Frame Time: {np.mean(dt_arr)*1000:.2f} ms (Camera: {np.mean(camera_times[5:])*1000:.2f}ms)")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 6: Robot with LiDAR Enabled
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BENCHMARK] Stage 6: Robot with LiDAR Enabled...")
lidar_mgr = LiDARSensorManager()
lidar_mgr.register_robot_lidar("Arogya_Delivery")
lidar_mgr.select_robot("Arogya_Delivery")

times = []
lidar_times = []
for _ in range(35):
    t0 = time.perf_counter()
    world.step(render=False)
    robot1.step_autonomous(dt=0.016)
    t_l0 = time.perf_counter()
    scan = lidar_mgr.sensors["Arogya_Delivery"].scan(
        robot_x=robot1.x, robot_y=robot1.y, robot_yaw=robot1.yaw,
        collision_guard=collision_guard
    )
    t_l = time.perf_counter() - t_l0

    times.append(time.perf_counter() - t0)
    lidar_times.append(t_l)

dt_arr = times[5:]
fps = 1.0 / np.mean(dt_arr)
results["Stage 6: Robot with LiDAR"] = {
    "fps": round(fps, 1),
    "frame_time_ms": round(float(np.mean(dt_arr) * 1000), 2),
    "lidar_time_ms": round(float(np.mean(lidar_times[5:]) * 1000), 2),
    **get_gpu_info(),
    **get_sys_info(),
}
print(f"  -> FPS: {fps:.1f} | Frame Time: {np.mean(dt_arr)*1000:.2f} ms (LiDAR: {np.mean(lidar_times[5:])*1000:.2f}ms)")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 7: ROS2 Integration Enabled
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BENCHMARK] Stage 7: ROS2 Integration Enabled...")
ros2_bridge = IsaacSimROS2Bridge(fleet, publish_rate_hz=10.0)

times = []
ros2_times = []
for i in range(35):
    t0 = time.perf_counter()
    world.step(render=False)
    robot1.step_autonomous(dt=0.016)
    t_r0 = time.perf_counter()
    ros2_bridge.step(current_sim_time=i * 0.016)
    t_r = time.perf_counter() - t_r0

    times.append(time.perf_counter() - t0)
    ros2_times.append(t_r)

dt_arr = times[5:]
fps = 1.0 / np.mean(dt_arr)
results["Stage 7: ROS2 Integration"] = {
    "fps": round(fps, 1),
    "frame_time_ms": round(float(np.mean(dt_arr) * 1000), 2),
    "ros2_overhead_ms": round(float(np.mean(ros2_times[5:]) * 1000), 2),
    **get_gpu_info(),
    **get_sys_info(),
}
print(f"  -> FPS: {fps:.1f} | Frame Time: {np.mean(dt_arr)*1000:.2f} ms (ROS2: {np.mean(ros2_times[5:])*1000:.2f}ms)")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 8: SLAM Enabled
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BENCHMARK] Stage 8: SLAM Enabled...")
times = []
slam_times = []
for i in range(35):
    t0 = time.perf_counter()
    world.step(render=False)
    robot1.step_autonomous(dt=0.016)
    scan = lidar_mgr.sensors["Arogya_Delivery"].scan(
        robot_x=robot1.x, robot_y=robot1.y, robot_yaw=robot1.yaw,
        collision_guard=collision_guard
    )
    t_s0 = time.perf_counter()
    SLAM_ENGINE.integrate_lidar_scan(robot1.x, robot1.y, robot1.yaw, scan)
    t_s = time.perf_counter() - t_s0

    times.append(time.perf_counter() - t0)
    slam_times.append(t_s)

dt_arr = times[5:]
fps = 1.0 / np.mean(dt_arr)
results["Stage 8: SLAM Enabled"] = {
    "fps": round(fps, 1),
    "frame_time_ms": round(float(np.mean(dt_arr) * 1000), 2),
    "slam_time_ms": round(float(np.mean(slam_times[5:]) * 1000), 2),
    **get_gpu_info(),
    **get_sys_info(),
}
print(f"  -> FPS: {fps:.1f} | Frame Time: {np.mean(dt_arr)*1000:.2f} ms (SLAM: {np.mean(slam_times[5:])*1000:.2f}ms)")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 9: Full AAROGYA Application (Combined Fleet, Sensors, ROS2, SLAM, HUD)
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BENCHMARK] Stage 9: Full AAROGYA Application Pipeline...")
times = []
for i in range(35):
    t0 = time.perf_counter()
    world.step(render=True)
    robot1.step_autonomous(dt=0.016)
    scan = lidar_mgr.sensors["Arogya_Delivery"].scan(
        robot_x=robot1.x, robot_y=robot1.y, robot_yaw=robot1.yaw,
        collision_guard=collision_guard
    )
    camera_mgr.update_all(fleet)
    ros2_bridge.step(current_sim_time=i * 0.016)
    SLAM_ENGINE.integrate_lidar_scan(robot1.x, robot1.y, robot1.yaw, scan)
    times.append(time.perf_counter() - t0)

dt_arr = times[5:]
fps = 1.0 / np.mean(dt_arr)
results["Stage 9: Full Application"] = {
    "fps": round(fps, 1),
    "frame_time_ms": round(float(np.mean(dt_arr) * 1000), 2),
    **get_gpu_info(),
    **get_sys_info(),
}
print(f"  -> FPS: {fps:.1f} | Frame Time: {np.mean(dt_arr)*1000:.2f} ms")

# Save baseline report to JSON
out_path = os.path.join(repo_root, "diagnostics", "phase1_baseline_profile.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print("\n" + "=" * 80)
print("  PHASE 1 BASELINE PROFILING COMPLETE")
print("  Saved to:", out_path)
print("=" * 80)
for k, v in results.items():
    print(f"  * {k:<34} : FPS={v['fps']:>5.1f} | Frame={v['frame_time_ms']:>6.1f}ms | GPU={v.get('gpu_util_pct', 0)}% | VRAM={v.get('gpu_vram_used_mb', 0)}MB | CPU={v.get('cpu_util_pct', 0)}%")

simulation_app.close()

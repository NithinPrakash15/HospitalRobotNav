"""
Diagnostic Profiler: Identify Exact Frame-Time Bottleneck in Isaac Sim
======================================================================
Tests execution time of:
1. world.step(render=True) baseline
2. world.step(render=True) + rep.create.render_product
3. rep.orchestrator.step() vs no rep.orchestrator.step()
4. JPEG compression on main thread vs background thread
5. dynamic_obstacles.step()
6. AMRLiDARSensor.scan()
"""

import time
import os
import sys
import io
import numpy as np
from PIL import Image

from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": True})

_SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
_BASE_DIR = os.path.abspath(os.path.dirname(_SCRIPT_DIR))
_ROOT_DIR = os.path.abspath(os.path.dirname(_BASE_DIR))
sys.path.insert(0, _ROOT_DIR)
sys.path.insert(0, _BASE_DIR)
print(f"[DEBUG PATH] BASE: {_BASE_DIR} | ROOT: {_ROOT_DIR}")

import omni.usd
from pxr import Gf, Sdf, UsdGeom
import omni.replicator.core as rep

from omni.isaac.core import World
from environments.hospital_env import HospitalEnvironment
from environments.dynamic_obstacles import DynamicObstacleManager
from sensors.lidar_manager import AMRLiDARSensor

world = World(stage_units_in_meters=1.0)
env = HospitalEnvironment(wall_height=1.30, wall_thickness=0.22, door_width=2.0)
env.build_all()
collision_guard = env.get_collision_guard(robot_radius=0.38)
dynamic_obstacles = DynamicObstacleManager(traffic_mode="normal")

# Create test camera
stage = world.stage
cam_prim = UsdGeom.Camera.Define(stage, Sdf.Path("/World/TestCamera"))
cam_prim.GetFocalLengthAttr().Set(24.0)

world.reset()

print("\n" + "=" * 70)
print("PHASE 1: MEASURING BASELINE WORLD.STEP(RENDER=TRUE)")
print("=" * 70)

# Warmup 10 steps
for _ in range(10):
    world.step(render=True)

times_base = []
for _ in range(30):
    t0 = time.perf_counter()
    world.step(render=True)
    times_base.append((time.perf_counter() - t0) * 1000.0)

print(f"Baseline world.step(render=True): avg = {np.mean(times_base):.2f} ms, max = {np.max(times_base):.2f} ms")

print("\n" + "=" * 70)
print("PHASE 2: ATTACHING REPLICATOR RENDER PRODUCT (480x270)")
print("=" * 70)

rp = rep.create.render_product("/World/TestCamera", (480, 270))
rgb_ann = rep.AnnotatorRegistry.get_annotator("rgb")
rgb_ann.attach(rp)

# Warmup 5 steps
for _ in range(5):
    world.step(render=True)

times_with_rp = []
for _ in range(30):
    t0 = time.perf_counter()
    world.step(render=True)
    times_with_rp.append((time.perf_counter() - t0) * 1000.0)

print(f"world.step(render=True) WITH RenderProduct: avg = {np.mean(times_with_rp):.2f} ms, max = {np.max(times_with_rp):.2f} ms")

print("\n" + "=" * 70)
print("PHASE 3: CALLING REP.ORCHESTRATOR.STEP() IN ADDITION")
print("=" * 70)

times_orch = []
for _ in range(30):
    t0 = time.perf_counter()
    rep.orchestrator.step()
    times_orch.append((time.perf_counter() - t0) * 1000.0)

print(f"rep.orchestrator.step() alone: avg = {np.mean(times_orch):.2f} ms, max = {np.max(times_orch):.2f} ms")

print("\n" + "=" * 70)
print("PHASE 4: CHECK IF RGB_ANN HAS DATA WITHOUT REP.ORCHESTRATOR.STEP()")
print("=" * 70)

world.step(render=True)
data_direct = rgb_ann.get_data()
has_direct = data_direct is not None and getattr(data_direct, "size", 0) > 0
print(f"rgb_ann.get_data() after world.step(render=True): shape = {getattr(data_direct, 'shape', None)}, valid = {has_direct}")

print("\n" + "=" * 70)
print("PHASE 5: JPEG ENCODING OVERHEAD")
print("=" * 70)

dummy_rgb = np.zeros((270, 480, 3), dtype=np.uint8)
times_jpeg = []
for _ in range(30):
    t0 = time.perf_counter()
    img = Image.fromarray(dummy_rgb)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75)
    _ = buf.getvalue()
    times_jpeg.append((time.perf_counter() - t0) * 1000.0)

print(f"PIL JPEG compression (480x270, Q=75): avg = {np.mean(times_jpeg):.2f} ms, max = {np.max(times_jpeg):.2f} ms")

print("\n" + "=" * 70)
print("PHASE 6: DYNAMIC OBSTACLE STEP (8 AGENTS)")
print("=" * 70)

times_dyn = []
for _ in range(30):
    t0 = time.perf_counter()
    dynamic_obstacles.step(dt=0.016, collision_guard=collision_guard)
    times_dyn.append((time.perf_counter() - t0) * 1000.0)

print(f"dynamic_obstacles.step(8 agents): avg = {np.mean(times_dyn):.2f} ms, max = {np.max(times_dyn):.2f} ms")

print("\n" + "=" * 70)
print("PHASE 7: LIDAR 180-BEAM RAYCAST SCAN")
print("=" * 70)

lidar = AMRLiDARSensor(robot_name="Arogya_Delivery", num_beams=180)
dyn_positions = dynamic_obstacles.get_obstacle_positions()
times_lidar = []
for _ in range(30):
    t0 = time.perf_counter()
    _ = lidar.scan(
        robot_x=34.5,
        robot_y=33.0,
        robot_yaw=0.0,
        collision_guard=collision_guard,
        dynamic_obstacles=dyn_positions,
    )
    times_lidar.append((time.perf_counter() - t0) * 1000.0)

print(f"AMRLiDARSensor.scan(180 beams): avg = {np.mean(times_lidar):.2f} ms, max = {np.max(times_lidar):.2f} ms")

print("\n" + "=" * 70)
print("SUMMARY OF TIMING MEASUREMENTS")
print("=" * 70)

simulation_app.close()

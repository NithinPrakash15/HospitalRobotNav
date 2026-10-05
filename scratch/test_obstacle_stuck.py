import sys
import os
import numpy as np

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from isaac_sim_hospital.environments.hospital_env import HospitalEnvironment
from isaac_sim_hospital.environments.dynamic_obstacles import DynamicObstacleManager

env = HospitalEnvironment(wall_height=1.30, wall_thickness=0.22, door_width=2.0)
env.build_all()
guard = env.get_collision_guard(robot_radius=0.38)

manager = DynamicObstacleManager(traffic_mode="normal", random_seed=42)

print(f"\n[DIAGNOSTIC] Total Agents: {len(manager.agents)}")
for idx, agent in enumerate(manager.agents):
    print(f"\n--- Agent {idx+1}: {agent.name} (Role: {agent.role}, Prim: {agent.prim_path}) ---")
    print(f"  Initial Pos: ({agent.x:.2f}, {agent.y:.2f}), Yaw: {np.degrees(agent.yaw):.1f}°")
    print(f"  Waypoints: {agent.waypoints}")
    print(f"  Current WP Idx: {agent.current_wp_idx} -> Target: {agent.waypoints[agent.current_wp_idx]}")
    
    # Check if initial position collides with collision guard
    collides = guard.check_point_collision(agent.x, agent.y, margin=0.35)
    print(f"  Collides with wall at start? {collides}")

print("\n[DIAGNOSTIC] Simulating 120 steps (approx 2 seconds of sim)...")
stuck_counters = {agent.name: 0 for agent in manager.agents}
rotation_accum = {agent.name: 0.0 for agent in manager.agents}
last_yaws = {agent.name: agent.yaw for agent in manager.agents}
positions_history = {agent.name: [] for agent in manager.agents}

for step in range(300):
    for agent in manager.agents:
        prev_x, prev_y = agent.x, agent.y
        prev_yaw = agent.yaw
        agent.step(dt=0.016, collision_guard=guard)
        
        move_dist = np.hypot(agent.x - prev_x, agent.y - prev_y)
        dyaw = abs((agent.yaw - prev_yaw + np.pi) % (2.0 * np.pi) - np.pi)
        rotation_accum[agent.name] += dyaw
        
        if move_dist < 0.001:
            stuck_counters[agent.name] += 1
        positions_history[agent.name].append((agent.x, agent.y))

print("\n--- SUMMARY OF OBSTACLE MOBILITY OVER 300 STEPS ---")
for agent in manager.agents:
    hist = np.array(positions_history[agent.name])
    total_disp = np.hypot(hist[-1, 0] - hist[0, 0], hist[-1, 1] - hist[0, 1])
    bbox_x = hist[:, 0].max() - hist[:, 0].min()
    bbox_y = hist[:, 1].max() - hist[:, 1].min()
    print(f"Agent: {agent.name:<35} | Stuck steps: {stuck_counters[agent.name]:3d}/300 | Total Rot: {np.degrees(rotation_accum[agent.name]):6.1f}° | Travel Box: ({bbox_x:.2f}m x {bbox_y:.2f}m) | Cur WP: {agent.current_wp_idx}")

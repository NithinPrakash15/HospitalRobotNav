import sys
import os

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from isaac_sim_hospital.environments.hospital_env import HospitalEnvironment

env = HospitalEnvironment()
env.build_all()

# Find all collision boxes near X=14.0, Y between 0 and 35
print("Collision boxes near East Corridor (X ~ 14.0):")
for b in env.collision_boxes:
    min_x, min_y, max_x, max_y = b
    if min_x <= 16.0 and max_x >= 12.0 and min_y <= 35.0 and max_y >= 0.0:
        print(f"  Box: X[{min_x:.2f}, {max_x:.2f}] Y[{min_y:.2f}, {max_y:.2f}] (width={max_x-min_x:.2f}, height={max_y-min_y:.2f})")

# Check collision check for Paramedic_Stretcher1 at X=14.3
guard = env.get_collision_guard(0.38)
for y_test in [4.0, 5.0, 5.89, 10.0, 14.0, 18.0, 20.0, 25.0, 30.0, 32.0]:
    for x_test in [13.0, 13.5, 14.0, 14.3, 14.5, 15.0]:
        c = guard.check_point_collision(x_test, y_test, margin=0.40)
        print(f"Pos ({x_test:.1f}, {y_test:.1f}) collides (margin=0.40)? {c}")

#!/usr/bin/env bash
# Diagnostic for the hospital_robot_nav_core shim.
set -u
ROOT="/mnt/c/Users/nithi/OneDrive/Desktop/Main Project for vs/HospitalRobotNav"
WS="$ROOT/hospital_robot_nav_ws"

echo "=== main.py presence ==="
ls -la "$ROOT/main.py" 2>&1 | head -3

echo ""
echo "=== module file location ==="
ls -la "$WS/src/hospital_robot_nav_core/hospital_robot_nav_core/__init__.py"

echo ""
echo "=== python diagnostic ==="
cd "$WS"
echo "PYTHONPATH = $WS/src/hospital_robot_nav_core"
PYTHONPATH="$WS/src/hospital_robot_nav_core" python3 - <<'PYEOF'
import sys
import hospital_robot_nav_core as core
print("__file__:", core.__file__)
print("has _PROJECT_ROOT:", "_PROJECT_ROOT" in core.__dict__)
print("has _SUBMODULES:", "_SUBMODULES" in core.__dict__)
print("PROJECT_ROOT:", core.__dict__.get("_PROJECT_ROOT"))
print("submodules:", list(core.__dict__.get("_SUBMODULES", ())))
print("all keys:", [k for k in core.__dict__ if not k.startswith("__")][:40])
PYEOF


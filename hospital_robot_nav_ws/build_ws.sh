#!/usr/bin/env bash
# Build the HospitalRobotNav ROS 2 workspace (run inside WSL).
# Note: NO `set -u` — ROS /opt/ros/jazzy/setup.bash references unset vars.

WS="/mnt/c/Users/nithi/OneDrive/Desktop/Main Project for vs/HospitalRobotNav/hospital_robot_nav_ws"

source /opt/ros/jazzy/setup.bash

cd "$WS" || { echo "Cannot cd to $WS"; exit 1; }

echo "=== Removing stale build/install/log ==="
rm -rf build install log

echo "=== colcon build --symlink-install ==="
colcon build --symlink-install
BUILD_RC=$?

if [ $BUILD_RC -ne 0 ]; then
  echo ""
  echo "=== BUILD FAILED (rc=$BUILD_RC) — see log/latest_build for details ==="
  exit $BUILD_RC
fi

echo ""
echo "=== Build OK. Sourcing install/setup.bash ==="
source install/setup.bash

echo ""
echo "=== Available packages ==="
colcon list --names-only

echo ""
echo "=== Node executables in hospital_robot_nav_nodes ==="
ls install/hospital_robot_nav_nodes/lib/hospital_robot_nav_nodes/ 2>/dev/null

echo ""
echo "=== Verify interfaces build ==="
ros2 interface show hospital_robot_nav_msgs/msg/MissionRequest >/dev/null 2>&1 \
  && echo "MissionRequest msg OK" \
  || echo "MissionRequest msg NOT FOUND"

echo ""
echo "=== BUILD COMPLETE ==="
echo "Run the full hospital system with:"
echo "  ros2 launch hospital_robot_nav_bringup hospital_robot.launch.py"


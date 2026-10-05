#!/usr/bin/env bash
# Diagnostic: verify ROS2 install layout, executables, and single-node launch.
set +u
source /opt/ros/jazzy/setup.bash

WS="/mnt/c/Users/nithi/OneDrive/Desktop/Main Project for vs/HospitalRobotNav/hospital_robot_nav_ws"
source "$WS/install/setup.bash"

echo "=== ROS_DISTRO ==="
echo "$ROS_DISTRO"

echo "=== executables installed (hospital_robot_nav_nodes) ==="
ls -la "$WS/install/hospital_robot_nav_nodes/lib/hospital_robot_nav_nodes/" 2>&1

echo "=== bringup share config dir ==="
ls -la "$WS/install/hospital_robot_nav_bringup/share/hospital_robot_nav_bringup/config/" 2>&1

echo "=== bringup share launch dir ==="
ls -la "$WS/install/hospital_robot_nav_bringup/share/hospital_robot_nav_bringup/launch/" 2>&1

echo "=== amos: try launching audio_capture_node directly (2s timeout) ==="
timeout 5 ros2 run hospital_robot_nav_nodes audio_capture_node --ros-args --params-file "$WS/install/hospital_robot_nav_bringup/share/hospital_robot_nav_bringup/config/audio_params.yaml" 2>&1 | head -40
echo "EXIT_CODE=$?"

echo "=== ros2 pkg prefix ==="
ros2 pkg prefix hospital_robot_nav_nodes 2>&1
echo "=== ros2 pkg executables ==="
ros2 pkg executables hospital_robot_nav_nodes 2>&1 | head -30

echo "DIAG COMPLETE"


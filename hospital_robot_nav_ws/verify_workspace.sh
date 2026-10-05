#!/usr/bin/env bash
# Verify the built ROS 2 workspace: packages, interfaces, nodes, executables.
# Note: NO `set -u` — ROS setup.bash references unset variables.

WS="/mnt/c/Users/nithi/OneDrive/Desktop/Main Project for vs/HospitalRobotNav/hospital_robot_nav_ws"
source /opt/ros/jazzy/setup.bash
source "$WS/install/setup.bash"

echo "=== 1. Available packages ==="
colcon list --names-only 2>/dev/null || (cd "$WS" && colcon list --names-only)

echo ""
echo "=== 2. Node executables ==="
ls "$WS/install/hospital_robot_nav_nodes/lib/hospital_robot_nav_nodes/" 2>/dev/null

echo ""
echo "=== 3. Interface verification ==="
for iface in \
  hospital_robot_nav_msgs/msg/GridPos \
  hospital_robot_nav_msgs/msg/MissionRequest \
  hospital_robot_nav_msgs/msg/MissionPlan \
  hospital_robot_nav_msgs/msg/AgentStatus \
  hospital_robot_nav_msgs/msg/SpeechAnalysis \
  hospital_robot_nav_msgs/srv/ResolveDestination \
  hospital_robot_nav_msgs/srv/PlanPath \
  hospital_robot_nav_msgs/action/ExecuteMission ; do
  if ros2 interface show "$iface" >/dev/null 2>&1; then
    echo "  OK  $iface"
  else
    echo "  MISSING  $iface"
  fi
done

echo ""
echo "=== 4. Launchable files ==="
ls "$WS/install/hospital_robot_nav_bringup/share/hospital_robot_nav_bringup/launch/" 2>/dev/null

echo ""
echo "=== 5. ros2 pkg prefixes ==="
ros2 pkg prefix hospital_robot_nav_msgs 2>/dev/null || echo "  (pkg not found on PATH)"
ros2 pkg prefix hospital_robot_nav_nodes 2>/dev/null || echo "  (pkg not found on PATH)"
ros2 pkg prefix hospital_robot_nav_bringup 2>/dev/null || echo "  (pkg not found on PATH)"

echo ""
echo "=== WORKSPACE VERIFICATION COMPLETE ==="


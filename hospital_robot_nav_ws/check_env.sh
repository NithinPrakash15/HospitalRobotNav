#!/usr/bin/env bash
# Quick environment check for running the ROS 2 workspace under WSL.
set -u

echo "=== ROS 2 ==="
if [ -f /opt/ros/jazzy/setup.bash ]; then
  source /opt/ros/jazzy/setup.bash >/dev/null 2>&1
  echo "ROS_DISTRO=${ROS_DISTRO:-<unset>}"
  ros2 --help >/dev/null 2>&1 && echo "ros2 CLI OK" || echo "ros2 CLI FAILED"
else
  echo "Jazzy NOT installed at /opt/ros/jazzy"
fi

echo ""
echo "=== Python deps (core) ==="
for mod in numpy networkx scipy pygame; do
  if python3 -c "import $mod" 2>/dev/null; then
    echo "  $mod OK"
  else
    echo "  $mod MISSING"
  fi
done

echo ""
echo "=== colcon ==="
command -v colcon >/dev/null 2>&1 && echo "colcon OK" || echo "colcon MISSING"

echo ""
echo "=== Workspace check ==="
WS="/mnt/c/Users/nithi/OneDrive/Desktop/Main Project for vs/HospitalRobotNav/hospital_robot_nav_ws"
ls "$WS/src" >/dev/null 2>&1 && echo "src dir OK: $(ls "$WS/src")" || echo "cannot read workspace src"

echo ""
echo "Done."


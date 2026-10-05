#!/usr/bin/env bash
# Diagnostic: launch the full speech pipeline, wait, list nodes, then dump the log.
set +u
export AMENT_TRACE_SETUP_FILES="${AMENT_TRACE_SETUP_FILES:-}"
export AMENT_PYTHON_EXECUTABLE="${AMENT_PYTHON_EXECUTABLE:-$(command -v python3)}"
source /opt/ros/jazzy/setup.bash

WS="/mnt/c/Users/nithi/OneDrive/Desktop/Main Project for vs/HospitalRobotNav/hospital_robot_nav_ws"
source "$WS/install/setup.bash"

LOG=/tmp/diag_launch.log
rm -f "$LOG"

echo "Starting launch..."
ros2 launch hospital_robot_nav_bringup speech_pipeline.launch.py text_mode:=true > "$LOG" 2>&1 &
LPID=$!
echo "Launch PID: $LPID"
sleep 15

echo ""
echo "=== ros2 node list (after 15s) ==="
ros2 node list 2>&1 | sort

echo ""
echo "=== launch log (head 60) ==="
head -60 "$LOG"

echo ""
echo "=== launch log (tail 40) ==="
tail -40 "$LOG"

echo ""
echo "=== shutting down ==="
kill "$LPID" 2>/dev/null || true
pkill -f speech_pipeline.launch 2>/dev/null || true
pkill -f "hospital_robot_nav_nodes" 2>/dev/null || true
sleep 2
echo "DIAG LAUNCH COMPLETE"


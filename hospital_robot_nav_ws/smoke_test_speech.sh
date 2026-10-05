#!/usr/bin/env bash
# Phase 3 — Speech pipeline smoke test (text-input mode).
# Run inside WSL:
#   bash hospital_robot_nav_ws/smoke_test_speech.sh
# NOTE: avoid `set -u` here — ROS 2 setup.bash / local_setup.sh reference
# AMENT_* variables without defaults and would abort under nounset.
set -e

WS="/mnt/c/Users/nithi/OneDrive/Desktop/Main Project for vs/HospitalRobotNav/hospital_robot_nav_ws"
# ROS 2 setup.bash / local_setup.sh reference several AMENT_* variables without
# defaults, which trips bash's nounset.  Pre-seed them (and do not use set -u).
export AMENT_TRACE_SETUP_FILES="${AMENT_TRACE_SETUP_FILES:-}"
export AMENT_PYTHON_EXECUTABLE="${AMENT_PYTHON_EXECUTABLE:-$(command -v python3)}"
source /opt/ros/jazzy/setup.bash
source "$WS/install/setup.bash"

PIPE_LOG=/tmp/smoke_pipeline.log
ANALYSIS_OUT=/tmp/smoke_analysis_out.txt
SAY_OUT=/tmp/smoke_say_out.txt

echo "=== [1/6] Launching speech pipeline (text mode) ==="
ros2 launch hospital_robot_nav_bringup speech_pipeline.launch.py > "$PIPE_LOG" 2>&1 &
LAUNCH_PID=$!
echo "Launch PID: $LAUNCH_PID"

sleep 12   # allow all 7 nodes to spin up

echo ""
echo "=== [2/6] Running node list ==="
ros2 node list 2>&1 | sort

echo ""
echo "=== [3/6] Subscribing to /robot/speech_analysis (background) ==="
timeout 20 ros2 topic echo /robot/speech_analysis > "$ANALYSIS_OUT" 2>&1 &
ECHO_ANALYSIS_PID=$!

timeout 20 ros2 topic echo /robot/say > "$SAY_OUT" 2>&1 &
ECHO_SAY_PID=$!

sleep 3   # let subscribers connect

echo ""
echo "=== [4/6] Publishing test command to /speech/text_input ==="
ros2 topic pub -1 /speech/text_input std_msgs/msg/String \
  "{data: 'take paracetamol to room 204'}" 2>&1
ros2 topic pub -1 /speech/text_input std_msgs/msg/String \
  "{data: 'navigate to the pharmacy'}" 2>&1

echo ""
echo "=== [5/6] Waiting for pipeline output ==="
wait "$ECHO_ANALYSIS_PID" 2>/dev/null || true
wait "$ECHO_SAY_PID" 2>/dev/null || true

echo "----- /robot/speech_analysis -----"
cat "$ANALYSIS_OUT"
echo "----- /robot/say -----"
cat "$SAY_OUT"

echo ""
echo "=== [6/6] Shutting down launch ==="
kill "$LAUNCH_PID" 2>/dev/null || true
sleep 2
pkill -f speech_pipeline.launch 2>/dev/null || true
pkill -f "speech_analysis_node" 2>/dev/null || true

echo ""
echo "===== Pipeline launch log (tail) ====="
tail -30 "$PIPE_LOG"
echo ""
echo "SMOKE TEST COMPLETE"


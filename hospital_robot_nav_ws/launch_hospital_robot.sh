#!/usr/bin/env bash
# Launch the full hospital robot system (ROS 2 Jazzy) inside WSL.
# Usage (from WSL or via PowerShell wrapper):
#   bash launch_hospital_robot.sh
#   bash launch_hospital_robot.sh speech   # launch only the speech pipeline
# NOTE: No `set -u` here — ROS setup.bash references unset variables
#       (e.g. AMENT_TRACE_SETUP_FILES) and would abort under `set -u`.

WS="/mnt/c/Users/nithi/OneDrive/Desktop/Main Project for vs/HospitalRobotNav/hospital_robot_nav_ws"

source /opt/ros/jazzy/setup.bash
source "$WS/install/setup.bash"

MODE="${1:-full}"

if [ "$MODE" = "speech" ]; then
    echo "=== Launching SPEECH PIPELINE only ==="
    exec ros2 launch hospital_robot_nav_bringup speech_pipeline.launch.py
else
    echo "=== Launching FULL HOSPITAL ROBOT SYSTEM ==="
    echo "  (Ctrl-C to stop)"
    exec ros2 launch hospital_robot_nav_bringup hospital_robot.launch.py
fi


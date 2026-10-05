#!/usr/bin/env bash
# Retry wrapper for setup_ros2.sh — keeps retrying the apt install step
# on transient network failures (packages.ros.org is flaky from this network).
set -u

SCRIPT="/mnt/c/Users/nithi/OneDrive/Desktop/Main Project for vs/HospitalRobotNav/setup_ros2.sh"
MAX_ATTEMPTS=8
attempt=1

while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  echo ""
  echo "################################################################"
  echo "# Attempt $attempt / $MAX_ATTEMPTS"
  echo "################################################################"
  if bash "$SCRIPT" 2>&1 | tee "/tmp/setup_ros2_attempt_${attempt}.log"; then
    if ros2 --help >/dev/null 2>&1 || [ -f /opt/ros/jazzy/setup.bash ]; then
      echo ""
      echo "=== ROS 2 Jazzy install SUCCEEDED on attempt $attempt ==="
      exit 0
    fi
  fi

  # Check if the failure is a network error vs a real package error
  LOG="/tmp/setup_ros2_attempt_${attempt}.log"
  if grep -qiE "Failed to fetch|Connection timed out|Could not connect|Network is unreachable|Temporary failure resolving" "$LOG"; then
    echo ""
    echo ">>> Network-related failure detected. Will retry..."
  else
    echo ""
    echo ">>> Non-network failure — aborting instead of blind retry."
    break
  fi

  attempt=$((attempt + 1))
  if [ "$attempt" -le "$MAX_ATTEMPTS" ]; then
    echo "Waiting 10s before next attempt..."
    sleep 10
  fi
done

echo ""
echo "=== setup_ros2.sh exhausted $((attempt - 1)) attempts. Manual intervention needed. ==="
exit 1


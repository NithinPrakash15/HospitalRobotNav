#!/usr/bin/env bash
# Find all get_logger() calls that use printf-style format strings (the bug).
NODES_DIR="/mnt/c/Users/nithi/OneDrive/Desktop/Main Project for vs/HospitalRobotNav/hospital_robot_nav_ws/src/hospital_robot_nav_nodes/hospital_robot_nav_nodes"
OUT="/tmp/find_logs.txt"
rm -f "$OUT"
grep -rn 'get_logger()' "$NODES_DIR" > "$OUT"
echo "----- files with get_logger -----"
cat "$OUT"
echo ""
echo "----- lines with % format placeholders (suspects) -----"
grep -rn 'get_logger()' "$NODES_DIR" | grep '%' || echo "no % placeholders found"


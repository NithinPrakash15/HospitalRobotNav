#!/usr/bin/env bash
# HospitalRobotNav — ROS 2 Jazzy installation helper (Ubuntu 24.04 / WSL2)
# Run inside WSL:  bash setup_ros2.sh
set -e

echo "=== [0/5] Network hardening for packages.ros.org ==="
# WSL sometimes has no IPv6 route; force IPv4 + generous timeouts/retries.
sudo tee /etc/apt/apt.conf.d/99ros-network-hardening > /dev/null <<'EOF'
Acquire::ForceIPv4 "true";
Acquire::http::Timeout "15";
Acquire::http::Retries "5";
Acquire::Retries "5";
EOF
echo "apt hardened: ForceIPv4 + 5 retries + 15s timeout"
echo ""

echo "=== [1/5] Adding ROS 2 apt repository key ==="
sudo curl -4 -sSL --retry 5 --retry-delay 2 https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg

echo "=== [1/5] Adding ROS 2 apt source list ==="
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

echo "=== ROS 2 repository configured ==="
cat /etc/apt/sources.list.d/ros2.list

echo ""
echo "=== [2/5] Updating apt with ROS 2 repository ==="
sudo apt update

echo ""
echo "=== [3/5] Installing ROS 2 Jazzy (desktop) + build tools ==="
echo "This step downloads ~1.5 GB and may take 5–15 minutes..."
sudo apt install -y -o Acquire::Retries=5 -o Acquire::http::Timeout=30 \
    ros-jazzy-desktop python3-colcon-common-extensions python3-rosdep ros-dev-tools

echo ""
echo "=== [4/5] Sourcing ROS 2 in .bashrc ==="
if ! grep -q "/opt/ros/jazzy/setup.bash" ~/.bashrc; then
  echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
  echo "Added 'source /opt/ros/jazzy/setup.bash' to ~/.bashrc"
else
  echo "ROS 2 source already present in ~/.bashrc"
fi

echo ""
echo "=== [5/5] Verifying ROS 2 installation ==="
source /opt/ros/jazzy/setup.bash
ros2 --help >/dev/null 2>&1 && echo "ros2 CLI OK" || echo "ros2 CLI NOT FOUND"
printenv ROS_DISTRO 2>/dev/null | sed 's/^/ROS_DISTRO=/' || echo "ROS_DISTRO not set"
ros2 pkg list 2>/dev/null | head -5

echo ""
echo "======================================================"
echo "  ROS 2 Jazzy installation COMPLETE! 🎉"
echo "  Next steps:"
echo "    source /opt/ros/jazzy/setup.bash"
echo "    cd /mnt/c/Users/nithi/OneDrive/Desktop/Main Project for vs/HospitalRobotNav/hospital_robot_nav_ws"
echo "    colcon build --symlink-install"
echo "======================================================"


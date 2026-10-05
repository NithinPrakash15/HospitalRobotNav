"""Launch robot_state_publisher with the Arogya hospital robot URDF."""

import os
from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description() -> LaunchDescription:
    pkg_dir = get_package_share_directory("hospital_robot_nav_description")
    urdf_file = os.path.join(pkg_dir, "urdf", "arogya_robot.urdf.xacro")

    # Read URDF (xacro → raw XML if xacro is available, else just read)
    try:
        import xacro
        robot_description = xacro.process_file(urdf_file).toxml()
    except Exception:
        with open(urdf_file, "r") as f:
            robot_description = f.read()

    return LaunchDescription([
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            name="robot_state_publisher",
            output="screen",
            parameters=[{"robot_description": robot_description}],
        ),
        Node(
            package="joint_state_publisher",
            executable="joint_state_publisher",
            name="joint_state_publisher",
            output="screen",
        ),
    ])

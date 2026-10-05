"""Launch the core AAROGYA ROS 2 robotics system.

This launches the autonomous hospital robot navigation, semantic map,
planners, mission executor, fleet coordinator, obstacle tracker,
robot controller, and robot state publisher / RViz visualization.
"""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description() -> LaunchDescription:
    pkg_dir = get_package_share_directory("hospital_robot_nav_bringup")

    declare_rviz = DeclareLaunchArgument(
        "rviz", default_value="false",
        description="Launch RViz2 with pre-configured 3D hospital robot visualization.",
    )

    # Core Navigation & Mission nodes
    semantic_map_node = Node(
        package="hospital_robot_nav_nodes",
        executable="semantic_map_node",
        name="semantic_map_node",
        output="screen",
    )

    planner_node = Node(
        package="hospital_robot_nav_nodes",
        executable="planner_node",
        name="planner_node",
        output="screen",
        parameters=[
            os.path.join(pkg_dir, "config", "planner_params.yaml"),
        ],
    )

    obstacle_tracker_node = Node(
        package="hospital_robot_nav_nodes",
        executable="obstacle_tracker_node",
        name="obstacle_tracker_node",
        output="screen",
        parameters=[
            os.path.join(pkg_dir, "config", "obstacle_params.yaml"),
        ],
    )

    robot_controller_node = Node(
        package="hospital_robot_nav_nodes",
        executable="robot_controller_node",
        name="robot_controller_node",
        output="screen",
        parameters=[
            os.path.join(pkg_dir, "config", "robot_params.yaml"),
        ],
    )

    mission_executor_node = Node(
        package="hospital_robot_nav_nodes",
        executable="mission_executor_node",
        name="mission_executor_node",
        output="screen",
    )

    fleet_coordinator_node = Node(
        package="hospital_robot_nav_nodes",
        executable="fleet_coordinator_node",
        name="fleet_coordinator_node",
        output="screen",
        parameters=[
            os.path.join(pkg_dir, "config", "fleet_params.yaml"),
        ],
    )

    # Robot Description (URDF + TF tree)
    desc_pkg_dir = get_package_share_directory("hospital_robot_nav_description")
    robot_description_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(desc_pkg_dir, "launch", "robot_state_publisher.launch.py")
        ),
    )

    rviz_config_path = os.path.join(pkg_dir, "config", "hospital_robot_3d.rviz")
    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        arguments=["-d", rviz_config_path],
        output="screen",
        condition=IfCondition(LaunchConfiguration("rviz")),
        additional_env={"LIBGL_ALWAYS_SOFTWARE": "1"},
    )

    return LaunchDescription(
        [
            declare_rviz,
            SetEnvironmentVariable("FASTDDS_BUILTIN_TRANSPORTS", "UDPv4"),
            LogInfo(msg="Launching AAROGYA ROS 2 Robotics System..."),
            semantic_map_node,
            planner_node,
            obstacle_tracker_node,
            robot_controller_node,
            mission_executor_node,
            fleet_coordinator_node,
            robot_description_launch,
            rviz_node,
        ]
    )

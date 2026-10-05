"""Launch the complete HospitalRobotNav ROS 2 system.

This launches the full autonomous hospital robot stack:
speech pipeline, NLU/dialogue, semantic map, planners, mission executor,
fleet coordinator, obstacle tracker, robot controller, and optional
headless simulator bridge.
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

    # ── Arguments ──────────────────────────────────────────────────────────
    speech_enabled = LaunchConfiguration("speech", default="true")
    sim_bridge = LaunchConfiguration("sim_bridge", default="false")

    declare_speech = DeclareLaunchArgument(
        "speech", default_value="true",
        description="Enable the full offline speech pipeline (STT/NLU/TTS).",
    )
    declare_sim = DeclareLaunchArgument(
        "sim_bridge", default_value="false",
        description="Also launch the headless legacy simulator bridge.",
    )
    declare_rviz = DeclareLaunchArgument(
        "rviz", default_value="false",
        description="Launch RViz2 with pre-configured 3D hospital robot visualization.",
    )

    # ── Speech pipeline nodes ──────────────────────────────────────────────
    asr_node = Node(
        package="hospital_robot_nav_nodes",
        executable="asr_node",
        name="asr_node",
        output="screen",
        parameters=[
            os.path.join(pkg_dir, "config", "asr_params.yaml"),
        ],
    )

    wake_word_node = Node(
        package="hospital_robot_nav_nodes",
        executable="wake_word_node",
        name="wake_word_node",
        output="screen",
    )

    nlu_node = Node(
        package="hospital_robot_nav_nodes",
        executable="nlu_node",
        name="nlu_node",
        output="screen",
    )

    dialogue_node = Node(
        package="hospital_robot_nav_nodes",
        executable="dialogue_node",
        name="dialogue_node",
        output="screen",
    )

    tts_node = Node(
        package="hospital_robot_nav_nodes",
        executable="tts_node",
        name="tts_node",
        output="screen",
        parameters=[
            os.path.join(pkg_dir, "config", "tts_params.yaml"),
        ],
    )

    speech_analysis_node = Node(
        package="hospital_robot_nav_nodes",
        executable="speech_analysis_node",
        name="speech_analysis_node",
        output="screen",
    )

    audio_capture_node = Node(
        package="hospital_robot_nav_nodes",
        executable="audio_capture_node",
        name="audio_capture_node",
        output="screen",
        parameters=[
            os.path.join(pkg_dir, "config", "audio_params.yaml"),
        ],
    )

    # ── Navigation / mission nodes ─────────────────────────────────────────
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

    sim_bridge_node = Node(
        package="hospital_robot_nav_nodes",
        executable="hospital_sim_node",
        name="hospital_sim_node",
        output="screen",
        condition=IfCondition(LaunchConfiguration("sim_bridge")),
    )

    # ── Robot Description (URDF + TF tree) ─────────────────────────────────
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
        # WSLg/Mesa can reject RViz's indexed OccupancyGrid shader on some
        # GPUs.  Restrict the workaround to RViz; robot nodes keep hardware
        # acceleration where applicable.
        additional_env={"LIBGL_ALWAYS_SOFTWARE": "1"},
    )

    return LaunchDescription(
        [
            declare_speech,
            declare_sim,
            declare_rviz,
            # Avoid Fast DDS shared-memory lock failures under WSL/OneDrive.
            # ROS discovery and topic traffic continue over localhost UDP.
            SetEnvironmentVariable("FASTDDS_BUILTIN_TRANSPORTS", "UDPv4"),
            LogInfo(msg="Launching HospitalRobotNav ROS 2 system..."),
            # Speech pipeline
            audio_capture_node,
            asr_node,
            wake_word_node,
            nlu_node,
            dialogue_node,
            tts_node,
            speech_analysis_node,
            # Navigation & missions
            semantic_map_node,
            planner_node,
            obstacle_tracker_node,
            robot_controller_node,
            mission_executor_node,
            fleet_coordinator_node,
            sim_bridge_node,
            robot_description_launch,
            rviz_node,
        ]
    )


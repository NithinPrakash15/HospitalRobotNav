"""Launch only the offline speech → STT → NLU → dialogue → TTS pipeline.

This is the ideal launch for demonstrating and analysing the full speech
understanding chain.  Echo ``/robot/speech_analysis`` to see each utterance's
transcript, STT confidence, NLU intent, entities, and robot response.
"""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description() -> LaunchDescription:
    pkg_dir = get_package_share_directory("hospital_robot_nav_bringup")

    # Text-input mode (no mic) vs microphone mode
    text_mode = LaunchConfiguration("text_mode", default="true")

    declare_text_mode = DeclareLaunchArgument(
        "text_mode", default_value="true",
        description="Use typed text input instead of a microphone (Vosk optional).",
    )

    audio_node = Node(
        package="hospital_robot_nav_nodes",
        executable="audio_capture_node",
        name="audio_capture_node",
        output="screen",
        parameters=[
            os.path.join(pkg_dir, "config", "audio_params.yaml"),
        ],
    )

    asr_node = Node(
        package="hospital_robot_nav_nodes",
        executable="asr_node",
        name="asr_node",
        output="screen",
        parameters=[
            os.path.join(pkg_dir, "config", "asr_params.yaml"),
        ],
    )

    wake_node = Node(
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

    analysis_node = Node(
        package="hospital_robot_nav_nodes",
        executable="speech_analysis_node",
        name="speech_analysis_node",
        output="screen",
    )

    return LaunchDescription(
        [
            declare_text_mode,
            LogInfo(
                msg="Launching HospitalRobotNav speech pipeline. "
                    "Publish text to /speech/text_input (std_msgs/String) to test, "
                    "or speak the wake word if a microphone is available."
            ),
            audio_node,
            asr_node,
            wake_node,
            nlu_node,
            dialogue_node,
            tts_node,
            analysis_node,
        ]
    )


import os
from glob import glob
from setuptools import find_packages, setup

package_name = "hospital_robot_nav_nodes"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Hospital Robot Navigation Team",
    maintainer_email="team@hospitalrobotnav.org",
    description=(
        "ROS 2 nodes for the autonomous hospital robot navigation platform."
    ),
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "semantic_map_node = hospital_robot_nav_nodes.semantic_map_node:main",
            "planner_node = hospital_robot_nav_nodes.planner_node:main",
            "obstacle_tracker_node = hospital_robot_nav_nodes.obstacle_tracker_node:main",
            "robot_controller_node = hospital_robot_nav_nodes.robot_controller_node:main",
            "mission_executor_node = hospital_robot_nav_nodes.mission_executor_node:main",
            "fleet_coordinator_node = hospital_robot_nav_nodes.fleet_coordinator_node:main",
        ],
    },
)


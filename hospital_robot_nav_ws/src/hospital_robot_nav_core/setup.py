from setuptools import find_packages, setup

package_name = "hospital_robot_nav_core"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Hospital Robot Navigation Team",
    maintainer_email="team@hospitalrobotnav.org",
    description=(
        "Pure-Python logic library for the autonomous hospital robot "
        "navigation platform (no ROS 2 dependency)."
    ),
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={},
)


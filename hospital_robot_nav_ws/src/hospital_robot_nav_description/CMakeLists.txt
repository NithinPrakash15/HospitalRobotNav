cmake_minimum_required(VERSION 3.8)
project(hospital_robot_nav_description)

find_package(ament_cmake REQUIRED)

# Install URDF/Xacro files
install(DIRECTORY urdf/
  DESTINATION share/${PROJECT_NAME}/urdf
)

# Install launch files
install(DIRECTORY launch/
  DESTINATION share/${PROJECT_NAME}/launch
)

ament_package()

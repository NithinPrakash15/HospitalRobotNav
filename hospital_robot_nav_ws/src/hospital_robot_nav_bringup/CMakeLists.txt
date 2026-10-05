cmake_minimum_required(VERSION 3.8)
project(hospital_robot_nav_bringup)

find_package(ament_cmake REQUIRED)

# Install launch files
install(DIRECTORY launch
  DESTINATION share/${PROJECT_NAME}
)

# Install parameter YAML files
install(DIRECTORY config
  DESTINATION share/${PROJECT_NAME}
)

ament_package()


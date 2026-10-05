# ROS2 Migration & Deployment Guide

This document provides a step-by-step technical guide for translating this Python prototype codebase into a production-grade ROS2 Navigation (Nav2) package for real hospital hardware or Isaac Sim / Gazebo simulation environments.

---

## 1. ROS2 Architecture & Node Mapping

The module abstractions in this system map 1-to-1 with standard ROS2 nodes, interfaces, and Nav2 plugins:

| System Component | ROS2 Node / Package Equivalent | ROS2 Interface / Type |
| :--- | :--- | :--- |
| `OccupancyGrid` | `nav2_costmap_2d` | `nav2_msgs/msg/Costmap` |
| `SemanticMap` | Custom ROS2 node (`semantic_map_server`) | `std_srvs/srv/Trigger` / Custom Service |
| `ObstacleManager` | `nav2_people_server` / Tracked Obstacle Filter | `people_msgs/msg/People` |
| `PlannerFactory` / `AStar` / `Theta*` | `nav2_planner_server` Plugins | `nav2_core::GlobalPlanner` |
| `HybridAStarPlanner` | `nav2_smac_planner` Plugin | `nav2_core::GlobalPlanner` |
| `PathSmoother` | `nav2_smoother_server` Plugin | `nav2_core::Smoother` |
| `CollisionDetector` | `nav2_collision_monitor` | `nav2_msgs/msg/CollisionDetectorState` |
| `RobotStateMachine` | `nav2_bt_navigator` | `behavior_tree_msgs` |
| `EventBus` | ROS2 Pub/Sub Middleware | `rclpy` / `rclcpp` topics |

---

## 2. Directory Mapping for ROS2 Package

To convert `HospitalRobotNav` into a ROS2 package `hospital_robot_nav`:

```
hospital_robot_nav/
├── CMakeLists.txt
├── package.xml
├── launch/
│   ├── hospital_simulation.launch.py
│   └── nav2_hospital.launch.py
├── config/
│   ├── nav2_params.yaml          <-- Maps from config/settings.py
│   └── hospital_costmap.yaml
├── maps/
│   ├── hospital_map.yaml
│   └── hospital_map.pgm          <-- Generated from HospitalMap array
├── hospital_robot_nav/
│   ├── __init__.py
│   ├── semantic_map_node.py      <-- ROS2 wrapper for environment/semantic_map.py
│   ├── obstacle_tracker_node.py  <-- ROS2 wrapper for environment/obstacle_manager.py
│   └── robot_controller_node.py  <-- ROS2 wrapper for robot/robot.py & simulation/physics.py
└── test/
    └── test_planners.py
```

---

## 3. ROS2 Topic Structure

When running under ROS2, communication transitions from `EventBus` to the standard ROS2 graph:

### Published Topics:
- `/map` (`nav_msgs/msg/OccupancyGrid`): Published by `map_server`.
- `/global_costmap/costmap` (`nav2_msgs/msg/Costmap`): Combined static and dynamic obstacle map.
- `/odom` (`nav_msgs/msg/Odometry`): Published by robot odometry driver at 50 Hz.
- `/plan` (`nav_msgs/msg/Path`): Global trajectory published by planner node.
- `/battery_state` (`sensor_msgs/msg/BatteryState`): Hardware battery status.

### Subscribed Topics:
- `/cmd_vel` (`geometry_msgs/msg/Twist`): Differential drive motor velocity commands.
- `/goal_pose` (`geometry_msgs/msg/PoseStamped`): Destination pose published by RViz2 or UI.

---

## 4. Nav2 Plugin Implementation Example (C++)

To implement our custom `Theta*` planner as a Nav2 C++ plugin for maximum performance:

```cpp
#include "nav2_core/global_planner.hpp"
#include "rclcpp/rclcpp.hpp"

namespace hospital_robot_nav
{
class ThetaStarPlanner : public nav2_core::GlobalPlanner
{
public:
  void configure(
    const rclcpp_lifecycle::LifecycleNode::WeakPtr & parent,
    std::string name, std::shared_ptr<tf2_ros::Buffer> tf,
    std::shared_ptr<nav2_costmap_2d::Costmap2DROS> costmap_ros) override;

  nav_msgs::msg::Path createPlan(
    const geometry_msgs::msg::PoseStamped & start,
    const geometry_msgs::msg::PoseStamped & goal) override;
};
}
```

---

## 5. Deployment Commands

```bash
# 1. Source ROS2 Humble/Jazzy environment
source /opt/ros/humble/setup.bash

# 2. Build package
colcon build --packages-select hospital_robot_nav

# 3. Launch full hospital simulation in Gazebo/Isaac Sim + RViz2
ros2 launch hospital_robot_nav hospital_simulation.launch.py
```

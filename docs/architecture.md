# System Architecture — Autonomous Hospital Robot Navigation

## 1. Overview
The **Multi-Agent Autonomous Hospital Robot Navigation System** is engineered using **Clean Architecture**, **SOLID Principles**, and **Event-Driven Design**. The architecture isolates domain logic from visualization and framework dependencies, creating a modular structure that compiles directly into ROS2 nodes.

```
                    ┌─────────────────────────┐
                    │      Pygame UI          │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │    Simulator (Engine)   │
                    └────────────┬────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
┌────────▼────────┐    ┌─────────▼────────┐    ┌─────────▼────────┐
│  Robot & FSM    │    │  PlannerFactory  │    │ Dynamic Obstacle │
└────────┬────────┘    └─────────┬────────┘    └─────────┬────────┘
         │                       │                       │
┌────────▼────────┐    ┌─────────▼────────┐    ┌─────────▼────────┐
│  Battery Model  │    │ Path Planners    │    │ Occupancy Grid   │
└─────────────────┘    │ (A*, Theta*, ...)│    └─────────┬────────┘
                       └──────────────────┘              │
                                               ┌─────────▼────────┐
                                               │   Hospital Map   │
                                               └──────────────────┘
```

## 2. Layer Definitions

### Layer 1: Configuration (`config/`)
- `settings.py`: Application dimensions, color schemes, display configuration, and global simulation parameters.
- `hospital_config.py`: Hospital floor plan dimensions (100×100 grid, 0.5m cell resolution), wall thicknesses, and room count.
- `robot_config.py`: Differential drive kinematics (max linear/angular velocity, radius, battery capacity).

### Layer 2: Utilities (`utilities/`)
- `logger.py`: Structured colored logging.
- `geometry.py`: Spatial distance metrics (Euclidean, Manhattan, Chebyshev), Bresenham raycasting, and line-of-sight algorithms.
- `priority_queue.py`: Min-heap implementation supporting $O(\log N)$ decrease-key operations for search algorithms.
- `event_bus.py`: Publish/Subscribe middleware mirroring ROS2 topics.

### Layer 3: Maps (`maps/`)
- `room_definitions.py`: Database of 25+ hospital departments (ICU, Operating Theaters, Radiology, Pharmacy, Wards).
- `hospital_map.py`: Grid layout generator placing outer boundaries, central corridors, sub-hallways, and doorways.

### Layer 4: Environment (`environment/`)
- `occupancy_grid.py`: 2D Costmap layer (Static + Dynamic + Obstacle Inflation gradient).
- `navigation_graph.py`: Topological room-to-room connectivity graph using NetworkX.
- `semantic_map.py`: Natural language destination resolver for VLM/LLM interfaces ("Go to ICU" → cell (18, 60)).
- `obstacle_manager.py`: Dynamic obstacle lifecycle manager (human staff, stretchers, medical carts).

### Layer 5: Algorithms (`algorithms/`)
- `heuristics.py`: Manhattan, Euclidean, Diagonal (Octile), Chebyshev, and Weighted A* heuristics.
- `base_planner.py`: Abstract Base Class for path planners providing benchmark profiling (time, memory, node expansions).
- `astar.py`: Standard A* search with open/closed set visualization.
- `dijkstra.py`: Uniform-cost search baseline and flood-fill distance maps.
- `theta_star.py`: Lazy Theta* any-angle path planner for smooth corridor paths.
- `hybrid_astar.py`: Continuous state-space $(x, y, \theta)$ planner with bicycle kinematics.
- `dstar_lite.py`: Incremental dynamic replanner for real-time obstacle avoidance.

### Layer 6: Robot Core (`robot/`)
- `robot_state.py`: Finite State Machine with 13 guarded states (IDLE, PLANNING, MOVING, REPLANNING, BLOCKED, CHARGING, etc.).
- `battery.py`: LiFePO4 battery model with discharge kinetics and automated charging behaviors.
- `robot.py`: Main differential-drive robot entity.

### Layer 7: Navigation & Planning (`navigation/`, `planning/`)
- `planner_factory.py`: Strategy Pattern for switching path planners at runtime.
- `path_smoother.py`: Shortcut pruning, cubic Bezier curves, and Catmull-Rom splines.
- `collision_detector.py`: Circular footprint collision checker and lookahead monitor.

### Layer 8: Simulation & Visualization (`simulation/`, `visualization/`, `metrics/`)
- `clock.py`: Time manager supporting $0.25\times$ to $8.0\times$ speed multipliers.
- `physics.py`: PD velocity and heading controller.
- `simulator.py`: Master orchestrator.
- `renderer.py`: Pygame rendering engine with dual side panels, zoom/pan camera, and minimap.
- `performance_metrics.py`: Metrics collector for IEEE-style evaluation tables.

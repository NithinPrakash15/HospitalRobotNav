# API Reference

Complete API documentation for all public classes and methods.

---

## `OccupancyGrid` — `environment/occupancy_grid.py`

The core 2D costmap layer used by all planners.

### Constructor
```python
OccupancyGrid(hospital_map: HospitalMap, inflation_radius: float = 1.5)
```

### Key Methods
| Method | Signature | Description |
| :----- | :-------- | :---------- |
| `is_free` | `(row, col) → bool` | True if cell is passable |
| `get_cost` | `(row, col) → float` | Navigation cost at cell |
| `find_nearest_free` | `(row, col) → (row, col)` | BFS nearest passable cell |
| `get_neighbors_8` | `(row, col) → List[(row,col)]` | 8-connected passable neighbors |
| `add_dynamic_obstacle` | `(row, col)` | Block a cell dynamically |
| `remove_dynamic_obstacle` | `(row, col)` | Unblock a cell |
| `move_dynamic_obstacle` | `(old, new)` | Atomic move obstacle |
| `clear_dynamic_obstacles` | `()` | Remove all dynamic obstacles |

---

## `BasePlanner` — `algorithms/base_planner.py`

Abstract base class for all path planners.

### Constructor
```python
BasePlanner(occupancy_grid: OccupancyGrid, heuristic_type: HeuristicType = HeuristicType.DIAGONAL)
```

### Key Methods
| Method | Signature | Description |
| :----- | :-------- | :---------- |
| `plan` | `(start, goal) → PlannerResult` | Run path planning |
| `set_heuristic` | `(HeuristicType, weight)` | Change heuristic at runtime |
| `get_expansion_log` | `() → List[GridPos]` | All expanded nodes (for viz) |

### `PlannerResult` Fields
```python
@dataclass
class PlannerResult:
    status:   PlannerStatus    # SUCCESS | NO_PATH | TIMEOUT | ERROR
    path:     List[GridPos]    # Ordered waypoints from start to goal
    metrics:  PlannerMetrics   # Timing, node count, memory
    expanded: List[GridPos]    # All expanded nodes (for animation)
```

---

## `PlannerFactory` — `planning/planner_factory.py`

Strategy pattern wrapper for runtime algorithm switching.

### Constructor
```python
PlannerFactory(occupancy_grid, default_planner=PlannerType.ASTAR, default_heuristic=HeuristicType.DIAGONAL)
```

### Key Methods
| Method | Signature | Description |
| :----- | :-------- | :---------- |
| `plan` | `(start, goal) → PlannerResult` | Plan with active algorithm |
| `replan` | `(current, goal) → PlannerResult` | Replan (D* Lite uses incremental) |
| `set_planner` | `(PlannerType)` | Switch active planner |
| `set_heuristic` | `(HeuristicType, weight)` | Change heuristic |
| `notify_obstacle_change` | `(cells, pos)` | Alert D* Lite of changes |
| `active_planner_name` | `→ str` | Display name of active planner |

---

## `RobotController` — `controllers/robot_controller.py`

Pure-Pursuit + PD cascade motion controller.

### Constructor
```python
RobotController(collision_detector: CollisionDetector, lookahead_dist: float = 2.5)
```

### Key Methods
| Method | Signature | Description |
| :----- | :-------- | :---------- |
| `update` | `(robot: Robot) → VelocityCommand` | Compute cmd_vel this frame |
| `reset` | `()` | Reset smoothing state |

### `VelocityCommand` Fields
```python
class VelocityCommand:
    linear_x:  float   # Forward speed (cells/second)
    angular_z: float   # Rotation (rad/second)
```

---

## `Robot` — `robot/robot.py`

Central robot entity.

### Constructor
```python
Robot(robot_id=None, robot_type=RobotType.GENERAL, start_pos=(80, 11))
```

### Key Properties
| Property | Type | Description |
| :-------- | :---- | :----------- |
| `position` | `(float, float)` | Current (row, col) |
| `grid_pos` | `(int, int)` | Rounded grid cell |
| `state` | `RobotState` | Current FSM state |
| `path_progress` | `float` | 0.0 → 1.0 completion |
| `remaining_waypoints` | `int` | Waypoints left |

### Key Methods
| Method | Description |
| :----- | :---------- |
| `set_path(path)` | Assign planned path |
| `advance_waypoint()` | Step to next waypoint |
| `enqueue_mission(m)` | Add mission to queue |
| `start_next_mission()` | Dequeue and activate |
| `complete_current_mission(success)` | Mark done/failed |
| `get_stats()` | Return analytics dict |
| `reset(start_pos)` | Full state reset |

---

## `SemanticQueryEngine` — `semantic/semantic_query_engine.py`

Natural-language destination resolver.

### Constructor
```python
SemanticQueryEngine(occupancy_grid: OccupancyGrid)
```

### Key Methods
| Method | Signature | Description |
| :----- | :-------- | :---------- |
| `resolve` | `(query, robot_pos=None) → GridPos` | Resolve query to grid position |
| `resolve_all` | `(query, robot_pos=None) → List[GridPos]` | All matching rooms |
| `get_destination_names` | `() → List[(id, label, pos)]` | All navigable rooms |

### Supported Query Formats
```
"ICU"                    → exact room ID
"icu"                    → case-insensitive
"intensive care"         → substring match
"nearest pharmacy"       → proximity match
"take me to emergency"   → prefix-stripped
"ER"                     → alias lookup
```

---

## `HospitalEvent` — `utilities/event_bus.py`

All system events (ROS2 topic equivalents).

```python
class HospitalEvent(Enum):
    ROBOT_GOAL_REACHED      # /robot/goal_reached
    ROBOT_STUCK             # /robot/stuck
    PATH_PLANNED            # /robot/path
    PATH_FAILED             # /robot/path_failed
    REPLANNING_STARTED      # /robot/replanning
    REPLANNING_COMPLETE     # /robot/replan_done
    MISSION_STARTED         # /robot/mission_start
    MISSION_COMPLETE        # /robot/mission_done
    MISSION_FAILED          # /robot/mission_fail
    OBSTACLE_DETECTED       # /robot/obstacle
    DYNAMIC_OBSTACLE_ADD    # /sim/obstacle_add
    DYNAMIC_OBSTACLE_REMOVE # /sim/obstacle_remove
    DYNAMIC_OBSTACLE_MOVE   # /sim/obstacle_move
    EMERGENCY_ALERT         # /hospital/emergency
    CORRIDOR_BLOCKED        # /hospital/corridor_blocked
    FIRE_ALARM              # /hospital/fire
    POWER_FAILURE           # /hospital/power_fail
    PATIENT_CROSSING        # /hospital/patient_cross
    BATTERY_LOW             # /robot/battery_low
    BATTERY_CRITICAL        # /robot/battery_critical
    ROBOT_CHARGING          # /robot/charging
    ROBOT_CHARGED           # /robot/charged
    SIMULATION_RESET        # /sim/reset
    SIMULATION_PAUSED       # /sim/paused
    SIMULATION_RESUMED      # /sim/resumed
    PLANNER_CHANGED         # /robot/planner
    SPEED_CHANGED           # /sim/speed
```

### Usage
```python
from utilities.event_bus import EVENT_BUS, HospitalEvent

# Publish
EVENT_BUS.publish(HospitalEvent.PATH_PLANNED, {"planner": "A*", "path_len": 100})

# Subscribe
EVENT_BUS.subscribe(HospitalEvent.BATTERY_LOW, lambda payload: handle_low_battery())
```

---

## `PerformanceMetrics` — `metrics/performance_metrics.py`

IEEE-style algorithm benchmarking.

```python
metrics = PerformanceMetrics()
metrics.record_plan(result, planner_name="A*")
table = metrics.get_comparison_table()   # Returns formatted string table
metrics.export_csv("results.csv")
```

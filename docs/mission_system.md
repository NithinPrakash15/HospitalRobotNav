# Mission System — Design & Implementation

## Overview

The mission system manages the lifecycle of all tasks the robot performs, from
high-level request creation to low-level step execution.

```
MissionRequest
    ↓
MissionPlanner          (decompose into ordered TaskStep list)
    ↓
MissionExecutor         (step-by-step FSM execution)
    ↓
Robot FSM               (navigate, collect, deliver, wait)
    ↓
MedicineManager         (inventory verification & deduction)
    ↓
PatientAssistance       (patient interaction sub-task)
```

---

## Mission Types (`missions/mission_types.py`)

| Type | States | Description |
|---|---|---|
| `MEDICINE_DELIVERY` | NAVIGATE_PICKUP → COLLECT → NAVIGATE_DEST → DELIVER | Transport medicine from pharmacy to ward |
| `PATIENT_GUIDE` | NAVIGATE_TO_PATIENT → ESCORT → NAVIGATE_DEST | Escort patient between locations |
| `EMERGENCY_RESPONSE` | NAVIGATE_EMERGENCY | Respond to code blue/red |
| `REPORT_DELIVERY` | NAVIGATE_SOURCE → COLLECT → NAVIGATE_DEST → DELIVER | Transport lab/imaging reports |
| `SAMPLE_TRANSPORT` | NAVIGATE_PICKUP → COLLECT → NAVIGATE_DEST → DELIVER | Transport pathology samples |
| `WHEELCHAIR_FETCH` | NAVIGATE_STORAGE → COLLECT → NAVIGATE_DEST → DELIVER | Fetch mobility equipment |
| `VISITOR_ESCORT` | NAVIGATE_ENTRANCE → ESCORT → NAVIGATE_DEST | Guide visitors to rooms |
| `PATROL` | NAVIGATE (cyclic waypoints) | Periodic area patrol |

### Priority Levels

| Level | Value | Response Time |
|---|---|---|
| CRITICAL | 1 | Immediate — preempts any mission |
| HIGH | 2 | < 60 s |
| NORMAL | 3 | < 5 min |
| LOW | 4 | Opportunistic |
| BACKGROUND | 5 | Idle only |

---

## Mission Planner (`missions/mission_planner.py`)

Decomposes a `MissionRequest` into an ordered list of `TaskStep` objects:

```python
planner = MissionPlanner(medicine_manager, semantic_map)
plan = planner.create_plan(mission_request)
# plan.steps → [TaskStep(NAVIGATE, ...),  TaskStep(COLLECT, ...), ...]
```

**Planning logic:**

1. Resolve all location names via `SemanticMap`
2. Insert pharmacy pickup step if pickup location not specified
3. Assign estimated durations based on Manhattan distance
4. Handle multi-drop (multiple medicine packages → multiple delivery steps)

---

## Mission Executor (`missions/mission_executor.py`)

Drives the `Robot` FSM through each `TaskStep` in sequence:

```
IDLE
  │  assign_mission(plan)
  ▼
EXECUTING
  │  step.type == NAVIGATE → robot transitions IDLE→PLANNING→MOVING
  │  step.type == COLLECT  → robot transitions →COLLECTING (3 s timer)
  │  step.type == DELIVER  → robot transitions →DELIVERING (2 s timer)
  │  step.type == WAIT     → robot transitions →WAITING    (N s timer)
  │  step.type == INTERACT → PatientAssistance.run()
  │
  ▼ on ROBOT_GOAL_REACHED / step_timer expires
STEP_COMPLETE
  │  advance to next step
  ▼
MISSION_COMPLETE / MISSION_FAILED
```

---

## Medicine Manager (`missions/medicine_manager.py`)

Manages the onboard medicine inventory:

| Method | Description |
|---|---|
| `check_stock(name)` | Returns available quantity |
| `verify_stock(name, qty)` | Returns True if qty available |
| `dispense(name, qty)` | Deduct from inventory |
| `restock(name, qty)` | Add to inventory |
| `get_medicine(name)` | Return `MedicineRecord` object |
| `get_formulary()` | Return all 30 medicines |

**Default formulary (30 medicines):**
Paracetamol, Ibuprofen, Amoxicillin, Metformin, Atorvastatin, Omeprazole,
Amlodipine, Losartan, Metoprolol, Aspirin, Atenolol, Ciprofloxacin,
Azithromycin, Doxycycline, Sertraline, Fluoxetine, Gabapentin, Pregabalin,
Insulin Glargine, Insulin Regular, Warfarin, Heparin, Morphine, Tramadol,
Ondansetron, Dexamethasone, Hydrocortisone, Salbutamol, Normal Saline, Ringer's Lactate.

---

## Patient Assistance (`missions/patient_assistance.py`)

Handles human-robot interaction during escort and assistance missions:

| Sub-task | Description |
|---|---|
| `greet_patient()` | TTS greeting + proximity check |
| `confirm_identity()` | Ask patient to state name / show wristband |
| `instruct_follow()` | "Please follow me" TTS |
| `arrival_report()` | "We have arrived at Radiology" TTS |
| `emergency_alert()` | Broadcast emergency event |

---

## Medicine Animation (`missions/medicine_animation.py`)

Pygame particle system for visual delivery confirmation:

- **Pickup animation:** Green sparkles at pharmacy centroid
- **Delivery animation:** Confetti burst at destination room centroid
- Animations are time-bounded and non-blocking

---

## EventBus Integration

| Event | When Published |
|---|---|
| `MISSION_STARTED` | MissionExecutor begins execution |
| `MISSION_COMPLETE` | Final step confirmed complete |
| `MISSION_FAILED` | Unrecoverable failure |
| `MISSION_STEP_COMPLETE` | Single step done |
| `MEDICINE_COLLECTED` | Dispense step successful |
| `MEDICINE_DELIVERED` | Delivery step confirmed |
| `PATIENT_ESCORTED` | Escort mission complete |

---

## ROS2 Migration Path

| Module | ROS2 Node | Topics/Services |
|---|---|---|
| `MissionPlanner` | `mission_planner_node` | `/mission/request` → `/mission/plan` |
| `MissionExecutor` | `mission_executor_node` | `/mission/plan` → `/robot/cmd` |
| `MedicineManager` | `pharmacy_node` | `/pharmacy/dispense` (service) |
| `PatientAssistance` | `interaction_node` | `/patient/interact` |

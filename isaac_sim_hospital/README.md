# Multi-Agent Embodied AI Hospital Robot — Isaac Sim Digital Twin

**Project Title:** Multi-Agent Embodied AI Robot for Autonomous Hospital Assistance using Vision-Language Reasoning

## Architecture Overview

```
C:\isaacsim\python.bat scripts\milestone_2_hospital.py
         |
         v
scripts\run_embodied_hospital_ai.py        <- MAIN SIMULATION ENTRY
         |
         +-- environments\hospital_env.py          (60m x 60m hospital, 24 depts)
         +-- environments\dynamic_obstacles.py     (Doctors, Nurses, Stretchers)
         +-- environments\bilingual_voice.py        (EN + HI Windows SAPI TTS)
         +-- environments\command_interface.py      (stdin + Vosk ASR terminal)
         +-- environments\status_dashboard.py       (real-time console HUD)
         +-- robots\arogya_robot.py                 (Arogya AMR + CompanionAMR)
         +-- robots\robot_state_machine.py          (9 states, 5 priorities)
         +-- navigation\collision_guard.py           (A* + dynamic replanning)
         +-- ai_reasoning\mission_understander.py   (bilingual NLU)
         +-- multi_agent\hospital_agent_manager.py  (Contract-Net coordinator)
         +-- agents\{delivery,reception,emergency}_agent.py
```

## Run Commands

### Interactive 3D Simulation (Robot starts IDLE — awaiting your command)
```powershell
cd "c:\Users\nithi\OneDrive\Desktop\Main Project for vs\HospitalRobotNav\isaac_sim_hospital"
C:\isaacsim\python.bat scripts\milestone_2_hospital.py
```

### With Microphone Voice Input (Vosk ASR)
```powershell
C:\isaacsim\python.bat scripts\milestone_2_hospital.py --mic
```

### Headless Automated Testing
```powershell
C:\isaacsim\python.bat scripts\milestone_2_hospital.py --headless
```

### 7-Scenario Logic Test Suite (no Isaac Sim required)
```powershell
python isaac_sim_hospital\tests\test_7_scenarios_headless.py
```

## Interactive Command Reference

Once running, type commands in the terminal to control the robot:

| Command | Action |
|---------|--------|
| `go pharmacy` | Navigate to Pharmacy |
| `go ward` | Navigate to Ward 101 |
| `go icu` | Navigate to ICU |
| `go reception` | Navigate to Reception |
| `go dock` / `go home` | Return to Charging Bay |
| `deliver paracetamol` | NLU-parsed delivery mission |
| `emergency icu` | Trigger Code Blue preemption |
| `stop` / `idle` | Halt robot, return to IDLE |
| `resume` | Resume last preempted task |
| `status` | Print fleet status report |
| `help` | Show command list |
| `quit` | Close simulation |

## System Features

### 1. Robot State Machine (9 States)
| State | Description |
|-------|-------------|
| `IDLE` | Standby on charging pad |
| `MISSION_ANALYSIS` | NLU parsing voice/text command |
| `TASK_ASSIGNED` | Contract-Net winner selected |
| `PLANNING` | A* path computation |
| `NAVIGATING` | Corridor waypoint following |
| `EXECUTING_TASK` | Clinical action at destination |
| `BLOCKED` | Yielding to dynamic humanoid |
| `EMERGENCY_OVERRIDE` | Priority-1 Code Blue mode |
| `MISSION_COMPLETE` | Returning to coordinator |

### 2. Priority Levels
| Level | Label | Speed |
|-------|-------|-------|
| 1 | CRITICAL_EMERGENCY | 1.25× |
| 2 | URGENT_MEDICINE | 1.10× |
| 3 | SCHEDULED_DELIVERY | 1.00× |
| 4 | VISITOR_ESCORT | 0.85× |
| 5 | RETURN_TO_DOCK | 0.80× |

### 3. Multi-Agent Fleet (Contract-Net Protocol)
- **CoordinatorAgent** — Fleet manager, auction supervisor
- **DeliveryAgent** — Medicine transport, pharmacy dispatch
- **ReceptionAgent** — Patient triage, visitor escort
- **EmergencyAgent** — Code Blue response, trauma resupply

### 4. Clinical Activities (8 Milestones)
| ID | Activity | Location |
|----|----------|----------|
| ACT-01 | Mission Dispatch | CHG-01 Charging Bay |
| ACT-02 | Patient Triage Check-in | RCT-01 Reception |
| ACT-03 | Medication Collection | PHM-01 Pharmacy |
| ACT-04 | Chart Handoff | NST-01 Nurse Station |
| ACT-05 | Bedside Delivery | PAT-101 Ward |
| ACT-06 | Trauma Kit Drop | EMR-01 Emergency |
| ACT-07 | ICU Escort Patrol | ICU-01 Critical Care |
| ACT-08 | Autonomous Docking | CHG-01 Charging Bay |

### 5. Dynamic Obstacles
- Dr. Sharma — Doctor patrolling North Corridor H1
- Nurse Priya — Nurse patrolling Central Corridor H2
- Paramedic Alex — Wheeled stretcher on East Corridor V3
- Orderly Carlos — Medicine cart on West Corridor V1
- Visitor Maya — Visitor in Reception atrium

### 6. Bilingual Voice System
- English announcements at each clinical milestone
- Hindi (हिंदी) parallel translations
- Async Windows SAPI synthesis (non-blocking daemon thread)
- Startup greeting, command acknowledgments, mission complete

## Test Results (7-Scenario Suite)

Run: `python isaac_sim_hospital\tests\test_7_scenarios_headless.py`

| Scenario | Status |
|----------|--------|
| T1: System Startup (IDLE on boot) | PASS |
| T2: Delivery Mission (NLU + Contract-Net) | PASS |
| T3: Wall Collision Guard (100% safe) | PASS |
| T4: Dynamic Obstacle Yield (BLOCKED) | PASS |
| T5: Multi-Agent Allocation (winner selection) | PASS |
| T6: Emergency Preemption (P1 override + resume) | PASS |
| T7: State Machine Transitions (all 9 states) | PASS |

## Hardware Target
- ASUS ROG Strix G15 (Intel i7-13650HX)
- NVIDIA RTX 4050 Laptop GPU, 6GB VRAM
- DirectX 12 API, RTX Real-Time rendering

# AAROGYA — Hospital Autonomous Assistance Platform

> **Final-Year Research Project:**  
> *"Multi-Agent Embodied AI Robot for Autonomous Hospital Assistance using Vision-Language Reasoning"*

---

## 🏥 Platform Overview

**AAROGYA** is a production-grade autonomous hospital robotics and multi-agent coordination platform. It integrates a relational hospital management system, strict clinical role-based access control (RBAC), multi-agent contract-net dispatching, offline and online natural language voice gateways, and **NVIDIA Isaac Sim** as the primary and final 3D photorealistic digital twin simulation environment.

```
+-----------------------------------------------------------------------------------+
|                           AAROGYA WEB APPLICATION                                 |
|   Role-Based Dashboards | Interactive Isaac Canvas | 10Hz Telemetry | Voice Mic   |
+-----------------------------------------+-----------------------------------------+
                                          | REST API + WebSockets
                                          v
+-----------------------------------------------------------------------------------+
|                               FASTAPI BACKEND HUB                                 |
|  - JWT + Bcrypt Auth & RBAC (Admin, Doctor, Nurse, Patient, Visitor)             |
|  - Clinical Medication Safety Engine (Duplicate Task Prevention, Discontinued Rx) |
|  - Multi-Agent Task Dispatcher & Preemption Stack                                 |
|  - 10Hz Telemetry & Camera Director Orchestrator                                 |
+-------------------+-------------------------------------+-------------------------+
                    |                                     |
                    v                                     v
+-----------------------------------+   +-------------------------------------------+
|       RELATIONAL DATABASE         |   |         NVIDIA ISAAC SIM 5.1.0            |
| - SQLite / PostgreSQL             |   | - 28-Department Grand Digital Twin        |
| - SQLAlchemy 2.0 ORM              |   | - Triple-Layer Collision Guard            |
| - Departments, Rooms, Beds        |   | - Dynamic Obstacle Detours & A*           |
| - Patients, Prescriptions, Tasks  |   | - 4 Autonomous AMRs (Delivery, Guide, etc)|
| - AMRs, Schedules, Audit Logs     |   | - Camera Director (Follow, Task, Overview)|
+-----------------------------------+   +-------------------------------------------+
```

---

## ✨ Key System Capabilities

### 1. 🛡️ Clinical Role-Based Access Control (RBAC) & Voice Security
- **Role Hierarchy**: `ADMIN`, `DOCTOR`, `NURSE`, `PATIENT`, `VISITOR`.
- **Stateless JWT Tokens**: Issued via `/api/auth/login` using secure `bcrypt` credential hashing.
- **Voice Input Rule**: Voice is strictly an *input channel*, **never** an authorization bypass.
  - An unauthorized visitor attempting to order medication delivery (e.g. *"Deliver morphine to ICU"*) receives an immediate `403 Forbidden` / `ACCESS DENIED` audit alert.
  - Visitors are permitted to ask general navigation questions (e.g. *"Where is the pharmacy?"* or *"Where is Dr. Sharma's clinic?"*) which routes to the `Nandi_Guide` reception AMR.

### 2. 💊 Medication Management & Duplicate Task Prevention
- **Automated Long-Term Schedules**: When a physician creates an active prescription (e.g., *Paracetamol 650mg every 8 hours for 7 days*), the medication engine generates timestamped administration slots across the full duration.
- **Clinical Safety Guards**:
  - Automatically rejects delivery orders for **discontinued** prescriptions (`400 Bad Request`).
  - Automatically rejects delivery orders for **discharged** patients (`400 Bad Request`).
- **Backend/DB-Level Duplicate Prevention**:
  - If a delivery mission is already pending or in progress for a given patient and medication, any subsequent dispatch attempt triggers a `409 Conflict`.
  - The response payload returns the existing task ID, assigned AMR, status, and creation time, preventing accidental hospital double-dosing.

### 3. 🤖 Multi-Agent Fleet & Emergency Preemption
- **Fleet Allocation**:
  - `Aarogya_Delivery`: Pharmaceutical and medical supply delivery AMR.
  - `Nandi_Guide`: Visitor guidance, reception, and patient intake AMR.
  - `Garuda_Emergency`: Code Blue emergency crash cart response AMR.
  - `Dhanvantari_General`: General ward specimen and equipment transit AMR.
- **Priority Preemption**:
  - When **Code Blue** is triggered (via Web UI or voice), routine delivery tasks are placed on an interruption stack.
  - `Garuda_Emergency` is dispatched with preemption authority, navigating directly to the critical room.

### 4. 🌐 Modern Glassmorphic Web Application (SPA)
- **Zero External Dependencies**: Pure Vanilla HTML5, CSS3, and JavaScript, served directly by FastAPI.
- **Interactive 2D Spatial Canvas**: Real-time rendering of all 28 departments, corridors, patient beds (e.g. ICU Bed 3), and AMR poses matching Isaac Sim world coordinates `(x, y, yaw)`.
- **Camera Director**: Real-time switching between `FOLLOW_ROBOT`, `FOLLOW_TASK`, and `OVERVIEW` modes.
- **10Hz Telemetry & Terminal**: Live WebSocket `/ws/telemetry` streaming robot coordinates, battery state of charge, mission progress bars, and audit logs.

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.10 through 3.13)
- Windows 10/11 or Ubuntu Linux

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/your-org/HospitalRobotNav.git
cd HospitalRobotNav

# Install required packages
pip install -r requirements.txt
```

### 3. Launching the AAROGYA Platform
Simply double-click `run_aarogya_platform.bat` or run:

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Then open your browser to **`http://localhost:8000`**.

### 4. Default Seed Personas (RBAC Demo)

| Persona | Username | Password | Role | Permitted Actions |
| --- | --- | --- | --- | --- |
| **Dr. Sarah Patel** | `doctor` | `doctor123` | `DOCTOR` | Issue Prescriptions, Discontinue Rx, Dispatch AMRs, View All |
| **Nurse Priya Sharma** | `nurse` | `nurse123` | `NURSE` | Dispatch Delivery AMRs, View Inpatients, View Tasks |
| **System Admin** | `admin` | `admin123` | `ADMIN` | Full System Access, Emergency Dispatch, Fleet Control |
| **Arun Patel** | `patient` | `patient123` | `PATIENT` | View Personal Room (ICU Bed 3) & Active Prescriptions |
| **Vikram V.** | `visitor` | `visitor123` | `VISITOR` | Reception Navigation Inquiries (No Clinical Dispatch) |

---

## 🎮 NVIDIA Isaac Sim 3D Digital Twin

NVIDIA Isaac Sim is the **primary and final** 3D simulation environment.

```bash
# Launch interactive 3D simulation
C:\isaacsim\python.bat isaac_sim_hospital\scripts\run_embodied_hospital_ai.py

# Launch with specific traffic density
C:\isaacsim\python.bat isaac_sim_hospital\scripts\run_embodied_hospital_ai.py --traffic high

# Launch in automated headless mode
C:\isaacsim\python.bat isaac_sim_hospital\scripts\run_embodied_hospital_ai.py --headless
```

---

## 🧪 Automated Test Suite

Run the full end-to-end platform and unit test suite:

```bash
# Master Platform & RBAC Tests (8 tests)
python -m pytest tests/test_aarogya_e2e_platform.py -v

# Kinematics & Differential Drive Deadband Tests
python -m pytest tests/test_kinematics.py -v

# Isaac Sim Command Center & Crash Prevention Tests
python -m pytest isaac_sim_hospital/tests/test_command_center_verification.py -v

# Isaac Sim Priority 10 End-to-End Scenarios
python -m pytest isaac_sim_hospital/tests/test_priority_10_end_to_end.py -v

# Isaac Sim Master Correction & Collision Guard Tests
python -m pytest isaac_sim_hospital/tests/test_master_correction_features.py -v
```

---

## 📁 Repository Directory Structure

```text
HospitalRobotNav/
├── ai_reasoning/            # Natural Language Understanding & Mission Parser
├── backend/                 # FastAPI REST Hub, Auth (JWT+Bcrypt), Simulation Orchestrator
├── config/                  # Facility & AMR configuration settings
├── controllers/             # Differential robot kinematics & motion profiles
├── data/                    # aarogya.db (SQLite database)
├── database/                # SQLAlchemy 2.0 Models, Session Factory, Seed Data
├── frontend/                # Single-Page Web Application
│   ├── index.html           # Master glassmorphic UI
│   └── static/
│       ├── css/app.css      # Dark glassmorphic design system
│       └── js/app.js        # RBAC, WebSocket telemetry, 2D canvas, Voice Gateway
├── hospital_robot_nav_ws/   # ROS 2 Colcon workspace (bridge, odom, cmd_vel)
├── isaac_sim_hospital/      # NVIDIA Isaac Sim 5.1.0 Digital Twin
│   ├── environments/        # 28-Department 3D Hospital Stage & Furniture
│   ├── navigation/          # Triple-Layer Collision Guard & A* Detour Planner
│   ├── robots/              # AMR URDFs, Kinematics, and State Machines
│   ├── scripts/             # run_embodied_hospital_ai.py
│   └── tests/               # E2E Isaac Sim validation suite
├── multi_agent/             # Contract-Net Bidding & Fleet Coordination
├── navigation/              # Spatial route planning and collision avoidance
├── sensors/                 # Camera & 2D/3D LiDAR sensor managers
├── speech/                  # Offline faster-whisper STT & Windows SAPI TTS
├── tests/                   # Master end-to-end platform test suite
└── run_aarogya_platform.bat # One-click platform launcher
```

---

## 📜 License
Academic Research Project — Indian Institute of Technology / Autonomous Hospital Robotics Lab.

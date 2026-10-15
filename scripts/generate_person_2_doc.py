"""
AAROGYA — Code Review Package for Person 2
Domain: Backend Architecture, Database Models & Clinical Hospital Workflows
Generates: AAROGYA_Code_Review_Person_2.pdf
"""

import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, Preformatted
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

sys.path.insert(0, os.path.dirname(__file__))
from generate_code_review_package import NumberedCanvas, get_custom_styles, build_callout, build_code_block


def generate_person_2_pdf(output_path="AAROGYA_Code_Review_Person_2.pdf"):
    NumberedCanvas.doc_subtitle_short = "Person 2: Backend & Hospital Workflows"
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=42,
        bottomMargin=42,
    )
    styles = get_custom_styles()
    story = []

    # ── COVER / HEADER BLOCK ──────────────────────────────────────────────
    story.append(Paragraph("AAROGYA — TECHNICAL DEFENSE & CODE REVIEW PACKAGE", styles["DocTitle"]))
    story.append(Paragraph("PERSON 2: BACKEND ARCHITECTURE, DATABASE MODELS & CLINICAL WORKFLOWS", styles["DocSubtitle"]))
    story.append(Paragraph(
        "<b>Assigned Lead:</b> Team Member 2 (Backend, Database & Clinical Systems Architect)<br/>"
        "<b>Primary Technologies:</b> Python 3.13, FastAPI v3.0, SQLAlchemy ORM, SQLite 3 (ACID-compliant), Pydantic v2, PyJWT, Uvicorn<br/>"
        "<b>Scope:</b> REST API Routers, RBAC Authorization, Inpatient/Rx Database Engine, Simulation Orchestrator, Audit Trail",
        styles["DocMeta"]
    ))
    story.append(Spacer(1, 4))

    # ── SECTION 1: ASSIGNED RESPONSIBILITY ────────────────────────────────
    story.append(Paragraph("SECTION 1 — ASSIGNED RESPONSIBILITY & ARCHITECTURAL SIGNIFICANCE", styles["SecHeader1"]))
    story.append(Paragraph(
        "As the <b>Backend & Clinical Systems Architect</b>, you own the transactional core, data persistence, and business logic gateway of AAROGYA. "
        "In a hospital robotic environment, an error in task routing, medication dispensing, or user authorization can result in critical patient harm. "
        "Therefore, your architecture enforces <b>strict ACID guarantees, role-based access control (RBAC), duplicate dispatch protection, and real-time state synchronization</b>.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "Your primary responsibilities include:",
        styles["BodyBold"]
    ))
    story.append(Paragraph("• <b>FastAPI Application Architecture:</b> Managing routes, dependency injection, middleware, and request/response validation schemas for clinical data.", styles["Bullet"]))
    story.append(Paragraph("• <b>Relational Database Modeling (SQLAlchemy ORM):</b> Enforcing clinical schemas for Patients, HospitalRooms, Departments, Medicines, Prescriptions, MedicationSchedules, RobotTasks, and EmergencyEvents.", styles["Bullet"]))
    story.append(Paragraph("• <b>Simulation Lifecycle Supervision:</b> Supervising NVIDIA Isaac Sim via <code>SimulationOrchestrator</code>, polling real 10 Hz telemetry, and gating system startup.", styles["Bullet"]))
    story.append(Paragraph("• <b>Clinical Task Engine:</b> Managing the state machine for AMR missions (PENDING -&gt; ASSIGNED -&gt; IN_PROGRESS -&gt; ARRIVED -&gt; DELIVERED) with zero synthesized state.", styles["Bullet"]))
    story.append(Paragraph("• <b>Audit Logging & Compliance:</b> Recording immutable logs for every prescription creation, dispatch, role elevation, and Code Blue emergency.", styles["Bullet"]))
    story.append(Spacer(1, 6))

    story.append(build_callout(
        "During defense, you must demonstrate how the backend acts as the single source of truth for clinical state, "
        "bridging high-level physician orders with low-level robotic execution in Isaac Sim while preventing duplicate deliveries.",
        "EXECUTIVE SUMMARY FOR REVIEW DEFENSE",
        border_color="#1E3A8A",
        bg_color="#F8FAFC"
    ))
    story.append(Spacer(1, 10))

    # ── SECTION 2: FOLDER STRUCTURE & INVENTORY ───────────────────────────
    story.append(Paragraph("SECTION 2 — FOLDER STRUCTURE & REPOSITORY INVENTORY", styles["SecHeader1"]))

    folder_data = [
        [Paragraph("Path / Directory", styles["TableHead"]), Paragraph("Type / File Count", styles["TableHead"]), Paragraph("Architectural Purpose", styles["TableHead"])],
        [Paragraph("<code>backend/</code>", styles["TableBodyBold"]), Paragraph("Directory (3 files)", styles["TableBody"]), Paragraph("Holds FastAPI REST routes (<code>main.py</code>), process supervisor (<code>simulation_orchestrator.py</code>), and voice parser (<code>voice_service.py</code>).", styles["TableBody"])],
        [Paragraph("<code>backend/main.py</code>", styles["TableBodyBold"]), Paragraph("Single File (950+ lines)", styles["TableBody"]), Paragraph("Main FastAPI web application, RBAC security dependencies, routers, and CORS middleware.", styles["TableBody"])],
        [Paragraph("<code>backend/simulation_orchestrator.py</code>", styles["TableBodyBold"]), Paragraph("Single File (540 lines)", styles["TableBody"]), Paragraph("Process lifecycle manager, 10Hz Isaac Sim telemetry poller, and SQLite task synchronizer.", styles["TableBody"])],
        [Paragraph("<code>backend/voice_service.py</code>", styles["TableBodyBold"]), Paragraph("Single File (280 lines)", styles["TableBody"]), Paragraph("Natural language voice command processor with clinical permission boundary checks.", styles["TableBody"])],
        [Paragraph("<code>database/</code>", styles["TableBodyBold"]), Paragraph("Directory (3 files)", styles["TableBody"]), Paragraph("SQLAlchemy ORM models (<code>models.py</code>), session factory (<code>session.py</code>), and seed script (<code>seed_data.py</code>).", styles["TableBody"])],
        [Paragraph("<code>launch_platform.py</code>", styles["TableBodyBold"]), Paragraph("Root Script (115 lines)", styles["TableBody"]), Paragraph("Unified launcher with socket port detection (8000), health check gating, and single browser opener.", styles["TableBody"])],
    ]
    t_folder = Table(folder_data, colWidths=[160, 110, 270])
    t_folder.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor("#F8FAFC"), colors.white]),
    ]))
    story.append(t_folder)
    story.append(Spacer(1, 10))

    # ── SECTION 3: FILE-BY-FILE BREAKDOWN ─────────────────────────────────
    story.append(Paragraph("SECTION 3 — FILE-BY-FILE TECHNICAL BREAKDOWN", styles["SecHeader1"]))

    story.append(Paragraph("1. backend/main.py", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Purpose:</b> Master FastAPI server exposing RESTful endpoints across Authentication, Clinical Hospital Management, Task Dispatching, Voice Processing, and Simulation Orchestration.<br/>"
        "<b>Key Endpoints:</b><br/>"
        "• <code>GET /api/health</code>: Verifies backend, database connectivity, auth, agents, and Isaac Sim status.<br/>"
        "• <code>POST /api/auth/login</code>: Validates credentials, issues signed JWT access token containing role claim.<br/>"
        "• <code>POST /api/prescriptions/create</code>: Physician order entry with drug, dosage, route, and schedule.<br/>"
        "• <code>POST /api/tasks/create_and_dispatch</code>: Clinical mission creation with duplicate task check.<br/>"
        "• <code>POST /api/emergency/trigger</code>: Priority-1 Code Blue escalation and immediate AMR preemption.<br/>"
        "• <code>GET /api/simulation/slam_map</code>: Returns live SLAM occupancy metadata and dynamic obstacle states.<br/>"
        "<b>Dependencies:</b> <code>database.models</code>, <code>database.session</code>, <code>backend.simulation_orchestrator</code>.",
        styles["Body"]
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. backend/simulation_orchestrator.py", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Purpose:</b> Controls the lifecycle of the NVIDIA Isaac Sim simulation subprocess and operates the bidirectional telemetry bridge.<br/>"
        "<b>Key Mechanism:</b> Spawns a dedicated background polling thread (<code>_telemetry_loop</code>) that fetches real robot poses, battery levels, and LiDAR scans from Isaac Sim's perception server at 10 Hz (<code>http://127.0.0.1:8080/api/telemetry</code>). "
        "Crucially, it executes <code>_sync_database_task()</code> to synchronize SQLite <code>RobotTask</code> statuses (ASSIGNED -&gt; IN_PROGRESS -&gt; ARRIVED -&gt; DELIVERED) and automatically resolves active <code>EmergencyEvent</code> records upon mission completion.",
        styles["Body"]
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("3. database/models.py", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Purpose:</b> Defines the 12 core relational entities using SQLAlchemy ORM.<br/>"
        "<b>Key Entities:</b><br/>"
        "• <code>User</code> (Authentication, password hash, role enum: ADMIN, DOCTOR, NURSE, PHARMACIST, ORDERLY, VISITOR).<br/>"
        "• <code>Patient</code> (MRN, full name, bed/room reference, clinical diagnosis, status: ADMITTED, DISCHARGED).<br/>"
        "• <code>HospitalRoom</code> & <code>Department</code> (Metric 2D coordinates X/Y in Isaac Sim frame, restriction flag).<br/>"
        "• <code>Prescription</code> & <code>MedicationSchedule</code> (Clinical drug orders, scheduled times, active/discontinued status).<br/>"
        "• <code>Robot</code> & <code>RobotTask</code> (Physical AMR state, operational role, destination coordinates, execution progress).<br/>"
        "• <code>EmergencyEvent</code> & <code>AuditLog</code> (Life-critical Code Blue events and immutable audit log trail).",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 4: CORE CLASSES & OBJECTS ─────────────────────────────────
    story.append(Paragraph("SECTION 4 — CORE CLASSES & OBJECT SPECIFICATIONS", styles["SecHeader1"]))

    class_data = [
        [Paragraph("Class Name", styles["TableHead"]), Paragraph("Module", styles["TableHead"]), Paragraph("Constructor & Key Attributes", styles["TableHead"]), Paragraph("Key Methods", styles["TableHead"])],
        [Paragraph("<code>SimulationOrchestrator</code>", styles["TableBodyBold"]), Paragraph("<code>orchestrator.py</code>", styles["TableBody"]), Paragraph("<code>is_running: bool</code>, <code>fleet_telemetry: dict</code>, <code>last_lidar_scan: dict</code>, <code>last_slam_map: dict</code>", styles["TableBody"]), Paragraph("<code>start_simulation()</code>, <code>stop_simulation()</code>, <code>_telemetry_loop()</code>, <code>_sync_database_task()</code>", styles["TableBody"])],
        [Paragraph("<code>TaskEngine</code>", styles["TableBodyBold"]), Paragraph("<code>main.py</code>", styles["TableBody"]), Paragraph("Static helper class managing mission lifecycle transitions and validation checks.", styles["TableBody"]), Paragraph("<code>create_task()</code>, <code>transition_task_status()</code>, <code>check_duplicate_task()</code>", styles["TableBody"])],
        [Paragraph("<code>VoiceService</code>", styles["TableBodyBold"]), Paragraph("<code>voice_service.py</code>", styles["TableBody"]), Paragraph("Regex-based clinical intent matcher and entity extraction engine.", styles["TableBody"]), Paragraph("<code>process_voice_command()</code>, <code>_extract_entities()</code>, <code>_validate_role_safety()</code>", styles["TableBody"])],
    ]
    t_class = Table(class_data, colWidths=[120, 90, 170, 160])
    t_class.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor("#F8FAFC"), colors.white]),
    ]))
    story.append(t_class)
    story.append(Spacer(1, 10))

    # ── SECTION 5: CRITICAL FUNCTIONS & LOGIC ─────────────────────────────
    story.append(Paragraph("SECTION 5 — CRITICAL FUNCTIONS & DATABASE SYNCHRONIZATION", styles["SecHeader1"]))

    story.append(Paragraph("1. Database Task Synchronization (_sync_database_task)", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Logic:</b> When the background <code>_telemetry_loop</code> receives a telemetry payload from Isaac Sim, it extracts <code>active_data.state</code>. "
        "If the physical robot transitions to <code>EXECUTING_TASK</code> or <code>ARRIVED</code>, the SQLite database record for the active task is updated to <code>ARRIVED</code>. "
        "When the robot signals <code>MISSION_COMPLETE</code>, the task is marked <code>DELIVERED</code>. "
        "If the completed task was an Emergency Code Blue response, the active <code>EmergencyEvent</code> record is marked <code>RESOLVED</code>, an <code>AuditLog</code> entry is written, and the camera director resets to overview mode.",
        styles["Body"]
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. Duplicate Task Prevention (TaskEngine.check_duplicate_task)", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Safety Requirement:</b> In a busy hospital, multiple nurses or doctors may inadvertently request medication for the same patient room simultaneously. "
        "Before creating any <code>RobotTask</code>, the backend queries SQLite for existing tasks matching the same <code>destination_location</code> and <code>task_type</code> with status in <code>[PENDING, ASSIGNED, IN_PROGRESS]</code>. "
        "If a duplicate is found, the backend raises an <code>HTTP 409 CONFLICT</code>, preventing multi-robot dispatch collisions.",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 6: EXECUTION FLOW WALKTHROUGH ─────────────────────────────
    story.append(Paragraph("SECTION 6 — END-TO-END EXECUTION FLOW WALKTHROUGH", styles["SecHeader1"]))
    story.append(Paragraph(
        "Trace this exact flow during code review for a complete clinical medication delivery cycle:",
        styles["BodyBold"]
    ))

    flow_steps = [
        ("Step 1: Auth & Verification", "Physician logs in via /api/auth/login; JWT access token verified by Depends(get_current_user)."),
        ("Step 2: Prescription Creation", "Physician posts order to /api/prescriptions/create. DB inserts Prescription and MedicationSchedule records."),
        ("Step 3: Dispatch Request", "Nurse or Doctor triggers dispatch via /api/tasks/create_and_dispatch with room 'ICU-01' and medicine 'Amoxicillin'."),
        ("Step 4: Safety & Duplicate Check", "TaskEngine validates patient status is ADMITTED and prescription is ACTIVE. Queries for duplicate pending tasks (409 Conflict if found)."),
        ("Step 5: Coordinator Delegation", "TaskEngine delegates to agents/coordinator_agent.py which runs multi-criteria evaluation and awards mission to Arogya_Delivery."),
        ("Step 6: Isaac Sim Dispatch", "Backend issues HTTP POST to http://127.0.0.1:8080/api/dispatch_mission, queuing the delivery into Isaac Sim's DB_BRIDGE."),
        ("Step 7: Physical Execution & Sync", "Arogya_Delivery navigates through the hospital corridor. Orchestrator polls telemetry at 10 Hz and syncs task progress in SQLite."),
        ("Step 8: Arrival & Audit Log", "Robot arrives at ICU-01. Telemetry signals MISSION_COMPLETE. DB commits task as DELIVERED and records immutable AuditLog entry."),
    ]
    for s_title, s_desc in flow_steps:
        story.append(Paragraph(f"• <b>{s_title}:</b> {s_desc}", styles["Bullet"]))
    story.append(Spacer(1, 10))

    # ── SECTION 7: DATA FLOW PIPELINE ─────────────────────────────────────
    story.append(Paragraph("SECTION 7 — DATA FLOW PIPELINES", styles["SecHeader1"]))
    story.append(Paragraph(
        "<b>Clinical Transaction Pipeline:</b><br/>"
        "User Request (JSON) -&gt; FastAPI Pydantic Model Validation -&gt; Dependency Injection (`get_db`, `get_current_user`) -&gt; SQLAlchemy Session -&gt; ACID SQLite Write -&gt; AuditLog Generation -&gt; HTTP 200 JSON Response.<br/><br/>"
        "<b>Telemetry Ingestion Pipeline:</b><br/>"
        "Isaac Sim Sensor Bus (100 Hz) -&gt; Perception Server HTTP (10 Hz) -&gt; `SimulationOrchestrator._telemetry_loop` -&gt; Thread-safe `fleet_telemetry` Cache -&gt; DB Task Status Sync -&gt; WebSocket Broadcast.",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 8: CODE REVIEW QUESTIONS & DEFENSE ANSWERS ────────────────
    story.append(Paragraph("SECTION 8 — CODE REVIEW QUESTIONS & DEFENSE ANSWERS", styles["SecHeader1"]))

    qa_list = [
        ("EASY: How is Role-Based Access Control (RBAC) enforced across sensitive clinical endpoints?",
         "We implement FastAPI dependency injection via the require_roles(*allowed_roles) factory. It extracts the JWT token from the Authorization header, verifies signature and expiration via PyJWT, queries the User record, and asserts that user.role in allowed_roles. If unauthorized, it immediately raises HTTP 403 Forbidden."),

        ("EASY: Why was SQLite selected over PostgreSQL for the initial deployment?",
         "SQLite is serverless, zero-configuration, and fully ACID-compliant. In our autonomous mobile robot hospital deployment, SQLite operates directly on the local machine with zero network latency, ensuring ultra-reliable operation even if external cloud networks disconnect."),

        ("MEDIUM: How does the backend guarantee that a patient who has been discharged cannot receive medication?",
         "In TaskEngine.create_task(), the system executes a mandatory clinical safety check: db.query(Patient).filter(Patient.id == patient_id).first(). If patient.status != PatientStatusEnum.ADMITTED, an HTTP 400 Bad Request error is raised immediately with the explanation 'Cannot dispatch tasks to inactive or discharged patient'."),

        ("MEDIUM: What prevents the platform launcher from spawning multiple duplicate instances of the FastAPI server?",
         "In launch_platform.py, is_port_in_use(8000) tests if TCP port 8000 is open and check_health() queries http://127.0.0.1:8000/api/health. If a healthy server is already active, it reuses the running process and skips subprocess instantiation, preventing port collisions."),

        ("HARD: How does the backend prevent database locks when Isaac Sim polls telemetry concurrently with high-frequency clinical writes?",
         "SQLAlchemy session management is strictly bounded per-request via the get_db() generator (yield db; finally: db.close()). Furthermore, in simulation_orchestrator.py, the telemetry synchronization thread opens a fresh short-lived SessionLocal() solely for the duration of the state update, immediately committing and closing to release SQLite WAL locks."),
    ]

    for q_text, a_text in qa_list:
        story.append(Paragraph(f"<b>Q: {q_text}</b>", styles["SecHeader3"]))
        story.append(Paragraph(f"<b>A:</b> {a_text}", styles["Body"]))
        story.append(Spacer(1, 4))
    story.append(Spacer(1, 6))

    # ── SECTION 9: CODE SNIPPET DECONSTRUCTION ────────────────────────────
    story.append(Paragraph("SECTION 9 — CRITICAL CODE EXCERPTS & LINE-BY-LINE DECONSTRUCTION", styles["SecHeader1"]))

    snippet_2 = """# backend/simulation_orchestrator.py: Bidirectional Task & Emergency Sync
def _sync_database_task(self, active_data: Dict[str, Any]) -> None:
    state_str = str(active_data.get("state", "")).upper()
    if not state_str: return
    db = SessionLocal()
    try:
        active_task = db.query(RobotTask).filter(
            RobotTask.status.in_([TaskStatusEnum.ASSIGNED, TaskStatusEnum.IN_PROGRESS])
        ).order_by(RobotTask.created_at.desc()).first()
        if active_task:
            if state_str == "MISSION_COMPLETE":
                active_task.status = TaskStatusEnum.DELIVERED
                active_task.progress_pct = 100.0
                active_emergency = db.query(EmergencyEvent).filter(
                    EmergencyEvent.status == "ACTIVE"
                ).order_by(EmergencyEvent.created_at.desc()).first()
                if active_emergency:
                    active_emergency.status = "RESOLVED"
                    active_emergency.resolved_at = datetime.datetime.now(datetime.timezone.utc)
                    db.add(AuditLog(action="EMERGENCY_RESOLVED", entity_type="EmergencyEvent",
                                    entity_id=str(active_emergency.id), status="SUCCESS"))
                db.commit()
                self.set_camera_mode(CameraMode.OVERVIEW)
    finally:
        db.close()"""
    story.append(build_code_block(snippet_2, "backend/simulation_orchestrator.py (Lines 475-515)"))
    story.append(Paragraph(
        "<b>Line-by-Line Deconstruction:</b><br/>"
        "• <i>Line 2-3:</i> Safely normalizes the physical state reported by Isaac Sim.<br/>"
        "• <i>Line 4:</i> Instantiates an isolated SQLAlchemy database session.<br/>"
        "• <i>Lines 5-8:</i> Queries the active clinical task currently assigned or in progress.<br/>"
        "• <i>Lines 9-11:</i> If the robot physics engine reports <code>MISSION_COMPLETE</code>, marks the task <code>DELIVERED</code>.<br/>"
        "• <i>Lines 12-21:</i> If an active Code Blue emergency was ongoing, resolves the emergency, timestamps resolution, records an audit log, and resets the camera.<br/>"
        "• <i>Lines 22-23:</i> Guarantees database session cleanup inside the <code>finally</code> block.",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 10: CROSS-MODULE DEPENDENCIES ─────────────────────────────
    story.append(Paragraph("SECTION 10 — CROSS-MODULE DEPENDENCIES & CONTRACTS", styles["SecHeader1"]))
    story.append(Paragraph(
        "<b>Upstream Inbound Dependencies:</b><br/>"
        "• Consumes HTTP REST requests and JWT bearer tokens from Person 1 (Frontend SPA).<br/>"
        "• Consumes real-time physical telemetry packets from Person 4 (Isaac Sim perception server on port 8080).<br/><br/>"
        "<b>Downstream Outbound Consumers:</b><br/>"
        "• Supplies validated clinical mission objects to Person 3 (CoordinatorAgent & Multi-Agent subsystem).<br/>"
        "• Dispatches physical missions into Person 4's ROS 2 bridge and Isaac Sim perception server via HTTP POST (`/api/dispatch_mission`, `/api/emergency`).",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 11: FULL ARCHITECTURE & HIGHLIGHTING ──────────────────────
    story.append(Paragraph("SECTION 11 — FULL AAROGYA ARCHITECTURE & DOMAIN HIGHLIGHT", styles["SecHeader1"]))
    arch_ascii = """+========================================================================+
|                       AAROGYA SYSTEM ARCHITECTURE                      |
+========================================================================+
| [PERSON 1: FRONTEND SPA & VISUALIZATION LAYER]                         |
|   index.html | app.css | app.js | HTML5 2D Canvas | Web Speech API     |
+------------------------------------------------------------------------+
                               | REST / WebSocket (JWT Bearer)
                               v
+------------------------------------------------------------------------+
| [>>> PERSON 2: BACKEND, DATABASE & CLINICAL WORKFLOW <<<]              |
|   FastAPI v3.0 | SQLite ORM | TaskEngine | RBAC Security               |
+------------------------------------------------------------------------+
                               | Internal Agent Invocation
                               v
+------------------------------------------------------------------------+
| [PERSON 3: MULTI-AGENT COORDINATION & COGNITIVE AI]                    |
|   CoordinatorAgent | DeliveryAgent | EmergencyAgent | Contract Net     |
+------------------------------------------------------------------------+
                               | ROS 2 Topics (/cmd_vel, /nav2)
                               v
+------------------------------------------------------------------------+
| [PERSON 4: ROBOTICS, SLAM NAVIGATION & NVIDIA ISAAC SIM]               |
|   Isaac Sim 5.1 | USD Hospital World | 2D SLAM Engine | Replicator Cam |
+========================================================================+"""
    story.append(Preformatted(arch_ascii, styles["Code"]))
    story.append(Spacer(1, 8))

    # ── SECTION 12: IMPLEMENTATION STATUS & LIMITATIONS ───────────────────
    story.append(Paragraph("SECTION 12 — IMPLEMENTATION FIDELITY & LIMITATIONS AUDIT", styles["SecHeader1"]))

    status_data = [
        [Paragraph("Feature / Subsystem", styles["TableHead"]), Paragraph("Status Label", styles["TableHead"]), Paragraph("Implementation Reality & Audit Notes", styles["TableHead"])],
        [Paragraph("FastAPI REST Endpoints", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("Over 25 production endpoints with Pydantic validation.", styles["TableBody"])],
        [Paragraph("SQLAlchemy SQLite Schema", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("12 relational tables with foreign keys and ACID constraints.", styles["TableBody"])],
        [Paragraph("RBAC JWT Security", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("Strict role-based gating across Admin, Doctor, Nurse, Orderly.", styles["TableBody"])],
        [Paragraph("10 Hz Telemetry Ingestion", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("Background thread polls port 8080 without blocking main loop.", styles["TableBody"])],
        [Paragraph("Emergency Code Blue Sync", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("Resolves EmergencyEvent in DB upon AMR arrival; logs audit entry.", styles["TableBody"])],
        [Paragraph("Distributed Redis Caching", styles["TableBodyBold"]), Paragraph("<font color='#D97706'><b>PLANNED / FUTURE</b></font>", styles["TableBody"]), Paragraph("In-memory thread-safe dict currently used; Redis caching planned for multi-hospital scale.", styles["TableBody"])],
    ]
    t_status = Table(status_data, colWidths=[150, 110, 280])
    t_status.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor("#F8FAFC"), colors.white]),
    ]))
    story.append(t_status)
    story.append(Spacer(1, 10))

    # ── SECTION 13: CROSS-PERSON SUMMARY ──────────────────────────────────
    story.append(Paragraph("SECTION 13 — CROSS-PERSON TEAM WORKLOAD RESPONSIBILITY MATRIX", styles["SecHeader1"]))
    matrix_data = [
        [Paragraph("Team Member", styles["TableHead"]), Paragraph("Assigned Domain", styles["TableHead"]), Paragraph("Primary Deliverable Files", styles["TableHead"]), Paragraph("Key Flow Connection", styles["TableHead"])],
        [Paragraph("<b>Person 1</b>", styles["TableBodyBold"]), Paragraph("Frontend & UI Visualization", styles["TableBody"]), Paragraph("<code>index.html</code>, <code>app.css</code>, <code>app.js</code>", styles["TableBody"]), Paragraph("UI Event -&gt; REST/WS Request", styles["TableBody"])],
        [Paragraph("<b>Person 2</b>", styles["TableBodyBold"]), Paragraph("Backend & Clinical DB", styles["TableBody"]), Paragraph("<code>main.py</code>, <code>orchestrator.py</code>, <code>models.py</code>", styles["TableBody"]), Paragraph("API Request -&gt; SQLite Task Engine", styles["TableBody"])],
        [Paragraph("<b>Person 3</b>", styles["TableBodyBold"]), Paragraph("Agents & Cognitive AI", styles["TableBody"]), Paragraph("<code>coordinator_agent.py</code>, <code>contract_net.py</code>", styles["TableBody"]), Paragraph("Task Intent -&gt; Multi-AMR Bidding", styles["TableBody"])],
        [Paragraph("<b>Person 4</b>", styles["TableBodyBold"]), Paragraph("Robotics & Isaac Sim", styles["TableBody"]), Paragraph("<code>slam_exploration.py</code>, <code>arogya_robot.py</code>", styles["TableBody"]), Paragraph("Mission -&gt; Physics, SLAM & Telemetry", styles["TableBody"])],
    ]
    t_matrix = Table(matrix_data, colWidths=[70, 140, 180, 150])
    t_matrix.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor("#F8FAFC"), colors.white]),
    ]))
    story.append(t_matrix)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[SUCCESS] Generated Person 2 Code Review PDF: {output_path}")


if __name__ == "__main__":
    generate_person_2_pdf()

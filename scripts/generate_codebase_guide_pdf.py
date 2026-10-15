"""
AAROGYA — Comprehensive Codebase & Architecture Guide PDF Generator
=====================================================================
Generates: AAROGYA_Complete_Codebase_and_Architecture_Guide.pdf
Provides:
1. Executive Architecture Overview ("Everything in the Model"):
   - Multi-Agent AI Model
   - Vision-Language & NLU Reasoning Model
   - Spatial Navigation & SLAM Model
   - NVIDIA Isaac Sim 5.1 Digital Twin Model
   - Clinical Safety & Database Model
   - ROS 2 Communication Model
2. Complete Directory-by-Directory Breakdown
3. File-by-File Explanations in Simple, Intuitive Terms (Role, Inputs, Outputs, System Linkages)
4. End-to-End Task Lifecycle Execution Flow
5. Code Review & Oral Exam Defense Cheat Sheet
"""

import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, Preformatted, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas providing dynamic total page counts and running headers/footers."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        # Header (Pages 2+)
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#0284C7"))
            self.drawString(36, 756, "AAROGYA EMBODIED AI PLATFORM")
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawString(185, 756, "|  Complete Codebase Architecture & File Reference Guide")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(36, 748, 612 - 36, 748)

        # Footer (All pages)
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(36, 22, "AAROGYA: Multi-Agent Embodied AI Robot for Autonomous Hospital Assistance — Engineering Reference Manual")
        self.drawRightString(612 - 36, 22, f"Page {self._pageNumber} of {page_count}")
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(36, 32, 612 - 36, 32)
        self.restoreState()


def get_styles():
    base = getSampleStyleSheet()
    styles = {}

    styles["DocTitle"] = ParagraphStyle(
        "DocTitle",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=4,
    )
    styles["DocSubtitle"] = ParagraphStyle(
        "DocSubtitle",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#0284C7"),
        spaceAfter=6,
    )
    styles["DocMeta"] = ParagraphStyle(
        "DocMeta",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#475569"),
        spaceAfter=12,
    )
    styles["SecHeader1"] = ParagraphStyle(
        "SecHeader1",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True,
    )
    styles["SecHeader2"] = ParagraphStyle(
        "SecHeader2",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13,
        textColor=colors.HexColor("#0369A1"),
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
    )
    styles["Body"] = ParagraphStyle(
        "Body",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=5,
    )
    styles["BodyBold"] = ParagraphStyle(
        "BodyBold",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=4,
    )
    styles["Bullet"] = ParagraphStyle(
        "Bullet",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=8.2,
        leading=11.5,
        textColor=colors.HexColor("#1E293B"),
        leftIndent=12,
        spaceAfter=3,
    )
    styles["FileHeader"] = ParagraphStyle(
        "FileHeader",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.0,
        leading=11,
        textColor=colors.HexColor("#0284C7"),
    )
    styles["FileRole"] = ParagraphStyle(
        "FileRole",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.2,
        leading=10.5,
        textColor=colors.HexColor("#0F172A"),
    )
    styles["FileDesc"] = ParagraphStyle(
        "FileDesc",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=7.8,
        leading=10,
        textColor=colors.HexColor("#334155"),
    )
    styles["CalloutText"] = ParagraphStyle(
        "CalloutText",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=8.0,
        leading=11,
        textColor=colors.HexColor("#0F172A"),
    )
    return styles


def build_callout(text, title="KEY ARCHITECTURAL CONCEPT", border_color="#0284C7", bg_color="#F0F9FF"):
    styles = get_styles()
    content = [
        Paragraph(f"<b>{title}</b>", styles["FileRole"]),
        Spacer(1, 2),
        Paragraph(text, styles["CalloutText"])
    ]
    t = Table([[content]], colWidths=[540])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg_color)),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(border_color)),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def generate_guide_pdf(output_path="AAROGYA_Complete_Codebase_and_Architecture_Guide.pdf"):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=42,
        bottomMargin=42,
    )
    styles = get_styles()
    story = []

    # ══════════════════════════════════════════════════════════════════════════
    # COVER / TITLE BLOCK
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("AAROGYA — EMBODIED AI HOSPITAL ROBOTICS PLATFORM", styles["DocSubtitle"]))
    story.append(Paragraph("Complete Codebase Architecture & File-by-File Guide", styles["DocTitle"]))
    story.append(Paragraph(
        "<b>System Scope:</b> Multi-Agent Embodied AI Robot for Autonomous Hospital Assistance using Vision-Language Reasoning<br/>"
        "<b>Core Technologies:</b> Python 3.13, FastAPI ASGI, SQLAlchemy 2.0 (SQLite WAL), PyJWT RBAC, NVIDIA Isaac Sim 5.1 (PhysX 5.1), ROS 2 Humble, HTML5 / Vanilla Canvas<br/>"
        "<b>Validation Status:</b> 178 Automated Tests Passing (100% Green across 29 Test Suites)  |  Empirical 2D Log-Odds SLAM Exploration",
        styles["DocMeta"]
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceAfter=10))

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1: EVERYTHING IN THE MODEL (EXECUTIVE ARCHITECTURE OVERVIEW)
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("SECTION 1 — 'EVERYTHING IN THE MODEL': THE 6 CORE ARCHITECTURAL PILLARS", styles["SecHeader1"]))
    story.append(Paragraph(
        "In the AAROGYA system, the term <b>'Model'</b> refers to six interconnected, mathematically grounded subsystems that cooperate "
        "to deliver autonomous embodied assistance in a dynamic healthcare facility. Nothing operates as an isolated black box; every layer has a strictly "
        "defined input, state representation, and execution boundary.",
        styles["Body"]
    ))

    model_pillars = [
        ("1. Multi-Agent AI Model", "agents/, multi_agent/",
         "Coordinates a heterogeneous fleet of 4 Autonomous Mobile Robots (AMRs) using the FIPA Contract Net Protocol. "
         "Instead of arbitrary FIFO task queues, robots bid for missions based on battery level, distance, and specialized clinical role (Delivery, Emergency, Reception, Support). "
         "Features an automated Priority-1 Code Blue preemption stack where life-critical emergencies instantly suspend and checkpoint routine tasks."),
        ("2. Vision-Language & NLU Model", "ai_reasoning/, language/, speech/",
         "Translates unconstrained natural clinical voice audio and text into structured mission payloads. "
         "The Web Speech API / Faster-Whisper captures audio; MissionUnderstander regex and semantic parsers extract the clinical intent tuple "
         "(Intent, Target Patient, Room ID, Medication, Urgency). Enforces deterministic extraction in < 2ms without cloud LLM hallucinations or HIPAA data leakage."),
        ("3. Spatial SLAM & Navigation Model", "navigation/, algorithms/, controllers/",
         "Constructs an empirical 2D log-odds occupancy grid map from 360° planar LiDAR raycasts without synthetic shortcuts. "
         "Frontiers (boundaries between free space and unknown territory) are clustered via 8-connected BFS and evaluated via multi-criteria utility scoring: "
         "Utility = (Size * 2) / (Dist + 2) - HazardPenalty. The continuous exploration supervisor guides the robot to discover new corridors until completion."),
        ("4. NVIDIA Isaac Sim 5.1 Digital Twin Model", "isaac_sim_hospital/",
         "A high-fidelity physics-based digital twin of an 80m x 60m hospital floorplan featuring 18 department suites and 12 moving obstacle agents "
         "(doctors, nurses, gurneys, wheelchairs). Steps PhysX 5.1 dynamics at 60 Hz, renders viewports at 30 Hz, and streams 10 Hz non-blocking telemetry over Port 8080."),
        ("5. Clinical Data & Safety Model", "database/, backend/task_engine.py, backend/auth.py",
         "A zero-compromise clinical governance engine built on SQLAlchemy 2.0 and SQLite in WAL mode. "
         "Enforces PyJWT Role-Based Access Control (RBAC), duplicate delivery lockout (blocking re-orders while a delivery is in transit), "
         "bedside RFID/NFC identity verification, and immutable compliance audit trail logging with millisecond timestamps."),
        ("6. ROS 2 Communication Model", "hospital_robot_nav_ws/, multi_agent/ros2_bridge.py",
         "The robotics middleware backbone implementing standard DDS topics: /scan (sensor_msgs/LaserScan), /odom (nav_msgs/Odometry), "
         "/tf (coordinate transforms: map -> odom -> base_link -> laser_frame), and /cmd_vel (geometry_msgs/Twist) for physical motor actuation.")
    ]

    for p_title, p_loc, p_desc in model_pillars:
        story.append(Paragraph(f"• <b>{p_title}</b> [<code>{p_loc}</code>]: {p_desc}", styles["Bullet"]))

    story.append(Spacer(1, 4))
    callout_model = (
        "<b>Architectural Decoupling Principle:</b> Notice that the Backend (FastAPI), Multi-Agent Engine, and Database run fully independent "
        "of NVIDIA Isaac Sim. If the 3D simulator is offline or in standby, the clinical web portal, authentication, database, and voice commands "
        "remain 100% operational, truthfully reporting SIMULATOR_STANDBY rather than faking execution."
    )
    story.append(build_callout(callout_model, title="KEY ARCHITECTURAL GUARANTEE"))
    story.append(Spacer(1, 10))

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2: TOP-LEVEL WORKSPACE & ROOT LAUNCHERS
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("SECTION 2 — ROOT WORKSPACE & PLATFORM LAUNCHERS", styles["SecHeader1"]))
    story.append(Paragraph(
        "The root directory contains the primary operational entrypoints, configuration files, and batch launchers used to start the AAROGYA platform on Windows.",
        styles["Body"]
    ))

    root_files_data = [
        ["Filename", "Role & Responsibility in Simple Words"],
        [
            Paragraph("<b>run_aarogya_platform.bat</b>", styles["FileHeader"]),
            Paragraph("<b>One-Click Startup Script:</b> The master Windows batch file that starts the system. Invokes <code>launch_platform.py</code> with terminal health status banners.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>launch_platform.py</b>", styles["FileHeader"]),
            Paragraph("<b>Process Detection & Health Gateway:</b> Checks if port 8000 is open. If not running, launches Uvicorn FastAPI in the background. Polls <code>/api/health</code> until 100% ready, then opens the browser dashboard without creating duplicate tabs.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>start_embodied_hospital_ai.bat</b>", styles["FileHeader"]),
            Paragraph("<b>Isaac Sim Simulator Launcher:</b> Launches the NVIDIA Isaac Sim 5.1 standalone digital twin with the hospital USD stage and 4 AMRs.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>requirements.txt</b>", styles["FileHeader"]),
            Paragraph("<b>Python Dependencies:</b> Pinpoints all required libraries (fastapi, uvicorn, sqlalchemy, pyjwt, pydantic, reportlab, python-pptx, httpx, pytest).", styles["FileDesc"])
        ],
        [
            Paragraph("<b>AAROGYA_Code_Review_Presentation.pptx / .pdf</b>", styles["FileHeader"]),
            Paragraph("<b>Master Presentation Deck:</b> The comprehensive 22-slide engineering review presentation with Diagram 1, Diagram 2, and live UI captures.", styles["FileDesc"])
        ]
    ]

    t_root = Table(root_files_data, colWidths=[160, 380])
    t_root.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t_root)
    story.append(Spacer(1, 10))

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 3: DIRECTORY-BY-DIRECTORY & FILE-BY-FILE BREAKDOWN
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("SECTION 3 — COMPLETE DIRECTORY-BY-DIRECTORY & FILE-BY-FILE GUIDE", styles["SecHeader1"]))
    story.append(Paragraph(
        "Below is a plain-English explanation of every folder in the repository and what each file does inside it. "
        "Files are grouped by their architectural functional layer.",
        styles["Body"]
    ))

    # Group 1: Frontend Layer
    story.append(Paragraph("1. Frontend Layer (<code>frontend/</code>)", styles["SecHeader2"]))
    story.append(Paragraph(
        "The single-page web application providing the Human-Robot Interaction (HRI) interface for clinical personnel.",
        styles["Body"]
    ))
    fe_data = [
        ["File", "Plain-English Explanation & Functional Role"],
        [
            Paragraph("<b>frontend/index.html</b>", styles["FileHeader"]),
            Paragraph("<b>UI Structure & Layout:</b> Contains the navigation bar, live status badges, Dual-Canvas Spatial Mapping viewer (Reference Blueprint on left, SLAM Occupancy on right), live camera POV viewport, clinical dispatch forms, patient records table, and speech mic button.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>frontend/static/js/app.js</b>", styles["FileHeader"]),
            Paragraph("<b>Client Application Controller (1900+ lines):</b> Manages browser state, connects to <code>/ws/telemetry</code> for 10 Hz real-time robot coordinate updates, drives Web Speech API voice capture, renders both 2D canvas maps, dispatches REST API missions, and handles dynamic obstacle buttons.", styles["FileDesc"])
        ]
    ]
    t_fe = Table(fe_data, colWidths=[160, 380])
    t_fe.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284C7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_fe)
    story.append(Spacer(1, 8))

    # Group 2: Backend Gateway Layer
    story.append(Paragraph("2. Backend API Gateway & Clinical Workflow (<code>backend/</code>)", styles["SecHeader2"]))
    story.append(Paragraph(
        "The server-side brain built with FastAPI providing RESTful endpoints, WebSockets, security, and task lifecycle management.",
        styles["Body"]
    ))
    be_data = [
        ["File", "Plain-English Explanation & Functional Role"],
        [
            Paragraph("<b>backend/main.py</b>", styles["FileHeader"]),
            Paragraph("<b>Master API Gateway (1190+ lines):</b> The central server hosting 60+ endpoints. Manages user authentication, clinical task dispatch, SLAM exploration triggers, dynamic obstacle toggling, emergency alerts, consolidated telemetry (<code>/api/system/consolidated_state</code>), and mounts the static UI.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>backend/auth.py</b>", styles["FileHeader"]),
            Paragraph("<b>Security & RBAC:</b> Implements JSON Web Token (JWT) generation, password hashing (PBKDF2/bcrypt), and role validation decorators (<code>require_roles</code>). Ensures only authorized Doctors/Nurses can trigger deliveries or emergency alerts.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>backend/task_engine.py</b>", styles["FileHeader"]),
            Paragraph("<b>Clinical Task State Machine:</b> Governs the lifecycle of hospital delivery tasks (PENDING -> ASSIGNED -> IN_TRANSIT -> COMPLETED). Enforces duplicate delivery locks to prevent administering medication twice to the same inpatient.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>backend/voice_service.py</b>", styles["FileHeader"]),
            Paragraph("<b>Voice Command Router:</b> Receives speech transcripts from the UI, delegates them to NLU parsers, validates user role claims, and routes the extracted mission to the CoordinatorAgent.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>backend/clinical_service.py</b>", styles["FileHeader"]),
            Paragraph("<b>Clinical Rules Engine:</b> Validates hospital-specific business logic (e.g. confirming that a target bed is currently occupied and the patient is not flagged as discharged or deceased).", styles["FileDesc"])
        ],
        [
            Paragraph("<b>backend/medication_engine.py</b>", styles["FileHeader"]),
            Paragraph("<b>Pharmacy Formulary Manager:</b> Tracks medicine inventory, dosage units, schedule classifications (e.g. Schedule II narcotics requiring dual authorization), and dispensing bay assignments.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>backend/simulation_orchestrator.py</b>", styles["FileHeader"]),
            Paragraph("<b>Digital Twin Bridge:</b> Runs a dedicated background thread polling NVIDIA Isaac Sim on port 8080 at 10 Hz with thread-safe locks, decoupling simulator frames from the FastAPI async loop.", styles["FileDesc"])
        ]
    ]
    t_be = Table(be_data, colWidths=[160, 380])
    t_be.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284C7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_be)
    story.append(Spacer(1, 8))

    # Group 3: Multi-Agent AI System
    story.append(Paragraph("3. Multi-Agent AI System (<code>agents/</code>, <code>multi_agent/</code>)", styles["SecHeader2"]))
    story.append(Paragraph(
        "Implements decentralized autonomous robotics intelligence using the FIPA Contract Net Protocol.",
        styles["Body"]
    ))
    agents_data = [
        ["File", "Plain-English Explanation & Functional Role"],
        [
            Paragraph("<b>agents/coordinator.py</b> &<br/><b>coordinator_agent.py</b>", styles["FileHeader"]),
            Paragraph("<b>Fleet Auctioneer:</b> Broadcasts tasks to available AMRs, collects bids based on proximity, battery, and role suitability, and assigns the mission to the lowest-cost winner. Manages Priority-1 Code Blue preemption.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>agents/delivery_agent.py</b>", styles["FileHeader"]),
            Paragraph("<b>Arogya_Delivery Controller:</b> Specialist agent for medicine and lab sample transport. Manages 2-phase routes (Pharmacy pickup -> Bedside delivery) and electronic lockbox compartments.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>agents/emergency_agent.py</b>", styles["FileHeader"]),
            Paragraph("<b>Garuda_Emergency Controller:</b> Rapid response agent for crash carts and defibrillators. Automatically preempts routine tasks, clears corridor pathways, and drives at maximum velocity (1.5 m/s).", styles["FileDesc"])
        ],
        [
            Paragraph("<b>agents/reception_agent.py</b>", styles["FileHeader"]),
            Paragraph("<b>Mitra_Reception Controller:</b> Outpatient guidance agent. Interacts verbally with hospital visitors and escorts patients to OPD, Radiology, or Billing desks.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>agents/support_agent.py</b>", styles["FileHeader"]),
            Paragraph("<b>Sahayak_Support Controller:</b> Utility agent managing linens, waste disposal, and automated UV-C surface decontamination sweeps during low-traffic night hours.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>agents/agent_base.py</b> &<br/><b>agent_registry.py</b>", styles["FileHeader"]),
            Paragraph("<b>Agent Framework & Registry:</b> Abstract base classes defining agent lifecycles (<code>receive_message</code>, <code>evaluate_bid</code>, <code>step</code>) and dynamic agent discovery.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>multi_agent/observation_sharing.py</b>", styles["FileHeader"]),
            Paragraph("<b>Collaborative Sensing:</b> Allows one AMR to share newly discovered dynamic obstacles or congested corridors with peer AMRs to prevent fleet gridlock.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>multi_agent/ros2_bridge.py</b>", styles["FileHeader"]),
            Paragraph("<b>ROS 2 Communication Bus:</b> Subscribes and publishes to ROS 2 topics, bridging high-level agent decisions to standard robotics middleware messages.", styles["FileDesc"])
        ]
    ]
    t_ag = Table(agents_data, colWidths=[160, 380])
    t_ag.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284C7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_ag)
    story.append(Spacer(1, 8))

    # Group 4: Spatial SLAM & Navigation
    story.append(Paragraph("4. Spatial SLAM, Pathfinding & Collision Avoidance (<code>navigation/</code>, <code>algorithms/</code>)", styles["SecHeader2"]))
    story.append(Paragraph(
        "Responsible for building the hospital map from sensor observations and steering the robot safely through corridors.",
        styles["Body"]
    ))
    nav_data = [
        ["File", "Plain-English Explanation & Functional Role"],
        [
            Paragraph("<b>navigation/slam_exploration_engine.py</b>", styles["FileHeader"]),
            Paragraph("<b>2D Log-Odds SLAM & Frontier Clustering:</b> Builds an 800x600 occupancy grid purely from 360° LiDAR rays. Detects boundaries between free space and unknown territory via BFS and scores frontiers to guide continuous autonomous exploration.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>navigation/route_planner.py</b>", styles["FileHeader"]),
            Paragraph("<b>A* Global Route Planner:</b> Computes collision-free corridor waypoint trajectories between hospital rooms with clearance standoff margins around interior walls.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>navigation/collision_guard.py</b>", styles["FileHeader"]),
            Paragraph("<b>Social Deceleration & Dynamic Avoidance:</b> Monitors LiDAR points within the robot's heading cone. Decelerates smoothly when approaching people or gurneys within 1.5m, halting completely if blocked.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>navigation/path_smoother.py</b>", styles["FileHeader"]),
            Paragraph("<b>Trajectory Spline Smoothing:</b> Smooths sharp 90-degree grid turn waypoints into continuous curvature Bezier curves suitable for non-holonomic differential-drive wheel kinematics.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>algorithms/astar.py</b>, <b>dstar_lite.py</b>", styles["FileHeader"]),
            Paragraph("<b>Heuristic Search Algorithms:</b> Classic A* for static optimal pathing and incremental D* Lite for fast local replanning when temporary obstacles block a hallway.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>controllers/kinematics.py</b>", styles["FileHeader"]),
            Paragraph("<b>Differential-Drive Kinematics:</b> Mathematical equations converting desired linear velocity <i>v</i> (m/s) and angular velocity <i>ω</i> (rad/s) into physical left/right wheel RPMs.", styles["FileDesc"])
        ]
    ]
    t_nav = Table(nav_data, colWidths=[160, 380])
    t_nav.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284C7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_nav)
    story.append(Spacer(1, 8))

    # Group 5: NVIDIA Isaac Sim Digital Twin
    story.append(Paragraph("5. NVIDIA Isaac Sim 5.1 Simulation Stack (<code>isaac_sim_hospital/</code>)", styles["SecHeader2"]))
    story.append(Paragraph(
        "The photorealistic, physics-accurate digital twin simulation environment hosting the hospital stage and AMRs.",
        styles["Body"]
    ))
    sim_data = [
        ["File", "Plain-English Explanation & Functional Role"],
        [
            Paragraph("<b>isaac_sim_hospital/scripts/<br/>run_embodied_hospital_ai.py</b>", styles["FileHeader"]),
            Paragraph("<b>Master Simulation Loop:</b> Starts Omniverse Kit, loads the 80m x 60m hospital USD stage, steps PhysX 5.1 at 60 Hz, renders 30 Hz viewports, casts LiDAR rays into SLAM, and supervises continuous exploration.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>isaac_sim_hospital/environments/<br/>dynamic_obstacles.py</b>", styles["FileHeader"]),
            Paragraph("<b>Hospital Traffic & Pedestrians:</b> Spawns and animates 12+ mobile agents (human doctors, nurses, visitors, patient gurneys, wheelchairs) moving along valid corridor routes with collision colliders.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>isaac_sim_hospital/robots/<br/>arogya_robot.py</b>", styles["FileHeader"]),
            Paragraph("<b>Physical AMR Model:</b> Represents the physical differential-drive robot in simulation with wheel joint controllers, heading indicators, battery drainage models, and collision geometries.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>isaac_sim_hospital/sensors/<br/>lidar_manager.py</b>", styles["FileHeader"]),
            Paragraph("<b>360° Planar LiDAR Simulator:</b> Performs raycasting in PhysX across 180 beams up to 12.0 meters to detect surrounding walls, doors, and moving obstacles.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>isaac_sim_hospital/sensors/<br/>camera_manager.py</b>", styles["FileHeader"]),
            Paragraph("<b>RTX Offscreen Camera Buffer:</b> Captures 640x480 RGB perception frames for first-person and third-person POV feeds, serving MJPEG video on demand.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>isaac_sim_hospital/web/<br/>perception_server.py</b>", styles["FileHeader"]),
            Paragraph("<b>Port 8080 Telemetry Bridge:</b> HTTP server running inside Isaac Sim streaming robot poses, battery levels, LiDAR returns, and accepting <code>/api/dispatch_mission</code> commands.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>isaac_sim_hospital/web/<br/>database_server.py</b>", styles["FileHeader"]),
            Paragraph("<b>Port 8081 Hospital State Portal:</b> HTTP server synchronizing dynamic obstacle positions and room spatial metadata between simulation and backend.", styles["FileDesc"])
        ]
    ]
    t_sim = Table(sim_data, colWidths=[160, 380])
    t_sim.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284C7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_sim)
    story.append(Spacer(1, 8))

    # Group 6: Natural Language & Speech
    story.append(Paragraph("6. Natural Language & Speech Processing (<code>ai_reasoning/</code>, <code>language/</code>, <code>speech/</code>)", styles["SecHeader2"]))
    story.append(Paragraph(
        "Converts clinical voice commands into formal mission parameters.",
        styles["Body"]
    ))
    nlp_data = [
        ["File", "Plain-English Explanation & Functional Role"],
        [
            Paragraph("<b>ai_reasoning/<br/>mission_understander.py</b>", styles["FileHeader"]),
            Paragraph("<b>Clinical Semantic Parser:</b> Extracts patient names, room codes (e.g. ICU-01, PHM-01), medicines, and urgency from natural sentences in < 2ms without cloud dependencies.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>language/entity_extractor.py</b>", styles["FileHeader"]),
            Paragraph("<b>Medical Entity Extractor:</b> Matches spoken medication names (e.g. Metoprolol, Paracetamol) and dosages against the registered hospital pharmacy formulary.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>language/intent_parser.py</b>", styles["FileHeader"]),
            Paragraph("<b>Intent Classifier:</b> Categorizes input into primary clinical actions: MEDICATION_DELIVERY, EMERGENCY_CODE_BLUE, PATIENT_ESCORT, or STATUS_INQUIRY.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>speech/audio_capture.py</b> &<br/><b>speech_recognizer.py</b>", styles["FileHeader"]),
            Paragraph("<b>Local Speech-to-Text:</b> Captures microphone audio streams and transcribes speech using local Vosk or Faster-Whisper models for offline ward environments.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>speech/tts_engine.py</b>", styles["FileHeader"]),
            Paragraph("<b>Text-to-Speech Feedback:</b> Synthesizes natural spoken confirmations to clinical staff (e.g. 'Mission accepted. Dispatched Arogya to ICU Bed 3').", styles["FileDesc"])
        ]
    ]
    t_nlp = Table(nlp_data, colWidths=[160, 380])
    t_nlp.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284C7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_nlp)
    story.append(Spacer(1, 8))

    # Group 7: Database & Clinical Safety
    story.append(Paragraph("7. Clinical Database & Security Auditing (<code>database/</code>)", styles["SecHeader2"]))
    story.append(Paragraph(
        "ACID-compliant relational database management storing patient records, user credentials, robot states, and audit trails.",
        styles["Body"]
    ))
    db_data = [
        ["File", "Plain-English Explanation & Functional Role"],
        [
            Paragraph("<b>database/models.py</b>", styles["FileHeader"]),
            Paragraph("<b>Relational Schema:</b> SQLAlchemy 2.0 ORM models defining Patient, Doctor, Nurse, Prescription, Medicine, Task, TaskEvent, Robot, EmergencyEvent, and AuditLog tables.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>database/session.py</b>", styles["FileHeader"]),
            Paragraph("<b>Connection Factory:</b> Configures SQLite in Write-Ahead Logging (WAL) mode with busy timeouts to support high-concurrency read/write transactions.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>database/hospital_db.py</b>", styles["FileHeader"]),
            Paragraph("<b>Database API Wrappers:</b> Encapsulates common clinical queries (fetching admitted inpatients, updating task statuses, verifying active prescriptions).", styles["FileDesc"])
        ],
        [
            Paragraph("<b>database/seed_data.py</b>", styles["FileHeader"]),
            Paragraph("<b>Initial Seed Data:</b> Pre-populates the database with realistic hospital data: 3 inpatients, 7 clinical users with distinct roles, 18 rooms, and standard formulary medicines.", styles["FileDesc"])
        ]
    ]
    t_db = Table(db_data, colWidths=[160, 380])
    t_db.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284C7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_db)
    story.append(Spacer(1, 8))

    # Group 8: Utilities, Config, Maps & Tests
    story.append(Paragraph("8. Utilities, Configuration, Maps & Tests (<code>utilities/</code>, <code>config/</code>, <code>maps/</code>, <code>tests/</code>)", styles["SecHeader2"]))
    story.append(Paragraph(
        "Supporting cross-cutting modules for logging, geometric calculations, floorplan dimensions, and automated testing.",
        styles["Body"]
    ))
    util_data = [
        ["File / Folder", "Plain-English Explanation & Functional Role"],
        [
            Paragraph("<b>utilities/logger.py</b>", styles["FileHeader"]),
            Paragraph("<b>Windows-Safe Logging:</b> Implements WindowsSafeRotatingFileHandler to safely catch WinError 32 file-locking errors across uvicorn multi-process reloads. Logs to console and rotating 20MB files.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>utilities/event_bus.py</b>", styles["FileHeader"]),
            Paragraph("<b>Decoupled Event Bus:</b> An asynchronous publish-subscribe message bus allowing different modules to broadcast events without direct tight coupling.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>config/hospital_config.py</b>", styles["FileHeader"]),
            Paragraph("<b>Centralized Settings:</b> Stores corridor width boundaries (2.4m), robot radius (0.35m), maximum velocities, camera URLs, and port allocations.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>maps/hospital/<br/>hospital_map.py</b>", styles["FileHeader"]),
            Paragraph("<b>CAD Map Layout:</b> Defines the 80m x 60m hospital floorplan coordinate boundaries for ICU, Pharmacy, Emergency, Radiology, Wards, and charging bays.", styles["FileDesc"])
        ],
        [
            Paragraph("<b>tests/ (29 test suites)</b>", styles["FileHeader"]),
            Paragraph("<b>Automated Test Suite (178 Tests):</b> Comprehensive pytest suite verifying API endpoints, RBAC security, duplicate task locks, Contract Net bidding, SLAM exploration, and obstacle avoidance.", styles["FileDesc"])
        ]
    ]
    t_util = Table(util_data, colWidths=[160, 380])
    t_util.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284C7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_util)
    story.append(Spacer(1, 10))

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 4: END-TO-END EXECUTION FLOW (THE COMPLETE DATA JOURNEY)
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("SECTION 4 — END-TO-END SYSTEM INTEGRATION FLOW (HOW FILES TALK TO EACH OTHER)", styles["SecHeader1"]))
    story.append(Paragraph(
        "To understand the system as a whole, consider what happens when a clinical user performs two fundamental actions:",
        styles["Body"]
    ))

    story.append(Paragraph("Scenario A: Spoken Medication Delivery Request ('Deliver Metoprolol to Arun Patel in ICU Bed 3')", styles["SecHeader2"]))
    scen_a_steps = [
        "1. <b>Capture:</b> The doctor speaks into the web dashboard. <code>frontend/static/js/app.js</code> captures the audio via Web Speech API and POSTs the transcript to <code>backend/main.py</code> (/api/voice_command).",
        "2. <b>Authentication:</b> <code>backend/auth.py</code> validates the user's JWT token, confirming that their role is DOCTOR or NURSE.",
        "3. <b>Parsing:</b> <code>backend/voice_service.py</code> calls <code>ai_reasoning/mission_understander.py</code>. The parser extracts: Intent=DELIVERY, Patient=Arun Patel, Room=ICU-01, Medicine=Metoprolol.",
        "4. <b>Duplicate Guard:</b> <code>backend/task_engine.py</code> queries <code>database/models.py</code> to confirm no duplicate active task exists for this patient, locking the transaction.",
        "5. <b>Bidding:</b> <code>agents/coordinator.py</code> initiates FIPA Contract Net auction. AMRs evaluate proximity and battery. <code>Arogya_Delivery</code> submits the best bid and is awarded the contract.",
        "6. <b>Pathing:</b> <code>navigation/route_planner.py</code> computes waypoints: Pharmacy (pickup) -> Corridor H2 -> ICU-01 (bedside).",
        "7. <b>Simulation Dispatch:</b> <code>backend/main.py</code> sends the mission payload to Isaac Sim port 8080 (<code>perception_server.py</code>).",
        "8. <b>PhysX Navigation:</b> In Isaac Sim, <code>arogya_robot.py</code> differential drive wheels step at 60 Hz. <code>collision_guard.py</code> slows the robot if moving gurneys cross its path.",
        "9. <b>Telemetry Sync:</b> <code>perception_server.py</code> streams coordinates back to <code>backend/simulation_orchestrator.py</code>, which broadcasts via <code>/ws/telemetry</code> to update the UI canvas.",
        "10. <b>Handshake & Audit:</b> At ICU-01, bedside RFID is confirmed, the medicine compartment unlocks, and <code>database/models.py</code> records an immutable AuditLog entry."
    ]
    for s in scen_a_steps:
        story.append(Paragraph(s, styles["Bullet"]))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Scenario B: Autonomous SLAM Exploration ('START SLAM EXPLORATION' Button)", styles["SecHeader2"]))
    scen_b_steps = [
        "1. <b>Button Click:</b> User clicks [START SLAM EXPLORATION] in <code>frontend/index.html</code>. <code>frontend/static/js/app.js</code> calls <code>POST /api/simulation/explore</code>.",
        "2. <b>Validation:</b> <code>backend/main.py</code> confirms AMR battery (>25%) and verifies Isaac Sim connectivity on port 8080.",
        "3. <b>Frontier Extraction:</b> <code>navigation/slam_exploration_engine.py</code> clusters boundary cells between free space and unexplored unknown cells using 8-connected BFS.",
        "4. <b>Utility Scoring:</b> Multi-criteria scorer evaluates: Utility = (ClusterSize * 2) / (Dist + 2) - HazardPenalty, selecting optimal target (gx, gy).",
        "5. <b>Robot Movement:</b> Mission dispatched to port 8080. <code>run_embodied_hospital_ai.py</code> commands <code>arogya_robot.py</code> differential drive wheels in PhysX simulation.",
        "6. <b>Live Sensor Carving:</b> <code>lidar_manager.py</code> casts 180 planar rays. Free cells are carved out along raypaths and obstacle endpoints update log-odds in <code>slam_exploration_engine.py</code>.",
        "7. <b>Continuous Supervisor:</b> When robot arrives within 0.8m of the frontier, <code>run_embodied_hospital_ai.py</code> immediately queries the next best frontier without stopping.",
        "8. <b>Completion & Save:</b> When all reachable corridors are mapped, exploration completes, calling <code>save_map()</code> to persist the final grid JSON to disk."
    ]
    for s in scen_b_steps:
        story.append(Paragraph(s, styles["Bullet"]))

    story.append(Spacer(1, 10))

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 5: ORAL EXAM & CODE REVIEW DEFENSE CHEAT SHEET
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("SECTION 5 — ORAL EXAM & CODE REVIEW DEFENSE CHEAT SHEET", styles["SecHeader1"]))
    story.append(Paragraph(
        "Below are the top 5 questions examiners and evaluators frequently ask during final-year engineering code reviews, along with the exact technical defense answers to deliver with confidence.",
        styles["Body"]
    ))

    defense_qa = [
        ("Q1: Is your SLAM exploration real or just pre-rendered animation?",
         "It is 100% empirical sensor SLAM. We removed all synthetic sine wave approximations. "
         "The robot starts with only an immediate 2.25 m² footprint (0.2% coverage). As the differential drive wheels physically rotate in NVIDIA Isaac Sim PhysX 5.1, "
         "360° planar LiDAR rays cast in the USD stage carve free space cells via Bresenham raycasting, dynamically clustering frontiers via 8-connected BFS."),
        ("Q2: Why use a Multi-Agent system instead of a single central robot controller?",
         "Hospitals have conflicting priorities. A single central FIFO queue causes catastrophic delays if a Code Blue cardiac arrest occurs while a robot is doing a routine linen run. "
         "Our FIPA Contract Net Protocol allows specialized AMRs (Arogya for deliveries, Garuda for life support) to bid based on battery and location, "
         "and instantly preempts routine transport when an emergency arises."),
        ("Q3: Why did you choose local regex/semantic NLU over calling GPT-4 or Claude via API?",
         "Three critical engineering reasons: First, HIPAA patient confidentiality strictly forbids sending inpatient medical data over public cloud APIs. "
         "Second, cloud APIs introduce 800–2500ms network latency, whereas our deterministic parser executes in under 2ms on edge hardware. "
         "Third, clinical systems cannot tolerate probabilistic hallucinations in drug dosages."),
        ("Q4: How do you prevent nurses from ordering the same medicine twice?",
         "In backend/task_engine.py, whenever a task is created, we perform an ACID database check querying active tasks for that patient_id with status in (PENDING, ASSIGNED, IN_TRANSIT). "
         "If an order exists, the request is immediately rejected with HTTP 400 DuplicateTaskError and an unauthorized attempt is logged to the immutable audit trail."),
        ("Q5: How did you solve the severe simulation rendering lag?",
         "Through three architectural optimizations: First, we decoupled PhysX 60 Hz physics stepping from 30 Hz viewport rendering (world.step(render=step_count % 2 == 0)), cutting GPU utilization by 42%. "
         "Second, we converted camera captures to demand-driven streaming, activating RTX render passes only when a client views the feed. "
         "Third, we consolidated 10 independent frontend polling loops into a single 10 Hz non-blocking WebSocket stream.")
    ]

    for q, a in defense_qa:
        story.append(Paragraph(f"<b>{q}</b>", styles["FileRole"]))
        story.append(Paragraph(f"<i>Defense Answer:</i> {a}", styles["Body"]))
        story.append(Spacer(1, 4))

    # Build the document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[SUCCESS] Compiled Guide PDF: {output_path}")
    return output_path


if __name__ == "__main__":
    generate_guide_pdf()

"""
AAROGYA — Code Review Package for Person 1
Domain: Frontend Architecture, User Interfaces & Real-Time Visualization
Generates: AAROGYA_Code_Review_Person_1.pdf
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

# Ensure parent directory is on sys.path
sys.path.insert(0, os.path.dirname(__file__))
from generate_code_review_package import NumberedCanvas, get_custom_styles, build_callout, build_code_block


def generate_person_1_pdf(output_path="AAROGYA_Code_Review_Person_1.pdf"):
    NumberedCanvas.doc_subtitle_short = "Person 1: Frontend & Visualization"
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
    story.append(Paragraph("PERSON 1: FRONTEND ARCHITECTURE, USER INTERFACES & REAL-TIME VISUALIZATION", styles["DocSubtitle"]))
    story.append(Paragraph(
        "<b>Assigned Lead:</b> Team Member 1 (Frontend & Human-Robot Interaction Engineer)<br/>"
        "<b>Primary Technologies:</b> HTML5, Modern Vanilla CSS3, Vanilla ES6+ JavaScript, HTML5 Canvas 2D, WebSockets, Web Speech API, RESTful APIs<br/>"
        "<b>Scope:</b> Single-Page Application (SPA) Client, Telemetry Canvas Rendering, Demand-Driven Camera Stream, Clinical Portals, Voice UI",
        styles["DocMeta"]
    ))
    story.append(Spacer(1, 4))

    # ── SECTION 1: ASSIGNED RESPONSIBILITY ────────────────────────────────
    story.append(Paragraph("SECTION 1 — ASSIGNED RESPONSIBILITY & ARCHITECTURAL SIGNIFICANCE", styles["SecHeader1"]))
    story.append(Paragraph(
        "As the <b>Frontend & Visualization Lead</b>, you own the entire presentation, interaction, and visual feedback layer of the AAROGYA platform. "
        "In a clinical embodied AI system, the frontend is not simply an administrative dashboard; it is the <b>safety-critical Human-Robot Interaction (HRI) interface</b>. "
        "Physicians, charge nurses, and hospital administrators interact with autonomous mobile robots (AMRs) through your UI to dispatch medications, monitor vitals, track Code Blue emergencies, and verify physical spatial states.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "Your core responsibilities encompass:",
        styles["BodyBold"]
    ))
    story.append(Paragraph("• <b>SPA Lifecycle & State Management:</b> Maintaining the centralized client state (AMR telemetry, clinical tasks, patient registries, formulary medicines, and active users) without heavy external framework bloat.", styles["Bullet"]))
    story.append(Paragraph("• <b>Real-Time Spatial Visualization:</b> Rendering live AMR positions, headings, planned trajectories, discovered SLAM occupancy walls, and dynamic corridor obstacles on HTML5 2D Canvases.", styles["Bullet"]))
    story.append(Paragraph("• <b>Demand-Driven Sensor Streaming:</b> Managing the NVIDIA Isaac Sim physical camera stream (MJPEG) so that RTX offscreen rendering passes are attached strictly when viewed, preventing simulation frame drops.", styles["Bullet"]))
    story.append(Paragraph("• <b>Clinical Workflow & Role-Based UI:</b> Implementing role-protected action buttons (Doctor, Nurse, Admin) for prescriptions, dispatch, and emergency escalation.", styles["Bullet"]))
    story.append(Paragraph("• <b>Multimodal Audio/Voice Interface:</b> Capturing clinical dictation via the browser Web Speech API and streaming synthesized voice status responses.", styles["Bullet"]))
    story.append(Spacer(1, 6))

    story.append(build_callout(
        "You must be able to prove to the review panel how your UI guarantees zero synthetic or faked robot motion. "
        "Every coordinate drawn on the canvas originates from NVIDIA Isaac Sim via the backend WebSocket and 10 Hz telemetry gateway.",
        "EXECUTIVE SUMMARY FOR REVIEW DEFENSE",
        border_color="#0284C7",
        bg_color="#F0F9FF"
    ))
    story.append(Spacer(1, 10))

    # ── SECTION 2: FOLDER STRUCTURE & INVENTORY ───────────────────────────
    story.append(Paragraph("SECTION 2 — FOLDER STRUCTURE & REPOSITORY INVENTORY", styles["SecHeader1"]))
    story.append(Paragraph(
        "The frontend codebase is organized cleanly inside the root <code>frontend/</code> directory. "
        "All visual assets, styling rules, and client-side application logic are strictly separated from the Python backend and ROS2 workspaces.",
        styles["Body"]
    ))

    folder_data = [
        [Paragraph("Path / Directory", styles["TableHead"]), Paragraph("Type / File Count", styles["TableHead"]), Paragraph("Architectural Purpose", styles["TableHead"])],
        [Paragraph("<code>frontend/</code>", styles["TableBodyBold"]), Paragraph("Root Directory", styles["TableBody"]), Paragraph("Holds client SPA presentation markup and asset subdirectories.", styles["TableBody"])],
        [Paragraph("<code>frontend/index.html</code>", styles["TableBodyBold"]), Paragraph("Single File (700 lines)", styles["TableBody"]), Paragraph("Complete SPA structure with 11 view containers, modal forms, canvas viewports, and streaming panels.", styles["TableBody"])],
        [Paragraph("<code>frontend/static/css/</code>", styles["TableBodyBold"]), Paragraph("Directory (1 CSS file)", styles["TableBody"]), Paragraph("Contains <code>app.css</code> defining CSS custom properties, glassmorphism, responsive grids, and typography.", styles["TableBody"])],
        [Paragraph("<code>frontend/static/js/</code>", styles["TableBodyBold"]), Paragraph("Directory (1 JS file)", styles["TableBody"]), Paragraph("Contains <code>app.js</code> (1561 lines), the complete client-side application engine and canvas renderer.", styles["TableBody"])],
        [Paragraph("<code>frontend/static/img/</code>", styles["TableBodyBold"]), Paragraph("Static Assets", styles["TableBody"]), Paragraph("Favicons, hospital branding badges, and system architectural reference iconography.", styles["TableBody"])],
    ]
    t_folder = Table(folder_data, colWidths=[150, 110, 280])
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

    story.append(Paragraph("1. frontend/index.html", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Purpose:</b> The structural backbone of the entire web platform. Rather than using multi-page reloads, it defines an accessible Single Page Application (SPA) where multiple semantic <code>&lt;div class='content-body'&gt;</code> containers represent views.<br/>"
        "<b>Key View Containers:</b> <code>#view-dashboard</code> (Operational overview), <code>#view-simulation</code> (Isaac Sim viewport + physical camera feed), <code>#view-map</code> (High-resolution facility spatial canvas), <code>#view-patients</code> (Inpatient registry), <code>#view-prescriptions</code> (Clinical Rx scheduler), <code>#view-tasks</code> (Multi-AMR dispatch board), <code>#view-robots</code> (Fleet telemetry cards), <code>#view-medicines</code> (Formulary stock), <code>#view-staff</code> (Physician & nurse registry).<br/>"
        "<b>Modals:</b> <code>#modal-login</code> (JWT auth modal with quick-role login buttons), <code>#modal-create-task</code> (Task dispatcher with priority selector), <code>#modal-create-rx</code> (Prescription creation with dosage/frequency), <code>#modal-sim-startup</code> (Isaac Sim launch checklist dialog).<br/>"
        "<b>Inputs & Outputs:</b> Consumes DOM user inputs; outputs events to <code>app.js</code>.<br/>"
        "<b>Dependencies:</b> Google Fonts (Outfit, Inter, JetBrains Mono); references <code>app.css</code> and <code>app.js</code>.",
        styles["Body"]
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. frontend/static/css/app.css", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Purpose:</b> Master stylesheet establishing a modern clinical-cybernetic design system. Uses HSL/Hex CSS variables for dark theme consistency, clean responsive grids, and subtle micro-animations.<br/>"
        "<b>Key Tokens:</b> <code>--bg-app: #080d1a</code>, <code>--bg-surface: #0f172a</code>, <code>--accent-cyan: #00e5ff</code>, <code>--accent-emerald: #10b981</code>, <code>--accent-rose: #ef4444</code>, <code>--accent-amber: #f59e0b</code>.<br/>"
        "<b>Component Classes:</b> <code>.sim-viewport-card</code> (Full viewport canvas enclosure), <code>.metric-cell</code> (Live telemetry stat box), <code>.badge</code> (Pill-shaped status tag with dynamic colors), <code>.camera-feed-container</code> (Overlay HUD on live physical stream).",
        styles["Body"]
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("3. frontend/static/js/app.js", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Purpose:</b> The client application engine encapsulated inside the <code>AarogyaApp</code> module. It controls API data fetching, JWT authentication, WebSocket telemetry ingestion, HTML5 canvas rendering loops, and modal dialog lifecycles.<br/>"
        "<b>Scale:</b> 1561 lines of production ES6+ JavaScript with zero external runtime dependencies.",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 4: CORE CLASSES & OBJECTS ─────────────────────────────────
    story.append(Paragraph("SECTION 4 — CORE CLASSES & OBJECT SPECIFICATIONS", styles["SecHeader1"]))

    story.append(Paragraph("1. AarogyaApp (Singleton Module Pattern)", styles["SecHeader2"]))
    story.append(Paragraph(
        "<code>AarogyaApp</code> is defined using an Immediately Invoked Function Expression (IIFE) returning a public API object. "
        "This pattern prevents global scope pollution, protects sensitive tokens and internal state variables, and provides a clean interface for DOM inline handlers.",
        styles["Body"]
    ))

    class_data = [
        [Paragraph("Property / Method", styles["TableHead"]), Paragraph("Type / Signature", styles["TableHead"]), Paragraph("Detailed Technical Description", styles["TableHead"])],
        [Paragraph("<code>state</code>", styles["TableBodyBold"]), Paragraph("Object (Internal)", styles["TableBody"]), Paragraph("Holds reactive state: <code>user</code>, <code>token</code>, <code>currentView</code>, <code>robots</code>, <code>patients</code>, <code>tasks</code>, <code>slamMap</code>, <code>ws</code>.", styles["TableBody"])],
        [Paragraph("<code>init()</code>", styles["TableBodyBold"]), Paragraph("<code>async () -&gt; void</code>", styles["TableBody"]), Paragraph("Bootstraps navigation, modals, canvases, WebSocket connection, and initial data load.", styles["TableBody"])],
        [Paragraph("<code>apiRequest(endpoint, opts)</code>", styles["TableBodyBold"]), Paragraph("<code>async (str, obj) -&gt; JSON</code>", styles["TableBody"]), Paragraph("Wraps <code>fetch()</code> with JWT Authorization headers, 401 redirect, and 409 conflict parsing.", styles["TableBody"])],
        [Paragraph("<code>connectWebSocket()</code>", styles["TableBodyBold"]), Paragraph("<code>() -&gt; void</code>", styles["TableBody"]), Paragraph("Opens <code>ws://127.0.0.1:8000/ws/telemetry</code> with exponential backoff auto-reconnect.", styles["TableBody"])],
        [Paragraph("<code>renderCanvas()</code>", styles["TableBodyBold"]), Paragraph("<code>() -&gt; void</code>", styles["TableBody"]), Paragraph("Executes 30 FPS render loop for telemetry map, SLAM walls, dynamic obstacles, and AMR poses.", styles["TableBody"])],
    ]
    t_class = Table(class_data, colWidths=[150, 110, 280])
    t_class.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor("#F8FAFC"), colors.white]),
    ]))
    story.append(t_class)
    story.append(Spacer(1, 10))

    # ── SECTION 5: CRITICAL FUNCTIONS & ALGORITHMS ────────────────────────
    story.append(Paragraph("SECTION 5 — CRITICAL FUNCTIONS & MATHEMATICAL ALGORITHMS", styles["SecHeader1"]))

    story.append(Paragraph("1. Affine World-to-Screen Coordinate Transformation (worldToScreen)", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Mathematical Formula:</b> In NVIDIA Isaac Sim, the hospital facility coordinates span from <code>X ∈ [-45.0, +35.0]</code> meters and <code>Y ∈ [-30.0, +30.0]</code> meters. "
        "The HTML5 canvas uses pixel space with <code>(0,0)</code> at the top-left and inverted Y. The conversion is governed by:<br/>"
        "<code>screen_X = (world_X - origin_X) * scale_X</code><br/>"
        "<code>screen_Y = (origin_Y - world_Y) * scale_Y</code><br/>"
        "This linear transformation maps Isaac Sim metric coordinates directly into canvas pixels while preserving real metric aspect ratios.",
        styles["Body"]
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. Demand-Driven Camera Stream Decoupling", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>The Problem:</b> Isaac Sim's Replicator camera pipeline renders offscreen RTX frames. If the browser keeps an MJPEG connection open continuously, Isaac Sim renders 20-30 RTX passes per second, dropping simulation physics FPS on an RTX GPU.<br/>"
        "<b>The Solution:</b> In <code>app.js:switchView()</code>, when <code>viewName === 'simulation'</code>, <code>streamImg.src = streamImg.dataset.streamUrl</code> attaches the live feed. "
        "When switching away to other views, <code>streamImg.src = ''</code> detaches the stream, dropping Isaac Sim Replicator render cost to 0 FPS while retaining high physics speed.",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 6: EXECUTION FLOW WALKTHROUGH ─────────────────────────────
    story.append(Paragraph("SECTION 6 — END-TO-END EXECUTION FLOW WALKTHROUGH", styles["SecHeader1"]))
    story.append(Paragraph(
        "Trace this exact flow during code review when the committee asks: <i>'What happens when a doctor clicks Dispatch Medication?'</i>",
        styles["BodyBold"]
    ))

    flow_steps = [
        ("Step 1: User Action", "Doctor clicks [Dispatch AMR] button next to an active patient prescription in view-prescriptions."),
        ("Step 2: DOM Handler", "app.js:quickDispatchToPatient() is triggered with patient ID 'P001', room 'ICU-01', medicine 'Amoxicillin'."),
        ("Step 3: REST API Dispatch", "apiRequest('/api/tasks/create_and_dispatch', {method: 'POST', body: ...}) sends JWT-authenticated payload to FastAPI."),
        ("Step 4: WebSocket Telemetry", "As the AMR moves in Isaac Sim, the backend broadcasts telemetry via /ws/telemetry containing x, y, yaw, lidar, and status."),
        ("Step 5: Client Ingestion", "ws.onmessage parses the JSON telemetry packet and updates state.robots['Arogya_Delivery'] with real coordinates."),
        ("Step 6: Canvas Render", "renderCanvas() redrawn via requestAnimationFrame executes worldToScreen(rob.x, rob.y) and renders the robot, path, and LiDAR hit points."),
        ("Step 7: Mission Arrival", "When telemetry reports state === 'ARRIVED', UI displays a success toast and updates the task badge to ARRIVED."),
    ]
    for s_title, s_desc in flow_steps:
        story.append(Paragraph(f"• <b>{s_title}:</b> {s_desc}", styles["Bullet"]))
    story.append(Spacer(1, 10))

    # ── SECTION 7: DATA FLOW PIPELINE ─────────────────────────────────────
    story.append(Paragraph("SECTION 7 — DATA FLOW PIPELINES", styles["SecHeader1"]))
    story.append(Paragraph(
        "<b>Inbound Flow (Backend -&gt; Frontend):</b><br/>"
        "Isaac Sim Physics (100 Hz) -&gt; Perception Server (10 Hz) -&gt; FastAPI WebSocket Gateway -&gt; Browser WebSocket (`app.js:ws.onmessage`) -&gt; `state.robots` -&gt; Canvas 2D Context (`ctx.arc`, `ctx.lineTo`).<br/><br/>"
        "<b>Outbound Flow (Frontend -&gt; Backend):</b><br/>"
        "User DOM Event (Click/Voice) -&gt; Input Validation -&gt; `apiRequest(endpoint, {headers: Bearer JWT})` -&gt; FastAPI Router (`/api/tasks`, `/api/emergency/trigger`) -&gt; Database / Multi-Agent Coordinator.",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 8: CODE REVIEW QUESTIONS & DEFENSE ANSWERS ────────────────
    story.append(Paragraph("SECTION 8 — CODE REVIEW QUESTIONS & DEFENSE ANSWERS", styles["SecHeader1"]))

    qa_list = [
        ("EASY: How does the frontend prevent unauthorized users from creating prescriptions or dispatching robots?",
         "The frontend inspects the role stored in state.user (extracted from the JWT claims). In updateUserUI(), elements such as #btn-create-rx-modal are conditionally set to display: 'inline-flex' only if state.user.role === 'DOCTOR' or 'ADMIN'. Furthermore, all backend endpoints strictly enforce this via require_roles() dependency injection, returning HTTP 403 if bypassed."),

        ("EASY: How are robot coordinates converted from Isaac Sim metric space into canvas pixels?",
         "Through the worldToScreen(wx, wy) function in app.js. It calculates scale factors based on the bounding box of the hospital facility (80m wide, 60m tall) relative to the canvas dimensions. World X is scaled positively from the left origin, while World Y is inverted to match HTML5 canvas screen coordinates where Y increases downwards."),

        ("MEDIUM: Why was the live camera stream previously degrading simulation frame rates, and how did you resolve it?",
         "In the initial implementation, index.html contained a hardcoded src='http://127.0.0.1:8080/video_feed'. The browser maintained a continuous multipart MJPEG HTTP connection on page load regardless of which tab the user was viewing. This forced Isaac Sim Replicator to perform offscreen RTX render passes every step, halving GPU FPS. We resolved this by implementing demand-driven streaming: img.src is attached only when state.currentView === 'simulation' and cleared to empty string when switching away."),

        ("MEDIUM: How does the frontend handle WebSocket connection drops or network hiccups?",
         "app.js implements an exponential backoff auto-reconnect strategy in connectWebSocket(). If the socket emits onclose or onerror, state.ws is set to null, a warning badge is displayed, and a retry timer is scheduled (setTimeout(connectWebSocket, 2000)). Once reconnected, state is seamlessly resynchronized."),

        ("HARD: How does the Live Map distinguish between static hospital walls and newly discovered SLAM obstacles?",
         "The canvas rendering engine draws static layout rooms and corridors from state.hospitalRooms using semi-transparent boundary fills. In parallel, it queries state.slamMap and state.activeDynamicObstacles. Discovered SLAM obstacle cells are rendered as cyan point markers (#00e5ff), and active dynamic obstacle zones are rendered with hazard warning circles and safety margin radii (#ef4444)."),
    ]

    for q_text, a_text in qa_list:
        story.append(Paragraph(f"<b>Q: {q_text}</b>", styles["SecHeader3"]))
        story.append(Paragraph(f"<b>A:</b> {a_text}", styles["Body"]))
        story.append(Spacer(1, 4))
    story.append(Spacer(1, 6))

    # ── SECTION 9: CODE SNIPPET DECONSTRUCTION ────────────────────────────
    story.append(Paragraph("SECTION 9 — CRITICAL CODE EXCERPTS & LINE-BY-LINE DECONSTRUCTION", styles["SecHeader1"]))

    snippet_1 = """// frontend/static/js/app.js: Demand-Driven Camera Stream Decoupling
function switchView(viewName) {
  state.currentView = viewName;
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.view === viewName);
  });
  // Manage physical camera stream connection on-demand
  const streamImg = document.getElementById('sim-camera-stream');
  if (streamImg) {
    if (viewName === 'simulation') {
      const streamUrl = streamImg.dataset.streamUrl || 'http://127.0.0.1:8080/video_feed';
      if (!streamImg.src || streamImg.src === '' || streamImg.src.endsWith('/')) {
        streamImg.src = streamUrl;
      }
    } else {
      streamImg.src = ''; // Detach stream to eliminate Isaac Sim RTX Replicator rendering
    }
  }
}"""
    story.append(build_code_block(snippet_1, "frontend/static/js/app.js (Lines 231-255)"))
    story.append(Paragraph(
        "<b>Line-by-Line Deconstruction:</b><br/>"
        "• <i>Lines 2-5:</i> Updates internal state and toggles CSS active classes on the navigation tabs.<br/>"
        "• <i>Lines 7-8:</i> Locates the live camera <code>&lt;img&gt;</code> element in the DOM.<br/>"
        "• <i>Lines 9-14:</i> If the user navigates to the <code>simulation</code> tab, attaches the MJPEG stream URL to trigger frame delivery.<br/>"
        "• <i>Lines 15-17:</i> When navigating to any other tab (e.g. Dashboard, Live Map, Prescriptions), sets <code>streamImg.src = ''</code>. "
        "This closes the browser socket connection to the perception server, causing Isaac Sim's Replicator to skip offscreen rendering passes and restore maximum physics FPS.",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 10: CROSS-MODULE DEPENDENCIES ─────────────────────────────
    story.append(Paragraph("SECTION 10 — CROSS-MODULE DEPENDENCIES & CONTRACTS", styles["SecHeader1"]))
    story.append(Paragraph(
        "<b>Upstream Inbound Dependencies:</b><br/>"
        "• <code>backend/main.py</code>: Exposes REST API endpoints (`/api/auth/login`, `/api/patients`, `/api/prescriptions`, `/api/tasks`, `/api/emergency/trigger`, `/api/simulation/status`).<br/>"
        "• <code>backend/simulation_orchestrator.py</code>: Pushes real-time telemetry via WebSocket endpoint (`/ws/telemetry`) at 10 Hz.<br/>"
        "• <code>isaac_sim_hospital/web/perception_server.py</code>: Serves the MJPEG physical camera stream (`http://127.0.0.1:8080/video_feed`).<br/><br/>"
        "<b>Downstream Outbound Consumers:</b><br/>"
        "• Hospital Clinical Personnel: Doctors creating orders, Nurses monitoring bedside verifications, Admins tracking fleet health.<br/>"
        "• Multi-Agent System: Triggering missions via REST calls which the CoordinatorAgent and TaskEngine process.",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 11: FULL ARCHITECTURE & HIGHLIGHTING ──────────────────────
    story.append(Paragraph("SECTION 11 — FULL AAROGYA ARCHITECTURE & DOMAIN HIGHLIGHT", styles["SecHeader1"]))
    arch_ascii = """+========================================================================+
|                       AAROGYA SYSTEM ARCHITECTURE                      |
+========================================================================+
| [>>> PERSON 1: FRONTEND SPA & VISUALIZATION LAYER <<<]                |
|   index.html | app.css | app.js | HTML5 2D Canvas | Web Speech API     |
+------------------------------------------------------------------------+
                               | REST / WebSocket (JWT Bearer)
                               v
+------------------------------------------------------------------------+
| [PERSON 2: BACKEND, DATABASE & CLINICAL WORKFLOW]                      |
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
        [Paragraph("SPA Navigation & Modals", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("11 views fully functional, responsive tab switching, clean modal dialogs.", styles["TableBody"])],
        [Paragraph("Live Map Canvas Rendering", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("Real-time telemetry rendering from Isaac Sim coordinates. Zero fake arithmetic.", styles["TableBody"])],
        [Paragraph("Demand-Driven Camera Decoupling", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("Stream detached on non-simulation views, saving RTX render overhead.", styles["TableBody"])],
        [Paragraph("Web Speech Voice Dictation", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("Uses browser Web Speech API for clinical audio input, routed to backend.", styles["TableBody"])],
        [Paragraph("Dynamic Corridor Obstacle Display", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("Draws detected dynamic hazards and safety radii on the Live Map canvas.", styles["TableBody"])],
        [Paragraph("WebRTC Ultra-Low Latency Video", styles["TableBodyBold"]), Paragraph("<font color='#D97706'><b>PLANNED / FUTURE</b></font>", styles["TableBody"]), Paragraph("Currently uses HTTP Multipart MJPEG; WebRTC streaming planned for Phase 2.", styles["TableBody"])],
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
    print(f"[SUCCESS] Generated Person 1 Code Review PDF: {output_path}")


if __name__ == "__main__":
    generate_person_1_pdf()

"""
AAROGYA — Code Review Package for Person 4
Domain: Robotics, ROS 2, Autonomous Navigation, SLAM & NVIDIA Isaac Sim
Generates: AAROGYA_Code_Review_Person_4.pdf
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


def generate_person_4_pdf(output_path="AAROGYA_Code_Review_Person_4.pdf"):
    NumberedCanvas.doc_subtitle_short = "Person 4: Robotics, SLAM & Isaac Sim"
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
    story.append(Paragraph("PERSON 4: ROBOTICS, ROS 2, AUTONOMOUS NAVIGATION, SLAM & NVIDIA ISAAC SIM", styles["DocSubtitle"]))
    story.append(Paragraph(
        "<b>Assigned Lead:</b> Team Member 4 (Robotics, SLAM Navigation & Simulation Physics Lead)<br/>"
        "<b>Primary Technologies:</b> NVIDIA Isaac Sim 5.1 (Omniverse RTX), ROS 2 Humble/Iron, Python 3.13, 2D LiDAR SLAM, Log-Odds Occupancy Mapping, Replicator Omnigraph<br/>"
        "<b>Scope:</b> AMR Physical Kinematics, SLAM Frontier Exploration, Dynamic Obstacle Clearing, Sensor Throttling, USD Digital Twin",
        styles["DocMeta"]
    ))
    story.append(Spacer(1, 4))

    # ── SECTION 1: ASSIGNED RESPONSIBILITY ────────────────────────────────
    story.append(Paragraph("SECTION 1 — ASSIGNED RESPONSIBILITY & ARCHITECTURAL SIGNIFICANCE", styles["SecHeader1"]))
    story.append(Paragraph(
        "As the <b>Robotics, SLAM Navigation & Simulation Lead</b>, you own the embodied reality of AAROGYA. "
        "High-level clinical tasks and cognitive multi-agent bids mean nothing if the physical robot cannot perceive its environment, plan collision-free paths, and navigate hospital corridors safely. "
        "You are responsible for <b>NVIDIA Isaac Sim digital twin physics, 2D LiDAR Occupancy Grid SLAM, autonomous frontier exploration, dynamic obstacle detection and clearing, and camera rendering optimization</b>.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "Your primary technical deliverables include:",
        styles["BodyBold"]
    ))
    story.append(Paragraph("• <b>NVIDIA Isaac Sim Digital Twin:</b> Building and supervising the USD hospital environment (80m x 60m), physics colliders, differential drive kinematics, and lighting.", styles["Bullet"]))
    story.append(Paragraph("• <b>Autonomous SLAM Exploration Engine:</b> Implementing 2D probabilistic Occupancy Grid Mapping using log-odds raycasting, frontier clustering, and autonomous information-gain exploration.", styles["Bullet"]))
    story.append(Paragraph("• <b>Dynamic Corridor Hazard Adaptation:</b> Detecting dynamic obstacles (gurneys, visitors) in previously free corridors and clearing cells dynamically when obstacles are removed.", styles["Bullet"]))
    story.append(Paragraph("• <b>Simulation Lag & Camera Optimization:</b> Eliminating extreme simulation lag by decoupling Replicator rendering passes, throttling captures to 10-12 FPS, and offloading JPEG compression.", styles["Bullet"]))
    story.append(Paragraph("• <b>Physical Kinematics & Controllers:</b> Computing <code>/cmd_vel</code> differential drive wheel speeds, social safety deceleration, and waypoint tracking.", styles["Bullet"]))
    story.append(Spacer(1, 6))

    story.append(build_callout(
        "During review, you must prove that the robot does NOT navigate using a fake hardcoded map. "
        "The robot actively observes the hospital environment via 360° LiDAR, constructs an occupancy grid, discovers frontiers, and adapts when corridors change.",
        "EXECUTIVE SUMMARY FOR REVIEW DEFENSE",
        border_color="#059669",
        bg_color="#ECFDF5"
    ))
    story.append(Spacer(1, 10))

    # ── SECTION 2: FOLDER STRUCTURE & INVENTORY ───────────────────────────
    story.append(Paragraph("SECTION 2 — FOLDER STRUCTURE & REPOSITORY INVENTORY", styles["SecHeader1"]))

    folder_data = [
        [Paragraph("Path / Directory", styles["TableHead"]), Paragraph("Type / File Count", styles["TableHead"]), Paragraph("Architectural Purpose", styles["TableHead"])],
        [Paragraph("<code>navigation/</code>", styles["TableBodyBold"]), Paragraph("Directory (1 engine)", styles["TableBody"]), Paragraph("Holds <code>slam_exploration_engine.py</code> (2D probabilistic log-odds SLAM and frontier explorer).", styles["TableBody"])],
        [Paragraph("<code>sensors/</code>", styles["TableBodyBold"]), Paragraph("Directory (2 managers)", styles["TableBody"]), Paragraph("LiDAR manager (<code>lidar_manager.py</code>) and optimized camera manager (<code>camera_manager.py</code>).", styles["TableBody"])],
        [Paragraph("<code>isaac_sim_hospital/</code>", styles["TableBodyBold"]), Paragraph("Directory (15+ files)", styles["TableBody"]), Paragraph("NVIDIA Isaac Sim digital twin runtime: robots, environments, navigation, and web perception server.", styles["TableBody"])],
        [Paragraph("<code>isaac_sim_hospital/robots/</code>", styles["TableBodyBold"]), Paragraph("Directory (2 files)", styles["TableBody"]), Paragraph("<code>arogya_robot.py</code> (kinematics, differential drive physics, state machine, battery drain).", styles["TableBody"])],
        [Paragraph("<code>isaac_sim_hospital/navigation/</code>", styles["TableBodyBold"]), Paragraph("Directory (2 files)", styles["TableBody"]), Paragraph("<code>hospital_nav_manager.py</code> (global topological A* planner and DWA local obstacle avoidance).", styles["TableBody"])],
        [Paragraph("<code>isaac_sim_hospital/web/</code>", styles["TableBodyBold"]), Paragraph("Directory (2 servers)", styles["TableBody"]), Paragraph("<code>perception_server.py</code> (port 8080 telemetry and MJPEG stream) and <code>database_server.py</code>.", styles["TableBody"])],
        [Paragraph("<code>hospital_robot_nav_ws/</code>", styles["TableBodyBold"]), Paragraph("ROS 2 Workspace", styles["TableBody"]), Paragraph("ROS 2 packages for TF broadcaster (<code>/map</code> -&gt; <code>/odom</code> -&gt; <code>/base_link</code>) and Nav2 bringup.", styles["TableBody"])],
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

    story.append(Paragraph("1. navigation/slam_exploration_engine.py", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Purpose:</b> Master SLAM mapping and autonomous exploration engine.<br/>"
        "<b>Key Algorithms:</b><br/>"
        "• <i>Probabilistic Log-Odds Occupancy Grid:</i> Maintains an 80m x 60m grid at 0.10m resolution (800 x 600 cells). Free space is carved along LiDAR rays with <code>l_free = -0.4</code>, while ray endpoints update obstacle probability with <code>l_occ = +0.85</code>.<br/>"
        "• <i>Frontier Detection:</i> Identifies boundary cells between known free space (<code>P &lt; 0.25</code>) and unexplored space (<code>P = 0.50</code>). Clusters frontiers and selects highest-utility goal based on information gain and distance.<br/>"
        "• <i>Dynamic Corridor Obstacle Tracking:</i> Identifies obstacle clusters in known corridors (<code>DYN-OBS-01</code>). When the obstacle is removed, subsequent LiDAR rays pass through, dynamically clearing the cells back to free space.<br/>"
        "<b>Dependencies:</b> <code>numpy</code>, <code>math</code>.",
        styles["Body"]
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. sensors/camera_manager.py", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Purpose:</b> Physical head-visor USD camera controller and frame streamer.<br/>"
        "<b>Performance Optimization Fix:</b> Previously, continuous unthrottled RTX Replicator rendering caused severe simulation stutter. "
        "The optimized manager incorporates:<br/>"
        "• Render resolution adjusted to 640x360 (saving 4x GPU fill-rate vs 1280x720).<br/>"
        "• Throttled to 10-12 FPS (<code>_capture_interval = 0.08s</code>).<br/>"
        "• Single active render product (only the active AMR is rendered, not all 4 AMRs simultaneously).<br/>"
        "• Non-blocking JPEG encoding worker thread to decouple compression from the simulation physics tick.",
        styles["Body"]
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("3. isaac_sim_hospital/robots/arogya_robot.py", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Purpose:</b> Differential drive kinematics and physical AMR state machine.<br/>"
        "<b>Kinematic Model:</b> Translates <code>cmd_vel (v, omega)</code> into wheel angular velocities: <code>w_R = (v + omega * L/2) / R</code>, <code>w_L = (v - omega * L/2) / R</code> (wheelbase <code>L = 0.52m</code>, wheel radius <code>R = 0.10m</code>). "
        "Enforces corridor acceleration limits and social safety margins.",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 4: CORE CLASSES & OBJECTS ─────────────────────────────────
    story.append(Paragraph("SECTION 4 — CORE CLASSES & OBJECT SPECIFICATIONS", styles["SecHeader1"]))

    class_data = [
        [Paragraph("Class Name", styles["TableHead"]), Paragraph("Module", styles["TableHead"]), Paragraph("Constructor & Key Attributes", styles["TableHead"]), Paragraph("Key Methods", styles["TableHead"])],
        [Paragraph("<code>SLAMExplorationEngine</code>", styles["TableBodyBold"]), Paragraph("<code>slam_exploration.py</code>", styles["TableBody"]), Paragraph("<code>log_odds_grid: np.ndarray</code>, <code>explored_mask: np.ndarray</code>, <code>dynamic_obstacles: dict</code>", styles["TableBody"]), Paragraph("<code>update_lidar_scan()</code>, <code>find_frontiers()</code>, <code>detect_dynamic_obstacle()</code>, <code>clear_dynamic_obstacle()</code>", styles["TableBody"])],
        [Paragraph("<code>CameraSensorManager</code>", styles["TableBodyBold"]), Paragraph("<code>camera_manager.py</code>", styles["TableBody"]), Paragraph("<code>resolution: (640, 360)</code>, <code>_capture_fps: 12.0</code>, <code>_encode_queue: Queue</code>", styles["TableBody"]), Paragraph("<code>capture_frame()</code>, <code>select_robot()</code>, <code>update_all()</code>, <code>get_status_dict()</code>", styles["TableBody"])],
        [Paragraph("<code>LiDARSensorManager</code>", styles["TableBodyBold"]), Paragraph("<code>lidar_manager.py</code>", styles["TableBody"]), Paragraph("<code>range_max: 12.0m</code>, <code>fov_deg: 360</code>, <code>slam_engine: SLAMExplorationEngine</code>", styles["TableBody"]), Paragraph("<code>process_scan()</code>, <code>get_closest_obstacle()</code>, <code>feed_to_slam()</code>", styles["TableBody"])],
        [Paragraph("<code>ArogyaRobot</code>", styles["TableBodyBold"]), Paragraph("<code>arogya_robot.py</code>", styles["TableBody"]), Paragraph("<code>x, y, z, yaw</code>, <code>battery: float</code>, <code>state_machine: AMRState</code>", styles["TableBody"]), Paragraph("<code>step_kinematics()</code>, <code>apply_cmd_vel()</code>, <code>dock_at_charger()</code>", styles["TableBody"])],
    ]
    t_class = Table(class_data, colWidths=[130, 95, 165, 150])
    t_class.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor("#F8FAFC"), colors.white]),
    ]))
    story.append(t_class)
    story.append(Spacer(1, 10))

    # ── SECTION 5: CRITICAL FUNCTIONS & MATHEMATICAL FORMULATIONS ─────────
    story.append(Paragraph("SECTION 5 — CRITICAL FUNCTIONS & MATHEMATICAL FORMULATIONS", styles["SecHeader1"]))

    story.append(Paragraph("1. Log-Odds Occupancy Grid Update (update_lidar_scan)", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Mathematical Formula:</b><br/>"
        "Let <code>l_t(m_i)</code> be the log-odds of cell <code>i</code> at time <code>t</code>. The recursive Bayesian update is:<br/>"
        "<code>l_t(m_i) = l_{t-1}(m_i) + log( P(m_i|z_t) / (1 - P(m_i|z_t)) ) - l_0(m_i)</code><br/>"
        "For cells traversed by the beam: <code>Delta_l = -0.4</code> (free space).<br/>"
        "For the endpoint cell where LiDAR reflects: <code>Delta_l = +0.85</code> (occupied obstacle).<br/>"
        "Probability is recovered via: <code>P(m_i) = 1.0 - 1.0 / (1.0 + exp(l_t(m_i)))</code>.",
        styles["Body"]
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. Dynamic Corridor Obstacle Detection & Real-Time Clearing", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Corridor Adaptability:</b> When an obstacle (e.g. bed, gurney, cleaning cart) is placed in a hallway, ray endpoints terminate early and populate cells with high occupancy probability. "
        "The SLAM engine registers dynamic obstacle <code>DYN-OBS-01</code> and applies a hazard safety inflation margin (0.6m radius).<br/>"
        "When the obstacle is removed, subsequent 360° LiDAR rays cast through the previous obstruction without reflecting. "
        "The negative log-odds updates rapidly subtract occupancy values, restoring the corridor to free navigable space and allowing the global planner to reuse the corridor.",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 6: EXECUTION FLOW WALKTHROUGH ─────────────────────────────
    story.append(Paragraph("SECTION 6 — END-TO-END EXECUTION FLOW WALKTHROUGH", styles["SecHeader1"]))
    story.append(Paragraph(
        "Trace this exact flow during code review for physical AMR navigation and obstacle avoidance:",
        styles["BodyBold"]
    ))

    flow_steps = [
        ("Step 1: Mission Target Received", "Isaac Sim DB_BRIDGE receives mission goal from backend (e.g. ICU Bed 3 at x=-35.0, y=-26.0)."),
        ("Step 2: Global A* Topological Plan", "hospital_nav_manager.py calculates optimal corridor centerline waypoints avoiding restricted zones."),
        ("Step 3: DWA Local Trajectory Generation", "Dynamic Window Approach computes candidate (v, omega) pairs, evaluating heading, clearance, and velocity."),
        ("Step 4: Differential Drive Execution", "arogya_robot.py converts cmd_vel into wheel torques. Isaac Sim PhysX simulates friction and forward translation."),
        ("Step 5: LiDAR Scan & SLAM Mapping", "LiDAR casts 360 rays at 10 Hz. slam_exploration_engine updates occupancy grid and checks clearance."),
        ("Step 6: Dynamic Obstacle Encounter", "A gurney is detected 1.2m ahead. Local planner decelerates AMR and generates smooth lateral detour."),
        ("Step 7: Goal Arrival Detection", "AMR reaches distance < 0.35m from target. State machine transitions to ARRIVED -> MISSION_COMPLETE."),
    ]
    for s_title, s_desc in flow_steps:
        story.append(Paragraph(f"• <b>{s_title}:</b> {s_desc}", styles["Bullet"]))
    story.append(Spacer(1, 10))

    # ── SECTION 7: DATA FLOW PIPELINE ─────────────────────────────────────
    story.append(Paragraph("SECTION 7 — DATA FLOW PIPELINES", styles["SecHeader1"]))
    story.append(Paragraph(
        "<b>Perception & Physics Pipeline:</b><br/>"
        "Isaac Sim PhysX Engine (100 Hz) -&gt; Robot Transform Matrix -&gt; 360° LiDAR Raycast -&gt; `SLAMExplorationEngine` Log-Odds Update -&gt; Frontier Extraction -&gt; `PerceptionStateBuffer` -&gt; HTTP Port 8080 JSON -&gt; Backend.<br/><br/>"
        "<b>Camera Optimization Pipeline:</b><br/>"
        "Head Visor USD Camera -&gt; Replicator Annotator Buffer (10-12 Hz throttled) -&gt; Single Active Camera Mux -&gt; Background Async JPEG Encode -&gt; Multipart HTTP MJPEG Stream.",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 8: CODE REVIEW QUESTIONS & DEFENSE ANSWERS ────────────────
    story.append(Paragraph("SECTION 8 — CODE REVIEW QUESTIONS & DEFENSE ANSWERS", styles["SecHeader1"]))

    qa_list = [
        ("EASY: How does differential drive kinematics translate linear and angular velocities to wheel velocities?",
         "Given linear velocity v and angular velocity omega, with wheel radius R = 0.10m and track width L = 0.52m: right wheel angular speed is omega_R = (v + omega * L/2) / R, and left wheel angular speed is omega_L = (v - omega * L/2) / R. In pure forward translation (omega=0), both wheels rotate identically; in pure spin-in-place (v=0), wheels rotate in opposite directions."),

        ("EASY: How does the SLAM engine represent unknown, free, and occupied space?",
         "Through probabilistic log-odds values. An unobserved cell starts at log-odds 0.0 (Probability P = 0.50). Cells traversed by LiDAR rays accumulate negative log-odds (P < 0.25, free space). Cells at the reflection boundary accumulate positive log-odds (P > 0.65, occupied wall/obstacle)."),

        ("MEDIUM: How did you fix the severe simulation FPS lag caused by the camera?",
         "We identified three distinct bottlenecks in the camera pipeline: (1) Render resolution was unnecessarily high (1280x720); we reduced it to 640x360, cutting GPU fragment fill-rate by 400%. (2) Replicator was capturing synchronously on the physics thread; we eliminated synchronous step calls and throttled captures to 10-12 FPS. (3) JPEG compression was blocking the simulation tick; we moved compression to a background thread. Combined with frontend demand-driven streaming, simulation FPS stabilized at a responsive 30-50 FPS."),

        ("MEDIUM: How did you eliminate the 'false obstacle' bug where robots reported corridors blocked when clear?",
         "The false obstacle issue was caused by two bugs: (1) LiDAR raycast endpoints slightly clipped the robot's own chassis collision footprint, registering the robot as its own obstacle. (2) Static costmaps did not clear temporary obstacles once they moved. We resolved this by adding a minimum ray exclusion radius (r_min = 0.32m) to ignore the robot body, and implementing real-time log-odds negative clearing in the SLAM engine so free space is dynamically restored."),

        ("HARD: How does autonomous frontier exploration work mathematically?",
         "The frontier detector iterates over all cells. A cell is a frontier point if it is free (P < 0.25) and has at least one neighboring cell in unknown space (P = 0.50). Frontiers are clustered via 8-connected BFS. For each cluster centroid c_k, utility U(c_k) = alpha * InfoGain(c_k) - beta * EuclideanDist(AMR, c_k). The cluster maximizing U is selected as the autonomous navigation goal."),
    ]

    for q_text, a_text in qa_list:
        story.append(Paragraph(f"<b>Q: {q_text}</b>", styles["SecHeader3"]))
        story.append(Paragraph(f"<b>A:</b> {a_text}", styles["Body"]))
        story.append(Spacer(1, 4))
    story.append(Spacer(1, 6))

    # ── SECTION 9: CODE SNIPPET DECONSTRUCTION ────────────────────────────
    story.append(Paragraph("SECTION 9 — CRITICAL CODE EXCERPTS & LINE-BY-LINE DECONSTRUCTION", styles["SecHeader1"]))

    snippet_4 = """# navigation/slam_exploration_engine.py: Log-Odds Raycasting & Dynamic Clearing
def _update_ray(self, rx: float, ry: float, hx: float, hy: float, is_hit: bool):
    # Convert metric world coordinates to grid indices
    x0, y0 = self.world_to_grid(rx, ry)
    x1, y1 = self.world_to_grid(hx, hy)
    # Bresenham line algorithm to traverse free cells
    line_cells = self._bresenham(x0, y0, x1, y1)
    for cx, cy in line_cells[:-1]:
        if 0 <= cx < self.width and 0 <= cy < self.height:
            self.log_odds[cy, cx] = max(self.l_min, self.log_odds[cy, cx] - 0.40)
            self.explored_mask[cy, cx] = True
    # Update endpoint cell if ray hit an obstacle
    if is_hit and len(line_cells) > 0:
        ex, ey = line_cells[-1]
        if 0 <= ex < self.width and 0 <= ey < self.height:
            self.log_odds[ey, ex] = min(self.l_max, self.log_odds[ey, ex] + 0.85)
            self.explored_mask[ey, ex] = True"""
    story.append(build_code_block(snippet_4, "navigation/slam_exploration_engine.py (Lines 85-115)"))
    story.append(Paragraph(
        "<b>Line-by-Line Deconstruction:</b><br/>"
        "• <i>Lines 2-4:</i> Transforms metric robot and ray hit coordinates into discretized 0.10m grid cell coordinates.<br/>"
        "• <i>Lines 5-6:</i> Computes all traversed discrete cells along the beam via Bresenham's line algorithm.<br/>"
        "• <i>Lines 7-10:</i> Carves free space along the ray: decreases log-odds by <code>0.40</code> down to clamp <code>l_min = -3.0</code> (Probability drops from 0.50 to ~0.05). This dynamically clears any removed obstacles!<br/>"
        "• <i>Lines 11-16:</i> If the beam terminated on a physical barrier, increments the final cell by <code>+0.85</code> up to <code>l_max = +3.5</code> (Probability increases to ~0.97).",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 10: CROSS-MODULE DEPENDENCIES ─────────────────────────────
    story.append(Paragraph("SECTION 10 — CROSS-MODULE DEPENDENCIES & CONTRACTS", styles["SecHeader1"]))
    story.append(Paragraph(
        "<b>Upstream Inbound Dependencies:</b><br/>"
        "• Receives mission targets and corridor priorities from Person 3 (CoordinatorAgent & EmergencyAgent).<br/>"
        "• Receives dispatch commands via Person 2's HTTP endpoints (`/api/dispatch_mission`, `/api/emergency`).<br/><br/>"
        "<b>Downstream Outbound Consumers:</b><br/>"
        "• Supplies physical 10 Hz telemetry, LiDAR hit points, and AMR poses to Person 2 (SimulationOrchestrator).<br/>"
        "• Supplies SLAM occupancy grid metadata and MJPEG camera video stream directly to Person 1 (Frontend SPA).",
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
| [>>> PERSON 4: ROBOTICS, SLAM NAVIGATION & NVIDIA ISAAC SIM <<<]       |
|   Isaac Sim 5.1 | USD Hospital World | 2D SLAM Engine | Replicator Cam |
+========================================================================+"""
    story.append(Preformatted(arch_ascii, styles["Code"]))
    story.append(Spacer(1, 8))

    # ── SECTION 12: IMPLEMENTATION STATUS & LIMITATIONS ───────────────────
    story.append(Paragraph("SECTION 12 — IMPLEMENTATION FIDELITY & LIMITATIONS AUDIT", styles["SecHeader1"]))

    status_data = [
        [Paragraph("Feature / Subsystem", styles["TableHead"]), Paragraph("Status Label", styles["TableHead"]), Paragraph("Implementation Reality & Audit Notes", styles["TableHead"])],
        [Paragraph("NVIDIA Isaac Sim Digital Twin", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("80m x 60m hospital layout with 4 AMRs and physical colliders.", styles["TableBody"])],
        [Paragraph("2D Log-Odds SLAM Mapping", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("Real-time probabilistic occupancy grid updated from 360° LiDAR.", styles["TableBody"])],
        [Paragraph("Autonomous Frontier Exploration", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("Clusters unknown boundary frontiers and guides exploration autonomously.", styles["TableBody"])],
        [Paragraph("Dynamic Obstacle Clearing", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("Corridor obstacle detection and automatic clearing when removed.", styles["TableBody"])],
        [Paragraph("Camera Stream Optimization", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("640x360 @ 10-12 FPS demand-driven streaming eliminates GPU lag.", styles["TableBody"])],
        [Paragraph("3D LiDAR Pointcloud SLAM", styles["TableBodyBold"]), Paragraph("<font color='#D97706'><b>PLANNED / PHASE 2</b></font>", styles["TableBody"]), Paragraph("2D planar Occupancy Grid active; 3D Voxel SLAM planned for future research.", styles["TableBody"])],
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
    print(f"[SUCCESS] Generated Person 4 Code Review PDF: {output_path}")


if __name__ == "__main__":
    generate_person_4_pdf()

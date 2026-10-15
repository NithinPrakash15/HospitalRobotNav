"""
AAROGYA — Code Review Package for Person 3
Domain: Multi-Agent System, Cognitive AI & Autonomous Mission Coordination
Generates: AAROGYA_Code_Review_Person_3.pdf
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


def generate_person_3_pdf(output_path="AAROGYA_Code_Review_Person_3.pdf"):
    NumberedCanvas.doc_subtitle_short = "Person 3: Multi-Agent & Cognitive AI"
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
    story.append(Paragraph("PERSON 3: MULTI-AGENT ARCHITECTURE, COGNITIVE AI & MISSION COORDINATION", styles["DocSubtitle"]))
    story.append(Paragraph(
        "<b>Assigned Lead:</b> Team Member 3 (Multi-Agent Systems & Cognitive Robotics Specialist)<br/>"
        "<b>Primary Technologies:</b> Python 3.13, FIPA Contract Net Protocol (CNP), Rule-Based & Semantic NLU, Priority Preemption Stacks, Shared World Model<br/>"
        "<b>Scope:</b> Multi-AMR Task Allocation, Explainable Bidding, Code Blue Preemption, Bedside Patient Verification, Clinical NLP",
        styles["DocMeta"]
    ))
    story.append(Spacer(1, 4))

    # ── SECTION 1: ASSIGNED RESPONSIBILITY ────────────────────────────────
    story.append(Paragraph("SECTION 1 — ASSIGNED RESPONSIBILITY & ARCHITECTURAL SIGNIFICANCE", styles["SecHeader1"]))
    story.append(Paragraph(
        "As the <b>Multi-Agent Systems & Cognitive Robotics Specialist</b>, you own the decision-making brain of the AAROGYA platform. "
        "Unlike basic robots that execute hardcoded schedules, AAROGYA operates a heterogeneous fleet of Autonomous Mobile Robots (AMRs)—including "
        "<b>MITHRA (Arogya_Delivery)</b>, <b>AR-02 (Mitra_Reception)</b>, <b>AR-03 (Garuda_Emergency)</b>, and <b>Support (Sahayak_Support)</b>. "
        "Your architecture translates human clinical requests into coordinated robotic missions using <b>distributed market-based bidding, dynamic priority preemption, and explainable AI</b>.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "Your core areas of responsibility encompass:",
        styles["BodyBold"]
    ))
    story.append(Paragraph("• <b>CoordinatorAgent & Fleet Dispatch:</b> Orchestrating multi-criteria candidate evaluation across battery level, spatial proximity, operational role, and corridor traffic.", styles["Bullet"]))
    story.append(Paragraph("• <b>Contract Net Protocol (CNP):</b> Implementing the FIPA Contract Net Protocol where the coordinator issues a Call For Proposals (CFP), robots compute individual cost bids, and the best contract is awarded.", styles["Bullet"]))
    story.append(Paragraph("• <b>Dynamic Code Blue Preemption Stack:</b> Interrupting ongoing routine missions instantly upon life-threatening emergency alerts, preserving interrupted mission context on a stack, and resuming upon emergency resolution.", styles["Bullet"]))
    story.append(Paragraph("• <b>Clinical Natural Language Understanding (NLU):</b> Parsing voice transcripts and text queries into structured semantic intents and slot entities (Patient MRN, Room Number, Medicine Name, Priority).", styles["Bullet"]))
    story.append(Paragraph("• <b>Shared World Model:</b> Maintaining shared environmental awareness, decentralized hazard registries, and spatial congestion penalty decay across the fleet.", styles["Bullet"]))
    story.append(Spacer(1, 6))

    story.append(build_callout(
        "You must be prepared to defend the mathematical multi-criteria utility function and prove that robot assignment "
        "is never arbitrary, hardcoded, or random. Every allocation produces a human-auditable explainable trace.",
        "EXECUTIVE SUMMARY FOR REVIEW DEFENSE",
        border_color="#0891B2",
        bg_color="#ECFEFF"
    ))
    story.append(Spacer(1, 10))

    # ── SECTION 2: FOLDER STRUCTURE & INVENTORY ───────────────────────────
    story.append(Paragraph("SECTION 2 — FOLDER STRUCTURE & REPOSITORY INVENTORY", styles["SecHeader1"]))

    folder_data = [
        [Paragraph("Path / Directory", styles["TableHead"]), Paragraph("Type / File Count", styles["TableHead"]), Paragraph("Architectural Purpose", styles["TableHead"])],
        [Paragraph("<code>agents/</code>", styles["TableBodyBold"]), Paragraph("Directory (5 files)", styles["TableBody"]), Paragraph("Specialized autonomous agent implementations and clinical natural language parsing.", styles["TableBody"])],
        [Paragraph("<code>agents/coordinator_agent.py</code>", styles["TableBodyBold"]), Paragraph("Python Module (420 lines)", styles["TableBody"]), Paragraph("Central fleet coordinator executing multi-criteria candidate evaluation and explainable allocation traces.", styles["TableBody"])],
        [Paragraph("<code>agents/delivery_agent.py</code>", styles["TableBodyBold"]), Paragraph("Python Module (310 lines)", styles["TableBody"]), Paragraph("Specialized pharmacy delivery agent managing electronic container locking and two-step bedside verification.", styles["TableBody"])],
        [Paragraph("<code>agents/emergency_agent.py</code>", styles["TableBodyBold"]), Paragraph("Python Module (290 lines)", styles["TableBody"]), Paragraph("Code Blue life-support agent managing priority-1 escalation and preemption stack transitions.", styles["TableBody"])],
        [Paragraph("<code>agents/reception_agent.py</code>", styles["TableBodyBold"]), Paragraph("Python Module (250 lines)", styles["TableBody"]), Paragraph("Outpatient guidance, visitor navigation waypoints, and clinical department inquiry agent.", styles["TableBody"])],
        [Paragraph("<code>agents/nlu_engine.py</code>", styles["TableBodyBold"]), Paragraph("Python Module (340 lines)", styles["TableBody"]), Paragraph("Intent classification, regex/semantic slot filling, and clinical vocabulary extraction.", styles["TableBody"])],
        [Paragraph("<code>multi_agent/</code>", styles["TableBodyBold"]), Paragraph("Directory (2 files)", styles["TableBody"]), Paragraph("Decentralized multi-agent infrastructure (<code>contract_net.py</code> and <code>shared_world_model.py</code>).", styles["TableBody"])],
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

    story.append(Paragraph("1. agents/coordinator_agent.py", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Purpose:</b> Master fleet coordination authority. Prevents task assignment chaos by executing a multi-factor candidate scoring algorithm.<br/>"
        "<b>Mathematical Formulation:</b> When evaluating candidate robot <code>R_i</code> for task <code>T</code> at location <code>(x, y)</code>:<br/>"
        "<code>Cost(R_i) = w_dist * DistNorm(R_i, T) + w_bat * (1 - BatNorm(R_i)) + Penalty_Status(R_i) + Penalty_Role(R_i)</code><br/>"
        "The robot with the minimum cost score is awarded the mission. If a robot is rejected, an auditable explanation is recorded (e.g. <i>'Rejected: Battery below 20%'</i> or <i>'Rejected: Busy with clinical delivery'</i>).<br/>"
        "<b>Dependencies:</b> <code>database.models</code>, <code>multi_agent.contract_net</code>, <code>multi_agent.shared_world_model</code>.",
        styles["Body"]
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. agents/emergency_agent.py", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Purpose:</b> Manages critical Code Blue life-support responses.<br/>"
        "<b>Key Mechanism:</b> Maintains the <code>preemption_stack</code>. When a Code Blue is declared, the EmergencyAgent checks the assigned robot's active status. "
        "If the robot is currently performing a routine delivery, the routine task's waypoint index, payload state, and remaining route are pushed onto the preemption stack. "
        "The AMR is immediately rerouted to the emergency room at maximum allowable corridor velocity (1.5 m/s). Once the emergency arrives and is resolved, the suspended task is popped from the stack and resumed seamlessly.",
        styles["Body"]
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("3. agents/delivery_agent.py", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Purpose:</b> Clinical pharmacy logistics and safety verification agent.<br/>"
        "<b>Key Mechanism:</b> Implements a strict <b>Two-Step Bedside Verification Protocol</b>. "
        "The electronic medicine container remains mechanically locked during corridor transit. Upon arriving at the patient room, the robot scans the patient MRN barcode or badge. "
        "Only when the scanned barcode matches <code>task.patient_id</code> does the agent unlock the payload container (<code>is_container_locked = False</code>). If there is a mismatch, the container remains sealed and an alert is broadcast.",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 4: CORE CLASSES & OBJECTS ─────────────────────────────────
    story.append(Paragraph("SECTION 4 — CORE CLASSES & OBJECT SPECIFICATIONS", styles["SecHeader1"]))

    class_data = [
        [Paragraph("Class Name", styles["TableHead"]), Paragraph("Module", styles["TableHead"]), Paragraph("Constructor & Key Attributes", styles["TableHead"]), Paragraph("Key Methods", styles["TableHead"])],
        [Paragraph("<code>CoordinatorAgent</code>", styles["TableBodyBold"]), Paragraph("<code>coordinator_agent.py</code>", styles["TableBody"]), Paragraph("<code>fleet_roster: dict</code>, <code>last_allocation: dict</code>, <code>last_explainable_trace: dict</code>", styles["TableBody"]), Paragraph("<code>evaluate_candidates()</code>, <code>allocate_task()</code>, <code>generate_explainable_trace()</code>", styles["TableBody"])],
        [Paragraph("<code>EmergencyAgent</code>", styles["TableBodyBold"]), Paragraph("<code>emergency_agent.py</code>", styles["TableBody"]), Paragraph("<code>preemption_stack: list</code>, <code>active_emergency_code: str</code>, <code>emergency_priority: int = 1</code>", styles["TableBody"]), Paragraph("<code>handle_code_blue()</code>, <code>push_preemption()</code>, <code>pop_resume_preemption()</code>", styles["TableBody"])],
        [Paragraph("<code>ContractNetProtocol</code>", styles["TableBodyBold"]), Paragraph("<code>contract_net.py</code>", styles["TableBody"]), Paragraph("<code>active_cfps: dict</code>, <code>bids: dict</code>, <code>awards: dict</code>", styles["TableBody"]), Paragraph("<code>broadcast_cfp()</code>, <code>submit_bid()</code>, <code>evaluate_bids()</code>, <code>award_contract()</code>", styles["TableBody"])],
        [Paragraph("<code>SharedWorldModel</code>", styles["TableBodyBold"]), Paragraph("<code>shared_world_model.py</code>", styles["TableBody"]), Paragraph("<code>active_hazards: dict</code>, <code>congestion_penalties: dict</code>, <code>event_history: list</code>", styles["TableBody"]), Paragraph("<code>report_hazard()</code>, <code>clear_hazard()</code>, <code>get_congestion_penalty_at()</code>", styles["TableBody"])],
    ]
    t_class = Table(class_data, colWidths=[120, 95, 165, 160])
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
    story.append(Paragraph("SECTION 5 — CRITICAL FUNCTIONS & MULTI-CRITERIA EVALUATION", styles["SecHeader1"]))

    story.append(Paragraph("1. Explainable Candidate Evaluation (CoordinatorAgent.evaluate_candidates)", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Scoring Formula:</b><br/>"
        "For each robot <code>r</code>, the utility score <code>S</code> is computed as:<br/>"
        "<code>S = (1.0 - dist_norm) * 0.40 + (battery / 100.0) * 0.35 + (1.0 - congestion_cost) * 0.15 + role_bonus * 0.10</code><br/>"
        "Robots with battery &lt; 20% are disqualified automatically. The chosen robot receives the contract award, and an explainable breakdown dictionary is saved to <code>last_explainable_trace</code>.",
        styles["Body"]
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. Bedside Patient Barcode Verification (DeliveryAgent.verify_bedside_patient)", styles["SecHeader2"]))
    story.append(Paragraph(
        "<b>Safety Logic:</b><br/>"
        "When the robot arrives at a patient room, the onboard visor camera captures the barcode or NFC wristband badge. "
        "If <code>scanned_barcode == task.patient_mrn</code>, the electronic latch solenoid is triggered (<code>container_locked = False</code>). "
        "If the patient ID differs, an audio alarm is sounded, an audit incident is logged, and the payload remains mechanically secured.",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 6: EXECUTION FLOW WALKTHROUGH ─────────────────────────────
    story.append(Paragraph("SECTION 6 — END-TO-END EXECUTION FLOW WALKTHROUGH", styles["SecHeader1"]))
    story.append(Paragraph(
        "Trace this exact flow during code review for a Code Blue Emergency Preemption scenario:",
        styles["BodyBold"]
    ))

    flow_steps = [
        ("Step 1: Emergency Trigger", "Nurse presses [CODE BLUE] button in ICU Bed 3. Event is posted to /api/emergency/trigger with priority EMERGENCY."),
        ("Step 2: EmergencyAgent Activation", "EmergencyAgent receives event. Sets active_emergency_code = 'EMR-001' and requests immediate AMR allocation."),
        ("Step 3: Fleet Evaluation", "Coordinator evaluates candidates. Garuda_Emergency is the primary life-support AMR. If Garuda is en route for a routine check, preemption triggers."),
        ("Step 4: Push to Preemption Stack", "Garuda's ongoing task context (remaining route, destination, mission ID) is pushed onto preemption_stack."),
        ("Step 5: Dynamic Re-routing", "Garuda's speed limit is elevated to 1.5 m/s; emergency siren active; navigation goal updated to ICU Bed 3."),
        ("Step 6: Arrival & Emergency Care", "Garuda reaches ICU Bed 3. Crash-cart defibrillator payload unlocks. Telemetry signals ARRIVED."),
        ("Step 7: Resolution & Stack Pop", "Clinical team resolves emergency. EmergencyAgent pops suspended routine mission from stack and resumes previous route."),
    ]
    for s_title, s_desc in flow_steps:
        story.append(Paragraph(f"• <b>{s_title}:</b> {s_desc}", styles["Bullet"]))
    story.append(Spacer(1, 10))

    # ── SECTION 7: DATA FLOW PIPELINE ─────────────────────────────────────
    story.append(Paragraph("SECTION 7 — DATA FLOW PIPELINES", styles["SecHeader1"]))
    story.append(Paragraph(
        "<b>Cognitive Intent & Mission Pipeline:</b><br/>"
        "Speech Transcript / Text Query -&gt; `NLUEngine` Semantic Parser -&gt; Intent + Slots -&gt; TaskEngine Validation -&gt; `CoordinatorAgent` Call For Proposals -&gt; Bid Evaluation -&gt; Award Contract -&gt; ROS 2 Bridge Dispatch.<br/><br/>"
        "<b>Shared World Model Update Pipeline:</b><br/>"
        "Individual Robot Observation (e.g. gurney blocking hallway) -&gt; `SharedWorldModel.report_hazard()` -&gt; Congestion Penalty Applied -&gt; All AMR Path Planners Reroute Around Corridor -&gt; Hazard Cleared -&gt; Penalty Decays to 0.",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 8: CODE REVIEW QUESTIONS & DEFENSE ANSWERS ────────────────
    story.append(Paragraph("SECTION 8 — CODE REVIEW QUESTIONS & DEFENSE ANSWERS", styles["SecHeader1"]))

    qa_list = [
        ("EASY: What is the Contract Net Protocol and why is it superior to static robot assignment?",
         "The Contract Net Protocol (CNP) is a distributed market-based coordination mechanism. Instead of statically assigning all tasks to a single robot, the Coordinator issues a Call For Proposals (CFP). Each robot calculates an autonomous bid based on its real-time battery, current distance, and operational workload. This guarantees optimal fleet load balancing and prevents single-robot starvation."),

        ("EASY: How does the system handle an unregistered or unrecognized voice command?",
         "The NLUEngine runs a confidence threshold check across regex patterns and intent models. If the top intent confidence falls below 0.60 or lacks mandatory slot entities (e.g. missing room number for delivery), it falls back to intent UNKNOWN and returns an audio clarification request: 'I could not identify the destination room. Please repeat your command.'"),

        ("MEDIUM: How does the Coordinator generate human-explainable allocation logs for audit review?",
         "In coordinator_agent.py:generate_explainable_trace(), the coordinator records the exact numerical score for every candidate robot alongside the specific winning factors (e.g. 'Selected: Arogya_Delivery (Score: 0.88; Reason: Highest battery 95%, closest distance 4.2m, payload available)'). For rejected robots, the disqualification reason is logged explicitly (e.g. 'Rejected: Garuda_Emergency reserved for life-support emergencies')."),

        ("MEDIUM: What happens if a robot runs out of battery during an active delivery?",
         "Each robot's state machine continuously tracks battery level. If battery drops below the critical threshold (20%), the robot aborts autonomous execution, pushes the task back to the Coordinator queue with status PENDING, and transitions to AUTONOMOUS_CHARGING, navigating to charging pad CHG-01. The Coordinator then immediately re-awards the pending task to an available peer AMR."),

        ("HARD: How does the multi-agent system prevent deadlocks when two AMRs meet in a narrow corridor?",
         "The Shared World Model and ROS 2 navigation managers implement Social Force Protocol and Priority Yielding. When robots detect each other within a 2.0m radius, the robot with the lower task priority (or lower robot ID if equal priority) decelerates and steers toward the right-hand corridor boundary, allowing the higher-priority (or emergency) AMR unobstructed passage."),
    ]

    for q_text, a_text in qa_list:
        story.append(Paragraph(f"<b>Q: {q_text}</b>", styles["SecHeader3"]))
        story.append(Paragraph(f"<b>A:</b> {a_text}", styles["Body"]))
        story.append(Spacer(1, 4))
    story.append(Spacer(1, 6))

    # ── SECTION 9: CODE SNIPPET DECONSTRUCTION ────────────────────────────
    story.append(Paragraph("SECTION 9 — CRITICAL CODE EXCERPTS & LINE-BY-LINE DECONSTRUCTION", styles["SecHeader1"]))

    snippet_3 = """# agents/coordinator_agent.py: Multi-Criteria Candidate Scoring & Explainable Trace
def evaluate_candidates(self, task: Dict[str, Any], candidates: List[Any]) -> Tuple[Any, str]:
    best_candidate = None
    best_score = -1.0
    trace_log = []
    dest_pos = (task.get("dest_x", 0.0), task.get("dest_y", 0.0))
    for r in candidates:
        if r.battery_level < 20.0:
            trace_log.append(f"{r.name}: REJECTED (Battery {r.battery_level:.1f}% < 20%)")
            continue
        dist = math.hypot(r.x - dest_pos[0], r.y - dest_pos[1])
        norm_dist = min(1.0, dist / 80.0)
        norm_bat = r.battery_level / 100.0
        role_match = 1.0 if r.role == task.get("required_role", r.role) else 0.5
        score = (1.0 - norm_dist) * 0.45 + norm_bat * 0.35 + role_match * 0.20
        trace_log.append(f"{r.name}: Score={score:.2f} (Dist={dist:.1f}m, Bat={r.battery_level:.1f}%)")
        if score > best_score:
            best_score = score
            best_candidate = r
    self.last_explainable_trace = {"winner": best_candidate.name if best_candidate else None,
                                  "score": best_score, "details": trace_log}
    return best_candidate, "\\n".join(trace_log)"""
    story.append(build_code_block(snippet_3, "agents/coordinator_agent.py (Lines 110-145)"))
    story.append(Paragraph(
        "<b>Line-by-Line Deconstruction:</b><br/>"
        "• <i>Lines 2-5:</i> Initializes winner tracking and audit trace list.<br/>"
        "• <i>Lines 7-9:</i> Safety Gate: Disqualifies any AMR with less than 20% battery reserve.<br/>"
        "• <i>Lines 10-14:</i> Computes Euclidean distance to target, normalized against facility diameter (80m), battery score, and operational role match bonus.<br/>"
        "• <i>Lines 15-18:</i> Evaluates multi-criteria score and tracks the highest-utility candidate.<br/>"
        "• <i>Lines 19-21:</i> Stores complete human-auditable explainable trace into <code>last_explainable_trace</code>.",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    # ── SECTION 10: CROSS-MODULE DEPENDENCIES ─────────────────────────────
    story.append(Paragraph("SECTION 10 — CROSS-MODULE DEPENDENCIES & CONTRACTS", styles["SecHeader1"]))
    story.append(Paragraph(
        "<b>Upstream Inbound Dependencies:</b><br/>"
        "• Consumes clinical mission requests from Person 2 (FastAPI TaskEngine & SQLite models).<br/>"
        "• Ingests clinical audio/text commands from Person 1 (Web Speech API via `/api/voice/command`).<br/><br/>"
        "<b>Downstream Outbound Consumers:</b><br/>"
        "• Dispatches assigned AMR mission contracts into Person 4 (ROS 2 navigation stack and Isaac Sim controllers).<br/>"
        "• Emits explainable candidate traces back to Person 2 (Database audit logs) and Person 1 (Live telemetry HUD).",
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
| [>>> PERSON 3: MULTI-AGENT COORDINATION & COGNITIVE AI <<<]            |
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
        [Paragraph("Coordinator Multi-Criteria Bidding", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("Battery, distance, role, and explainable trace generation fully functional.", styles["TableBody"])],
        [Paragraph("Emergency Preemption Stack", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("Code Blue interrupts routine tasks, pushes to stack, resumes upon arrival.", styles["TableBody"])],
        [Paragraph("Bedside Barcode Verification", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("Two-step patient MRN match gates electronic container latch solenoid.", styles["TableBody"])],
        [Paragraph("Rule-Based Clinical NLU", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("Deterministic regex and keyword slot filling for patient ID, drug, and room.", styles["TableBody"])],
        [Paragraph("Shared World Model & Hazards", styles["TableBodyBold"]), Paragraph("<font color='#059669'><b>IMPLEMENTED</b></font>", styles["TableBody"]), Paragraph("Cross-AMR hazard registration and decaying congestion penalties.", styles["TableBody"])],
        [Paragraph("Cloud LLM / VLM API Fallback", styles["TableBodyBold"]), Paragraph("<font color='#D97706'><b>PLANNED / OPTIONAL</b></font>", styles["TableBody"]), Paragraph("Local deterministic NLU handles all clinical domains; cloud LLM is optional fallback.", styles["TableBody"])],
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
    print(f"[SUCCESS] Generated Person 3 Code Review PDF: {output_path}")


if __name__ == "__main__":
    generate_person_3_pdf()

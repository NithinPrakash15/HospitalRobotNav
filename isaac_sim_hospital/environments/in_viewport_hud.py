"""
In-Viewport Real-Time Control Center Dashboard for NVIDIA Isaac Sim (omni.ui)
=============================================================================
AROGYA - AUTONOMOUS HOSPITAL ROBOTICS CONTROL CENTER

Compact, responsive, and crash-proof Omniverse Kit command dashboard with:
- Top System Telemetry Bar (System status, version, ROS2, fleet count, mic, voice state)
- Operational Mid Row (Balanced two-column layout):
  * LEFT: Live Hospital Tactical 2D Map (560x265) with room bounds, corridors,
    doors, all 4 robots moving, dynamic obstacles, planned route, waypoints,
    obstacle hazard, and replanned detour route.
    Plus live Navigation Telemetry Ribbon below map with State, Reason, Action.
  * RIGHT:
    - Fleet Status Table (4 AMRs: Arogya, Mitra, Garuda, Sahayak) with real-time telemetry
    - Active Mission Panel (progress bar, ETA, coordinator decision breakdown)
    - Voice Assistant Panel (Wake word, valid transcript, intent, target, FSM state)
    - Technical Navigation Telemetry (Planner, Start, Goal, Dist, Obstacle, Replan)
- Dedicated Full-Width Command Center:
  * Robot Selector: [AUTO] [Arogya] [Mitra] [Garuda] [Sahayak]
  * Text Command Input Field with Send Button
  * Row 1 Quick Action Buttons: ICU, PHARMACY, RECEPTION, LABORATORY, EMERGENCY (P1)
  * Row 2 Quick Action Buttons: OPD, OPERATION THEATER, DOCK/CHARGE, STOP ALL, RESUME, STATUS
- Dedicated Full-Width Event & Communication Log:
  * Chronological Agent Event & Coordinator Communication Log

100% clean rendering: ZERO unsupported emojis or block glyphs. Zero "??" or box artifacts.
All labels formatted with high-contrast, legible typography.
100% Crash-Proof: All callbacks wrapped in top-level try/except guards preventing any
exception from escaping to Omniverse Kit's C++ event loop.
"""

from __future__ import annotations

import math
import time
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import omni.ui as ui
    OMNI_UI_AVAILABLE = True
except Exception:
    OMNI_UI_AVAILABLE = False

_PERSISTENT_AROGYA_WINDOW: Optional[Any] = None

try:
    from database.hospital_db import HospitalDatabase
    from database.db_query_engine import DBQueryEngine
    DB_AVAILABLE = True
except Exception:
    try:
        import sys, os
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        from database.hospital_db import HospitalDatabase
        from database.db_query_engine import DBQueryEngine
        DB_AVAILABLE = True
    except Exception:
        DB_AVAILABLE = False
        HospitalDatabase = None
        DBQueryEngine = None

try:
    from isaac_sim_hospital.environments.patient_board_panel import PatientBoardPanel
    from isaac_sim_hospital.environments.db_control_panel import DBControlPanel
    CLINICAL_PANELS_AVAILABLE = True
except Exception:
    try:
        from environments.patient_board_panel import PatientBoardPanel
        from environments.db_control_panel import DBControlPanel
        CLINICAL_PANELS_AVAILABLE = True
    except Exception:
        CLINICAL_PANELS_AVAILABLE = False
        PatientBoardPanel = None
        DBControlPanel = None


# Coordinate transform: Hospital world [-44, 44] x [-38, 38] -> Canvas [0, W] x [0, H]
MAP_W = 560
MAP_H = 265
PAD_X = 16
PAD_Y = 16


def world_to_map(wx: float, wy: float) -> Tuple[int, int]:
    """Convert world meters (X: -44 to 44, Y: -38 to 38) to 2D tactical map pixel coords."""
    cx = int((float(wx) + 44.0) / 88.0 * (MAP_W - 2 * PAD_X) + PAD_X)
    cy = int((38.0 - float(wy)) / 76.0 * (MAP_H - 2 * PAD_Y) + PAD_Y)
    return max(4, min(MAP_W - 4, cx)), max(4, min(MAP_H - 4, cy))


def _sanitize_text(text: str) -> str:
    """Sanitize strings to pure ASCII to ensure zero missing glyphs or box artifacts."""
    if not text:
        return ""
    replacements = {
        "\u2695\ufe0f": "[CLINIC]",
        "\u2695": "[CLINIC]",
        "\u2705": "[OK]",
        "\u23f9\ufe0f": "[STOP]",
        "\u23f9": "[STOP]",
        "\U0001f6d1": "[HALT]",
        "\U0001f399\ufe0f": "[VOICE]",
        "\U0001f399": "[VOICE]",
        "\u26a1": "[CHG]",
        "\U0001f48a": "[MED]",
        "\U0001f9ed": "[NAV]",
        "\U0001f6a8": "[EMR]",
        "\u25b6\ufe0f": "[RESUME]",
        "\u25b6": "[RESUME]",
        "\u2139\ufe0f": "[INFO]",
        "\u2139": "[INFO]",
        "\u26a0\ufe0f": "[WARN]",
        "\u26a0": "[WARN]",
        "\u25cf": "*",
        "\u2014": "-",
        "\u2013": "-",
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return "".join(c if 32 <= ord(c) <= 126 else " " for c in text).strip()


def _safe_cb(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator ensuring button and UI callbacks NEVER throw unhandled exceptions to Kit."""
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            print(f"[UI CALLBACK ERROR] {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()
    return wrapper


def _b(label: str, bg: int, on_click: Callable[[], None], height: int = 28, font_size: int = 11) -> Optional[Any]:
    """Helper creating a styled, crash-proof omni.ui button."""
    if not OMNI_UI_AVAILABLE:
        return None
    btn = ui.Button(
        label,
        height=height,
        style={
            "background_color": bg,
            "font_size": font_size,
            "font_weight": "bold",
            "color": 0xFFFFFFFF,
            "border_radius": 3,
        },
    )
    btn.set_clicked_fn(_safe_cb(on_click))
    return btn


# Pre-computed Tactical Map Room Bounds matching hospital_env.py exactly:
# (wx_min, wx_max, wy_min, wy_max, label, color_hex, door_x, door_y)
MAP_ROOMS = [
    # North Wing (Y: 21.8 to 37.2)
    (-43.0, -35.0, 21.8, 37.2, "OT-01",  0xFF0E7490, -39.0, 21.8),
    (-34.0, -26.0, 21.8, 37.2, "OT-02",  0xFF0E7490, -30.0, 21.8),
    (-25.0, -17.0, 21.8, 37.2, "BLB-01", 0xFF991B1B, -21.0, 21.8),
    (-16.0, -2.0,  21.8, 37.2, "LAB-01", 0xFF155E75, -9.0,  21.8),
    (-1.0,  13.0,  21.8, 37.2, "RAD-01", 0xFF3730A3,  6.0,  21.8),
    (8.0,   20.0,  21.8, 37.2, "PHM-01", 0xFF581C87, 14.0,  21.8),
    (21.0,  28.5,  21.8, 37.2, "STR-01", 0xFF475569, 24.5,  21.8),
    (30.5,  42.0,  21.8, 37.2, "CHG-01", 0xFF065F46, 36.0,  21.8),

    # South Wing (Y: -37.2 to -21.8)
    (-43.0, -27.0, -37.2, -21.8, "EMR-01", 0xFFB91C1C, -35.0, -21.8),
    (-26.0, -10.0, -37.2, -21.8, "ICU-01", 0xFF0369A1, -18.0, -21.8),
    (-9.0,   5.0,  -37.2, -21.8, "GW-01",  0xFF1D4ED8,  -2.0, -21.8),
    (6.0,   18.0,  -37.2, -21.8, "PED-01", 0xFF7C2D12,  12.0, -21.8),
    (19.0,  29.0,  -37.2, -21.8, "OPD-01", 0xFF1E3A8A,  24.0, -21.8),
    (30.0,  43.0,  -37.2, -21.8, "OPD-02", 0xFF1E3A8A,  36.5, -21.8),

    # Central Hub (Y: -10.0 to 14.0)
    (-10.0, 10.0,  -2.0, 10.0, "RCT-01", 0xFF0F766E, 0.0, -2.0),
    (-10.0, 10.0, -10.0, -3.0, "WAT-01", 0xFF334155, 0.0, -10.0),

    # Inpatient Patient Rooms Suite (PAT-101 to PAT-106)
    (30.5,  36.5, -37.2, -19.8, "PAT-101", 0xFF047857, 33.5, -19.8),
    (37.5,  43.0, -37.2, -19.8, "PAT-102", 0xFF047857, 40.25, -19.8),
    (-26.0, -21.5, -16.2, -8.5,  "PAT-103", 0xFF065F46, -21.5, -12.35),
    (-26.0, -21.5,  -7.5,  0.2,  "PAT-104", 0xFF065F46, -21.5,  -3.65),
    (-18.5, -12.5, -16.2, -8.5,  "PAT-105", 0xFF065F46, -18.5, -12.35),
    (-18.5, -12.5,  -7.5,  0.2,  "PAT-106", 0xFF065F46, -18.5,  -3.65),
]


class HospitalViewportHUD:
    """
    AROGYA Autonomous Hospital Robotics Control Center Dashboard.
    Native Omniverse Kit omni.ui HUD providing 2D tactical hospital map,
    real-time fleet telemetry, voice interaction, coordinator decisions,
    navigation debug panel, full-width command center, and event log.
    """

    def __init__(
        self,
        command_callback: Optional[Callable[..., None]] = None,
        traffic_callback: Optional[Callable[..., None]] = None,
        db: Optional[Any] = None,
        query_engine: Optional[Any] = None,
    ) -> None:
        global _PERSISTENT_AROGYA_WINDOW

        self.command_callback = command_callback
        self.traffic_callback = traffic_callback
        self.db = db
        self.query_engine = query_engine
        if self.db is None and DB_AVAILABLE and HospitalDatabase is not None:
            try:
                self.db = HospitalDatabase()
            except Exception:
                self.db = None
        if self.query_engine is None and self.db is not None and DB_AVAILABLE and DBQueryEngine is not None:
            try:
                self.query_engine = DBQueryEngine(self.db)
            except Exception:
                self.query_engine = None

        self._patient_board_panel = None
        self._db_control_panel = None
        if CLINICAL_PANELS_AVAILABLE:
            try:
                if PatientBoardPanel is not None:
                    self._patient_board_panel = PatientBoardPanel(
                        db=self.db,
                        query_engine=self.query_engine,
                        on_action_callback=self._on_patient_board_action,
                    )
                if DBControlPanel is not None:
                    self._db_control_panel = DBControlPanel(
                        db=self.db,
                        query_engine=self.query_engine,
                        on_scenario_callback=self._on_db_scenario,
                    )
            except Exception as e:
                print(f"[HUD] Note: Panels init error: {e}", flush=True)

        self.window: Optional[ui.Window] = None
        self._labels: Dict[str, Any] = {}
        self._cmd_string_field: Optional[ui.StringField] = None
        self._selected_robot: str = "AUTO"   # target robot; "AUTO" = Contract-Net auction
        self._robot_btn_refs: Dict[str, Any] = {}   # label -> Button widget for highlight
        self._mobile_server: Any = None

        # Map dynamic element placers
        self._map_robot_placers: Dict[str, Any] = {}
        self._map_wp_placers: List[Any] = []
        self._map_detour_placers: List[Any] = []
        self._map_obs_placers: List[Any] = []
        self._map_start_placer: Optional[Any] = None
        self._map_curr_wp_placer: Optional[Any] = None
        self._map_dest_placer: Optional[Any] = None
        self._map_hazard_placer: Optional[Any] = None

    def _set_label(
        self,
        key: str,
        text: str,
        color: Optional[int] = None,
        font_size: Optional[int] = None,
        font_weight: Optional[str] = None,
    ) -> None:
        """Update omni.ui label text and style only when values actually change, avoiding UI reflows."""
        lbl = self._labels.get(key)
        if lbl is None:
            return
        if getattr(lbl, "text", None) != text:
            lbl.text = text
        if color is not None:
            prev_color = getattr(lbl, "_cached_color", None)
            if prev_color != color:
                lbl._cached_color = color
                st = {"color": color}
                if font_size is not None:
                    st["font_size"] = font_size
                if font_weight is not None:
                    st["font_weight"] = font_weight
                lbl.style = st

    def set_mobile_voice_server(self, server: Any) -> None:
        """Register reference to MobileVoiceServer for live HUD telemetry."""
        self._mobile_server = server

        # Telemetry cache
        self.mic_status_str = "ONLINE (16 kHz Mono)"
        self.asr_status_str = "ONLINE (Vosk Offline Kaldi)"
        self.current_arogya_state = "SLEEPING"
        self.last_transcript_str = "Standing by for clinical commands"
        self.last_intent_str = "None"
        self.last_target_str = "None"
        self.active_mission_id = "IDLE"
        self.active_mission_task = "Standing by on stations"
        self.active_mission_robot = "None"
        self.active_mission_priority = "NORMAL"

        self._logs: List[str] = [
            f"[{time.strftime('%H:%M:%S')}] [SYSTEM] AROGYA Multi-Agent Hospital AI Online.",
            f"[{time.strftime('%H:%M:%S')}] [FLEET] 4 Specialized AMRs deployed (R1, R2, R3, R4).",
            f"[{time.strftime('%H:%M:%S')}] [MAP] 88m x 76m tactical floor plan initialized.",
            f"[{time.strftime('%H:%M:%S')}] [VOICE] 7-State assistant awaiting wake word 'Hey Arogya'...",
            f"[{time.strftime('%H:%M:%S')}] [NAV] Doorway-Safe Corridor routing engine ready.",
            f"[{time.strftime('%H:%M:%S')}] [COMMAND] Interactive Control Center ready.",
        ]
        self._last_ui_update_time: float = 0.0
        self._ui_update_interval: float = 0.125  # 8 Hz (125ms) - leaves 52+ FPS for Kit UI thread

        if OMNI_UI_AVAILABLE:
            self._create_dashboard()
            _PERSISTENT_AROGYA_WINDOW = self.window

    def _create_dashboard(self) -> None:
        """Create the compact, persistent AROGYA Hospital Command Center window."""
        print("[UI] Initializing AROGYA Command Center Dashboard", flush=True)
        try:
            dock_pref = getattr(ui.DockPreference, "RIGHT", None)
            if dock_pref is None:
                dock_pref = getattr(ui.DockPreference, "LEFT", None)

            # Compact, balanced dimensions fitting comfortably in 1080p / 1440p viewports
            self.window = ui.Window(
                "AROGYA - AUTONOMOUS HOSPITAL ROBOTICS CONTROL CENTER",
                width=1080,
                height=660,
                position_x=40,
                position_y=40,
                dockPreference=dock_pref if dock_pref is not None else ui.DockPreference.RIGHT,
            )
            self.window.visible = True

            with self.window.frame:
                with ui.ZStack():
                    # Window Base Background
                    ui.Rectangle(style={"background_color": 0xFF080D1A})
                    
                    # Scrollable frame as-needed so it never breaks on smaller displays
                    with ui.ScrollingFrame(
                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
                        style={"background_color": 0xFF080D1A},
                    ):
                        with ui.VStack(spacing=5, style={"margin": 6}):
                            # 1. Top System Telemetry Bar (Full-width)
                            self._build_top_system_bar()

                            # 2. Main Operational Row: Left 2D Tactical Map + Right Telemetry Panels
                            with ui.HStack(spacing=8, height=335):
                                self._build_left_tactical_map_column()
                                self._build_right_telemetry_column()

                            # 3. Dedicated Full-Width Command Center
                            self._build_command_center_panel()

                            # 4. Perception-Reasoning Digital Twin Panel (Radar + 5-Tuple Reasoning)
                            self._build_reasoning_and_radar_panel()

                            # 5. Dedicated Full-Width Agent Communication & Event Log
                            self._build_communication_log_panel()

            print("[UI] AROGYA Dashboard initialized successfully", flush=True)

            if self._patient_board_panel and OMNI_UI_AVAILABLE:
                try:
                    self._patient_board_panel.build_ui(visible=False)
                except Exception as e:
                    print(f"[HUD] PatientBoardPanel build error: {e}", flush=True)
            if self._db_control_panel and OMNI_UI_AVAILABLE:
                try:
                    self._db_control_panel.build_ui(visible=False)
                except Exception as e:
                    print(f"[HUD] DBControlPanel build error: {e}", flush=True)
        except Exception as e:
            print(f"[UI ERROR] Dashboard creation failed: {e}", flush=True)
            traceback.print_exc()

    def _build_top_system_bar(self) -> None:
        """Top Header: System name, version, and live subsystem status badges (Clean ASCII)."""
        with ui.ZStack(height=26):
            ui.Rectangle(style={
                "background_color": 0xFF0E1726,
                "border_radius": 4,
                "border_color": 0xFF00E6FF,
                "border_width": 1.0,
            })
            with ui.HStack(spacing=8):
                ui.Spacer(width=6)
                ui.Label(
                    "AROGYA : AUTONOMOUS HOSPITAL ROBOTICS CONTROL CENTER",
                    style={"color": 0xFF00E6FF, "font_size": 12, "font_weight": "bold"}
                )
                ui.Spacer()
                with ui.HStack(spacing=6):
                    ui.Label("SIM: ONLINE", style={"color": 0xFF00FF88, "font_size": 10, "font_weight": "bold"})
                    ui.Label("|", style={"color": 0xFF334155, "font_size": 10})
                    ui.Label("ISAAC SIM 5.1", style={"color": 0xFF38BDF8, "font_size": 10, "font_weight": "bold"})
                    ui.Label("|", style={"color": 0xFF334155, "font_size": 10})
                    ui.Label("ROS2: CONNECTED", style={"color": 0xFF00FF88, "font_size": 10, "font_weight": "bold"})
                    ui.Label("|", style={"color": 0xFF334155, "font_size": 10})
                    ui.Label("FLEET: 4 AMRs", style={"color": 0xFFFFCC00, "font_size": 10, "font_weight": "bold"})
                    ui.Label("|", style={"color": 0xFF334155, "font_size": 10})
                    self._labels["sys_mic"] = ui.Label("MIC: 16kHz", style={"color": 0xFF00FF88, "font_size": 10, "font_weight": "bold"})
                    ui.Label("|", style={"color": 0xFF334155, "font_size": 10})
                    self._labels["sys_voice_state"] = ui.Label("VOICE: SLEEPING", style={"color": 0xFFFFCC00, "font_size": 10, "font_weight": "bold"})
                    ui.Label("|", style={"color": 0xFF334155, "font_size": 10})
                    ui.Label("NAV: ACTIVE", style={"color": 0xFF00FF88, "font_size": 10, "font_weight": "bold"})
                ui.Spacer(width=6)

    def _build_left_tactical_map_column(self) -> None:
        """Left Column: Live Hospital 2D Tactical Map with path planning and active AMR overlay."""
        with ui.VStack(width=MAP_W, spacing=3):
            # Map Header
            with ui.HStack(height=18):
                ui.Label("[MAP] LIVE HOSPITAL TACTICAL MAP", style={"color": 0xFF38BDF8, "font_size": 12, "font_weight": "bold"})
                ui.Spacer()
                ui.Label("88m x 76m Floor Plan | Doorway-Safe Routing", style={"color": 0xFF94A3B8, "font_size": 10})

            # Map Canvas ZStack
            with ui.ZStack(width=MAP_W, height=MAP_H):
                # 1. Base Hospital Slab
                ui.Rectangle(style={
                    "background_color": 0xFF0B1320,
                    "border_radius": 4,
                    "border_color": 0xFF1E293B,
                    "border_width": 1.5,
                })

                # 2. Corridors (H1, H2, H3, V1, V2, V3)
                _, cy_mid = world_to_map(0.0, 2.0)
                with ui.Placer(offset_x=PAD_X, offset_y=cy_mid - 12):
                    ui.Rectangle(width=MAP_W - 2 * PAD_X, height=24, style={"background_color": 0xFF111D30})
                _, cy_n = world_to_map(0.0, 20.0)
                with ui.Placer(offset_x=PAD_X, offset_y=cy_n - 10):
                    ui.Rectangle(width=MAP_W - 2 * PAD_X, height=20, style={"background_color": 0xFF111D30})
                _, cy_s = world_to_map(0.0, -16.0)
                with ui.Placer(offset_x=PAD_X, offset_y=cy_s - 10):
                    ui.Rectangle(width=MAP_W - 2 * PAD_X, height=20, style={"background_color": 0xFF111D30})
                for vx in (-20.0, 0.0, 20.0):
                    cx_v, _ = world_to_map(vx, 0.0)
                    with ui.Placer(offset_x=cx_v - 10, offset_y=PAD_Y):
                        ui.Rectangle(width=20, height=MAP_H - 2 * PAD_Y, style={"background_color": 0xFF111D30})

                # 3. Clinical Department Rooms
                for x1, x2, y1, y2, code, color_hex, dx, dy in MAP_ROOMS:
                    rx1, ry1 = world_to_map(x1, y2)
                    rx2, ry2 = world_to_map(x2, y1)
                    rw = max(24, rx2 - rx1)
                    rh = max(18, ry2 - ry1)

                    with ui.Placer(offset_x=rx1, offset_y=ry1):
                        with ui.ZStack(width=rw, height=rh):
                            ui.Rectangle(style={
                                "background_color": 0xFF0D1726,
                                "border_color": color_hex,
                                "border_width": 1.0,
                                "border_radius": 3,
                            })
                            with ui.VStack():
                                ui.Spacer()
                                with ui.HStack():
                                    ui.Spacer()
                                    ui.Label(code, style={"color": color_hex, "font_size": 9, "font_weight": "bold"})
                                    ui.Spacer()
                                ui.Spacer()

                    # Door threshold gold marker
                    door_mx, door_my = world_to_map(dx, dy)
                    with ui.Placer(offset_x=door_mx - 3, offset_y=door_my - 3):
                        ui.Rectangle(width=6, height=6, style={"background_color": 0xFFFFCC00, "border_radius": 1})

                # 4. Waypoint Pool for Active Planned Route (up to 20 waypoints)
                for _ in range(20):
                    placer = ui.Placer(offset_x=-100, offset_y=-100)
                    with placer:
                        with ui.ZStack(width=8, height=8):
                            ui.Circle(radius=3, style={"background_color": 0xFF00E6FF})
                    self._map_wp_placers.append(placer)

                # 4b. Detour Waypoint Pool for Replanned Route (up to 16 waypoints)
                for _ in range(16):
                    d_placer = ui.Placer(offset_x=-100, offset_y=-100)
                    with d_placer:
                        with ui.ZStack(width=8, height=8):
                            ui.Circle(radius=3, style={"background_color": 0xFFFF8800})
                    self._map_detour_placers.append(d_placer)

                # 5. Start Marker Beacon
                self._map_start_placer = ui.Placer(offset_x=-100, offset_y=-100)
                with self._map_start_placer:
                    with ui.ZStack(width=14, height=14):
                        ui.Circle(radius=6, style={"background_color": 0xFF00FF88})
                        ui.Label("S", style={"color": 0xFF000000, "font_size": 8, "font_weight": "bold"})

                # 6. Current Target Waypoint Indicator
                self._map_curr_wp_placer = ui.Placer(offset_x=-100, offset_y=-100)
                with self._map_curr_wp_placer:
                    with ui.ZStack(width=16, height=16):
                        ui.Circle(radius=7, style={"background_color": 0xFFFFCC00})
                        ui.Circle(radius=4, style={"background_color": 0xFF0B1320})

                # 7. Destination Marker Beacon
                self._map_dest_placer = ui.Placer(offset_x=-100, offset_y=-100)
                with self._map_dest_placer:
                    with ui.ZStack(width=20, height=18):
                        ui.Rectangle(width=18, height=16, style={"background_color": 0xFF00FF88, "border_radius": 2})
                        ui.Label("GOAL", style={"color": 0xFF000000, "font_size": 7, "font_weight": "bold"})

                # 8. Obstacle Hazard / Blockage Marker
                self._map_hazard_placer = ui.Placer(offset_x=-100, offset_y=-100)
                with self._map_hazard_placer:
                    with ui.ZStack(width=20, height=18):
                        ui.Rectangle(width=18, height=16, style={"background_color": 0xFFFF2222, "border_radius": 2})
                        ui.Label("OBS", style={"color": 0xFFFFFFFF, "font_size": 7, "font_weight": "bold"})

                # 9. Dynamic Moving Obstacles Pool (up to 8 agents)
                for _ in range(8):
                    obs_p = ui.Placer(offset_x=-100, offset_y=-100)
                    with obs_p:
                        with ui.ZStack(width=12, height=12):
                            ui.Circle(radius=4, style={"background_color": 0xFFFF6600})
                    self._map_obs_placers.append(obs_p)

                # 10. Robot Fleet Markers (4 AMRs)
                robot_meta = [
                    ("Arogya_Delivery", "R1", 0xFF00E6FF, (34.5, 33.0)),
                    ("Mitra_Reception", "R2", 0xFF00FF88, (0.0, -5.0)),
                    ("Garuda_Emergency", "R3", 0xFFFF3B3B, (-29.0, -8.8)),
                    ("Sahayak_Support", "R4", 0xFFFFCC00, (39.5, 33.0)),
                ]
                for r_name, r_code, r_col, def_pos in robot_meta:
                    ix, iy = world_to_map(def_pos[0], def_pos[1])
                    r_placer = ui.Placer(offset_x=ix - 12, offset_y=iy - 12)
                    with r_placer:
                        with ui.ZStack(width=24, height=24):
                            ui.Rectangle(style={"background_color": 0xFF142436, "border_color": r_col, "border_width": 1.5, "border_radius": 3})
                            with ui.VStack():
                                ui.Spacer()
                                with ui.HStack():
                                    ui.Spacer()
                                    ui.Label(r_code, style={"color": r_col, "font_size": 9, "font_weight": "bold"})
                                    ui.Spacer()
                                ui.Spacer()
                    self._map_robot_placers[r_name] = r_placer

            # Navigation Status Telemetry Ribbon below map
            with ui.ZStack(height=36):
                ui.Rectangle(style={"background_color": 0xFF0E1726, "border_radius": 4, "border_color": 0xFF1E293B, "border_width": 1})
                with ui.VStack(spacing=2, style={"margin": 4}):
                    with ui.HStack(spacing=6):
                        ui.Spacer(width=2)
                        self._labels["nav_active_robot"] = ui.Label("ACTIVE: None", style={"color": 0xFF38BDF8, "font_size": 11, "font_weight": "bold"})
                        self._labels["nav_status_state"] = ui.Label("STATE: IDLE", style={"color": 0xFF00FF88, "font_size": 11, "font_weight": "bold"})
                        self._labels["nav_dest_label"] = ui.Label("DEST: None", style={"color": 0xFFE2E8F0, "font_size": 11})
                        self._labels["nav_wp_progress"] = ui.Label("WP: 0/0", style={"color": 0xFFE2E8F0, "font_size": 11})
                        self._labels["nav_dist_rem"] = ui.Label("DIST: 0.0m", style={"color": 0xFFFFCC00, "font_size": 11, "font_weight": "bold"})
                        self._labels["nav_path_status"] = ui.Label("PATH: CLEAR", style={"color": 0xFF00FF88, "font_size": 11, "font_weight": "bold"})
                        ui.Spacer()
                    with ui.HStack(spacing=6):
                        ui.Spacer(width=2)
                        self._labels["nav_reason_label"] = ui.Label("Reason: Normal Standby", style={"color": 0xFF94A3B8, "font_size": 10})
                        ui.Spacer()
                        self._labels["nav_action_label"] = ui.Label("Action: Standby on Station", style={"color": 0xFF38BDF8, "font_size": 10, "font_weight": "bold"})
                        ui.Spacer(width=2)

    def _build_right_telemetry_column(self) -> None:
        """Right Column: Fleet Telemetry, Active Mission, Voice Assistant, Navigation Telemetry."""
        with ui.VStack(spacing=4):
            # 1. Fleet Status Table (4 AMRs)
            self._build_fleet_status_panel()

            # 2. Active Mission Panel
            self._build_active_mission_panel()

            # 3. Voice Assistant Panel
            self._build_voice_interaction_panel()

            # 4. Navigation Telemetry Panel
            self._build_nav_telemetry_panel()

    def _build_fleet_status_panel(self) -> None:
        """Fleet Status: Live monitoring cards for all 4 hospital AMRs with readable fonts."""
        with ui.ZStack(height=110):
            ui.Rectangle(style={"background_color": 0xFF0E1726, "border_radius": 4, "border_color": 0xFF1E293B, "border_width": 1})
            with ui.VStack(spacing=2, style={"margin": 5}):
                with ui.HStack(height=18):
                    ui.Label("[FLEET] ROBOT FLEET TELEMETRY (4 AMRs)", style={"color": 0xFF38BDF8, "font_size": 11, "font_weight": "bold"})
                    ui.Spacer()
                    ui.Label("Real-Time Telemetry", style={"color": 0xFF94A3B8, "font_size": 10})

                amr_defs = [
                    ("r1", "Arogya_Delivery", "R1 Delivery", 0xFF00E6FF),
                    ("r2", "Mitra_Reception", "R2 Reception", 0xFF00FF88),
                    ("r3", "Garuda_Emergency", "R3 Emergency", 0xFFFF3B3B),
                    ("r4", "Sahayak_Support", "R4 Support", 0xFFFFCC00),
                ]

                for pfx, full_name, display_title, col in amr_defs:
                    with ui.HStack(height=20):
                        ui.Label(f"[{display_title[:2]}] {display_title[3:]}", width=105, style={"color": col, "font_size": 11, "font_weight": "bold"})
                        self._labels[f"{pfx}_state"] = ui.Label("IDLE", width=85, style={"color": 0xFF00FF88, "font_size": 11, "font_weight": "bold"})
                        self._labels[f"{pfx}_batt"] = ui.Label("100%", width=50, style={"color": 0xFF00FF88, "font_size": 11})
                        self._labels[f"{pfx}_pos"] = ui.Label("(0.0, 0.0)", width=95, style={"color": 0xFF94A3B8, "font_size": 11})
                        self._labels[f"{pfx}_task"] = ui.Label("Standing by in IDLE", style={"color": 0xFFCBD5E1, "font_size": 11})

    def _build_active_mission_panel(self) -> None:
        """Active Mission & Multi-Agent Coordinator Decision Panel."""
        with ui.ZStack(height=65):
            ui.Rectangle(style={"background_color": 0xFF0E1726, "border_radius": 4, "border_color": 0xFF1E293B, "border_width": 1})
            with ui.VStack(spacing=2, style={"margin": 5}):
                with ui.HStack(height=18):
                    ui.Label("[MISSION] ACTIVE CLINICAL MISSION", style={"color": 0xFF38BDF8, "font_size": 11, "font_weight": "bold"})
                    ui.Spacer()
                    self._labels["mission_prio_badge"] = ui.Label("PRIORITY: NORMAL", style={"color": 0xFF00FF88, "font_size": 11, "font_weight": "bold"})

                with ui.HStack(height=18):
                    ui.Label("Mission:", width=55, style={"color": 0xFF94A3B8, "font_size": 11, "font_weight": "bold"})
                    self._labels["mission_title"] = ui.Label("Standing by on stations", width=220, style={"color": 0xFFE2E8F0, "font_size": 11})
                    ui.Label("Assigned:", width=60, style={"color": 0xFF94A3B8, "font_size": 11, "font_weight": "bold"})
                    self._labels["mission_assigned"] = ui.Label("None", style={"color": 0xFF00E6FF, "font_size": 11, "font_weight": "bold"})

                with ui.HStack(height=18):
                    ui.Label("Progress:", width=55, style={"color": 0xFF94A3B8, "font_size": 11, "font_weight": "bold"})
                    self._labels["mission_progress_bar"] = ui.Label("[------------] 0%", width=220, style={"color": 0xFFFFCC00, "font_size": 11, "font_weight": "bold"})
                    ui.Label("Bidding:", width=60, style={"color": 0xFF94A3B8, "font_size": 11, "font_weight": "bold"})
                    self._labels["mission_bidding"] = ui.Label("Contract-Net Ready", style={"color": 0xFF94A3B8, "font_size": 11})

    def _build_voice_interaction_panel(self) -> None:
        """Voice Assistant & Mobile Voice Terminal: FSM state, phone connection, URL, QR, command, intent."""
        with ui.ZStack(height=78):
            ui.Rectangle(style={"background_color": 0xFF0E1726, "border_radius": 4, "border_color": 0xFF1E293B, "border_width": 1})
            with ui.VStack(spacing=2, style={"margin": 5}):
                with ui.HStack(height=18):
                    ui.Label("[MOBILE VOICE] PRIMARY MIC & COMMAND CONSOLE", style={"color": 0xFF38BDF8, "font_size": 11, "font_weight": "bold"})
                    ui.Spacer()
                    self._labels["mobile_server_status"] = ui.Label("SERVER: ONLINE", style={"color": 0xFF00FF88, "font_size": 10, "font_weight": "bold"})
                    ui.Spacer(width=6)
                    self._labels["voice_fsm_state"] = ui.Label("[SLEEPING]", style={"color": 0xFFFFCC00, "font_size": 11, "font_weight": "bold"})

                with ui.HStack(height=18):
                    ui.Label("Phone Link:", width=75, style={"color": 0xFF94A3B8, "font_size": 11, "font_weight": "bold"})
                    self._labels["mobile_phone_conn"] = ui.Label("DISCONNECTED", width=105, style={"color": 0xFFFF3B3B, "font_size": 10, "font_weight": "bold"})
                    ui.Label("URL:", width=32, style={"color": 0xFF94A3B8, "font_size": 11, "font_weight": "bold"})
                    self._labels["mobile_url"] = ui.Label("https://192.168.x.x:8082", width=160, style={"color": 0xFF00E6FF, "font_size": 10})
                    ui.Label("Intent:", width=45, style={"color": 0xFF94A3B8, "font_size": 11, "font_weight": "bold"})
                    self._labels["voice_intent"] = ui.Label("None", style={"color": 0xFFE2E8F0, "font_size": 11, "font_weight": "bold"})

                with ui.HStack(height=18):
                    ui.Label("Transcript:", width=75, style={"color": 0xFF94A3B8, "font_size": 11, "font_weight": "bold"})
                    self._labels["voice_transcript"] = ui.Label("Standing by for mobile voice commands", style={"color": 0xFFCBD5E1, "font_size": 11})

                with ui.HStack(height=16):
                    ui.Label("QR Link:", width=75, style={"color": 0xFF94A3B8, "font_size": 10})
                    self._labels["mobile_qr_info"] = ui.Label("Scan QR on terminal or browse https://<IP>:8082", style={"color": 0xFF38BDF8, "font_size": 10})
                    ui.Spacer()
                    self._labels["stt_service_status"] = ui.Label("STT: READY", style={"color": 0xFF10B981, "font_size": 10, "font_weight": "bold"})

    def _build_nav_telemetry_panel(self) -> None:
        """Technical navigation telemetry panel."""
        with ui.ZStack(height=62):
            ui.Rectangle(style={"background_color": 0xFF0E1726, "border_radius": 4, "border_color": 0xFF1E293B, "border_width": 1})
            with ui.VStack(spacing=2, style={"margin": 5}):
                with ui.HStack(height=18):
                    ui.Label("[NAV] TOPOLOGICAL-METRIC NAVIGATION", style={"color": 0xFF38BDF8, "font_size": 11, "font_weight": "bold"})
                    ui.Spacer()
                    self._labels["dbg_goal_validity"] = ui.Label("Goal Validity: VALID", style={"color": 0xFF00FF88, "font_size": 10, "font_weight": "bold"})

                with ui.HStack(height=16):
                    self._labels["dbg_start_pos"] = ui.Label("Start: (34.5, 33.0)", width=140, style={"color": 0xFF94A3B8, "font_size": 10})
                    self._labels["dbg_goal_pos"] = ui.Label("Goal: (14.0, 23.2)", width=140, style={"color": 0xFF94A3B8, "font_size": 10})
                    self._labels["dbg_wps_count"] = ui.Label("Waypoints: 6 (Cur: 0)", style={"color": 0xFFE2E8F0, "font_size": 10})

                with ui.HStack(height=16):
                    self._labels["dbg_dist_rem"] = ui.Label("Dist Rem: 0.0m", width=140, style={"color": 0xFFFFCC00, "font_size": 10})
                    self._labels["dbg_obstacle_status"] = ui.Label("Obstacle: None", width=140, style={"color": 0xFF00FF88, "font_size": 10})
                    self._labels["dbg_replanned"] = ui.Label("Replanned: NO", style={"color": 0xFF38BDF8, "font_size": 10, "font_weight": "bold"})

    # =========================================================================
    # COMMAND CENTER  —  Primary full-width robot dispatch panel
    # =========================================================================

    def _build_command_center_panel(self) -> None:
        """
        Full-width Command Center panel:
        - Header with title, subtitle, and live status badge
        - Target Robot Selector: [AUTO] [Arogya] [Mitra] [Garuda] [Sahayak]
        - Natural language command text input + SEND button
        - Row 1 Quick Action Buttons: ICU, PHARMACY, RECEPTION, LABORATORY, EMERGENCY (P1)
        - Row 2 Quick Action Buttons: OPD CLINIC, OPERATION THEATER, DOCK/CHARGE, STOP ALL, RESUME, FLEET STATUS
        """
        with ui.ZStack(height=238):
            # High-visibility border
            ui.Rectangle(style={
                "background_color": 0xFF0A1628,
                "border_radius": 4,
                "border_color": 0xFF00E6FF,
                "border_width": 1.5,
            })
            with ui.VStack(spacing=4, style={"margin": 6}):

                # ── Header row ─────────────────────────────────────────────
                with ui.HStack(height=20):
                    ui.Label(
                        "COMMAND CENTER",
                        style={"color": 0xFF00E6FF, "font_size": 13, "font_weight": "bold"}
                    )
                    ui.Label(
                        " - Fleet Dispatch & Clinical Mission Controls",
                        style={"color": 0xFF94A3B8, "font_size": 10}
                    )
                    ui.Spacer()
                    _b("PATIENT WARD", 0xFF047857, self._toggle_patient_board, height=20, font_size=10)
                    ui.Spacer(width=4)
                    _b("CLINICAL DB", 0xFF0E7490, self._toggle_db_controls, height=20, font_size=10)
                    ui.Spacer(width=6)
                    self._labels["cmd_status"] = ui.Label(
                        "Ready",
                        style={"color": 0xFF00FF88, "font_size": 11, "font_weight": "bold"}
                    )

                # ── Robot selector ─────────────────────────────────────────
                with ui.HStack(height=26, spacing=6):
                    ui.Label("ROBOT:", width=55,
                             style={"color": 0xFF94A3B8, "font_size": 11, "font_weight": "bold"})
                    robot_opts = [
                        ("AUTO",    "AUTO",             0xFF00E6FF, 0xFF0E7490),
                        ("Arogya",  "Arogya_Delivery",  0xFF00E6FF, 0xFF1E3A8A),
                        ("Mitra",   "Mitra_Reception",  0xFF00FF88, 0xFF065F46),
                        ("Garuda",  "Garuda_Emergency", 0xFFFF3B3B, 0xFF7F1D1D),
                        ("Sahayak", "Sahayak_Support",  0xFFFFCC00, 0xFF78350F),
                    ]
                    for label_text, robot_key, hl_color, bg_color in robot_opts:
                        is_auto = (label_text == "AUTO")
                        btn = ui.Button(
                            label_text,
                            width=80,
                            height=24,
                            style={
                                "background_color": bg_color if is_auto else 0xFF1E293B,
                                "font_size": 11,
                                "font_weight": "bold",
                                "color": hl_color if is_auto else 0xFF64748B,
                                "border_radius": 3,
                            },
                        )
                        btn.set_clicked_fn(_safe_cb(lambda rk=robot_key, lt=label_text: self._on_robot_selected(rk, lt)))
                        self._robot_btn_refs[robot_key] = btn
                    ui.Spacer()

                # ── Command text input ─────────────────────────────────────
                with ui.HStack(height=28, spacing=6):
                    ui.Label("Command:", width=70,
                             style={"color": 0xFF94A3B8, "font_size": 11, "font_weight": "bold"})
                    self._cmd_string_field = ui.StringField(
                        height=26,
                        style={
                            "background_color": 0xFF142436,
                            "color": 0xFFFFFFFF,
                            "font_size": 11,
                            "border_radius": 3,
                            "border_color": 0xFF00E6FF,
                            "border_width": 1.0,
                        },
                    )
                    # Submit on enter in string field if model supports it
                    if hasattr(self._cmd_string_field, "model") and hasattr(self._cmd_string_field.model, "set_value"):
                        pass

                    btn_send = ui.Button(
                        "SEND", width=75, height=26,
                        style={"background_color": 0xFF0E7490, "font_size": 11, "font_weight": "bold", "border_radius": 3},
                    )
                    btn_send.set_clicked_fn(_safe_cb(self._on_cmd_field_submit))

                # ── Quick Action Row 1: Clinical Destinations ──────────────
                with ui.HStack(height=28, spacing=4):
                    _b("GO TO ICU",        0xFF0284C7, lambda: self._on_btn_clicked("go to ICU"), height=26, font_size=11)
                    _b("PHARMACY",         0xFF581C87, lambda: self._on_btn_clicked("go to Pharmacy"), height=26, font_size=11)
                    _b("RECEPTION",        0xFF1E3A8A, lambda: self._on_btn_clicked("go to Reception"), height=26, font_size=11)
                    _b("LABORATORY",       0xFF0F766E, lambda: self._on_btn_clicked("go to Laboratory"), height=26, font_size=11)
                    _b("EMERGENCY (P1)",   0xFFB91C1C, lambda: self._on_btn_clicked("emergency"), height=26, font_size=11)

                # ── Quick Action Row 2: Secondary + Fleet Directives ───────
                with ui.HStack(height=28, spacing=4):
                    _b("OPD CLINIC",        0xFF2563EB, lambda: self._on_btn_clicked("go to OPD"), height=26, font_size=11)
                    _b("OPERATION THEATER", 0xFF0E7490, lambda: self._on_btn_clicked("go to OT"), height=26, font_size=11)
                    _b("DOCK / CHARGE",     0xFF065F46, lambda: self._on_btn_clicked("return to charger"), height=26, font_size=11)
                    _b("STOP ALL",          0xFF991B1B, lambda: self._on_btn_clicked("stop"), height=26, font_size=11)
                    _b("RESUME",            0xFF1E40AF, lambda: self._on_btn_clicked("resume"), height=26, font_size=11)
                    _b("FLEET STATUS",      0xFF854D0E, lambda: self._on_btn_clicked("status"), height=26, font_size=11)

                # ── Quick Action Row 3: Clinical Database & Patient Operations ─
                with ui.HStack(height=28, spacing=4):
                    _b("[PATIENTS]",        0xFF047857, self._toggle_patient_board, height=26, font_size=11)
                    _b("[CLINICAL DB]",     0xFF0E7490, self._toggle_db_controls, height=26, font_size=11)
                    _b("ACTIVE PATIENTS",   0xFF1D4ED8, lambda: self._on_btn_clicked("show active patients"), height=26, font_size=11)
                    _b("MEDS ROUNDS",       0xFF581C87, lambda: self._on_btn_clicked("check medication schedule"), height=26, font_size=11)
                    _b("CODE BLUE P003",    0xFF991B1B, lambda: self._on_btn_clicked("code blue for patient P003"), height=26, font_size=11)
                    _b("DR FOR P001",       0xFF0F766E, lambda: self._on_btn_clicked("who is the doctor for patient P001"), height=26, font_size=11)

                # ── Environment & Dynamic Obstacles Row ──────────────────
                with ui.HStack(height=26, spacing=4):
                    ui.Label("ENVIRONMENT:", width=95, style={"color": 0xFF94A3B8, "font_size": 10, "font_weight": "bold"})
                    _b("LIGHT", 0xFF0E7490, lambda: self._on_traffic_change("light"), height=22, font_size=10)
                    _b("NORMAL", 0xFF1E40AF, lambda: self._on_traffic_change("normal"), height=22, font_size=10)
                    _b("BUSY", 0xFFB91C1C, lambda: self._on_traffic_change("busy"), height=22, font_size=10)
                    ui.Spacer(width=6)
                    self._labels["traffic_info"] = ui.Label("Density: NORMAL | Seed: AUTO", style={"color": 0xFF00FF88, "font_size": 10})
                    ui.Spacer()
                    _b("REGENERATE", 0xFF065F46, lambda: self._on_traffic_regenerate(), height=22, font_size=10)

    def _on_traffic_change(self, mode: str) -> None:
        """Handle traffic density selection from HUD."""
        self._current_traffic_mode = mode
        if self.traffic_callback:
            self.traffic_callback(action="set_mode", mode=mode)
        if "traffic_info" in self._labels:
            seed_str = getattr(self, "_current_traffic_seed", "AUTO")
            self._labels["traffic_info"].text = f"Density: {mode.upper()} | Seed: {seed_str}"
        self.add_log(f"[ENV] Traffic density set to {mode.upper()}")

    def _on_traffic_regenerate(self) -> None:
        """Regenerate hospital dynamic obstacles with a fresh seed."""
        seed = int(np.random.randint(10000, 99999))
        self._current_traffic_seed = seed
        mode = getattr(self, "_current_traffic_mode", "normal")
        if self.traffic_callback:
            self.traffic_callback(action="regenerate", mode=mode, seed=seed)
        if "traffic_info" in self._labels:
            self._labels["traffic_info"].text = f"Density: {mode.upper()} | Seed: {seed}"
        self.add_log(f"[ENV] Regenerated dynamic obstacles (Mode: {mode.upper()}, Seed: {seed})")

    def _build_bottom_command_center(self) -> None:
        """Backward compatibility stub for legacy callers."""
        pass

    def _build_reasoning_and_radar_panel(self) -> None:
        """
        AROGYA Perception-Reasoning Digital Twin Panel:
        - LEFT: Local LiDAR Perception Radar & Sensor Follow Telemetry (footprint, closest obstacle, yielding status)
        - RIGHT: Explainable Decision Engine (5-Tuple: Situation, Constraints, Options, Decision, Action)
        """
        with ui.ZStack(height=148):
            ui.Rectangle(style={
                "background_color": 0xFF0A1628,
                "border_radius": 4,
                "border_color": 0xFF38BDF8,
                "border_width": 1.0,
            })
            with ui.VStack(spacing=3, style={"margin": 5}):
                # Header row
                with ui.HStack(height=16):
                    ui.Label("[TWIN] PERCEPTION-REASONING DIGITAL TWIN", style={"color": 0xFF38BDF8, "font_size": 11, "font_weight": "bold"})
                    ui.Spacer()
                    self._labels["twin_sensor_mode"] = ui.Label("FOLLOW: Arogya_Delivery [Pinhole Cam (70 deg) + 360 LiDAR]", style={"color": 0xFF00FF88, "font_size": 9, "font_weight": "bold"})

                with ui.HStack(spacing=6):
                    # LEFT SUBPANEL: Local LiDAR Perception Radar
                    with ui.ZStack(width=340):
                        ui.Rectangle(style={"background_color": 0xFF0E1726, "border_radius": 3, "border_color": 0xFF1E293B, "border_width": 1})
                        with ui.VStack(spacing=2, style={"margin": 4}):
                            with ui.HStack(height=16):
                                ui.Label("LOCAL LIDAR RADAR (360)", style={"color": 0xFF00E6FF, "font_size": 10, "font_weight": "bold"})
                                ui.Spacer()
                                self._labels["radar_status_badge"] = ui.Label("180 BEAMS: ACTIVE", style={"color": 0xFF00FF88, "font_size": 9})

                            with ui.HStack(height=16):
                                ui.Label("Follow Target:", width=80, style={"color": 0xFF94A3B8, "font_size": 10})
                                self._labels["radar_robot_name"] = ui.Label("Arogya_Delivery", style={"color": 0xFF00E6FF, "font_size": 10, "font_weight": "bold"})

                            with ui.HStack(height=16):
                                ui.Label("Obstacle Dist:", width=80, style={"color": 0xFF94A3B8, "font_size": 10})
                                self._labels["radar_closest_obs"] = ui.Label("CLEAR (>5.0m)", style={"color": 0xFF00FF88, "font_size": 10, "font_weight": "bold"})

                            with ui.HStack(height=16):
                                ui.Label("Safety Zone:", width=80, style={"color": 0xFF94A3B8, "font_size": 10})
                                self._labels["radar_safety_zone"] = ui.Label("CLEAR (No Dynamic Blocks)", style={"color": 0xFF00FF88, "font_size": 10})

                            with ui.HStack(height=16):
                                ui.Label("Human Aware:", width=80, style={"color": 0xFF94A3B8, "font_size": 10})
                                self._labels["radar_human_yield"] = ui.Label("Social Clearance Nominal", style={"color": 0xFFCBD5E1, "font_size": 10})

                    # RIGHT SUBPANEL: Explainable Decision Engine (5-Tuple)
                    with ui.ZStack():
                        ui.Rectangle(style={"background_color": 0xFF0E1726, "border_radius": 3, "border_color": 0xFF1E293B, "border_width": 1})
                        with ui.VStack(spacing=1, style={"margin": 4}):
                            with ui.HStack(height=16):
                                ui.Label("COGNITIVE DECISION ENGINE (5-TUPLE)", style={"color": 0xFFFFCC00, "font_size": 10, "font_weight": "bold"})
                                ui.Spacer()
                                self._labels["reason_decision_badge"] = ui.Label("DECISION: STANDBY", style={"color": 0xFF00FF88, "font_size": 9, "font_weight": "bold"})

                            with ui.HStack(height=16):
                                ui.Label("SITUATION:", width=75, style={"color": 0xFF94A3B8, "font_size": 9, "font_weight": "bold"})
                                self._labels["reason_situation"] = ui.Label("Robot idle on designated station", style={"color": 0xFFE2E8F0, "font_size": 9})

                            with ui.HStack(height=16):
                                ui.Label("CONSTRAINTS:", width=75, style={"color": 0xFF94A3B8, "font_size": 9, "font_weight": "bold"})
                                self._labels["reason_constraints"] = ui.Label("Awaiting clinical mission dispatch", style={"color": 0xFFE2E8F0, "font_size": 9})

                            with ui.HStack(height=16):
                                ui.Label("OPTIONS:", width=75, style={"color": 0xFF94A3B8, "font_size": 9, "font_weight": "bold"})
                                self._labels["reason_options"] = ui.Label("STANDBY | CHARGE | DISPATCH", style={"color": 0xFFE2E8F0, "font_size": 9})

                            with ui.HStack(height=16):
                                ui.Label("DECISION:", width=75, style={"color": 0xFF94A3B8, "font_size": 9, "font_weight": "bold"})
                                self._labels["reason_decision"] = ui.Label("STANDBY", style={"color": 0xFF00FF88, "font_size": 9, "font_weight": "bold"})

                            with ui.HStack(height=16):
                                ui.Label("ACTION:", width=75, style={"color": 0xFF94A3B8, "font_size": 9, "font_weight": "bold"})
                                self._labels["reason_action"] = ui.Label("Awaiting clinical assignment with sensors active", style={"color": 0xFF38BDF8, "font_size": 9, "font_weight": "bold"})

    def _build_communication_log_panel(self) -> None:
        """Dedicated full-width agent communication and coordinator event feed."""
        with ui.ZStack(height=92):
            ui.Rectangle(style={"background_color": 0xFF0E1726, "border_radius": 4, "border_color": 0xFF1E293B, "border_width": 1})
            with ui.VStack(spacing=2, style={"margin": 5}):
                with ui.HStack(height=16):
                    ui.Label("[LOG] AGENT EVENT & COMMUNICATION LOG", style={"color": 0xFF38BDF8, "font_size": 11, "font_weight": "bold"})
                    ui.Spacer()
                    ui.Label("Live Chronological Agent Feed", style={"color": 0xFF94A3B8, "font_size": 9})
                with ui.ScrollingFrame(
                    height=64,
                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
                    style={"background_color": 0xFF070B12, "border_radius": 3, "border_color": 0xFF1E293B, "border_width": 1}
                ):
                    with ui.VStack(spacing=1, style={"margin": 3}):
                        for idx in range(6):
                            self._labels[f"comm_log_{idx}"] = ui.Label(
                                self._logs[idx] if idx < len(self._logs) else "",
                                style={"color": 0xFF94A3B8, "font_size": 10}
                            )

    def _on_robot_selected(self, robot_key: str, label: str) -> None:
        """Handle robot selector button click safely."""
        try:
            self._selected_robot = robot_key
            dim_style = {"background_color": 0xFF1E293B, "font_size": 11, "font_weight": "bold", "color": 0xFF64748B, "border_radius": 3}
            active_style = {"background_color": 0xFF0E7490, "font_size": 11, "font_weight": "bold", "color": 0xFF00E6FF, "border_radius": 3}
            for rk, btn in self._robot_btn_refs.items():
                try:
                    btn.style = active_style if rk == robot_key else dim_style
                except Exception:
                    pass
            self._set_cmd_status(f"Target: {label}", 0xFF00FF88)
            self.add_log(f"[CMD] Target robot set -> {label}")

            # Sensor Follow Mode: update physical camera & LiDAR to follow selected robot
            if robot_key != "AUTO":
                try:
                    from sensors.camera_manager import CameraSensorManager
                    from sensors.lidar_manager import LiDARSensorManager
                    CameraSensorManager.select_robot(robot_key)
                    LiDARSensorManager.select_robot(robot_key)
                except Exception:
                    try:
                        from isaac_sim_hospital.sensors.camera_manager import CameraSensorManager
                        from isaac_sim_hospital.sensors.lidar_manager import LiDARSensorManager
                        CameraSensorManager.select_robot(robot_key)
                        LiDARSensorManager.select_robot(robot_key)
                    except Exception:
                        pass
                try:
                    from web import PERCEPTION_BUFFER
                    PERCEPTION_BUFFER.set_selected_robot(robot_key)
                except Exception:
                    pass
        except Exception as e:
            print(f"[HUD ERROR] _on_robot_selected: {e}", flush=True)
            traceback.print_exc()

    def _set_cmd_status(self, text: str, color: int = 0xFF00FF88) -> None:
        """Update the Command Center status label safely."""
        if "cmd_status" in self._labels:
            try:
                self._labels["cmd_status"].text = text
                self._labels["cmd_status"].style = {"color": color, "font_size": 11, "font_weight": "bold"}
            except Exception:
                pass

    def _on_cmd_field_submit(self) -> None:
        """Dispatch text command from UI StringField safely."""
        try:
            if hasattr(self, "_cmd_string_field") and self._cmd_string_field and hasattr(self._cmd_string_field, "model"):
                val = getattr(self._cmd_string_field.model, "as_string", None)
                if val is None and hasattr(self._cmd_string_field.model, "get_value_as_string"):
                    val = self._cmd_string_field.model.get_value_as_string()
                text = (val or "").strip()
                if text:
                    try:
                        self._cmd_string_field.model.set_value("")
                    except Exception:
                        pass
                    self._on_btn_clicked(text)
        except Exception as e:
            print(f"[HUD ERROR] _on_cmd_field_submit: {e}", flush=True)
            traceback.print_exc()

    def _on_btn_clicked(self, command_text: str) -> None:
        """Execute clinical mission command through Coordinator pipeline safely."""
        try:
            clean_cmd = _sanitize_text(command_text).strip()
            if not clean_cmd:
                return
            robot_tag = getattr(self, "_selected_robot", "AUTO")
            self._set_cmd_status(f"Sent: {clean_cmd[:24]}", 0xFF00FF88)
            self.add_log(f"[USER] Command: \"{clean_cmd}\" | Target: {robot_tag}")

            if self.command_callback:
                try:
                    self.command_callback(clean_cmd, source="gui", target_robot=robot_tag)
                except TypeError:
                    try:
                        self.command_callback(clean_cmd, source="gui")
                    except TypeError:
                        self.command_callback(clean_cmd)
            else:
                self._set_cmd_status("No callback connected", 0xFFFF3B3B)
                self.add_log("[ERROR] No command_callback set on HUD")
        except Exception as e:
            print(f"[HUD ERROR] _on_btn_clicked failed: {e}", flush=True)
            traceback.print_exc()
            self._set_cmd_status("COMMAND ERROR", 0xFFFF3B3B)

    def _toggle_patient_board(self) -> None:
        """Toggle visibility of PatientBoardPanel safely."""
        try:
            if not self._patient_board_panel:
                self.add_log("[UI] Patient Board Panel not initialized")
                return
            if getattr(self._patient_board_panel, "_window", None) is None and OMNI_UI_AVAILABLE:
                self._patient_board_panel.build_ui(visible=True)
                self.add_log("[UI] Patient Board Panel opened")
            elif getattr(self._patient_board_panel, "_window", None) is not None:
                if self._patient_board_panel._window.visible:
                    self._patient_board_panel.hide()
                    self.add_log("[UI] Patient Board Panel hidden")
                else:
                    self._patient_board_panel.show()
                    self.add_log("[UI] Patient Board Panel opened")
        except Exception as e:
            print(f"[HUD ERROR] _toggle_patient_board: {e}", flush=True)

    def _toggle_db_controls(self) -> None:
        """Toggle visibility of DBControlPanel safely."""
        try:
            if not self._db_control_panel:
                self.add_log("[UI] Clinical DB Control Panel not initialized")
                return
            if getattr(self._db_control_panel, "_window", None) is None and OMNI_UI_AVAILABLE:
                self._db_control_panel.build_ui(visible=True)
                self.add_log("[UI] Clinical DB Control Panel opened")
            elif getattr(self._db_control_panel, "_window", None) is not None:
                if self._db_control_panel._window.visible:
                    self._db_control_panel.hide()
                    self.add_log("[UI] Clinical DB Control Panel hidden")
                else:
                    self._db_control_panel.show()
                    self.add_log("[UI] Clinical DB Control Panel opened")
        except Exception as e:
            print(f"[HUD ERROR] _toggle_db_controls: {e}", flush=True)

    def _on_patient_board_action(self, action: str, patient_id: str, data: Dict[str, Any]) -> None:
        """Handle actions triggered from PatientBoardPanel."""
        try:
            if action == "status_query":
                self._on_btn_clicked(f"check status of patient {patient_id}")
            elif action == "medication_delivery":
                self._on_btn_clicked(f"deliver medication to patient {patient_id}")
            elif action == "code_blue":
                self._on_btn_clicked(f"code blue for patient {patient_id}")
            else:
                self.add_log(f"[PATIENT BOARD] Action: {action} on {patient_id}")
        except Exception as e:
            print(f"[HUD ERROR] _on_patient_board_action: {e}", flush=True)

    def _on_db_scenario(self, scenario: str, data: Dict[str, Any]) -> None:
        """Handle clinical scenario injection from DBControlPanel."""
        try:
            if scenario == "med_delivery":
                med = data.get("medicine", "medication")
                p_id = data.get("patient_id", "P001")
                self._on_btn_clicked(f"deliver {med} to patient {p_id}")
            elif scenario == "doctor_query":
                p_id = data.get("patient_id", "P001")
                self._on_btn_clicked(f"who is the doctor for patient {p_id}")
            elif scenario == "active_patients":
                self._on_btn_clicked("show active patients")
            else:
                self.add_log(f"[CLINICAL DB] Scenario: {scenario}")
        except Exception as e:
            print(f"[HUD ERROR] _on_db_scenario: {e}", flush=True)

    def add_log(self, text: str) -> None:
        """Append message to Coordinator / Agent Communication log feed (Sanitized ASCII)."""
        try:
            safe_text = _sanitize_text(text)
            timestamp = time.strftime("%H:%M:%S")
            entry = f"[{timestamp}] {safe_text}"
            self._logs.append(entry)
            if len(self._logs) > 60:
                self._logs.pop(0)

            if OMNI_UI_AVAILABLE and self.window:
                latest = self._logs[-6:]
                for idx, log_entry in enumerate(latest):
                    key = f"comm_log_{idx}"
                    if key in self._labels:
                        self._labels[key].text = log_entry
                        if "CODE BLUE" in log_entry or "EMERGENCY" in log_entry or "Preempted" in log_entry:
                            self._labels[key].style = {"color": 0xFFFF3B3B, "font_size": 10, "font_weight": "bold"}
                        elif "Wake word" in log_entry or "WAKE" in log_entry or "AROGYA" in log_entry:
                            self._labels[key].style = {"color": 0xFF00FF88, "font_size": 10, "font_weight": "bold"}
                        elif "Awarded" in log_entry or "Selected" in log_entry or "Assigned" in log_entry:
                            self._labels[key].style = {"color": 0xFF38BDF8, "font_size": 10}
                        elif "Detour" in log_entry or "REPLAN" in log_entry or "Obstacle" in log_entry:
                            self._labels[key].style = {"color": 0xFFFFCC00, "font_size": 10, "font_weight": "bold"}
                        else:
                            self._labels[key].style = {"color": 0xFF94A3B8, "font_size": 10}
        except Exception:
            pass

    def add_task(self, task_desc: str, priority_str: str, assigned_robot: str, status_str: str = "ACTIVE") -> None:
        """Record mission assignment in dashboard and communication log."""
        try:
            self.active_mission_task = _sanitize_text(task_desc)
            self.active_mission_robot = _sanitize_text(assigned_robot)
            self.active_mission_priority = _sanitize_text(priority_str)
            self.add_log(f"Mission Awarded: {self.active_mission_task} -> {self.active_mission_robot} [Prio: {self.active_mission_priority}]")
        except Exception:
            pass

    def update(
        self,
        robots: Dict[str, Any],
        voice_state_str: str = "SLEEPING",
        is_listening: bool = False,
        mic_status: Optional[str] = None,
        last_transcript: Optional[str] = None,
        dynamic_obstacles: Optional[Any] = None,
        coordinator_info: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Refresh dynamic telemetry labels and map markers for all 4 robots each simulation step.
        """
        if not OMNI_UI_AVAILABLE or not self.window:
            return

        now = time.time()
        # Requirement 4: Throttle UI updates to 8 Hz (125ms) so Kit UI/GLFW thread is never starved
        last_u = getattr(self, "_last_ui_update_time", 0.0)
        interval = getattr(self, "_ui_update_interval", 0.125)
        if last_u and (now - last_u < interval):
            return
        self._last_ui_update_time = now

        try:
            if hasattr(self, "_step_counter"):
                self._step_counter += 1
            else:
                self._step_counter = 0

            if self._step_counter % 60 == 0 and self._patient_board_panel:
                try:
                    if getattr(self._patient_board_panel, "_window", None) and self._patient_board_panel._window.visible:
                        self._patient_board_panel.refresh()
                except Exception:
                    pass

            # 1. Update Voice Panel & System Badge
            v_color = 0xFFFFCC00
            if "WAKE" in voice_state_str:
                v_color = 0xFF00FF88
            elif "LISTENING" in voice_state_str or is_listening:
                v_color = 0xFF00E6FF
            elif "TRANSCRIBING" in voice_state_str:
                v_color = 0xFF38BDF8
            elif "COMMAND" in voice_state_str or "PROCESSING" in voice_state_str:
                v_color = 0xFFE879F9
            elif "EXECUTING" in voice_state_str:
                v_color = 0xFF10B981

            self._set_label("voice_fsm_state", f"[{voice_state_str}]", color=v_color, font_size=11, font_weight="bold")
            self._set_label("sys_voice_state", f"VOICE: {voice_state_str[:12]}", color=v_color, font_size=10, font_weight="bold")

            if mic_status:
                col = 0xFFFF3B3B if "ERROR" in mic_status else 0xFF00FF88
                self._set_label("sys_mic", "MIC: ERROR" if "ERROR" in mic_status else "MIC: 16kHz", color=col, font_size=10, font_weight="bold")

            if last_transcript and last_transcript not in ("None", "", "huh", "um"):
                self._set_label("voice_transcript", f"\"{_sanitize_text(last_transcript)[:45]}\"")
            elif "LISTENING" in voice_state_str or is_listening:
                self._set_label("voice_transcript", "Listening for clinical request...")
            else:
                self._set_label("voice_transcript", "Standing by for clinical commands")

            # 1b. Update Mobile Voice Server Telemetry
            if self._mobile_server:
                try:
                    s_dict = self._mobile_server.get_status_dict()
                    is_connected = s_dict.get("client_connected", False)
                    lan_url = s_dict.get("url", "")
                    self._set_label(
                        "mobile_phone_conn",
                        "CONNECTED" if is_connected else "DISCONNECTED",
                        color=0xFF00FF88 if is_connected else 0xFFFF3B3B,
                        font_size=10,
                        font_weight="bold",
                    )
                    if lan_url:
                        self._set_label("mobile_url", lan_url)
                    srv_state = s_dict.get("server", "ONLINE")
                    self._set_label(
                        "mobile_server_status",
                        f"SERVER: {srv_state}",
                        color=0xFF00FF88 if srv_state == "ONLINE" else 0xFFFF3B3B,
                        font_size=10,
                        font_weight="bold",
                    )
                    stt_info = s_dict.get("stt_service", {})
                    stt_state = stt_info.get("status", "READY")
                    stt_color = 0xFF10B981 if stt_state == "READY" else (0xFFFFCC00 if stt_state in ("STARTING", "PROCESSING") else 0xFFFF3B3B)
                    self._set_label("stt_service_status", f"STT: {stt_state}", color=stt_color, font_size=10, font_weight="bold")
                except Exception:
                    pass

            # 2. Update Fleet Status Cards & Dynamic Map Markers
            robot_map = [
                ("Arogya_Delivery", "r1"),
                ("Mitra_Reception", "r2"),
                ("Garuda_Emergency", "r3"),
                ("Sahayak_Support", "r4"),
            ]

            active_amr = None
            for r_key, pfx in robot_map:
                r = robots.get(r_key)
                if not r:
                    continue

                if getattr(r, "mission_active", False) or getattr(r, "action_active", False):
                    if active_amr is None or r.priority_level < active_amr.priority_level:
                        active_amr = r

                # State
                st_name = getattr(r.state_machine.state, "name", "IDLE")
                st_col = 0xFF00FF88 if st_name in ["IDLE", "STANDBY"] else (0xFFFF3B3B if "EMERGENCY" in st_name or "BLOCKED" in st_name else 0xFF38BDF8)
                self._set_label(f"{pfx}_state", st_name, color=st_col, font_size=11, font_weight="bold")

                # Battery
                chg_tag = " (CHG)" if getattr(r, "is_charging", False) else ""
                batt_col = 0xFF00FF88 if r.battery_level > 30 else 0xFFFF3B3B
                self._set_label(f"{pfx}_batt", f"{r.battery_level:.0f}%{chg_tag}", color=batt_col, font_size=11)

                # Position
                pos = r.get_position() if hasattr(r, "get_position") else (r.x, r.y)
                self._set_label(f"{pfx}_pos", f"({pos[0]:.1f}, {pos[1]:.1f})")

                # Task
                t_desc = _sanitize_text(r.current_task_description or "Standing by in IDLE")
                self._set_label(f"{pfx}_task", t_desc[:26])

                # Update Map Marker Position
                if r_key in self._map_robot_placers:
                    mx, my = world_to_map(pos[0], pos[1])
                    self._map_robot_placers[r_key].offset_x = mx - 12
                    self._map_robot_placers[r_key].offset_y = my - 12

            # 3. Update Active AMR Navigation Ribbon & Mission Progress
            if active_amr:
                act_name = active_amr.name
                act_state = getattr(active_amr.state_machine.state, "name", "IDLE")
                act_wps = getattr(active_amr, "waypoints", [])
                act_idx = getattr(active_amr, "current_waypoint_idx", 0)
                act_dest = getattr(active_amr, "destination_name", "N/A")
                rem_dist = active_amr.get_remaining_distance() if hasattr(active_amr, "get_remaining_distance") else 0.0
                act_reason = _sanitize_text(getattr(active_amr.state_machine, "current_reason", "Normal Navigation"))
                act_action = _sanitize_text(getattr(active_amr.state_machine, "current_action", "Tracking Waypoints"))

                if "nav_active_robot" in self._labels:
                    self._labels["nav_active_robot"].text = f"ACTIVE: {act_name}"
                if "nav_status_state" in self._labels:
                    self._labels["nav_status_state"].text = f"STATE: {act_state}"
                if "nav_dest_label" in self._labels:
                    self._labels["nav_dest_label"].text = f"DEST: {act_dest}"
                if "nav_wp_progress" in self._labels:
                    self._labels["nav_wp_progress"].text = f"WP: {min(len(act_wps), act_idx + 1)}/{len(act_wps)}"
                if "nav_dist_rem" in self._labels:
                    self._labels["nav_dist_rem"].text = f"DIST: {rem_dist:.1f}m"

                # Path condition
                if "nav_path_status" in self._labels:
                    if getattr(active_amr, "is_replanned", False):
                        self._labels["nav_path_status"].text = "PATH: REPLANNED DETOUR"
                        self._labels["nav_path_status"].style = {"color": 0xFFFFCC00, "font_size": 11, "font_weight": "bold"}
                    elif getattr(active_amr, "is_blocked", False):
                        self._labels["nav_path_status"].text = "PATH: BLOCKED (YIELDING)"
                        self._labels["nav_path_status"].style = {"color": 0xFFFF3B3B, "font_size": 11, "font_weight": "bold"}
                    else:
                        self._labels["nav_path_status"].text = "PATH: CLEAR"
                        self._labels["nav_path_status"].style = {"color": 0xFF00FF88, "font_size": 11, "font_weight": "bold"}

                if "nav_reason_label" in self._labels:
                    self._labels["nav_reason_label"].text = f"Reason: {act_reason[:50]}"
                if "nav_action_label" in self._labels:
                    self._labels["nav_action_label"].text = f"Action: {act_action[:40]}"

                # Update Active Mission Panel
                if "mission_title" in self._labels:
                    raw_desc = active_amr.current_task_description or "Navigating"
                    self._labels["mission_title"].text = f"{_sanitize_text(raw_desc)} -> {act_dest}"[:36]
                if "mission_assigned" in self._labels:
                    self._labels["mission_assigned"].text = act_name
                if "mission_prio_badge" in self._labels:
                    p = active_amr.priority_level
                    p_txt = "CRITICAL (P1)" if p == 1 else ("URGENT (P2)" if p == 2 else "NORMAL (P3)")
                    p_col = 0xFFFF3B3B if p == 1 else 0xFF00FF88
                    self._labels["mission_prio_badge"].text = f"PRIORITY: {p_txt}"
                    self._labels["mission_prio_badge"].style = {"color": p_col, "font_size": 11, "font_weight": "bold"}

                # Progress Bar (ASCII only: [==========] 100%)
                tot = max(1, len(act_wps))
                pct = int(round((min(tot, act_idx + 1) / tot) * 100.0))
                filled = int(round((pct / 100.0) * 12))
                bar_str = f"[{'=' * filled}{'-' * (12 - filled)}] {pct}%"
                if "mission_progress_bar" in self._labels:
                    self._labels["mission_progress_bar"].text = bar_str

                # Update Navigation Debug Panel
                if "dbg_start_pos" in self._labels and act_wps:
                    self._labels["dbg_start_pos"].text = f"Start: ({act_wps[0][0]:.1f}, {act_wps[0][1]:.1f})"
                if "dbg_goal_pos" in self._labels and act_wps:
                    self._labels["dbg_goal_pos"].text = f"Goal: ({act_wps[-1][0]:.1f}, {act_wps[-1][1]:.1f})"
                if "dbg_wps_count" in self._labels:
                    self._labels["dbg_wps_count"].text = f"Waypoints: {len(act_wps)} (Cur: {act_idx + 1})"
                if "dbg_dist_rem" in self._labels:
                    self._labels["dbg_dist_rem"].text = f"Dist Rem: {rem_dist:.1f}m"
                if "dbg_obstacle_status" in self._labels:
                    obs_pos = getattr(active_amr, "last_obstacle_pos", None)
                    if obs_pos:
                        self._labels["dbg_obstacle_status"].text = f"Obstacle: ({obs_pos[0]:.1f}, {obs_pos[1]:.1f})"
                        self._labels["dbg_obstacle_status"].style = {"color": 0xFFFF3B3B, "font_size": 10, "font_weight": "bold"}
                    else:
                        self._labels["dbg_obstacle_status"].text = "Obstacle: None"
                        self._labels["dbg_obstacle_status"].style = {"color": 0xFF00FF88, "font_size": 10}
                if "dbg_replanned" in self._labels:
                    is_rep = getattr(active_amr, "is_replanned", False)
                    self._labels["dbg_replanned"].text = f"Replanned: {'YES' if is_rep else 'NO'}"
                    rep_col = 0xFFFFCC00 if is_rep else 0xFF38BDF8
                    self._labels["dbg_replanned"].style = {"color": rep_col, "font_size": 10, "font_weight": "bold"}

                # Update 2D Map Waypoint Markers
                for i, placer in enumerate(self._map_wp_placers):
                    if i < len(act_wps):
                        wp = act_wps[i]
                        wx, wy = world_to_map(wp[0], wp[1])
                        placer.offset_x = wx - 4
                        placer.offset_y = wy - 4
                    else:
                        placer.offset_x = -100
                        placer.offset_y = -100

                # Start Beacon
                if act_wps and self._map_start_placer:
                    sx, sy = world_to_map(act_wps[0][0], act_wps[0][1])
                    self._map_start_placer.offset_x = sx - 7
                    self._map_start_placer.offset_y = sy - 7

                # Current Target Waypoint Beacon
                if act_wps and act_idx < len(act_wps) and self._map_curr_wp_placer:
                    c_wp = act_wps[act_idx]
                    cx, cy = world_to_map(c_wp[0], c_wp[1])
                    self._map_curr_wp_placer.offset_x = cx - 8
                    self._map_curr_wp_placer.offset_y = cy - 8
                elif self._map_curr_wp_placer:
                    self._map_curr_wp_placer.offset_x = -100
                    self._map_curr_wp_placer.offset_y = -100

                # Destination Beacon
                if act_wps and self._map_dest_placer:
                    dest_pt = act_wps[-1]
                    dx, dy = world_to_map(dest_pt[0], dest_pt[1])
                    self._map_dest_placer.offset_x = dx - 10
                    self._map_dest_placer.offset_y = dy - 9

                # Obstacle Hazard Beacon
                if getattr(active_amr, "last_obstacle_pos", None) and self._map_hazard_placer:
                    ox, oy = active_amr.last_obstacle_pos
                    hx, hy = world_to_map(ox, oy)
                    self._map_hazard_placer.offset_x = hx - 10
                    self._map_hazard_placer.offset_y = hy - 9
                elif self._map_hazard_placer:
                    self._map_hazard_placer.offset_x = -100
                    self._map_hazard_placer.offset_y = -100

            else:
                # All robots idle
                if "nav_active_robot" in self._labels:
                    self._labels["nav_active_robot"].text = "ACTIVE: Fleet IDLE"
                if "nav_status_state" in self._labels:
                    self._labels["nav_status_state"].text = "STATE: STANDBY"
                if "nav_dest_label" in self._labels:
                    self._labels["nav_dest_label"].text = "DEST: None"
                if "nav_reason_label" in self._labels:
                    self._labels["nav_reason_label"].text = "Reason: Standing by on base stations"
                if "nav_action_label" in self._labels:
                    self._labels["nav_action_label"].text = "Action: Standby"
                if "mission_title" in self._labels:
                    self._labels["mission_title"].text = "Standing by on stations"
                if "mission_assigned" in self._labels:
                    self._labels["mission_assigned"].text = "None"
                if "mission_progress_bar" in self._labels:
                    self._labels["mission_progress_bar"].text = "[------------] 0%"

                # Hide waypoints and beacons
                for placer in self._map_wp_placers:
                    placer.offset_x = -100
                    placer.offset_y = -100
                for placer in self._map_detour_placers:
                    placer.offset_x = -100
                    placer.offset_y = -100
                if self._map_start_placer:
                    self._map_start_placer.offset_x = -100
                    self._map_start_placer.offset_y = -100
                if self._map_curr_wp_placer:
                    self._map_curr_wp_placer.offset_x = -100
                    self._map_curr_wp_placer.offset_y = -100
                if self._map_dest_placer:
                    self._map_dest_placer.offset_x = -100
                    self._map_dest_placer.offset_y = -100
                if self._map_hazard_placer:
                    self._map_hazard_placer.offset_x = -100
                    self._map_hazard_placer.offset_y = -100

            # 4. Update Dynamic Obstacles on Map
            if dynamic_obstacles:
                obs_positions = dynamic_obstacles.get_obstacle_positions()
                for i, placer in enumerate(self._map_obs_placers):
                    if i < len(obs_positions):
                        ox, oy = obs_positions[i]
                        mx, my = world_to_map(ox, oy)
                        placer.offset_x = mx - 6
                        placer.offset_y = my - 6
                    else:
                        placer.offset_x = -100
                        placer.offset_y = -100

            # 5. Update Perception-Reasoning Digital Twin Panel (Follow Mode + LiDAR Radar + 5-Tuple Reasoning)
            sel_target = getattr(self, "_selected_robot", "AUTO")
            target_robot_obj = None
            if sel_target != "AUTO":
                target_robot_obj = robots.get(sel_target)
            if target_robot_obj is None:
                target_robot_obj = active_amr or robots.get("Arogya_Delivery")

            if target_robot_obj:
                r_name = getattr(target_robot_obj, "name", "Arogya_Delivery")
                if "twin_sensor_mode" in self._labels:
                    self._labels["twin_sensor_mode"].text = f"FOLLOW: {r_name} [Pinhole Cam (70 deg) + 360 LiDAR]"
                if "radar_robot_name" in self._labels:
                    self._labels["radar_robot_name"].text = r_name

                # Check closest obstacle from last LiDAR scan or collision guard
                scan = getattr(target_robot_obj, "last_lidar_scan", None)
                min_d = getattr(scan, "min_distance", 999.0) if scan else 999.0
                obs_txt = f"{min_d:.2f}m" if min_d < 12.0 else "CLEAR (>5.0m)"
                obs_col = 0xFFFF3B3B if min_d < 1.20 else (0xFFFFCC00 if min_d < 2.50 else 0xFF00FF88)
                self._set_label("radar_closest_obs", obs_txt, color=obs_col, font_size=10, font_weight="bold")

                # Safety zone
                if min_d < 1.20 or getattr(target_robot_obj, "is_blocked", False):
                    self._set_label("radar_safety_zone", "CRITICAL (<1.2m Block)", color=0xFFFF3B3B, font_size=10, font_weight="bold")
                elif min_d < 2.50:
                    self._set_label("radar_safety_zone", f"CAUTION ({min_d:.1f}m Slowdown)", color=0xFFFFCC00, font_size=10, font_weight="bold")
                else:
                    self._set_label("radar_safety_zone", "CLEAR (No Dynamic Blocks)", color=0xFF00FF88, font_size=10)

                # Human yielding
                if getattr(target_robot_obj, "is_yielding_to_human", False):
                    y_time = getattr(target_robot_obj, "human_yield_timer", 0)
                    self._set_label("radar_human_yield", f"YIELDING TO PERSON ({y_time}/90 steps)", color=0xFFFF3B3B, font_size=10, font_weight="bold")
                else:
                    self._set_label("radar_human_yield", "Social Clearance Nominal", color=0xFFCBD5E1, font_size=10)

                # Decision Engine 5-Tuple
                try:
                    from ai_reasoning.decision_engine import DECISION_ENGINE
                    dec_record = DECISION_ENGINE.get_decision(r_name)
                    if dec_record:
                        self._set_label("reason_situation", _sanitize_text(dec_record.situation)[:70])
                        self._set_label("reason_constraints", _sanitize_text(dec_record.constraints)[:70])
                        opts_str = " | ".join(dec_record.options)
                        self._set_label("reason_options", _sanitize_text(opts_str)[:70])
                        d_col = 0xFFFF3B3B if "EMERGENCY" in dec_record.decision else (0xFFFFCC00 if "REPLAN" in dec_record.decision else 0xFF00FF88)
                        self._set_label("reason_decision", dec_record.decision, color=d_col, font_size=9, font_weight="bold")
                        self._set_label("reason_action", _sanitize_text(dec_record.action)[:70])
                        self._set_label("reason_decision_badge", f"DECISION: {dec_record.decision}")
                except Exception:
                    pass

            # 6. Update Event Stream from SHARED_WORLD_MODEL
            try:
                from world_model.shared_world_model import SHARED_WORLD_MODEL
                recent_events = SHARED_WORLD_MODEL.event_stream[-6:]
                for idx, ev in enumerate(recent_events):
                    lbl_key = f"comm_log_{idx}"
                    if lbl_key in self._labels:
                        self._labels[lbl_key].text = _sanitize_text(ev.format())[:85]
            except Exception:
                pass

        except Exception:
            pass

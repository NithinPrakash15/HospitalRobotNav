"""
HospitalRobotNav — Patient Board Panel (omni.ui)
=================================================
Live Patient Directory & Ward Status Panel for NVIDIA Isaac Sim.

Displays:
- All registered hospital patients (P001 - P006)
- Assigned rooms (PAT-101 .. PAT-106)
- Live clinical status (ACTIVE, WAITING, EMERGENCY, DISCHARGED)
- Attending doctor & condition summary
- Action buttons: [Check Status], [Deliver Meds], [Code Blue Alert]
"""

from __future__ import annotations

import time
import traceback
from typing import Any, Callable, Dict, List, Optional

try:
    import omni.ui as ui
    OMNI_UI_AVAILABLE = True
except Exception:
    OMNI_UI_AVAILABLE = False

from database.hospital_db import HospitalDatabase, PatientStatus
from database.db_query_engine import DBQueryEngine
from utilities.logger import get_logger

log = get_logger(__name__)

# Status color badges (ARGB hexadecimal)
STATUS_COLORS = {
    PatientStatus.ACTIVE: 0xFF2ECC71,      # Green
    PatientStatus.EMERGENCY: 0xFFE74C3C,   # Red
    PatientStatus.WAITING: 0xFFF39C12,     # Amber
    PatientStatus.OUTPATIENT: 0xFF3498DB,  # Blue
    PatientStatus.DISCHARGED: 0xFF95A5A6,  # Grey
}


class PatientBoardPanel:
    """omni.ui Window for live hospital patient directory and ward oversight."""

    def __init__(
        self,
        db: Optional[HospitalDatabase] = None,
        query_engine: Optional[DBQueryEngine] = None,
        on_action_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
    ) -> None:
        self._db = db or HospitalDatabase()
        self._query_engine = query_engine or DBQueryEngine(self._db)
        self._on_action = on_action_callback
        self._window: Optional[Any] = None
        self._filter_status: Optional[str] = None
        self._patient_cards_container = None

    def build_ui(self, visible: bool = True) -> Optional[Any]:
        """Construct the omni.ui window if omni.ui is available."""
        if not OMNI_UI_AVAILABLE:
            log.warning("PatientBoardPanel: omni.ui not available in this environment.")
            return None

        try:
            self._window = ui.Window(
                "Patient Ward Directory — AROGYA",
                width=520,
                height=480,
                visible=visible,
            )

            with self._window.frame:
                with ui.VStack(spacing=8, style={"margin": 10}):
                    # Header
                    with ui.HStack(height=30):
                        ui.Label(
                            "PATIENT DIRECTORY & WARD STATUS",
                            style={"font_size": 16, "color": 0xFF00E5FF, "font_weight": "bold"},
                        )
                        ui.Spacer()
                        ui.Button("Refresh", width=70, clicked_fn=self.refresh)

                    ui.Line(height=2, style={"color": 0x44FFFFFF})

                    # Filter Buttons
                    with ui.HStack(height=26, spacing=6):
                        ui.Label("Filter:", width=45, style={"color": 0xFFAAAAAA, "font_size": 12})
                        ui.Button("ALL", width=55, clicked_fn=lambda: self._set_filter(None))
                        ui.Button("ACTIVE", width=65, clicked_fn=lambda: self._set_filter(PatientStatus.ACTIVE))
                        ui.Button("EMERGENCY", width=85, clicked_fn=lambda: self._set_filter(PatientStatus.EMERGENCY))
                        ui.Button("WAITING", width=70, clicked_fn=lambda: self._set_filter(PatientStatus.WAITING))

                    ui.Spacer(height=4)

                    # Scrollable Patients List
                    with ui.ScrollingFrame(height=360):
                        self._patient_cards_container = ui.VStack(spacing=6)
                        self._populate_cards()

            return self._window
        except Exception:
            log.error("Failed to build PatientBoardPanel UI:\n%s", traceback.format_exc())
            return None

    def _set_filter(self, status: Optional[str]) -> None:
        self._filter_status = status
        self.refresh()

    def _populate_cards(self) -> None:
        """Populate patient entries from database."""
        if not OMNI_UI_AVAILABLE or self._patient_cards_container is None:
            return

        self._patient_cards_container.clear()
        patients = self._query_engine.get_all_active_patients_brief()
        if self._filter_status:
            patients = [p for p in patients if p.get("status") == self._filter_status]

        if not patients:
            with self._patient_cards_container:
                ui.Label("No patients matching selected filter.", style={"color": 0xFF888888, "font_size": 13})
            return

        with self._patient_cards_container:
            for p in patients:
                pid = p.get("patient_id", "")
                name = p.get("name", "Unknown")
                room = p.get("assigned_room") or p.get("room_id") or "Unassigned"
                status = p.get("status", "ACTIVE")
                cond = p.get("condition") or "Under observation"
                doc = p.get("doctor_name", "Unassigned")
                badge_color = STATUS_COLORS.get(status, 0xFF888888)

                with ui.ZStack(height=72):
                    # Background Card Box
                    ui.Rectangle(style={"background_color": 0x221E242B, "border_radius": 4, "border_color": 0x443A4553, "border_width": 1})

                    with ui.HStack(spacing=10, style={"margin": 8}):
                        # Left: Patient ID & Badge
                        with ui.VStack(width=80, spacing=4):
                            ui.Label(pid, style={"font_size": 14, "color": 0xFFFFFFFF, "font_weight": "bold"})
                            ui.Label(f"[{status}]", style={"font_size": 10, "color": badge_color, "font_weight": "bold"})

                        # Center: Patient Details
                        with ui.VStack(width=220, spacing=2):
                            ui.Label(f"{name}  |  {room}", style={"font_size": 12, "color": 0xFFECEFF1, "font_weight": "bold"})
                            ui.Label(f"Dr: {doc}", style={"font_size": 11, "color": 0xFFB0BEC5})
                            ui.Label(f"Cond: {cond}", style={"font_size": 10, "color": 0xFF78909C})

                        ui.Spacer()

                        # Right: Interactive Action Buttons
                        with ui.VStack(width=130, spacing=4):
                            with ui.HStack(spacing=4):
                                ui.Button(
                                    "Status",
                                    width=60,
                                    height=22,
                                    style={"background_color": 0xFF2C3E50, "font_size": 10},
                                    clicked_fn=lambda p_id=pid: self._trigger_action("status_query", p_id, p),
                                )
                                ui.Button(
                                    "Meds",
                                    width=60,
                                    height=22,
                                    style={"background_color": 0xFF16A085, "font_size": 10},
                                    clicked_fn=lambda p_id=pid: self._trigger_action("medication_delivery", p_id, p),
                                )
                            ui.Button(
                                "CODE BLUE",
                                width=124,
                                height=22,
                                style={"background_color": 0xFFC0392B, "font_size": 10, "font_weight": "bold"},
                                clicked_fn=lambda p_id=pid: self._trigger_action("code_blue", p_id, p),
                            )

    def _trigger_action(self, action: str, patient_id: str, data: Dict[str, Any]) -> None:
        """Forward UI action button triggers to coordinator/simulation."""
        log.info("PatientBoardPanel Action: %s for %s", action, patient_id)
        if self._on_action:
            self._on_action(action, patient_id, data)

    def refresh(self) -> None:
        """Refresh patient card data from the database."""
        try:
            self._populate_cards()
        except Exception:
            log.error("PatientBoardPanel refresh failed: %s", traceback.format_exc())

    def show(self) -> None:
        if self._window:
            self._window.visible = True
            self.refresh()

    def hide(self) -> None:
        if self._window:
            self._window.visible = False

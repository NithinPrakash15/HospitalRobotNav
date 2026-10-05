"""
HospitalRobotNav — DB Control Panel (omni.ui)
==============================================
Live Clinical Simulation & Database Control Panel for NVIDIA Isaac Sim.

Allows evaluators to:
- Dynamically alter patient clinical states in the SQLite database
- Trigger standard medical workflows (Code Blue, Scheduled Meds, Consultations)
- Inspect live pharmacy inventory and audit trail
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
from utilities.event_bus import EVENT_BUS, HospitalEvent
from utilities.logger import get_logger

log = get_logger(__name__)


class DBControlPanel:
    """omni.ui Window for clinical scenario injection and database control."""

    def __init__(
        self,
        db: Optional[HospitalDatabase] = None,
        query_engine: Optional[DBQueryEngine] = None,
        on_scenario_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        self._db = db or HospitalDatabase()
        self._query_engine = query_engine or DBQueryEngine(self._db)
        self._on_scenario = on_scenario_callback
        self._window: Optional[Any] = None

        # Selection state
        self._selected_patient_id = "P003"
        self._selected_status = PatientStatus.EMERGENCY

    def build_ui(self, visible: bool = True) -> Optional[Any]:
        """Construct the omni.ui window if omni.ui is available."""
        if not OMNI_UI_AVAILABLE:
            log.warning("DBControlPanel: omni.ui not available in this environment.")
            return None

        try:
            self._window = ui.Window(
                "Hospital Database & Clinical Controls — AROGYA",
                width=480,
                height=420,
                visible=visible,
            )

            with self._window.frame:
                with ui.VStack(spacing=8, style={"margin": 10}):
                    # Header
                    with ui.HStack(height=26):
                        ui.Label(
                            "CLINICAL DATABASE & SCENARIO INJECTION",
                            style={"font_size": 15, "color": 0xFF00E5FF, "font_weight": "bold"},
                        )
                        ui.Spacer()

                    ui.Line(height=2, style={"color": 0x44FFFFFF})

                    # Section 1: Dynamic Patient Status Override
                    ui.Label("1. PATIENT STATUS INJECTION", style={"color": 0xFFFFB300, "font_size": 12, "font_weight": "bold"})
                    with ui.HStack(height=28, spacing=6):
                        ui.Label("Patient:", width=50, style={"color": 0xFFCCCCCC, "font_size": 11})
                        for pid in ("P001", "P002", "P003", "P004", "P005", "P006"):
                            ui.Button(
                                pid,
                                width=50,
                                height=24,
                                style={"background_color": 0xFF37474F if pid != self._selected_patient_id else 0xFF0288D1, "font_size": 10},
                                clicked_fn=lambda p=pid: self._select_patient(p),
                            )

                    with ui.HStack(height=28, spacing=6):
                        ui.Label("Status:", width=50, style={"color": 0xFFCCCCCC, "font_size": 11})
                        ui.Button("ACTIVE", width=70, height=24, style={"background_color": 0xFF2E7D32, "font_size": 10}, clicked_fn=lambda: self._apply_status(PatientStatus.ACTIVE))
                        ui.Button("EMERGENCY", width=85, height=24, style={"background_color": 0xFFC62828, "font_size": 10, "font_weight": "bold"}, clicked_fn=lambda: self._apply_status(PatientStatus.EMERGENCY))
                        ui.Button("WAITING", width=70, height=24, style={"background_color": 0xFFE65100, "font_size": 10}, clicked_fn=lambda: self._apply_status(PatientStatus.WAITING))
                        ui.Button("DISCHARGE", width=75, height=24, style={"background_color": 0xFF546E7A, "font_size": 10}, clicked_fn=lambda: self._apply_status(PatientStatus.DISCHARGED))

                    ui.Spacer(height=6)
                    ui.Line(height=1, style={"color": 0x33FFFFFF})

                    # Section 2: Clinical Demo Workflows
                    ui.Label("2. ONE-CLICK CLINICAL SCENARIOS", style={"color": 0xFFFFB300, "font_size": 12, "font_weight": "bold"})
                    with ui.VStack(spacing=6):
                        ui.Button(
                            "SCENARIO A: Code Blue in Room PAT-103 (Preempts Fleet → Garuda)",
                            height=26,
                            style={"background_color": 0xFFB71C1C, "font_size": 11, "font_weight": "bold"},
                            clicked_fn=self._run_scenario_code_blue,
                        )
                        ui.Button(
                            "SCENARIO B: Schedule Due: Paracetamol Delivery → PAT-101 (Arogya)",
                            height=26,
                            style={"background_color": 0xFF00695C, "font_size": 11},
                            clicked_fn=self._run_scenario_med_delivery,
                        )
                        ui.Button(
                            "SCENARIO C: Spoken Query: 'Who is treating Patient 1?'",
                            height=26,
                            style={"background_color": 0xFF1565C0, "font_size": 11},
                            clicked_fn=self._run_scenario_doctor_query,
                        )
                        ui.Button(
                            "SCENARIO D: Audit Active Patients in Wards",
                            height=26,
                            style={"background_color": 0xFF4527A0, "font_size": 11},
                            clicked_fn=self._run_scenario_active_patients,
                        )

                    ui.Spacer(height=6)
                    ui.Line(height=1, style={"color": 0x33FFFFFF})

                    # Section 3: Reset Demo Database
                    with ui.HStack(height=26):
                        ui.Label("Database State:", style={"color": 0xFF9E9E9E, "font_size": 11})
                        ui.Spacer()
                        ui.Button("Re-seed Synthetic Data", width=160, height=22, style={"background_color": 0xFF424242, "font_size": 10}, clicked_fn=self._reseed_db)

            return self._window
        except Exception:
            log.error("Failed to build DBControlPanel UI:\n%s", traceback.format_exc())
            return None

    def _select_patient(self, pid: str) -> None:
        self._selected_patient_id = pid
        log.info("DBControlPanel: Selected patient %s", pid)

    def _apply_status(self, status: str) -> None:
        """Update selected patient status in database."""
        pid = self._selected_patient_id
        ok = self._db.set_patient_status(pid, status, reason="DB Control Panel Override", operator="demo_user")
        if ok:
            log.info("DBControlPanel: Updated %s status to %s", pid, status)
            EVENT_BUS.publish(
                HospitalEvent.EMERGENCY_ALERT if status == PatientStatus.EMERGENCY else HospitalEvent.MISSION_REQUESTED,
                data={"patient_id": pid, "new_status": status},
                source="db_control_panel",
            )
            if self._on_scenario:
                self._on_scenario("status_changed", {"patient_id": pid, "status": status})

    def _run_scenario_code_blue(self) -> None:
        """Trigger Scenario A: Code Blue in PAT-103."""
        log.info("Running Scenario A: Code Blue in PAT-103")
        self._db.set_patient_status("P003", PatientStatus.EMERGENCY, reason="Cardiac arrhythmia event", operator="demo_user")
        EVENT_BUS.publish(
            HospitalEvent.EMERGENCY_ALERT,
            data={"room": "PAT-103", "patient_id": "P003", "condition": "Cardiac Arrhythmia Code Blue"},
            source="scenario_injection",
        )
        if self._on_scenario:
            self._on_scenario("code_blue", {"patient_id": "P003", "room": "PAT-103"})

    def _run_scenario_med_delivery(self) -> None:
        """Trigger Scenario B: Medication Delivery to P001 in PAT-101."""
        log.info("Running Scenario B: Scheduled Medication Delivery")
        EVENT_BUS.publish(
            HospitalEvent.MISSION_REQUESTED,
            data={"patient_id": "P001", "medicine": "Paracetamol", "room": "PAT-101"},
            source="scenario_injection",
        )
        if self._on_scenario:
            self._on_scenario("med_delivery", {"patient_id": "P001", "medicine": "Paracetamol", "room": "PAT-101"})

    def _run_scenario_doctor_query(self) -> None:
        """Trigger Scenario C: Doctor Query for P001."""
        log.info("Running Scenario C: Doctor Query")
        if self._on_scenario:
            self._on_scenario("doctor_query", {"patient_id": "P001"})

    def _run_scenario_active_patients(self) -> None:
        """Trigger Scenario D: Active Patients Audit."""
        log.info("Running Scenario D: Active Patients Audit")
        if self._on_scenario:
            self._on_scenario("active_patients", {})

    def _reseed_db(self) -> None:
        """Re-seed synthetic database data."""
        try:
            self._db._seed_synthetic_data()
            log.info("Database synthetic data re-seeded.")
        except Exception:
            log.error("Re-seeding failed: %s", traceback.format_exc())

    def show(self) -> None:
        if self._window:
            self._window.visible = True

    def hide(self) -> None:
        if self._window:
            self._window.visible = False

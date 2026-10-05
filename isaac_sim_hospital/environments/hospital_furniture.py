"""
AROGYA Autonomous Hospital Robot Fleet — Procedural Hospital Furniture & Static Props
=====================================================================================
Constructs realistic, research-grade visual furniture, clinical equipment, medical
racks, patient beds, and architectural amenities across all AROGYA Medical Center zones.

Architectural Zones Supported:
- Central Atrium (Curved reception island, directory totem, planter boxes, seating lounge)
- Elevator Lobby (2 Brushed stainless steel elevator doors, floor indicators, call buttons)
- Staircase Enclosure (Fire exit portal, safety signs)
- Main Entrance (Glass vestibule doors, AROGYA MEDICAL CENTER facade, concierge desk)
- Central Pharmacy (Dispensing counter, medicine shelves, ROBOT MEDICINE PICKUP bay)
- ICU / Critical Care (6 Monitored cubicles, beds, glowing ECG screens, IV stands, telemetry hub)
- Emergency & Trauma (Resuscitation red zone, trauma gurneys, crash carts, triage station)
- Operating Theaters (Surgical tables, overhead lamps, anesthesia machines, scrub stations)
- Pathology Laboratory (Specimen reception, lab islands, microscopes, centrifuges)
- Outpatient Department (Doctor consultation desks, exam couches, patient seating)
- AROGYA Robot Operations (Diagnostics server terminal, maintenance bench, charging pads)

All substantial props register simple 2D collision boxes safely inside room boundaries.
Corridors, doorways, and robot navigation paths remain 100% unobstructed.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple
import numpy as np

try:
    import omni.usd
    from pxr import Gf, Sdf, UsdGeom, Vt
    HAS_OMNI = True
except ImportError:
    omni = None
    Gf = Sdf = UsdGeom = Vt = None
    HAS_OMNI = False


# ─────────────────────────────────────────────────────────────────────────────
# Color Tokens for Hospital Props & Architecture
# ─────────────────────────────────────────────────────────────────────────────
COLOR_BED_FRAME     = (0.22, 0.25, 0.28)  # Matte dark steel
COLOR_MATTRESS_ICU  = (0.20, 0.45, 0.75)  # Medical wipeable blue
COLOR_MATTRESS_WARD = (0.92, 0.94, 0.96)  # White sterile linen
COLOR_PILLOW        = (0.75, 0.85, 0.92)  # Soft light blue pillow
COLOR_DESK_WOOD     = (0.42, 0.35, 0.28)  # Warm medical office oak
COLOR_DESK_CLINICAL = (0.88, 0.90, 0.92)  # Clean laminate grey/white
COLOR_COUNTER_TOP   = (0.24, 0.26, 0.30)  # Charcoal stone top
COLOR_CHAIR_SEAT    = (0.20, 0.42, 0.65)  # Durable waiting room blue
COLOR_CHAIR_FRAME   = (0.15, 0.15, 0.18)  # Black powder-coat steel
COLOR_CHROME        = (0.80, 0.82, 0.85)  # Polished stainless steel / IV pole
COLOR_ECG_SCREEN    = (0.05, 0.92, 0.25)  # Phosphor glowing green ECG monitor
COLOR_CRASH_CART    = (0.85, 0.18, 0.18)  # Emergency Resuscitation Red
COLOR_SURGERY_TEAL  = (0.15, 0.55, 0.48)  # Surgical OT table teal
COLOR_PHARM_SHELF   = (0.35, 0.40, 0.48)  # Steel medicine rack
COLOR_DOCK_CYAN     = (0.00, 0.85, 1.00)  # High-tech AMR dock pad
COLOR_TRASH_BIN     = (0.30, 0.32, 0.35)  # Sanitary receptacle grey
COLOR_ELEVATOR_DOOR = (0.72, 0.75, 0.78)  # Brushed stainless steel
COLOR_ELEVATOR_FRAME= (0.30, 0.32, 0.36)  # Dark architectural architrave
COLOR_PLANTER_WOOD  = (0.38, 0.30, 0.22)  # Natural walnut planter box
COLOR_PLANT_GREEN   = (0.18, 0.58, 0.28)  # Indoor atrium shrub greenery
COLOR_GLASS_TINT    = (0.75, 0.88, 0.95)  # Tinted vestibule glass


def _create_box(
    stage: Any,
    path: str,
    pos: Tuple[float, float, float],
    scale: Tuple[float, float, float],
    color_rgb: Tuple[float, float, float],
) -> None:
    """Create a USD box prim with local translate and scale."""
    if not HAS_OMNI or stage is None:
        return
    try:
        xf = UsdGeom.Xform.Define(stage, Sdf.Path(path))
        xf.AddTranslateOp().Set(Gf.Vec3d(float(pos[0]), float(pos[1]), float(pos[2])))
        xf.AddScaleOp().Set(Gf.Vec3d(float(scale[0]), float(scale[1]), float(scale[2])))

        mesh_path = f"{path}/Mesh"
        cube = UsdGeom.Cube.Define(stage, Sdf.Path(mesh_path))
        cube.GetSizeAttr().Set(1.0)
        prim = stage.GetPrimAtPath(Sdf.Path(mesh_path))
        if prim and prim.IsValid():
            r, g, b = float(color_rgb[0]), float(color_rgb[1]), float(color_rgb[2])
            cube.GetDisplayColorAttr().Set(Vt.Vec3fArray([Gf.Vec3f(r, g, b)]))
    except Exception:
        pass


class HospitalFurniture:
    """Procedural builder for hospital department furniture and equipment props."""

    def __init__(
        self,
        stage: Any = None,
        collision_boxes: Optional[List[Tuple[float, float, float, float]]] = None,
    ) -> None:
        self.stage = stage
        self.collision_boxes = collision_boxes
        if self.stage is None and HAS_OMNI and omni and omni.usd:
            ctx = omni.usd.get_context()
            if ctx:
                self.stage = ctx.get_stage()

        self.root_path = "/World/Hospital/Furniture"
        self._prop_count = 0

    def build_all(self) -> int:
        """Construct all clinical furniture suites across the facility and register collisions."""
        print("[HospitalFurniture] Building realistic clinical furniture and medical props for AROGYA Medical Center...")
        self._build_central_atrium()
        self._build_elevator_lobby()
        self._build_staircase_zone()
        self._build_main_entrance()
        self._build_pharmacy_and_pickup()
        self._build_icu_department()
        self._build_operating_theatres()
        self._build_emergency_trauma()
        self._build_pathology_laboratory()
        self._build_consultation_opd()
        self._build_general_inpatient_ward()
        self._build_robot_operations()
        self._build_healing_garden_courtyard()
        self._build_corridor_amenities()

        print(f"[HospitalFurniture] Successfully instantiated {self._prop_count} clinical furniture objects.")
        return self._prop_count

    def _add_box(
        self,
        name: str,
        pos: Tuple[float, float, float],
        scale: Tuple[float, float, float],
        color: Tuple[float, float, float],
        register_collision: bool = True,
    ) -> None:
        self._prop_count += 1
        prim_path = f"{self.root_path}/{name}"
        _create_box(self.stage, prim_path, pos, scale, color)

        # Register substantial furniture pieces into 2D collision boxes
        if register_collision and self.collision_boxes is not None:
            # Avoid registering tiny visual trims or flush floor decals
            if scale[0] >= 0.40 and scale[1] >= 0.40 and pos[2] <= 1.20 and scale[2] >= 0.25:
                b_xmin = float(pos[0] - scale[0] / 2.0)
                b_xmax = float(pos[0] + scale[0] / 2.0)
                b_ymin = float(pos[1] - scale[1] / 2.0)
                b_ymax = float(pos[1] + scale[1] / 2.0)
                self.collision_boxes.append((b_xmin, b_xmax, b_ymin, b_ymax))

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Central Atrium & Reception Rotunda (The Landmark Hub: (0.0, -4.5))
    # ─────────────────────────────────────────────────────────────────────────
    def _build_central_atrium(self) -> None:
        p = "Atrium"

        # ── Rotunda Ring of 8 Structural Architectural Columns ───────────────
        # Framing the grand rotunda landmark without blocking any circulation path
        # 8 columns at radius ~6.5m around (0.0, -4.5), leaving cardinal axes open
        rotunda_columns = [
            (-6.5, -1.0), (6.5, -1.0),
            (-8.0, -4.5), (8.0, -4.5),
            (-6.5, -8.0), (6.5, -8.0),
            (-4.5, -11.0), (4.5, -11.0),
        ]
        for c_idx, (cx, cy) in enumerate(rotunda_columns):
            # Column shaft (height 2.6m, sleek white architectural finish)
            self._add_box(f"{p}_ColShaft_{c_idx}", (cx, cy, 1.30), (0.70, 0.70, 2.60), (0.92, 0.94, 0.96), register_collision=True)
            # Dark slate base plinth (height 0.20m)
            self._add_box(f"{p}_ColBase_{c_idx}", (cx, cy, 0.10), (0.85, 0.85, 0.20), (0.20, 0.24, 0.28), register_collision=False)
            # Architectural capital trim (height 0.12m, Z = 2.55m)
            self._add_box(f"{p}_ColCap_{c_idx}", (cx, cy, 2.55), (0.82, 0.82, 0.12), (0.20, 0.24, 0.28), register_collision=False)

        # ── Overhead Rotunda Ring Header Beams (Z = 2.45m) ───────────────────
        # Connecting columns into an authentic open skylight/rotunda lightwell framing
        self._add_box(f"{p}_RingBeam_N", (0.0, -1.0, 2.45), (13.0, 0.22, 0.25), (0.88, 0.90, 0.92), register_collision=False)
        self._add_box(f"{p}_RingBeam_S", (0.0, -8.0, 2.45), (13.0, 0.22, 0.25), (0.88, 0.90, 0.92), register_collision=False)
        self._add_box(f"{p}_RingBeam_W", (-6.5, -4.5, 2.45), (0.22, 7.0, 0.25), (0.88, 0.90, 0.92), register_collision=False)
        self._add_box(f"{p}_RingBeam_E", (6.5, -4.5, 2.45), (0.22, 7.0, 0.25), (0.88, 0.90, 0.92), register_collision=False)

        # ── Faceted Curved Reception Island Desk ─────────────────────────────
        # Positioned at (0.0, -6.8), leaving (0.0, -5.0) 100% open for Mitra AMR
        self._add_box(f"{p}_ReceptionBase", (0.0, -6.8, 0.55), (6.0, 1.1, 1.1), COLOR_DESK_WOOD, register_collision=True)
        self._add_box(f"{p}_ReceptionCounterTop", (0.0, -6.8, 1.12), (6.2, 1.25, 0.06), COLOR_COUNTER_TOP, register_collision=False)
        # Angled wing chamfers framing the reception island
        self._add_box(f"{p}_ReceptionLeftWing", (-3.4, -7.4, 0.55), (1.4, 1.2, 1.1), COLOR_DESK_WOOD, register_collision=True)
        self._add_box(f"{p}_ReceptionRightWing", (3.4, -7.4, 0.55), (1.4, 1.2, 1.1), COLOR_DESK_WOOD, register_collision=True)

        # Reception Staff Monitors & Check-in Tablets
        self._add_box(f"{p}_Monitor1", (-1.5, -6.8, 1.35), (0.6, 0.1, 0.4), (0.12, 0.12, 0.15), register_collision=False)
        self._add_box(f"{p}_Monitor2", (1.5, -6.8, 1.35), (0.6, 0.1, 0.4), (0.12, 0.12, 0.15), register_collision=False)
        self._add_box(f"{p}_CheckinKiosk1", (-2.6, -6.8, 1.25), (0.35, 0.35, 0.30), (0.2, 0.3, 0.4), register_collision=False)
        self._add_box(f"{p}_CheckinKiosk2", (2.6, -6.8, 1.25), (0.35, 0.35, 0.30), (0.2, 0.3, 0.4), register_collision=False)

        # Architectural Planter Boxes with Lush Foliage (West & East flanking rotunda)
        for idx, px in enumerate([-6.5, 6.5]):
            self._add_box(f"{p}_PlanterBox_{idx}", (px, -3.5, 0.30), (1.4, 1.4, 0.60), COLOR_PLANTER_WOOD, register_collision=True)
            self._add_box(f"{p}_Foliage_{idx}", (px, -3.5, 0.75), (1.2, 1.2, 0.40), COLOR_PLANT_GREEN, register_collision=False)

        # 3D Interactive Hospital Directory Totem Kiosk
        self._add_box(f"{p}_DirectoryTotem", (5.5, -1.8, 0.90), (0.45, 0.45, 1.80), (0.15, 0.20, 0.25), register_collision=True)
        self._add_box(f"{p}_DirectoryScreen", (5.5, -1.8, 1.50), (0.48, 0.38, 0.60), (0.10, 0.55, 0.85), register_collision=False)

        # Central Waiting Lounge Modern Seating Clusters (WAT-01)
        for row_idx, wy in enumerate([-11.0, -14.0]):
            self._add_box(f"{p}_LoungeBenchW_{row_idx}", (-5.0, wy, 0.42), (3.6, 0.8, 0.55), COLOR_CHAIR_SEAT, register_collision=True)
            self._add_box(f"{p}_LoungeBenchE_{row_idx}", (5.0, wy, 0.42), (3.6, 0.8, 0.55), COLOR_CHAIR_SEAT, register_collision=True)

        # Low Magazine / Coffee Tables
        self._add_box(f"{p}_CoffeeTableW", (-5.0, -12.5, 0.22), (2.0, 0.8, 0.40), COLOR_DESK_WOOD, register_collision=True)
        self._add_box(f"{p}_CoffeeTableE", (5.0, -12.5, 0.22), (2.0, 0.8, 0.40), COLOR_DESK_WOOD, register_collision=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Elevator Lobby (ELV-01: East wall of Atrium at X ~ 10.0m)
    # ─────────────────────────────────────────────────────────────────────────
    def _build_elevator_lobby(self) -> None:
        p = "ElevatorLobby"
        # 2 Architectural Elevator Doors (Doors 1 & 2)
        elev_ys = [-3.5, -7.5]
        for idx, ey in enumerate(elev_ys):
            dnum = idx + 1
            # Outer Wall Architrave Frame
            self._add_box(f"{p}_Frame_{dnum}", (10.4, ey, 1.15), (0.20, 2.4, 2.3), COLOR_ELEVATOR_FRAME, register_collision=False)
            # Brushed Stainless Steel Sliding Doors
            self._add_box(f"{p}_DoorL_{dnum}", (10.35, ey - 0.52, 1.10), (0.08, 0.95, 2.15), COLOR_ELEVATOR_DOOR, register_collision=False)
            self._add_box(f"{p}_DoorR_{dnum}", (10.35, ey + 0.52, 1.10), (0.08, 0.95, 2.15), COLOR_ELEVATOR_DOOR, register_collision=False)
            # Door Center Seam Trim
            self._add_box(f"{p}_Seam_{dnum}", (10.32, ey, 1.10), (0.04, 0.04, 2.15), (0.2, 0.2, 0.2), register_collision=False)
            # Overhead Illuminated Floor Indicator ("▲ LEVEL 1 • TOWER A")
            self._add_box(f"{p}_Indicator_{dnum}", (10.30, ey, 2.25), (0.06, 0.80, 0.22), (0.1, 0.8, 0.3), register_collision=False)

        # Elevator Call Button Column between doors
        self._add_box(f"{p}_CallColumn", (10.35, -5.5, 1.05), (0.08, 0.25, 0.50), COLOR_ELEVATOR_FRAME, register_collision=False)
        self._add_box(f"{p}_CallButtonUp", (10.30, -5.5, 1.15), (0.04, 0.08, 0.08), (0.1, 0.8, 1.0), register_collision=False)
        self._add_box(f"{p}_CallButtonDown", (10.30, -5.5, 0.95), (0.04, 0.08, 0.08), (0.1, 0.8, 1.0), register_collision=False)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Staircase Zone (STAIR-01: East wall of Atrium at X ~ 10.0m, Y = -13.5)
    # ─────────────────────────────────────────────────────────────────────────
    def _build_staircase_zone(self) -> None:
        p = "Staircase"
        # Emergency Egress Fire Door Portal
        self._add_box(f"{p}_Frame", (10.4, -13.5, 1.15), (0.20, 1.8, 2.3), (0.35, 0.35, 0.40), register_collision=False)
        self._add_box(f"{p}_FireDoor", (10.35, -13.5, 1.10), (0.08, 1.5, 2.15), (0.75, 0.25, 0.25), register_collision=False)
        self._add_box(f"{p}_PanicBar", (10.28, -13.5, 1.00), (0.06, 1.2, 0.08), COLOR_CHROME, register_collision=False)
        # Green Illuminated Exit Signboard
        self._add_box(f"{p}_ExitSign", (10.28, -13.5, 2.25), (0.06, 0.60, 0.20), (0.10, 0.85, 0.25), register_collision=False)

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Main Entrance Foyer & Grand Portico (ENT-01: [-9, 9] x [-38.5, -19.8])
    # ─────────────────────────────────────────────────────────────────────────
    def _build_main_entrance(self) -> None:
        p = "MainEntrance"

        # ── Grand Entrance Portico Columns (Y = -38.2m, Z = 1.30m) ───────────
        # 4 grand architectural columns framing the projecting entrance portico
        portico_cols = [(-6.5, -38.2), (-2.8, -38.2), (2.8, -38.2), (6.5, -38.2)]
        for pc_idx, (pcx, pcy) in enumerate(portico_cols):
            self._add_box(f"{p}_PorticoCol_{pc_idx}", (pcx, pcy, 1.30), (0.65, 0.65, 2.60), (0.92, 0.94, 0.96), register_collision=True)
            self._add_box(f"{p}_PorticoBase_{pc_idx}", (pcx, pcy, 0.10), (0.80, 0.80, 0.20), (0.20, 0.24, 0.28), register_collision=False)

        # Portico Overhead Glass Canopy Roof (Z = 2.40m, Y in [-39.5, -38.0])
        self._add_box(f"{p}_PorticoCanopy", (0.0, -38.7, 2.40), (14.0, 2.0, 0.12), COLOR_GLASS_TINT, register_collision=False)
        self._add_box(f"{p}_CanopyBracketL", (-6.0, -38.7, 2.30), (0.15, 1.8, 0.15), (0.20, 0.24, 0.28), register_collision=False)
        self._add_box(f"{p}_CanopyBracketR", (6.0, -38.7, 2.30), (0.15, 1.8, 0.15), (0.20, 0.24, 0.28), register_collision=False)

        # Architectural Automatic Sliding Glass Doors (Z = 1.15m, Y = -38.2m)
        self._add_box(f"{p}_GlassDoorL", (-1.2, -38.2, 1.15), (2.0, 0.08, 2.2), COLOR_GLASS_TINT, register_collision=False)
        self._add_box(f"{p}_GlassDoorR", (1.2, -38.2, 1.15), (2.0, 0.08, 2.2), COLOR_GLASS_TINT, register_collision=False)
        self._add_box(f"{p}_DoorLintel", (0.0, -38.2, 2.30), (4.8, 0.20, 0.20), COLOR_ELEVATOR_FRAME, register_collision=False)

        # Entrance Walk-Off Carpet Mat (Recessed visual decal)
        self._add_box(f"{p}_WalkOffMat", (0.0, -33.5, 0.015), (5.5, 5.0, 0.01), (0.18, 0.24, 0.32), register_collision=False)

        # Security & Concierge Desk (Placed safely to the east at X = 5.5, Y = -30.0)
        self._add_box(f"{p}_ConciergeDesk", (5.5, -30.0, 0.55), (3.0, 1.0, 1.05), COLOR_DESK_WOOD, register_collision=True)
        self._add_box(f"{p}_ConciergePC", (5.5, -30.0, 1.25), (0.50, 0.15, 0.35), (0.1, 0.1, 0.1), register_collision=False)

        # Hand Sanitization Kiosk at Entrance
        self._add_box(f"{p}_SanitizerKiosk", (-4.5, -34.0, 0.70), (0.40, 0.40, 1.40), COLOR_CHROME, register_collision=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Central Pharmacy & Robot Medicine Pickup (PHM-01: [8, 20] x [21.8, 37.2])
    # ─────────────────────────────────────────────────────────────────────────
    def _build_pharmacy_and_pickup(self) -> None:
        p = "Pharmacy"
        # Dispensing Counter with Service Window (Center X = 14.0, Y = 24.5)
        self._add_box(f"{p}_CounterBase", (14.0, 24.5, 0.55), (5.5, 0.9, 1.05), COLOR_DESK_CLINICAL, register_collision=True)
        self._add_box(f"{p}_CounterTop", (14.0, 24.5, 1.10), (5.7, 1.0, 0.06), COLOR_COUNTER_TOP, register_collision=False)
        self._add_box(f"{p}_GlassPartition", (14.0, 24.5, 1.45), (5.2, 0.05, 0.65), COLOR_GLASS_TINT, register_collision=False)

        # Pharmacist Workstation PC & Label Printer
        self._add_box(f"{p}_WorkstationPC", (12.5, 24.5, 1.30), (0.50, 0.12, 0.35), (0.15, 0.15, 0.18), register_collision=False)
        self._add_box(f"{p}_PrescriptionTray", (15.5, 24.5, 1.15), (0.45, 0.35, 0.10), COLOR_CHROME, register_collision=False)

        # Dedicated "ROBOT MEDICINE PICKUP" Docking Pad (X = 14.0, Y = 23.2)
        # Flush floor pad decal for autonomous AMR alignment
        self._add_box(f"{p}_RobotPickupPad", (14.0, 23.2, 0.015), (1.8, 1.4, 0.01), COLOR_DOCK_CYAN, register_collision=False)
        self._add_box(f"{p}_RobotPickupBorder", (14.0, 23.2, 0.018), (2.0, 1.6, 0.008), (1.0, 0.85, 0.1), register_collision=False)

        # Pharmaceutical High-Density Medicine Shelves (North & West walls)
        self._add_box(f"{p}_ShelfNorth", (14.0, 35.0, 1.10), (9.0, 0.8, 2.2), COLOR_PHARM_SHELF, register_collision=True)
        self._add_box(f"{p}_ShelfWest", (9.2, 30.0, 1.10), (0.8, 6.0, 2.2), COLOR_PHARM_SHELF, register_collision=True)

        # Simulated Medicine Packages & Sterile Vials on shelves
        for idx, my in enumerate([28.0, 30.0, 32.0]):
            self._add_box(f"{p}_MedPackW_{idx}", (9.3, my, 1.30), (0.40, 1.0, 0.30), (0.2, 0.6, 0.8), register_collision=False)
            self._add_box(f"{p}_MedPackN_{idx}", (11.5 + idx * 2.2, 34.9, 1.30), (1.0, 0.40, 0.30), (0.8, 0.25, 0.25), register_collision=False)

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Intensive Care Unit - ICU (ICU-01: [-43, -26] x [3.8, 18.2])
    # ─────────────────────────────────────────────────────────────────────────
    def _build_icu_department(self) -> None:
        p = "ICU"
        # 6 Monitored ICU Suites / Bays with beds, vitals monitors, IV stands
        # West side cubicles: Y = [5.5, 9.0, 12.5, 16.0]
        for idx, by in enumerate([5.5, 9.0, 12.5, 16.0]):
            bnum = idx + 1
            # Bed frame & wipeable ICU mattress
            self._add_box(f"{p}_BedW_{bnum}_Frame", (-39.5, by, 0.35), (2.4, 1.0, 0.6), COLOR_BED_FRAME, register_collision=True)
            self._add_box(f"{p}_BedW_{bnum}_Matt", (-39.5, by, 0.70), (2.3, 0.9, 0.2), COLOR_MATTRESS_ICU, register_collision=False)
            self._add_box(f"{p}_BedW_{bnum}_Pillow", (-40.3, by, 0.84), (0.6, 0.7, 0.12), COLOR_PILLOW, register_collision=False)
            # Bedside Multi-Parameter Monitor with glowing green ECG screen
            self._add_box(f"{p}_MonitorW_{bnum}_Stand", (-42.0, by, 0.65), (0.45, 0.45, 1.3), COLOR_CHROME, register_collision=True)
            self._add_box(f"{p}_MonitorW_{bnum}_Screen", (-42.0, by, 1.25), (0.50, 0.40, 0.30), COLOR_ECG_SCREEN, register_collision=False)
            # Mobile Stainless Steel IV Drip Pole with Infusion Pump
            self._add_box(f"{p}_IVPoleW_{bnum}", (-37.5, by + 0.75, 1.05), (0.12, 0.12, 1.8), COLOR_CHROME, register_collision=False)
            self._add_box(f"{p}_IVBagW_{bnum}", (-37.5, by + 0.75, 1.85), (0.22, 0.16, 0.30), (0.9, 0.95, 1.0), register_collision=False)

        # Central ICU Nurse Command Hub (Compact central island leaving wide aisles on all sides)
        self._add_box(f"{p}_NurseCommandDesk", (-34.5, 11.0, 0.55), (1.2, 2.4, 1.05), COLOR_DESK_CLINICAL, register_collision=True)
        for mi in range(2):
            self._add_box(f"{p}_TelemetryMonitor_{mi}", (-34.5, 10.4 + mi * 1.2, 1.25), (0.12, 0.65, 0.40), COLOR_ECG_SCREEN, register_collision=False)

    # ─────────────────────────────────────────────────────────────────────────
    # 7. Operating Theatres (OT-01 & OT-02: [-43, -26] x [21.8, 37.2])
    # ─────────────────────────────────────────────────────────────────────────
    def _build_operating_theatres(self) -> None:
        p = "OT"
        # OT-01 General Surgery Table & Anesthesia
        self._add_box(f"{p}1_Pedestal", (-39.0, 30.0, 0.25), (0.7, 1.1, 0.5), COLOR_CHROME, register_collision=True)
        self._add_box(f"{p}1_SurgTableTop", (-39.0, 30.0, 0.65), (2.4, 1.1, 0.25), COLOR_SURGERY_TEAL, register_collision=False)
        self._add_box(f"{p}1_OverheadLamp", (-39.0, 30.0, 2.20), (1.2, 1.2, 0.15), (0.95, 0.98, 1.0), register_collision=False)
        self._add_box(f"{p}1_AnesthesiaCart", (-41.5, 33.5, 0.65), (0.8, 0.8, 1.3), COLOR_DESK_CLINICAL, register_collision=True)
        self._add_box(f"{p}1_ScrubStation", (-35.8, 30.0, 0.50), (0.6, 3.5, 1.0), COLOR_CHROME, register_collision=True)

        # OT-02 Robotic Surgery Suite
        self._add_box(f"{p}2_Pedestal", (-30.0, 30.0, 0.25), (0.7, 1.1, 0.5), COLOR_CHROME, register_collision=True)
        self._add_box(f"{p}2_SurgTableTop", (-30.0, 30.0, 0.65), (2.4, 1.1, 0.25), COLOR_SURGERY_TEAL, register_collision=False)
        self._add_box(f"{p}2_RoboticConsole", (-27.2, 33.5, 0.65), (1.1, 0.9, 1.3), (0.2, 0.35, 0.5), register_collision=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 8. Emergency & Trauma Department (EMR-01 & AMB-01: [-43, -26] x [-16.2, 0.2])
    # ─────────────────────────────────────────────────────────────────────────
    def _build_emergency_trauma(self) -> None:
        p = "Emergency"
        # Resuscitation Red-Zone Bay (TRM-01: center X = -39.0, Y = -8.0)
        self._add_box(f"{p}_RedZoneDecal", (-39.0, -8.0, 0.015), (5.5, 5.5, 0.01), (0.85, 0.18, 0.18), register_collision=False)
        self._add_box(f"{p}_TraumaGurney", (-40.5, -11.5, 0.40), (2.4, 1.1, 0.70), COLOR_BED_FRAME, register_collision=True)
        self._add_box(f"{p}_TraumaMatt", (-40.5, -11.5, 0.72), (2.3, 1.0, 0.20), COLOR_MATTRESS_ICU, register_collision=False)

        # Mobile Crash Cart with Defibrillator
        self._add_box(f"{p}_CrashCart", (-41.5, -14.0, 0.60), (0.85, 0.85, 1.15), COLOR_CRASH_CART, register_collision=True)
        self._add_box(f"{p}_Defibrillator", (-41.5, -14.0, 1.25), (0.45, 0.40, 0.25), (0.95, 0.85, 0.10), register_collision=False)

        # Emergency Triage Intake Counter (AMB-01: Placed safely along West wall at X = -32.5)
        self._add_box(f"{p}_TriageDesk", (-32.5, -8.0, 0.55), (1.2, 4.0, 1.05), COLOR_DESK_CLINICAL, register_collision=True)
        self._add_box(f"{p}_TriagePC", (-32.5, -8.0, 1.25), (0.15, 0.55, 0.35), (0.1, 0.1, 0.1), register_collision=False)

        # ── West Emergency Pavilion Exterior Canopy & Portico ────────────────
        # Projects outward on the West facade over ambulance arrival bay
        self._add_box(f"{p}_PorticoCanopy", (-45.5, -8.0, 2.40), (2.4, 8.0, 0.15), COLOR_CRASH_CART, register_collision=False)
        self._add_box(f"{p}_PorticoCol_N", (-45.8, -4.5, 1.20), (0.22, 0.22, 2.40), COLOR_ELEVATOR_FRAME, register_collision=True)
        self._add_box(f"{p}_PorticoCol_S", (-45.8, -11.5, 1.20), (0.22, 0.22, 2.40), COLOR_ELEVATOR_FRAME, register_collision=True)
        self._add_box(f"{p}_EmergencySignBacking", (-45.4, -8.0, 2.15), (0.10, 4.5, 0.60), (0.10, 0.12, 0.16), register_collision=False)

    # ─────────────────────────────────────────────────────────────────────────
    # 9. Pathology Laboratory (LAB-01: [-7, 6] x [21.8, 37.2])
    # ─────────────────────────────────────────────────────────────────────────
    def _build_pathology_laboratory(self) -> None:
        p = "Laboratory"
        # Specimen Reception Intake Counter (South door)
        self._add_box(f"{p}_IntakeDesk", (-0.5, 24.5, 0.55), (4.5, 0.9, 1.05), COLOR_DESK_CLINICAL, register_collision=True)
        # Central Diagnostic Lab Island Workbenches
        for idx, lx in enumerate([-3.5, 2.5]):
            self._add_box(f"{p}_Island_{idx}", (lx, 31.0, 0.50), (1.8, 5.0, 0.95), COLOR_DESK_CLINICAL, register_collision=True)
            self._add_box(f"{p}_Microscope_{idx}", (lx, 32.0, 1.05), (0.4, 0.4, 0.45), (0.15, 0.15, 0.18), register_collision=False)
            self._add_box(f"{p}_Centrifuge_{idx}", (lx, 29.5, 1.05), (0.5, 0.5, 0.40), COLOR_CHROME, register_collision=False)

    # ─────────────────────────────────────────────────────────────────────────
    # 10. Outpatient Department - OPD (OPD-01: [16, 29] x [-37.2, -19.8])
    # ─────────────────────────────────────────────────────────────────────────
    def _build_consultation_opd(self) -> None:
        p = "OPD"
        # Doctor Consultation Cubicles OPD-01 & OPD-02
        for idx, cx in enumerate([19.5, 25.5]):
            cnum = idx + 1
            self._add_box(f"{p}_DocDesk_{cnum}", (cx, -28.5, 0.45), (2.2, 1.0, 0.85), COLOR_DESK_WOOD, register_collision=True)
            self._add_box(f"{p}_DocPC_{cnum}", (cx, -28.5, 0.95), (0.45, 0.15, 0.35), (0.1, 0.1, 0.1), register_collision=False)
            self._add_box(f"{p}_ExamCouch_{cnum}", (cx, -34.0, 0.35), (1.0, 2.2, 0.65), COLOR_BED_FRAME, register_collision=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 11. General Inpatient Ward (GW-01: [16, 29] x [-16.2, 0.2])
    # ─────────────────────────────────────────────────────────────────────────
    def _build_general_inpatient_ward(self) -> None:
        p = "Ward"
        # Inpatient Beds with Privacy Dividers
        for idx, bx in enumerate([19.5, 25.5]):
            for row_i, by in enumerate([-4.0, -12.0]):
                bnum = idx * 2 + row_i + 1
                self._add_box(f"{p}_Bed_{bnum}_Frame", (bx, by, 0.35), (1.1, 2.4, 0.6), COLOR_BED_FRAME, register_collision=True)
                self._add_box(f"{p}_Bed_{bnum}_Matt", (bx, by, 0.70), (1.0, 2.3, 0.2), COLOR_MATTRESS_WARD, register_collision=False)
                self._add_box(f"{p}_BedsideLocker_{bnum}", (bx + 0.9, by, 0.40), (0.5, 0.5, 0.75), COLOR_DESK_CLINICAL, register_collision=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 12. AROGYA Robot Operations & Charging (CHG-01: [31.5, 43] x [21.8, 37.2])
    # ─────────────────────────────────────────────────────────────────────────
    def _build_robot_operations(self) -> None:
        p = "RobotOps"
        # Fleet Diagnostics Server Rack & Telemetry Console
        self._add_box(f"{p}_ServerRack", (33.0, 35.5, 1.00), (0.8, 2.0, 2.0), (0.12, 0.14, 0.18), register_collision=True)
        self._add_box(f"{p}_FleetDisplay", (33.0, 35.5, 1.60), (0.82, 1.6, 0.6), COLOR_DOCK_CYAN, register_collision=False)

        # Maintenance & Calibration Workbench
        self._add_box(f"{p}_Workbench", (41.0, 30.0, 0.50), (1.0, 4.0, 0.95), COLOR_DESK_WOOD, register_collision=True)
        self._add_box(f"{p}_ToolChest", (41.0, 34.0, 0.60), (0.9, 1.2, 1.2), COLOR_CRASH_CART, register_collision=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 13. South-West Healing Garden Courtyard & Outdoor Terrace ([-44, -26] x [-38.5, -18.5])
    # ─────────────────────────────────────────────────────────────────────────
    def _build_healing_garden_courtyard(self) -> None:
        p = "Courtyard"

        # Low Decorative Garden Planter Walls & Curbs (height 0.45m)
        self._add_box(f"{p}_RetainingWall_S", (-35.0, -38.2, 0.22), (18.0, 0.40, 0.45), COLOR_PLANTER_WOOD, register_collision=True)
        self._add_box(f"{p}_RetainingWall_W", (-43.8, -28.5, 0.22), (0.40, 19.0, 0.45), COLOR_PLANTER_WOOD, register_collision=True)

        # 4 Teak Outdoor Benches for Convalescence & Visitor Respite
        courtyard_benches = [
            (-38.0, -25.0), (-31.0, -25.0),
            (-38.0, -33.0), (-31.0, -33.0),
        ]
        for b_idx, (bx, by) in enumerate(courtyard_benches):
            self._add_box(f"{p}_Bench_{b_idx}", (bx, by, 0.42), (2.2, 0.80, 0.55), COLOR_DESK_WOOD, register_collision=True)
            self._add_box(f"{p}_BenchBack_{b_idx}", (bx, by + 0.35, 0.70), (2.2, 0.12, 0.40), COLOR_DESK_WOOD, register_collision=False)

        # Sculptural Garden Planter Boxes with Lush Evergreen Shrubs
        planters = [
            (-34.5, -29.0, 2.8, 2.8),
            (-41.0, -21.5, 1.8, 1.8),
            (-41.0, -35.5, 1.8, 1.8),
        ]
        for pl_idx, (plx, ply, pw, pd) in enumerate(planters):
            self._add_box(f"{p}_PlanterBox_{pl_idx}", (plx, ply, 0.35), (pw, pd, 0.70), COLOR_PLANTER_WOOD, register_collision=True)
            self._add_box(f"{p}_Evergreen_{pl_idx}", (plx, ply, 0.85), (pw * 0.90, pd * 0.90, 0.45), COLOR_PLANT_GREEN, register_collision=False)

        # Exterior Ambulance Staging Driveway Bays (Yellow Hazard Staging Decals)
        self._add_box(f"{p}_AmbulanceBay1", (-28.5, -22.5, 0.015), (3.0, 5.5, 0.01), (0.85, 0.75, 0.15), register_collision=False)
        self._add_box(f"{p}_AmbulanceBay2", (-28.5, -30.5, 0.015), (3.0, 5.5, 0.01), (0.85, 0.75, 0.15), register_collision=False)

    # ─────────────────────────────────────────────────────────────────────────
    # 14. Corridor Amenities (Sanitizer Posts & Signs Flush Against Walls)
    # ─────────────────────────────────────────────────────────────────────────
    def _build_corridor_amenities(self) -> None:
        p = "Amenities"
        # Wall-flush Hand Sanitizer Dispensers placed safely out of robot paths
        sanitizer_coords = [
            (2.2, 3.65, 1.20),
            (-2.2, 3.65, 1.20),
            (14.0, 18.3, 1.20),
            (-24.0, 18.3, 1.20),
        ]
        for idx, (sx, sy, sz) in enumerate(sanitizer_coords):
            self._add_box(f"{p}_SanitizerUnit_{idx}", (sx, sy, sz), (0.22, 0.14, 0.35), (0.2, 0.7, 0.9), register_collision=False)

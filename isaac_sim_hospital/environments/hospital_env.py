"""
Grand Hospital Environment (88m x 76m) -- Full Digital Twin v6.0
================================================================
Self-contained, ultra-rich procedural hospital digital twin for NVIDIA Isaac Sim 5.1.0.
Directly mirrors the complete clinical floor plan requested for the Final Year Major Project:
"Multi-Agent Embodied AI Robot for Autonomous Hospital Assistance using Vision-Language Reasoning"

Expanded Architecture Features:
    - 88.0m x 76.0m grand clinical facility (6,688 m²) with solid perimeter enclosure walls
    - Low 1.30m architectural cutaway walls completely eliminating the "small boxes" appearance
      and revealing all clinical interiors, beds, equipment, and navigating AMRs
    - 20 Grand, Expansive Clinical Departments:
      * OPERATING THEATER (OT-01, Dual Surgical Suites & Anesthesia)
      * RADIOLOGY & IMAGING (RAD-01, MRI & Multi-slice CT Scanner)
      * PATHOLOGY LABORATORY (LAB-01, Diagnostics & Lab Benches)
      * CENTRAL PHARMACY & DISPENSARY (PHM-01)
      * MEDICINE SECURE STORAGE & VAULT (STR-01)
      * PRIMARY ROBOT CHARGING STATION (CHG-01, 4 Fleet Docks)
      * INTENSIVE CARE UNIT (ICU-01, 8 Monitored Beds with ECG screens)
      * CENTRAL NURSE STATION (NST-01, Command Hub)
      * CONSULTATION CLINIC 1 (DOC-01, Internal Medicine)
      * CONSULTATION CLINIC 2 (DOC-02, Cardiology & Specialists)
      * ISOLATION UNIT (ISO-01, Negative Pressure Airborne Care)
      * STAFF ROOM & LOUNGE (CAF-01 / STF-01)
      * EMERGENCY & TRAUMA DEPARTMENT (EMR-01, Resuscitation Bays)
      * MAIN RECEPTION ATRIUM (RCT-01, 22m Wide Grand Atrium)
      * CENTRAL WAITING LOUNGE (WAT-01, 20m Wide Seating Area)
      * GENERAL INPATIENT WARD (GW-01, 27.5m Wide x 16.5m Deep, 8 Beds)
      * PUBLIC RESTROOMS & WASHROOMS (WSH-01)
      * BIOMEDICAL EQUIPMENT DEPOT (STR-02, Wheelchairs & Transport Carts)
      * GRAND HOSPITAL ENTRANCE FOYER (ENT-01)
      * OUTPATIENT DEPARTMENT (OPD-01, 27.5m Wide x 17.5m Deep, 4 Doctor Cubicles)
    - 3D Elevated Angled Room Nameboards (Z = 2.05m) facing the isometric camera directly
    - Doorway Lintel Signboards for corridor navigation
    - 4 Dedicated Robot Charging Docks (Docks 1, 2, 3, 4) with glowing cyan floor pads
    - 100% collision box registration with CollisionGuard for wall-safe navigation
"""

from __future__ import annotations

import numpy as np

try:
    import omni.usd
    from pxr import Gf, Sdf, UsdGeom, UsdLux
    from isaacsim.core.api.objects import (
        FixedCuboid as _FixedCuboid,
        GroundPlane as _GroundPlane,
        VisualCuboid as _VisualCuboid,
    )
    HAS_OMNI = True
except ImportError:
    omni = None
    Gf = Sdf = UsdGeom = UsdLux = None
    _FixedCuboid = _GroundPlane = _VisualCuboid = None
    HAS_OMNI = False


def VisualCuboid(*args, **kwargs):
    if HAS_OMNI and _VisualCuboid is not None:
        try:
            return _VisualCuboid(*args, **kwargs)
        except Exception:
            return None
    return None


def FixedCuboid(*args, **kwargs):
    if HAS_OMNI and _FixedCuboid is not None:
        try:
            return _FixedCuboid(*args, **kwargs)
        except Exception:
            return None
    return None


def GroundPlane(*args, **kwargs):
    if HAS_OMNI and _GroundPlane is not None:
        try:
            return _GroundPlane(*args, **kwargs)
        except Exception:
            return None
    return None


class HospitalEnvironment:
    """Procedural builder for the 88m x 76m grand hospital digital twin."""

    def __init__(
        self,
        wall_height: float = 1.30,  # Standard architectural cutaway height (eliminates boxy occlusion)
        wall_thickness: float = 0.22,
        door_width: float = 2.0,
        **kwargs,
    ) -> None:
        self.wall_height = wall_height
        self.perimeter_wall_height = 1.80  # Outer boundary containment
        self.wall_thickness = wall_thickness
        self.door_width = door_width
        self.stage = (
            omni.usd.get_context().get_stage()
            if (HAS_OMNI and omni and omni.usd and omni.usd.get_context())
            else None
        )

        # Architectural & Wall Colors — Professional Modern Hospital Palette
        self.color_wall = np.array([0.94, 0.95, 0.96])       # Clean architectural off-white
        self.color_baseboard = np.array([0.22, 0.25, 0.28])  # Dark slate protective kickplate
        self.color_floor_slab = np.array([0.88, 0.89, 0.91]) # Medical terrazzo foundation
        self.color_atrium_floor = np.array([0.92, 0.91, 0.88]) # Warm neutral porcelain tile
        self.color_room_floor = np.array([0.93, 0.94, 0.95])   # Sterile pale surgical vinyl
        self.color_corridor = np.array([0.88, 0.89, 0.91])
        self.color_corridor_accent = np.array([0.84, 0.86, 0.89])
        self.color_corridor_stripe = np.array([0.20, 0.55, 0.85])  # Architectural guide stripe
        self.color_door_beacon = np.array([0.85, 0.75, 0.25])        # Gold door beacon

        # Subtle Department Inset & Border Accents (Restrained, Professional Medical Tones)
        self.colors = {
            "reception":     np.array([0.90, 0.92, 0.91]),  # Muted Sage/Teal Atrium Inset
            "waiting":       np.array([0.91, 0.91, 0.90]),  # Warm Grey Lounge Inset
            "pharmacy":      np.array([0.90, 0.93, 0.92]),  # Clean Mint Inset
            "nurse_station": np.array([0.89, 0.93, 0.92]),  # Clinical Sage Inset
            "icu":           np.array([0.90, 0.92, 0.95]),  # Ice Blue Clinical Inset
            "ward":          np.array([0.91, 0.93, 0.92]),  # Seafoam Inset
            "emergency":     np.array([0.93, 0.90, 0.90]),  # Subtle Emergency Inset
            "trauma":        np.array([0.94, 0.89, 0.89]),  # Subtle Trauma Inset
            "consult":       np.array([0.92, 0.91, 0.93]),  # Soft Lavender Inset
            "ot":            np.array([0.89, 0.93, 0.92]),  # Surgical Teal Inset
            "lab":           np.array([0.90, 0.92, 0.94]),  # Diagnostic Blue Inset
            "general_ward":  np.array([0.91, 0.93, 0.92]),  # Calm Seafoam Inset
            "robot_dock":    np.array([0.89, 0.93, 0.95]),  # Tech Cyan Inset
            "cafeteria":     np.array([0.93, 0.91, 0.89]),  # Warm Wood Lounge Inset
            "isolation":     np.array([0.94, 0.93, 0.89]),  # Airborne Amber Inset
            "storage":       np.array([0.90, 0.91, 0.92]),  # Steel Equipment Inset
            "med_storage":   np.array([0.92, 0.91, 0.90]),  # Tan Vault Inset
            "entrance":      np.array([0.91, 0.92, 0.94]),  # Foyer Inset
            "opd":           np.array([0.92, 0.90, 0.92]),  # Outpatient Inset
            "washroom":      np.array([0.90, 0.92, 0.94]),  # Sanitary Inset
            "ot2":           np.array([0.89, 0.93, 0.92]),  # Robotic Surgery Inset
            "blood_bank":    np.array([0.94, 0.90, 0.91]),  # Transfusion Inset
            "pediatric":     np.array([0.94, 0.92, 0.89]),  # Pediatric Warm Inset
            "patient_suite": np.array([0.90, 0.92, 0.94]),  # Deluxe Suite Inset
            "sanitization":  np.array([0.89, 0.93, 0.92]),  # Sterile Decon Inset
            "ambulance":     np.array([0.93, 0.90, 0.89]),  # Triage Inset
        }

        # Thin Architectural Trim Accents (for wall stripes & wayfinding lines)
        self.accents = {
            "emergency": np.array([0.82, 0.20, 0.20]),
            "icu":       np.array([0.25, 0.55, 0.85]),
            "pharmacy":  np.array([0.22, 0.65, 0.52]),
            "ot":        np.array([0.18, 0.55, 0.48]),
            "lab":       np.array([0.20, 0.45, 0.75]),
            "opd":       np.array([0.35, 0.60, 0.65]),
            "robot":     np.array([0.00, 0.85, 1.00]),
            "atrium":    np.array([0.20, 0.55, 0.80]),
        }

        # Spatial Architecture Color Tokens
        self.color_garden_paver = np.array([0.74, 0.71, 0.66])    # Warm sandstone outdoor terrace pavers
        self.color_garden_border = np.array([0.42, 0.40, 0.38])   # Dark stone retaining curb
        self.color_atrium_medallion = np.array([0.96, 0.94, 0.90])# Warm ivory porcelain rotunda medallion
        self.color_atrium_gold = np.array([0.82, 0.70, 0.35])     # Inlaid brass/gold architectural ring
        self.color_spine_floor = np.array([0.94, 0.95, 0.97])     # Polished white pearl terrazzo concourse
        self.color_spine_border = np.array([0.20, 0.24, 0.28])    # Dark slate concourse margin band
        self.color_exterior_ground = np.array([0.84, 0.86, 0.87]) # Neutral exterior ground plane

        # Furniture Colors
        self.color_desk = np.array([0.28, 0.32, 0.38])
        self.color_bed_frame = np.array([0.24, 0.27, 0.30])
        self.color_mattress = np.array([0.95, 0.95, 0.97])
        self.color_pillow = np.array([0.45, 0.70, 0.85])
        self.color_counter = np.array([0.32, 0.36, 0.42])
        self.color_cabinet = np.array([0.50, 0.55, 0.60])
        self.color_ecg_screen = np.array([0.05, 0.95, 0.25])  # Glowing ECG green

        self._wall_counter = 0
        self.semantic_locations: dict[str, dict] = {}
        self.collision_boxes: list[tuple[float, float, float, float]] = []

    def build_all(self) -> None:
        """Construct the complete 88m x 76m grand hospital digital twin."""
        print("[HospitalEnv] Building grand 88m x 76m hospital digital twin stage...")
        self.build_lighting()
        self.build_floors()
        self.build_perimeter_walls()
        self.build_all_rooms()
        self.build_static_obstacles()
        print(
            f"[HospitalEnv] Complete! ({self._wall_counter} wall segments, "
            f"{len(self.semantic_locations)} clinical rooms mapped, "
            f"{len(self.collision_boxes)} collision barriers registered)"
        )

    def get_collision_guard(self, robot_radius: float = 0.38):
        try:
            from navigation.collision_guard import CollisionGuard
        except (ImportError, ModuleNotFoundError):
            from isaac_sim_hospital.navigation.collision_guard import CollisionGuard
        return CollisionGuard(
            collision_boxes=self.collision_boxes,
            robot_radius=robot_radius,
            grid_bounds=(-46.0, 46.0, -40.0, 40.0),
        )

    def get_semantic_locations(self) -> dict[str, dict]:
        """Return semantic locations mapping for navigation and task allocation."""
        return self.semantic_locations

    def build_lighting(self) -> None:
        """Create balanced key and fill lighting."""
        if not HAS_OMNI or self.stage is None:
            return
        sun = UsdLux.DistantLight.Define(self.stage, Sdf.Path("/World/Hospital/SunLight"))
        sun.CreateIntensityAttr(850.0)
        sun.CreateAngleAttr(0.53)
        sun.CreateColorAttr(Gf.Vec3f(0.98, 0.98, 1.0))

        dome = UsdLux.DomeLight.Define(self.stage, Sdf.Path("/World/Hospital/AmbientLight"))
        dome.CreateIntensityAttr(450.0)
        dome.CreateColorAttr(Gf.Vec3f(0.94, 0.96, 0.98))

    def build_floors(self) -> None:
        """Create articulated pavilion floor slabs, Central Atrium rotunda medallion, 5.0m Main Spine, and circulation hierarchy."""
        GroundPlane(prim_path="/World/GroundPlane", z_position=0.0)

        # ── 1. Global Site Foundation Base Plate (Neutral Site Concrete) ──────
        # Spans [-46, 46] in X, [-41, 40] in Y
        VisualCuboid(
            prim_path="/World/Hospital/Floors/FoundationSlab_Ground",
            position=np.array([0.0, 0.0, 0.0003]),
            size=1.0,
            scale=np.array([92.0, 82.0, 0.0005]),
            color=self.color_exterior_ground,
        )

        # ── 2. North Critical Care & Surgical Wing Floor Slab ────────────────
        # Spans [-44.0, 44.0] x [1.8, 37.5] — Polished Medical Terrazzo
        VisualCuboid(
            prim_path="/World/Hospital/Floors/FloorSlab_NorthWing",
            position=np.array([0.0, 19.65, 0.0007]),
            size=1.0,
            scale=np.array([88.0, 35.7, 0.0008]),
            color=self.color_floor_slab,
        )

        # ── 3. West Emergency Pavilion Outward Projection Slab ────────────────
        # Projects 1.0m further West to X = -44.5 ([-44.5, -24.5] x [-17.0, 2.0])
        VisualCuboid(
            prim_path="/World/Hospital/Floors/FloorSlab_EmergencyPavilion",
            position=np.array([-34.5, -7.5, 0.0009]),
            size=1.0,
            scale=np.array([20.0, 19.0, 0.0010]),
            color=np.array([0.91, 0.90, 0.92]),  # Clinical Emergency Vinyl
        )

        # ── 4. East Inpatient & Diagnostic Wing Floor Slab ───────────────────
        # Spans [13.5, 44.0] x [-37.5, 2.0] — Polished Medical Terrazzo
        VisualCuboid(
            prim_path="/World/Hospital/Floors/FloorSlab_EastWing",
            position=np.array([28.75, -17.75, 0.0007]),
            size=1.0,
            scale=np.array([30.5, 39.5, 0.0008]),
            color=self.color_floor_slab,
        )

        # ── 5. South Main Entrance Grand Portico Slab (Projecting Outward) ────
        # Projects forward 1.0m to Y = -38.5 ([-9.0, 9.0] x [-38.5, -36.5])
        VisualCuboid(
            prim_path="/World/Hospital/Floors/FloorSlab_EntrancePortico",
            position=np.array([0.0, -37.5, 0.0011]),
            size=1.0,
            scale=np.array([18.0, 2.0, 0.0014]),
            color=np.array([0.20, 0.23, 0.28]),  # Architectural Granite Threshold
        )

        # ── 6. South-West Healing Garden Courtyard & Outdoor Terrace ─────────
        # Distinct 18.5m x 20.0m landscaped outdoor courtyard breaking the outer box silhouette
        # Spans [-44.0, -25.5] x [-38.5, -18.5]
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Courtyard_GardenPavers",
            position=np.array([-34.75, -28.5, 0.0008]),
            size=1.0,
            scale=np.array([18.5, 20.0, 0.0012]),
            color=self.color_garden_paver,  # Warm sandstone terrace pavers
        )
        # Decorative Garden Retaining Curb & Perimeter Trim
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Courtyard_GardenBorder",
            position=np.array([-34.75, -28.5, 0.0012]),
            size=1.0,
            scale=np.array([18.9, 20.4, 0.0008]),
            color=self.color_garden_border,  # Dark stone garden curb
        )

        # ── 7. Central Atrium & Reception Grand Rotunda (The Main Landmark) ──
        # Spans X in [-11.0, 11.0], Y in [-16.2, 0.2] (Warm ivory porcelain stone base)
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Atrium_FloorSlab",
            position=np.array([0.0, -8.0, 0.0010]),
            size=1.0,
            scale=np.array([22.0, 16.4, 0.0012]),
            color=self.color_atrium_floor,
        )

        # Octagonal Rotunda Base Landmark centered at (0.0, -4.5)
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Atrium_RotundaBase",
            position=np.array([0.0, -4.5, 0.0014]),
            size=1.0,
            scale=np.array([14.0, 14.0, 0.0014]),
            color=self.color_atrium_medallion,
        )
        # Outer Decorative Slate Inlay Ring
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Atrium_SlateRing",
            position=np.array([0.0, -4.5, 0.0018]),
            size=1.0,
            scale=np.array([13.0, 13.0, 0.0010]),
            color=np.array([0.22, 0.25, 0.30]),
        )
        # Inlaid Brass/Gold Architectural Trim Ring
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Atrium_GoldRing",
            position=np.array([0.0, -4.5, 0.0022]),
            size=1.0,
            scale=np.array([12.0, 12.0, 0.0010]),
            color=self.color_atrium_gold,
        )
        # Warm Ivory Rotunda Medallion Field
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Atrium_IvoryField",
            position=np.array([0.0, -4.5, 0.0024]),
            size=1.0,
            scale=np.array([11.0, 11.0, 0.0010]),
            color=self.color_atrium_medallion,
        )
        # Inner Royal Navy Compass Medallion
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Atrium_NavyMedallion",
            position=np.array([0.0, -4.5, 0.0026]),
            size=1.0,
            scale=np.array([6.0, 6.0, 0.0010]),
            color=np.array([0.12, 0.35, 0.58]),
        )
        # Inlaid Medical 8-Point Compass Star Emblem
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Atrium_StarArm_NS",
            position=np.array([0.0, -4.5, 0.0030]),
            size=1.0,
            scale=np.array([0.9, 3.8, 0.0010]),
            color=np.array([0.96, 0.98, 1.0]),
        )
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Atrium_StarArm_EW",
            position=np.array([0.0, -4.5, 0.0030]),
            size=1.0,
            scale=np.array([3.8, 0.9, 0.0010]),
            color=np.array([0.96, 0.98, 1.0]),
        )
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Atrium_StarCenter",
            position=np.array([0.0, -4.5, 0.0032]),
            size=1.0,
            scale=np.array([1.2, 1.2, 0.0012]),
            color=self.color_atrium_gold,
        )

        # ── 8. Main Hospital Spine Concourse (Primary Circulation Highway) ────
        # Dedicated 5.0m-wide grand concourse connecting Entrance -> Atrium -> North Concourse
        # Spans X in [-2.5, 2.5], Y in [-38.5, 22.0] (Total length 60.5m)
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Spine_MainConcourse",
            position=np.array([0.0, -8.25, 0.0015]),
            size=1.0,
            scale=np.array([5.0, 60.5, 0.0015]),
            color=self.color_spine_floor,
        )
        # West Margin Slate Trim Band
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Spine_MarginWest",
            position=np.array([-2.42, -8.25, 0.0018]),
            size=1.0,
            scale=np.array([0.16, 60.5, 0.0010]),
            color=self.color_spine_border,
        )
        # East Margin Slate Trim Band
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Spine_MarginEast",
            position=np.array([2.42, -8.25, 0.0018]),
            size=1.0,
            scale=np.array([0.16, 60.5, 0.0010]),
            color=self.color_spine_border,
        )
        # Grand Concourse Royal Navy Center Wayfinding Guide Ribbon
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Spine_CenterRibbon",
            position=np.array([0.0, -8.25, 0.0020]),
            size=1.0,
            scale=np.array([0.24, 60.0, 0.0010]),
            color=np.array([0.15, 0.45, 0.75]),
        )

        # ── 9. Secondary Corridors (Hierarchy: 3.4m - 3.6m Width) ────────────
        # 1. Main Central East-West Corridor (Y ~ 2.0, [-42.0, 42.0] x [0.2, 3.8])
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Corridor_Central",
            position=np.array([0.0, 2.0, 0.0012]),
            size=1.0,
            scale=np.array([84.0, 3.6, 0.0015]),
            color=self.color_corridor_accent,
        )
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Corridor_Central_Stripe",
            position=np.array([0.0, 2.0, 0.0018]),
            size=1.0,
            scale=np.array([83.0, 0.15, 0.001]),
            color=np.array([0.20, 0.55, 0.85]),  # Clean Medical Blue Guide Ribbon
        )

        # 2. North East-West Corridor (Y ~ 20.0, [-42.0, 42.0] x [18.2, 21.8])
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Corridor_North",
            position=np.array([0.0, 20.0, 0.0012]),
            size=1.0,
            scale=np.array([84.0, 3.6, 0.0015]),
            color=self.color_corridor_accent,
        )
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Corridor_North_Stripe",
            position=np.array([0.0, 20.0, 0.0018]),
            size=1.0,
            scale=np.array([83.0, 0.15, 0.001]),
            color=np.array([0.22, 0.65, 0.52]),  # Pharmacy & Surgical Green Guide Ribbon
        )

        # 3. South East-West Corridor (Y ~ -18.0, [-24.0, 42.0] x [-19.8, -16.2])
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Corridor_South",
            position=np.array([9.0, -18.0, 0.0012]),
            size=1.0,
            scale=np.array([66.0, 3.6, 0.0015]),
            color=self.color_corridor_accent,
        )
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Corridor_South_Stripe",
            position=np.array([9.0, -18.0, 0.0018]),
            size=1.0,
            scale=np.array([65.0, 0.15, 0.001]),
            color=np.array([0.82, 0.20, 0.20]),  # Emergency & Trauma Red Guide Ribbon
        )

        # 4. West Longitudinal Spine (X ~ -24.0, [-25.8, -22.2] x [-18.0, 37.0])
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Corridor_WestSpine",
            position=np.array([-24.0, 9.5, 0.0013]),
            size=1.0,
            scale=np.array([3.4, 55.0, 0.0015]),
            color=self.color_corridor_accent,
        )
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Corridor_WestSpine_Stripe",
            position=np.array([-24.0, 9.5, 0.0018]),
            size=1.0,
            scale=np.array([0.15, 54.0, 0.001]),
            color=np.array([0.85, 0.35, 0.25]),  # Trauma Corridor Guideline
        )

        # 5. East Longitudinal Spine (X ~ 14.0, [12.2, 15.8] x [-37.0, 37.0])
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Corridor_EastSpine",
            position=np.array([14.0, 0.0, 0.0013]),
            size=1.0,
            scale=np.array([3.4, 74.0, 0.0015]),
            color=self.color_corridor_accent,
        )
        VisualCuboid(
            prim_path="/World/Hospital/Floors/Corridor_EastSpine_Stripe",
            position=np.array([14.0, 0.0, 0.0018]),
            size=1.0,
            scale=np.array([0.15, 73.0, 0.001]),
            color=np.array([0.00, 0.85, 1.00]),  # AROGYA Robot Fleet Cyan Guide Ribbon
        )

        # ── 10. Corridor Junction Splays (45° Floor Fillet Accents) ───────────
        # Chamfer fillets at major concourse intersections for organic spatial flow
        splay_junctions = [
            (-2.5, 0.2), (2.5, 0.2), (-2.5, 3.8), (2.5, 3.8),
            (-24.0, 0.2), (-24.0, 3.8), (14.0, 0.2), (14.0, 3.8),
            (-24.0, 18.2), (-24.0, 21.8), (14.0, 18.2), (14.0, 21.8),
        ]
        for s_idx, (sx, sy) in enumerate(splay_junctions):
            VisualCuboid(
                prim_path=f"/World/Hospital/Floors/JunctionSplay_{s_idx}",
                position=np.array([sx, sy, 0.0016]),
                size=1.0,
                scale=np.array([0.90, 0.90, 0.001]),
                color=self.color_spine_border,
            )

    def build_perimeter_walls(self) -> None:
        """Construct articulated architectural perimeter with projecting pavilions, porticos, and courtyards."""
        t = 0.28
        h = self.perimeter_wall_height

        # ── 1. West Boundary: Articulated Pavilion Structure ─────────────────
        # 1a. North-West Section (OT-01 & ICU-01: Y in [2.0, 37.5], X = -43.5)
        self._add_wall_box(x=-43.5, y=19.75, len_x=t, len_y=35.5, name="Perimeter_NW", wall_height=h)

        # 1b. Emergency Pavilion Outward Projection (EMR-01 & AMB-01: Y in [-17.0, 2.0], X = -44.5)
        # Projects 1.0m further West, establishing unmistakable emergency wing pavilion silhouette
        self._add_wall_box(x=-44.5, y=-7.5, len_x=t, len_y=19.0, name="Perimeter_EmergencyWest", wall_height=h)
        # Emergency Pavilion North Return Wall (Y = 2.0, X in [-44.5, -43.5])
        self._add_wall_box(x=-44.0, y=2.0, len_x=1.0, len_y=t, name="Perimeter_EmergencyReturnN", wall_height=h)
        # Emergency Pavilion South Return Wall (Y = -17.0, X in [-44.5, -26.0])
        self._add_wall_box(x=-35.25, y=-17.0, len_x=18.5, len_y=t, name="Perimeter_EmergencyReturnS", wall_height=h)

        # 1c. South-West Healing Garden Setback Wall (X = -26.0, Y in [-37.5, -17.0])
        # Indoor building facade steps back 17.5m, opening up the exterior Healing Garden Courtyard
        self._add_wall_box(x=-26.0, y=-27.25, len_x=t, len_y=20.5, name="Perimeter_GardenSetback", wall_height=h)

        # ── 2. East Boundary Wall (X = 43.5, Y in [-37.5, 37.5]) ─────────────
        self._add_wall_box(x=43.5, y=0.0, len_x=t, len_y=75.0, name="Perimeter_East", wall_height=h)

        # ── 3. North Boundary Wall (Y = 37.5, X in [-43.5, 43.5]) ────────────
        self._add_wall_box(x=0.0, y=37.5, len_x=87.0, len_y=t, name="Perimeter_North", wall_height=h)

        # ── 4. South Boundary: Projecting Entrance Portico & Articulated Facade ──
        # 4a. Grand Entrance Portico (Projects forward 1.0m to Y = -38.5, X in [-9.0, 9.0])
        # South Portico portal with 4.5m wide grand opening centered at X = 0.0
        self._add_wall_box(x=-6.75, y=-38.5, len_x=4.5, len_y=t, name="Portico_South_W", wall_height=h)
        self._add_wall_box(x=6.75, y=-38.5, len_x=4.5, len_y=t, name="Portico_South_E", wall_height=h)
        # Portico West Return Wall (X = -9.0, Y in [-38.5, -37.5])
        self._add_wall_box(x=-9.0, y=-38.0, len_x=t, len_y=1.0, name="Portico_Return_W", wall_height=h)
        # Portico East Return Wall (X = 9.0, Y in [-38.5, -37.5])
        self._add_wall_box(x=9.0, y=-38.0, len_x=t, len_y=1.0, name="Portico_Return_E", wall_height=h)

        # 4b. South-East Outpatient & Deluxe Inpatient Facade Wall (Y = -37.5, X in [9.0, 43.5])
        self._add_wall_box(x=26.25, y=-37.5, len_x=34.5, len_y=t, name="Perimeter_South_East", wall_height=h)

        # 4c. South-West Support Wing Wall along Garden Terrace (Y = -37.5, X in [-26.0, -9.0])
        self._add_wall_box(x=-17.5, y=-37.5, len_x=17.0, len_y=t, name="Perimeter_South_Support", wall_height=h)

        # ── 5. Prestigious Entrance Facade Signboard: "AROGYA MEDICAL CENTER" ──
        VisualCuboid(
            prim_path="/World/Hospital/Walls/FacadeSign_Backing",
            position=np.array([0.0, -38.45, 2.05]),
            size=1.0,
            scale=np.array([8.6, 0.12, 1.4]),
            color=np.array([0.08, 0.12, 0.18]),
        )
        try:
            from environments.signage_generator import create_textured_signboard_mesh
            create_textured_signboard_mesh(
                self.stage,
                "/World/Hospital/Walls/FacadeSign_Mesh",
                (0.0, -38.40, 2.05),
                (8.2, 1.3),
                "ENT-01",
                facing="north",
            )
        except Exception:
            pass

    def _add_wall_box(
        self,
        x: float,
        y: float,
        len_x: float,
        len_y: float,
        name: str,
        wall_height: float | None = None,
    ) -> None:
        """Helper to create static collision wall segment with dark slate baseboard kickplates."""
        if len_x <= 0.05 or len_y <= 0.05:
            return
        h = wall_height if wall_height is not None else self.wall_height
        self._wall_counter += 1
        clean_name = name.replace("-", "_")
        prim_name = f"{clean_name}_{self._wall_counter:03d}"
        FixedCuboid(
            prim_path=f"/World/Hospital/Walls/{prim_name}",
            position=np.array([x, y, h / 2.0]),
            size=1.0,
            scale=np.array([len_x, len_y, h]),
            color=self.color_wall,
        )
        self.collision_boxes.append((x - len_x / 2.0, x + len_x / 2.0, y - len_y / 2.0, y + len_y / 2.0))

        # Architectural Dark Slate Baseboard Kickplate (Z = 0.06m, height = 0.12m)
        VisualCuboid(
            prim_path=f"/World/Hospital/Walls/Baseboard_{prim_name}",
            position=np.array([x, y, 0.06]),
            size=1.0,
            scale=np.array([len_x + (0.02 if len_x > len_y else 0.0), len_y + (0.02 if len_y > len_x else 0.0), 0.12]),
            color=self.color_baseboard,
        )

    def _add_furniture_box(
        self,
        prim_path: str,
        position: np.ndarray | Tuple[float, float, float] | list,
        scale: np.ndarray | Tuple[float, float, float] | list,
        color: np.ndarray | Tuple[float, float, float] | list,
        register_collision: bool = True,
    ) -> None:
        """Helper to create static furniture and register 2D collision boundary."""
        pos = np.asarray(position, dtype=float)
        sc = np.asarray(scale, dtype=float)
        FixedCuboid(
            prim_path=prim_path,
            position=pos,
            size=1.0,
            scale=sc,
            color=color,
        )
        if register_collision:
            self.collision_boxes.append((
                float(pos[0] - sc[0] / 2.0),
                float(pos[0] + sc[0] / 2.0),
                float(pos[1] - sc[1] / 2.0),
                float(pos[1] + sc[1] / 2.0),
            ))

    def _build_room(
        self,
        room_id: str,
        name: str,
        xmin: float,
        xmax: float,
        ymin: float,
        ymax: float,
        door_wall: str = "north",
        door_pos: float = 0.0,
        door_width: float = 2.0,
        color: np.ndarray | None = None,
        floating_badge_w: float | None = None,
        floating_badge_h: float | None = None,
    ) -> None:
        """Construct a clinical room with cutaway walls, doorway, lintel, and angled 3D signboards."""
        clean_id = room_id.replace("-", "_")
        t = self.wall_thickness
        dw = door_width
        color = color if color is not None else self.colors.get("ward", self.color_corridor)

        width_x = xmax - xmin
        depth_y = ymax - ymin
        cx = (xmin + xmax) / 2.0
        cy = (ymin + ymax) / 2.0

        # 1. Department Floor Tile (Clean, Sterile Medical Vinyl)
        VisualCuboid(
            prim_path=f"/World/Hospital/Rooms/Floor_{clean_id}",
            position=np.array([cx, cy, 0.002]),
            size=1.0,
            scale=np.array([width_x - 0.05, depth_y - 0.05, 0.002]),
            color=self.color_room_floor,
        )
        # Subtle Architectural Department Inset Border
        VisualCuboid(
            prim_path=f"/World/Hospital/Rooms/Border_{clean_id}",
            position=np.array([cx, cy, 0.0024]),
            size=1.0,
            scale=np.array([width_x - 0.25, depth_y - 0.25, 0.001]),
            color=color if color is not None else self.color_room_floor,
        )

        # 2. Doorway Coordinate & Gold Floor Marker Beacon
        if door_wall == "north":
            door_coord = (door_pos, ymax)
            corridor_wp = (door_pos, ymax + 1.2)
        elif door_wall == "south":
            door_coord = (door_pos, ymin)
            corridor_wp = (door_pos, ymin - 1.2)
        elif door_wall == "west":
            door_coord = (xmin, door_pos)
            corridor_wp = (xmin - 1.2, door_pos)
        else:
            door_coord = (xmax, door_pos)
            corridor_wp = (xmax + 1.2, door_pos)

        VisualCuboid(
            prim_path=f"/World/Hospital/Rooms/DoorBeacon_{clean_id}",
            position=np.array([door_coord[0], door_coord[1], 0.02]),
            size=1.0,
            scale=np.array([0.8, 0.8, 0.02]),
            color=self.color_door_beacon,
        )

        # 3. Overhead Door Header / Lintel Beam (Z = 1.32m)
        lintel_z = self.wall_height + 0.08
        if door_wall in ("north", "south"):
            FixedCuboid(
                prim_path=f"/World/Hospital/Rooms/DoorLintel_{clean_id}",
                position=np.array([door_coord[0], door_coord[1], lintel_z]),
                size=1.0,
                scale=np.array([dw, t, 0.16]),
                color=self.color_wall,
            )
            # Door Jambs for Architectural Framing
            VisualCuboid(
                prim_path=f"/World/Hospital/Rooms/DoorJambL_{clean_id}",
                position=np.array([door_coord[0] - dw / 2.0, door_coord[1], self.wall_height / 2.0]),
                size=1.0,
                scale=np.array([0.12, t * 1.15, self.wall_height]),
                color=self.color_baseboard,
            )
            VisualCuboid(
                prim_path=f"/World/Hospital/Rooms/DoorJambR_{clean_id}",
                position=np.array([door_coord[0] + dw / 2.0, door_coord[1], self.wall_height / 2.0]),
                size=1.0,
                scale=np.array([0.12, t * 1.15, self.wall_height]),
                color=self.color_baseboard,
            )
        else:
            FixedCuboid(
                prim_path=f"/World/Hospital/Rooms/DoorLintel_{clean_id}",
                position=np.array([door_coord[0], door_coord[1], lintel_z]),
                size=1.0,
                scale=np.array([t, dw, 0.16]),
                color=self.color_wall,
            )
            VisualCuboid(
                prim_path=f"/World/Hospital/Rooms/DoorJambL_{clean_id}",
                position=np.array([door_coord[0], door_coord[1] - dw / 2.0, self.wall_height / 2.0]),
                size=1.0,
                scale=np.array([t * 1.15, 0.12, self.wall_height]),
                color=self.color_baseboard,
            )
            VisualCuboid(
                prim_path=f"/World/Hospital/Rooms/DoorJambR_{clean_id}",
                position=np.array([door_coord[0], door_coord[1] + dw / 2.0, self.wall_height / 2.0]),
                size=1.0,
                scale=np.array([t * 1.15, 0.12, self.wall_height]),
                color=self.color_baseboard,
            )

        # 3b. Doorway Lintel Signboard (Z = 1.34m)
        sign_w = min(1.80, dw * 0.92)
        sign_h = 0.32

        if door_wall == "north":
            sign_pos = (door_coord[0], ymax + t / 2.0 + 0.02, lintel_z)
        elif door_wall == "south":
            sign_pos = (door_coord[0], ymin - t / 2.0 - 0.02, lintel_z)
        elif door_wall == "west":
            sign_pos = (xmin - t / 2.0 - 0.02, door_coord[1], lintel_z)
        else:
            sign_pos = (xmax + t / 2.0 + 0.02, door_coord[1], lintel_z)

        try:
            from environments.signage_generator import create_textured_signboard_mesh
            create_textured_signboard_mesh(
                self.stage,
                f"/World/Hospital/Rooms/SignMesh_{clean_id}",
                sign_pos,
                (sign_w, sign_h),
                room_id,
                facing=door_wall,
            )
        except Exception:
            pass

        # 3c. Elevated Floating 3D Room Nameboard (Z = 2.05m, tilted 28° towards camera)
        badge_w = floating_badge_w if floating_badge_w is not None else max(4.5, min(7.0, width_x * 0.40))
        badge_h = floating_badge_h if floating_badge_h is not None else max(1.2, min(1.6, depth_y * 0.16))
        badge_z = 2.05

        # Solid sleek obsidian backing plate (replaces plain colored box)
        VisualCuboid(
            prim_path=f"/World/Hospital/Rooms/FloatingBacking_{clean_id}",
            position=np.array([cx, cy, badge_z - 0.02]),
            size=1.0,
            scale=np.array([badge_w + 0.25, badge_h + 0.15, 0.03]),
            color=np.array([0.10, 0.14, 0.20]),  # Sleek obsidian architectural plate
        )

        # Overhead Angled Quad Mesh Nameboard with explicit UVs facing camera
        try:
            from environments.signage_generator import create_textured_signboard_mesh
            create_textured_signboard_mesh(
                self.stage,
                f"/World/Hospital/Rooms/FloatingMesh_{clean_id}",
                (cx, cy, badge_z),
                (badge_w, badge_h),
                room_id,
                facing="angled",
            )
        except Exception:
            pass

        # 3d. Department Corridor Approach Threshold Marker
        VisualCuboid(
            prim_path=f"/World/Hospital/Rooms/Threshold_{clean_id}",
            position=np.array([corridor_wp[0], corridor_wp[1], 0.015]),
            size=1.0,
            scale=np.array([1.4, 0.40, 0.01]) if door_wall in ("north", "south") else np.array([0.40, 1.4, 0.01]),
            color=color,
        )

        # 4. North Wall
        if door_wall == "north":
            seg1_len = max(0.0, (door_pos - dw / 2.0) - xmin)
            self._add_wall_box(xmin + seg1_len / 2.0, ymax, seg1_len, t, f"{clean_id}_N1")
            seg2_len = max(0.0, xmax - (door_pos + dw / 2.0))
            self._add_wall_box(xmax - seg2_len / 2.0, ymax, seg2_len, t, f"{clean_id}_N2")
        else:
            self._add_wall_box(cx, ymax, width_x, t, f"{clean_id}_N")

        # 5. South Wall
        if door_wall == "south":
            seg1_len = max(0.0, (door_pos - dw / 2.0) - xmin)
            self._add_wall_box(xmin + seg1_len / 2.0, ymin, seg1_len, t, f"{clean_id}_S1")
            seg2_len = max(0.0, xmax - (door_pos + dw / 2.0))
            self._add_wall_box(xmax - seg2_len / 2.0, ymin, seg2_len, t, f"{clean_id}_S2")
        else:
            self._add_wall_box(cx, ymin, width_x, t, f"{clean_id}_S")

        # 6. West Wall
        if door_wall == "west":
            seg1_len = max(0.0, (door_pos - dw / 2.0) - ymin)
            self._add_wall_box(xmin, ymin + seg1_len / 2.0, t, seg1_len, f"{clean_id}_W1")
            seg2_len = max(0.0, ymax - (door_pos + dw / 2.0))
            self._add_wall_box(xmin, ymax - seg2_len / 2.0, t, seg2_len, f"{clean_id}_W2")
        else:
            self._add_wall_box(xmin, cy, t, depth_y, f"{clean_id}_W")

        # 7. East Wall
        if door_wall == "east":
            seg1_len = max(0.0, (door_pos - dw / 2.0) - ymin)
            self._add_wall_box(xmax, ymin + seg1_len / 2.0, t, seg1_len, f"{clean_id}_E1")
            seg2_len = max(0.0, ymax - (door_pos + dw / 2.0))
            self._add_wall_box(xmax, ymax - seg2_len / 2.0, t, seg2_len, f"{clean_id}_E2")
        else:
            self._add_wall_box(xmax, cy, t, depth_y, f"{clean_id}_E")

        # Register semantic location for navigation (using validated clinical interaction goal if defined)
        try:
            from navigation.goal_validator import CLINICAL_ROOM_GOALS
        except (ImportError, ModuleNotFoundError):
            from isaac_sim_hospital.navigation.goal_validator import CLINICAL_ROOM_GOALS

        if room_id in CLINICAL_ROOM_GOALS:
            gx, gy, gz, _, _ = CLINICAL_ROOM_GOALS[room_id]
            room_pos = np.array([gx, gy, gz])
        else:
            room_pos = np.array([cx, cy, 0.0])

        self.semantic_locations[room_id] = {
            "pos": room_pos,
            "door": np.array([door_coord[0], door_coord[1], 0.0]),
            "corridor_wp": np.array([corridor_wp[0], corridor_wp[1], 0.0]),
            "bounds": (xmin, xmax, ymin, ymax),
            "label": name,
        }

    def build_all_rooms(self) -> None:
        """Construct the 28 grand clinical departments matching the expanded floor plan."""

        # ═════════════════════════════════════════════════════════════════════
        # TOP ROW (NORTH WING, Y: 21.8 to 37.2, depth 15.4m)
        # ═════════════════════════════════════════════════════════════════════

        # ── 1. Operating Theater 1 (OT-01, General Surgery, 8.0m x 15.4m) ───
        self._build_room(
            "OT-01", "Operating Theater 1",
            xmin=-43.0, xmax=-35.0, ymin=21.8, ymax=37.2,
            door_wall="south", door_pos=-39.0, door_width=2.0,
            color=self.colors["ot"],
            floating_badge_w=5.5, floating_badge_h=1.6,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/OT1_Table",
            position=np.array([-39.0, 30.0, 0.45]),
            size=1.0, scale=np.array([2.4, 1.1, 0.8]), color=self.color_bed_frame,
        )
        VisualCuboid(
            prim_path="/World/Hospital/Furniture/OT1_Light",
            position=np.array([-39.0, 30.0, 1.25]),
            size=1.0, scale=np.array([1.4, 1.4, 0.15]), color=np.array([0.95, 0.98, 1.0]),
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/OT1_Anesthesia",
            position=np.array([-41.5, 33.5, 0.60]),
            size=1.0, scale=np.array([0.8, 0.8, 1.2]), color=self.color_cabinet,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/OT1_ScrubCounter",
            position=np.array([-35.8, 30.0, 0.50]),
            size=1.0, scale=np.array([0.6, 4.0, 1.0]), color=self.color_counter,
        )

        # ── 2. Operating Theater 2 (OT-02, Robotic & Ortho Surgery, 8.0m x 15.4m)
        self._build_room(
            "OT-02", "Operating Theater 2",
            xmin=-34.0, xmax=-26.0, ymin=21.8, ymax=37.2,
            door_wall="south", door_pos=-30.0, door_width=2.0,
            color=self.colors["ot2"],
            floating_badge_w=5.5, floating_badge_h=1.6,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/OT2_RoboticTable",
            position=np.array([-30.0, 30.0, 0.45]),
            size=1.0, scale=np.array([2.4, 1.1, 0.8]), color=self.color_bed_frame,
        )
        VisualCuboid(
            prim_path="/World/Hospital/Furniture/OT2_SurgicalLight",
            position=np.array([-30.0, 30.0, 1.25]),
            size=1.0, scale=np.array([1.4, 1.4, 0.15]), color=np.array([0.85, 0.95, 1.0]),
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/OT2_RobotConsole",
            position=np.array([-27.2, 33.5, 0.60]),
            size=1.0, scale=np.array([1.1, 0.9, 1.2]), color=np.array([0.2, 0.35, 0.5]),
        )

        # ── 3. Radiology & CT/MRI Imaging (RAD-01, 13.0m x 15.4m) ───────────
        self._build_room(
            "RAD-01", "Radiology",
            xmin=-22.0, xmax=-9.0, ymin=21.8, ymax=37.2,
            door_wall="south", door_pos=-15.5, door_width=2.2,
            color=self.colors["icu"],
            floating_badge_w=6.0, floating_badge_h=1.8,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/RAD_ScannerGantry",
            position=np.array([-15.5, 31.5, 0.9]),
            size=1.0, scale=np.array([3.2, 1.6, 1.8]), color=np.array([0.95, 0.96, 0.98]),
        )
        VisualCuboid(
            prim_path="/World/Hospital/Furniture/RAD_ScannerBore",
            position=np.array([-15.5, 31.5, 0.9]),
            size=1.0, scale=np.array([1.6, 1.65, 1.2]), color=np.array([0.15, 0.18, 0.22]),
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/RAD_ImagingTable",
            position=np.array([-15.5, 27.5, 0.40]),
            size=1.0, scale=np.array([1.0, 3.0, 0.7]), color=self.color_bed_frame,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/RAD_Console",
            position=np.array([-20.0, 27.5, 0.50]),
            size=1.0, scale=np.array([1.0, 3.2, 1.0]), color=self.color_desk,
        )

        # ── 4. Pathology Laboratory (LAB-01, 13.0m x 15.4m) ─────────────────
        self._build_room(
            "LAB-01", "Laboratory",
            xmin=-7.0, xmax=6.0, ymin=21.8, ymax=37.2,
            door_wall="south", door_pos=-0.5, door_width=2.0,
            color=self.colors["lab"],
            floating_badge_w=6.0, floating_badge_h=1.8,
        )
        for i, lx in enumerate([-3.5, 2.5]):
            FixedCuboid(
                prim_path=f"/World/Hospital/Furniture/LAB_Island_{i}",
                position=np.array([lx, 30.0, 0.45]),
                size=1.0, scale=np.array([2.0, 5.5, 0.90]), color=self.color_cabinet,
            )
            FixedCuboid(
                prim_path=f"/World/Hospital/Furniture/LAB_Microscope_{i}",
                position=np.array([lx, 31.0, 0.95]),
                size=1.0, scale=np.array([0.4, 0.4, 0.45]), color=np.array([0.15, 0.15, 0.18]),
            )

        # ── 5. Central Pharmacy (PHM-01, 12.0m x 15.4m) ─────────────────────
        self._build_room(
            "PHM-01", "Pharmacy",
            xmin=8.0, xmax=20.0, ymin=21.8, ymax=37.2,
            door_wall="south", door_pos=14.0, door_width=2.0,
            color=self.colors["pharmacy"],
            floating_badge_w=5.5, floating_badge_h=1.8,
        )
        self._add_furniture_box(
            prim_path="/World/Hospital/Furniture/PHM_DispenseCounter",
            position=np.array([14.0, 24.5, 0.50]),
            scale=np.array([6.0, 1.0, 1.0]),
            color=self.color_counter,
            register_collision=True,
        )
        self._add_furniture_box(
            prim_path="/World/Hospital/Furniture/PHM_StorageRack",
            position=np.array([14.0, 34.5, 0.60]),
            scale=np.array([8.0, 0.8, 1.2]),
            color=self.color_cabinet,
            register_collision=True,
        )

        # ── 6. Medicine Storage & Vault (STR-01, 7.5m x 15.4m) ──────────────
        self._build_room(
            "STR-01", "Medicine Storage",
            xmin=22.0, xmax=29.5, ymin=21.8, ymax=37.2,
            door_wall="south", door_pos=25.75, door_width=1.8,
            color=self.colors["med_storage"],
            floating_badge_w=5.0, floating_badge_h=1.6,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/STR1_Vault1",
            position=np.array([25.75, 34.5, 0.60]),
            size=1.0, scale=np.array([5.5, 0.9, 1.2]), color=self.color_cabinet,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/STR1_Vault2",
            position=np.array([23.2, 28.5, 0.60]),
            size=1.0, scale=np.array([0.9, 4.5, 1.2]), color=self.color_cabinet,
        )

        # ── 7. Primary Robot Fleet Charging Station (CHG-01, Top-Right) ─────
        self._build_room(
            "CHG-01", "Robot Charging Station",
            xmin=31.5, xmax=43.0, ymin=21.8, ymax=37.2,
            door_wall="south", door_pos=37.25, door_width=2.4,
            color=self.colors["robot_dock"],
            floating_badge_w=6.5, floating_badge_h=1.8,
        )
        # 4 Dedicated Fleet Charging Docks (Docks 1 - 4)
        dock_coords = [
            (34.5, 33.0, "1", "Dock 1: Delivery AMR (R1)"),
            (39.5, 33.0, "2", "Dock 2: Support AMR (R4)"),
            (34.5, 26.5, "3", "Dock 3: Reserve AMR"),
            (39.5, 26.5, "4", "Dock 4: Reserve AMR"),
        ]
        for dx, dy, dnum, dlabel in dock_coords:
            VisualCuboid(
                prim_path=f"/World/Hospital/ChargingStation/Pad_{dnum}",
                position=np.array([dx, dy, 0.02]),
                size=1.0, scale=np.array([1.8, 1.8, 0.02]), color=np.array([0.0, 0.92, 1.0]),
            )
            VisualCuboid(
                prim_path=f"/World/Hospital/ChargingStation/PadBorder_{dnum}",
                position=np.array([dx, dy, 0.022]),
                size=1.0, scale=np.array([2.0, 2.0, 0.01]), color=np.array([1.0, 0.85, 0.1]),
            )
            FixedCuboid(
                prim_path=f"/World/Hospital/ChargingStation/Terminal_{dnum}",
                position=np.array([dx, dy + 0.85, 0.55]),
                size=1.0, scale=np.array([0.40, 0.30, 1.1]), color=self.color_cabinet,
            )
            VisualCuboid(
                prim_path=f"/World/Hospital/ChargingStation/LED_{dnum}",
                position=np.array([dx, dy + 0.85, 1.15]),
                size=1.0, scale=np.array([0.16, 0.16, 0.10]), color=np.array([0.1, 1.0, 0.3]),
            )
            self.semantic_locations[f"DOCK-0{dnum}"] = {
                "pos": np.array([dx, dy, 0.0]),
                "door": np.array([37.25, 21.8, 0.0]),
                "corridor_wp": np.array([37.25, 20.0, 0.0]),
                "bounds": (31.5, 43.0, 21.8, 37.2),
                "label": f"Charging Dock {dnum}",
            }

        # ═════════════════════════════════════════════════════════════════════
        # MIDDLE ROW (Y: 3.8 to 18.2, depth 14.4m)
        # ═════════════════════════════════════════════════════════════════════

        # ── 8. Intensive Care Unit (ICU-01, Mid-Left, 17.0m x 14.4m, 8 Beds) ─
        self._build_room(
            "ICU-01", "ICU",
            xmin=-43.0, xmax=-26.0, ymin=3.8, ymax=18.2,
            door_wall="east", door_pos=11.0, door_width=2.4,
            color=self.colors["icu"],
            floating_badge_w=6.5, floating_badge_h=1.8,
        )
        # 8 Monitored ICU Beds (4 on West wall, 4 on East wall)
        icu_bed_ys = [5.5, 9.0, 12.5, 16.0]
        for i, by in enumerate(icu_bed_ys):
            # West side bed (Beds 1 - 4)
            bnum_w = i + 1
            FixedCuboid(
                prim_path=f"/World/Hospital/Furniture/ICU_Bed_W_{i}",
                position=np.array([-39.5, by, 0.35]),
                size=1.0, scale=np.array([2.4, 1.0, 0.6]), color=self.color_bed_frame,
            )
            VisualCuboid(
                prim_path=f"/World/Hospital/Furniture/ICU_Matt_W_{i}",
                position=np.array([-39.5, by, 0.70]),
                size=1.0, scale=np.array([2.3, 0.9, 0.2]), color=self.color_mattress,
            )
            FixedCuboid(
                prim_path=f"/World/Hospital/Furniture/ICU_Mon_W_{i}",
                position=np.array([-42.0, by, 0.60]),
                size=1.0, scale=np.array([0.5, 0.5, 1.2]), color=self.color_cabinet,
            )
            VisualCuboid(
                prim_path=f"/World/Hospital/Furniture/ICU_ECG_W_{i}",
                position=np.array([-42.0, by, 1.15]),
                size=1.0, scale=np.array([0.52, 0.45, 0.30]), color=self.color_ecg_screen,
            )
            bed_code_w = f"ICU-BED-0{bnum_w}"
            self.semantic_locations[bed_code_w] = {
                "pos": np.array([-36.5, by, 0.0]),
                "door": np.array([-26.0, 11.0, 0.0]),
                "corridor_wp": np.array([-24.0, 11.0, 0.0]),
                "bounds": (-43.0, -26.0, 3.8, 18.2),
                "label": f"ICU Bed {bnum_w}",
            }
            self.semantic_locations[f"ICU Bed {bnum_w}"] = self.semantic_locations[bed_code_w]
            self.semantic_locations[f"icu bed {bnum_w}"] = self.semantic_locations[bed_code_w]
            self.semantic_locations[f"bed {bnum_w}"] = self.semantic_locations[bed_code_w]

            # East side bed (Beds 5 - 8)
            bnum_e = i + 5
            FixedCuboid(
                prim_path=f"/World/Hospital/Furniture/ICU_Bed_E_{i}",
                position=np.array([-29.5, by, 0.35]),
                size=1.0, scale=np.array([2.4, 1.0, 0.6]), color=self.color_bed_frame,
            )
            VisualCuboid(
                prim_path=f"/World/Hospital/Furniture/ICU_Matt_E_{i}",
                position=np.array([-29.5, by, 0.70]),
                size=1.0, scale=np.array([2.3, 0.9, 0.2]), color=self.color_mattress,
            )
            FixedCuboid(
                prim_path=f"/World/Hospital/Furniture/ICU_Mon_E_{i}",
                position=np.array([-27.0, by, 0.60]),
                size=1.0, scale=np.array([0.5, 0.5, 1.2]), color=self.color_cabinet,
            )
            VisualCuboid(
                prim_path=f"/World/Hospital/Furniture/ICU_ECG_E_{i}",
                position=np.array([-27.0, by, 1.15]),
                size=1.0, scale=np.array([0.52, 0.45, 0.30]), color=self.color_ecg_screen,
            )
            bed_code_e = f"ICU-BED-0{bnum_e}"
            self.semantic_locations[bed_code_e] = {
                "pos": np.array([-32.5, by, 0.0]),
                "door": np.array([-26.0, 11.0, 0.0]),
                "corridor_wp": np.array([-24.0, 11.0, 0.0]),
                "bounds": (-43.0, -26.0, 3.8, 18.2),
                "label": f"ICU Bed {bnum_e}",
            }
            self.semantic_locations[f"ICU Bed {bnum_e}"] = self.semantic_locations[bed_code_e]
            self.semantic_locations[f"icu bed {bnum_e}"] = self.semantic_locations[bed_code_e]
            self.semantic_locations[f"bed {bnum_e}"] = self.semantic_locations[bed_code_e]

        # ── 9. Blood Bank & Transfusion Laboratory (BLB-01, 10.5m x 14.4m) ──
        self._build_room(
            "BLB-01", "Blood Bank",
            xmin=-22.0, xmax=-11.5, ymin=3.8, ymax=18.2,
            door_wall="south", door_pos=-16.75, door_width=2.0,
            color=self.colors["blood_bank"],
            floating_badge_w=5.5, floating_badge_h=1.6,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/BLB_CoolerVault1",
            position=np.array([-19.5, 15.5, 0.65]),
            size=1.0, scale=np.array([3.5, 1.2, 1.3]), color=np.array([0.85, 0.88, 0.92]),
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/BLB_CoolerVault2",
            position=np.array([-14.0, 15.5, 0.65]),
            size=1.0, scale=np.array([3.5, 1.2, 1.3]), color=np.array([0.85, 0.88, 0.92]),
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/BLB_TestingCounter",
            position=np.array([-16.75, 9.5, 0.50]),
            size=1.0, scale=np.array([6.5, 1.2, 1.0]), color=self.color_counter,
        )

        # ── 10. Central Nurse Station (NST-01, 14.0m x 14.4m) ───────────────
        self._build_room(
            "NST-01", "Nurse Station",
            xmin=-10.5, xmax=3.5, ymin=3.8, ymax=18.2,
            door_wall="south", door_pos=-3.5, door_width=2.4,
            color=self.colors["nurse_station"],
            floating_badge_w=6.5, floating_badge_h=1.8,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/NST_DeskMain",
            position=np.array([-3.5, 11.0, 0.55]),
            size=1.0, scale=np.array([8.0, 1.4, 1.1]), color=self.color_counter,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/NST_DeskWingW",
            position=np.array([-7.5, 11.0, 0.55]),
            size=1.0, scale=np.array([0.8, 5.0, 1.1]), color=self.color_counter,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/NST_DeskWingE",
            position=np.array([0.5, 11.0, 0.55]),
            size=1.0, scale=np.array([0.8, 5.0, 1.1]), color=self.color_counter,
        )

        # ── 11. Consultation Clinic 1 (DOC-01, Cardiology, 8.5m x 14.4m) ────
        self._build_room(
            "DOC-01", "Consultation 1",
            xmin=5.5, xmax=14.0, ymin=3.8, ymax=18.2,
            door_wall="south", door_pos=9.75, door_width=1.8,
            color=self.colors["consult"],
            floating_badge_w=5.0, floating_badge_h=1.6,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/DOC1_Desk",
            position=np.array([9.75, 12.0, 0.45]),
            size=1.0, scale=np.array([2.4, 1.0, 0.85]), color=self.color_desk,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/DOC1_Couch",
            position=np.array([12.5, 12.0, 0.35]),
            size=1.0, scale=np.array([1.0, 2.4, 0.6]), color=self.color_bed_frame,
        )

        # ── 12. Consultation Clinic 2 (DOC-02, General Medicine, 8.5m x 14.4m)
        self._build_room(
            "DOC-02", "Consultation 2",
            xmin=16.0, xmax=24.5, ymin=3.8, ymax=18.2,
            door_wall="south", door_pos=20.25, door_width=1.8,
            color=self.colors["consult"],
            floating_badge_w=5.0, floating_badge_h=1.6,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/DOC2_Desk",
            position=np.array([20.25, 12.0, 0.45]),
            size=1.0, scale=np.array([2.4, 1.0, 0.85]), color=self.color_desk,
        )

        # ── 13. Isolation Room (ISO-01, 7.0m x 14.4m) ───────────────────────
        self._build_room(
            "ISO-01", "Isolation Room",
            xmin=26.5, xmax=33.5, ymin=3.8, ymax=18.2,
            door_wall="south", door_pos=30.0, door_width=1.8,
            color=self.colors["isolation"],
            floating_badge_w=4.8, floating_badge_h=1.6,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/ISO_Bed",
            position=np.array([30.0, 12.0, 0.35]),
            size=1.0, scale=np.array([2.4, 1.0, 0.6]), color=self.color_bed_frame,
        )
        VisualCuboid(
            prim_path="/World/Hospital/Furniture/ISO_Matt",
            position=np.array([30.0, 12.0, 0.70]),
            size=1.0, scale=np.array([2.3, 0.9, 0.2]), color=self.color_mattress,
        )

        # ── 14. Staff Room & Lounge (CAF-01 / STF-01, 7.5m x 14.4m) ─────────
        self._build_room(
            "CAF-01", "Staff Room",
            xmin=35.5, xmax=43.0, ymin=3.8, ymax=18.2,
            door_wall="south", door_pos=39.25, door_width=1.8,
            color=self.colors["cafeteria"],
            floating_badge_w=4.8, floating_badge_h=1.6,
        )
        for i, y_pos in enumerate([8.0, 14.0]):
            FixedCuboid(
                prim_path=f"/World/Hospital/Furniture/CAF_Table_{i}",
                position=np.array([39.25, y_pos, 0.40]),
                size=1.0, scale=np.array([3.0, 1.4, 0.8]), color=np.array([0.45, 0.32, 0.20]),
            )
        self.semantic_locations["STF-01"] = self.semantic_locations["CAF-01"]

        # ═════════════════════════════════════════════════════════════════════
        # LOWER-MID ROW (Y: -16.2 to 0.2, depth 16.4m)
        # ═════════════════════════════════════════════════════════════════════

        # ── 15. Emergency Trauma Resuscitation (EMR-01, 8.0m x 16.4m) ───────
        self._build_room(
            "EMR-01", "Emergency Trauma",
            xmin=-43.0, xmax=-35.0, ymin=-16.2, ymax=0.2,
            door_wall="north", door_pos=-39.0, door_width=2.4,
            color=self.colors["emergency"],
            floating_badge_w=5.5, floating_badge_h=1.8,
        )
        VisualCuboid(
            prim_path="/World/Hospital/Furniture/EMR_RedZone",
            position=np.array([-39.0, -8.0, 0.015]),
            size=1.0, scale=np.array([5.5, 5.5, 0.01]), color=self.colors["trauma"],
        )
        self.semantic_locations["TRM-01"] = self.semantic_locations["EMR-01"]

        # ── 16. Ambulance Triage & Staging Bay (AMB-01, 8.0m x 16.4m) ────────
        self._build_room(
            "AMB-01", "Ambulance Triage",
            xmin=-34.0, xmax=-26.0, ymin=-16.2, ymax=0.2,
            door_wall="north", door_pos=-30.0, door_width=2.4,
            color=self.colors["ambulance"],
            floating_badge_w=5.5, floating_badge_h=1.8,
        )
        self.semantic_locations["TRG-01"] = self.semantic_locations["AMB-01"]

        # ── 17. Main Reception Atrium (RCT-01, 22.0m x 9.2m Grand Atrium) ────
        self._build_room(
            "RCT-01", "Reception",
            xmin=-11.0, xmax=11.0, ymin=-9.0, ymax=0.2,
            door_wall="north", door_pos=0.0, door_width=4.0,
            color=self.colors["reception"],
            floating_badge_w=6.5, floating_badge_h=1.8,
        )

        # ── 18. Central Waiting Lounge (WAT-01, 20.0m x 7.0m) ────────────────
        self._build_room(
            "WAT-01", "Waiting Area",
            xmin=-10.0, xmax=10.0, ymin=-16.2, ymax=-9.2,
            door_wall="north", door_pos=0.0, door_width=6.0,
            color=self.colors["waiting"],
            floating_badge_w=5.5, floating_badge_h=1.6,
        )

        # ── 18b. Central Atrium Rotunda Diagonal Chamfer Walls & Lightwell ───
        # 4 diagonal 45° chamfer wall portals transforming the rectangular room into an octagonal rotunda
        rotunda_chamfers = [
            (-9.25, -1.15, 2.4, 0.28, "AtriumChamfer_NW"),
            (9.25, -1.15, 2.4, 0.28, "AtriumChamfer_NE"),
            (-9.25, -14.85, 2.4, 0.28, "AtriumChamfer_SW"),
            (9.25, -14.85, 2.4, 0.28, "AtriumChamfer_SE"),
        ]
        for rcx, rcy, rclx, rcly, rcname in rotunda_chamfers:
            self._add_wall_box(rcx, rcy, rclx, rcly, rcname)

        # ── 19. General Inpatient Ward (GW-01, 13.0m x 16.4m, 4 Beds) ────────
        self._build_room(
            "GW-01", "General Ward",
            xmin=16.0, xmax=29.0, ymin=-16.2, ymax=0.2,
            door_wall="west", door_pos=-8.0, door_width=2.4,
            color=self.colors["general_ward"],
            floating_badge_w=6.0, floating_badge_h=1.8,
        )
        # 4 Inpatient Beds
        gw_xs = [19.5, 25.5]
        for idx, x_pos in enumerate(gw_xs):
            for row_i, y_pos in enumerate([-4.0, -12.0]):
                bnum = idx * 2 + row_i + 1
                FixedCuboid(
                    prim_path=f"/World/Hospital/Furniture/GW_Bed_{bnum}",
                    position=np.array([x_pos, y_pos, 0.35]),
                    size=1.0, scale=np.array([1.1, 2.4, 0.6]), color=self.color_bed_frame,
                )
                VisualCuboid(
                    prim_path=f"/World/Hospital/Furniture/GW_Matt_{bnum}",
                    position=np.array([x_pos, y_pos, 0.70]),
                    size=1.0, scale=np.array([1.0, 2.3, 0.2]), color=self.color_mattress,
                )
                bed_code = f"GW-BED-0{bnum}"
                self.semantic_locations[bed_code] = {
                    "pos": np.array([x_pos, y_pos + (1.5 if row_i == 0 else -1.5), 0.0]),
                    "door": np.array([16.0, -8.0, 0.0]),
                    "corridor_wp": np.array([14.0, -8.0, 0.0]),
                    "bounds": (16.0, 29.0, -16.2, 0.2),
                    "label": f"Ward Bed {bnum}",
                }

        # ── 20. Dedicated Pediatric Inpatient Ward (PED-01, 12.5m x 16.4m) ────
        self._build_room(
            "PED-01", "Pediatric Ward",
            xmin=30.5, xmax=43.0, ymin=-16.2, ymax=0.2,
            door_wall="west", door_pos=-8.0, door_width=2.4,
            color=self.colors["pediatric"],
            floating_badge_w=6.0, floating_badge_h=1.8,
        )
        for i, py in enumerate([-4.0, -12.0]):
            FixedCuboid(
                prim_path=f"/World/Hospital/Furniture/PED_Crib_{i}",
                position=np.array([36.5, py, 0.35]),
                size=1.0, scale=np.array([1.8, 1.1, 0.7]), color=np.array([0.95, 0.80, 0.35]),
            )
            VisualCuboid(
                prim_path=f"/World/Hospital/Furniture/PED_Matt_{i}",
                position=np.array([36.5, py, 0.70]),
                size=1.0, scale=np.array([1.7, 1.0, 0.18]), color=self.color_mattress,
            )

        # ═════════════════════════════════════════════════════════════════════
        # BOTTOM ROW (SOUTH WING, Y: -37.2 to -19.8, depth 17.4m)
        # ═════════════════════════════════════════════════════════════════════

        # ── 21. Public Restrooms & Washrooms (WSH-01, 8.0m x 17.4m) ─────────
        self._build_room(
            "WSH-01", "Washroom",
            xmin=-43.0, xmax=-35.0, ymin=-37.2, ymax=-19.8,
            door_wall="north", door_pos=-39.0, door_width=2.0,
            color=self.colors["washroom"],
            floating_badge_w=5.0, floating_badge_h=1.6,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/WSH_Vanity",
            position=np.array([-39.0, -34.5, 0.45]),
            size=1.0, scale=np.array([5.5, 0.8, 0.85]), color=self.color_counter,
        )

        # ── 22. Bio-Sanitization & CSSD (SAN-01, 6.0m x 17.4m) ──────────────
        self._build_room(
            "SAN-01", "Bio-Sanitization",
            xmin=-34.0, xmax=-28.0, ymin=-37.2, ymax=-19.8,
            door_wall="north", door_pos=-31.0, door_width=1.8,
            color=self.colors["sanitization"],
            floating_badge_w=5.0, floating_badge_h=1.6,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/SAN_AutoclaveUnit",
            position=np.array([-31.0, -32.5, 0.65]),
            size=1.0, scale=np.array([3.5, 1.4, 1.3]), color=np.array([0.7, 0.75, 0.8]),
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/SAN_WashTrough",
            position=np.array([-31.0, -25.5, 0.50]),
            size=1.0, scale=np.array([4.0, 1.0, 1.0]), color=self.color_counter,
        )

        # ── 23. Biomedical Equipment Depot (STR-02, 13.0m x 17.4m) ──────────
        self._build_room(
            "STR-02", "Equipment Storage",
            xmin=-26.0, xmax=-13.0, ymin=-37.2, ymax=-19.8,
            door_wall="north", door_pos=-19.5, door_width=2.0,
            color=self.colors["storage"],
            floating_badge_w=5.5, floating_badge_h=1.6,
        )
        for i, wx in enumerate([-22.5, -19.5, -16.5]):
            FixedCuboid(
                prim_path=f"/World/Hospital/Furniture/STR_Wheelchair_{i}",
                position=np.array([wx, -28.5, 0.45]),
                size=1.0, scale=np.array([0.9, 0.9, 0.9]), color=np.array([0.2, 0.4, 0.7]),
            )

        # ── 24. Grand Hospital Entrance Foyer (ENT-01, 22.0m x 17.4m) ───────
        self._build_room(
            "ENT-01", "Main Entrance",
            xmin=-11.0, xmax=11.0, ymin=-37.2, ymax=-19.8,
            door_wall="north", door_pos=0.0, door_width=3.6,
            color=self.colors["entrance"],
            floating_badge_w=6.5, floating_badge_h=1.8,
        )
        VisualCuboid(
            prim_path="/World/Hospital/Furniture/ENT_WelcomeMat",
            position=np.array([0.0, -32.0, 0.015]),
            size=1.0, scale=np.array([7.0, 4.0, 0.01]), color=np.array([0.15, 0.40, 0.55]),
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/ENT_Kiosk1",
            position=np.array([-5.0, -28.0, 0.55]),
            size=1.0, scale=np.array([0.6, 0.6, 1.1]), color=self.color_cabinet,
        )
        FixedCuboid(
            prim_path="/World/Hospital/Furniture/ENT_Kiosk2",
            position=np.array([5.0, -28.0, 0.55]),
            size=1.0, scale=np.array([0.6, 0.6, 1.1]), color=self.color_cabinet,
        )

        # ── 25. Outpatient Department - OPD (OPD-01, 13.0m x 17.4m) ─────────
        self._build_room(
            "OPD-01", "OPD",
            xmin=16.0, xmax=29.0, ymin=-37.2, ymax=-19.8,
            door_wall="north", door_pos=22.5, door_width=2.4,
            color=self.colors["opd"],
            floating_badge_w=6.0, floating_badge_h=1.8,
        )
        # 2 Doctor Consultation Cubicles
        for idx, cx_pos in enumerate([19.5, 25.5]):
            c_num = idx + 1
            FixedCuboid(
                prim_path=f"/World/Hospital/Furniture/OPD_Desk_{idx}",
                position=np.array([cx_pos, -28.5, 0.45]),
                size=1.0, scale=np.array([2.2, 1.0, 0.85]), color=self.color_desk,
            )
            self.semantic_locations[f"OPD-0{c_num}"] = {
                "pos": np.array([cx_pos, -28.5, 0.0]),
                "door": np.array([22.5, -19.8, 0.0]),
                "corridor_wp": np.array([22.5, -18.0, 0.0]),
                "bounds": (16.0, 29.0, -37.2, -19.8),
                "label": f"OPD Cubicle {c_num}",
            }

        # ── 26. Deluxe Patient Suite 101 (PAT-01, 6.0m x 17.4m) ─────────────
        self._build_room(
            "PAT-01", "Patient Room 101",
            xmin=30.5, xmax=36.5, ymin=-37.2, ymax=-19.8,
            door_wall="north", door_pos=33.5, door_width=1.8,
            color=self.colors["patient_suite"],
            floating_badge_w=5.0, floating_badge_h=1.6,
        )
        self._add_furniture_box(
            prim_path="/World/Hospital/Furniture/PAT101_Bed",
            position=np.array([33.5, -30.0, 0.35]),
            scale=np.array([1.2, 2.4, 0.6]),
            color=self.color_bed_frame,
        )
        VisualCuboid(
            prim_path="/World/Hospital/Furniture/PAT101_Matt",
            position=np.array([33.5, -30.0, 0.70]),
            size=1.0, scale=np.array([1.1, 2.3, 0.2]), color=self.color_mattress,
        )

        # ── 27. Deluxe Patient Suite 102 (PAT-02, 5.5m x 17.4m) ─────────────
        self._build_room(
            "PAT-02", "Patient Room 102",
            xmin=37.5, xmax=43.0, ymin=-37.2, ymax=-19.8,
            door_wall="north", door_pos=40.25, door_width=1.8,
            color=self.colors["patient_suite"],
            floating_badge_w=5.0, floating_badge_h=1.6,
        )
        self._add_furniture_box(
            prim_path="/World/Hospital/Furniture/PAT102_Bed",
            position=np.array([40.25, -30.0, 0.35]),
            scale=np.array([1.2, 2.4, 0.6]),
            color=self.color_bed_frame,
        )
        VisualCuboid(
            prim_path="/World/Hospital/Furniture/PAT102_Matt",
            position=np.array([40.25, -30.0, 0.70]),
            size=1.0, scale=np.array([1.1, 2.3, 0.2]), color=self.color_mattress,
        )

        # ── 28. Inpatient Patient Room 103 (PAT-103, 4.5m x 7.7m) ───────────
        self._build_room(
            "PAT-103", "Patient Room 103",
            xmin=-26.0, xmax=-21.5, ymin=-16.2, ymax=-8.5,
            door_wall="east", door_pos=-12.35, door_width=1.8,
            color=self.colors["patient_suite"],
            floating_badge_w=4.2, floating_badge_h=1.4,
        )
        self._add_furniture_box(
            prim_path="/World/Hospital/Furniture/PAT103_Bed",
            position=np.array([-24.5, -12.35, 0.35]),
            scale=np.array([1.2, 2.4, 0.6]),
            color=self.color_bed_frame,
        )
        VisualCuboid(
            prim_path="/World/Hospital/Furniture/PAT103_Matt",
            position=np.array([-24.5, -12.35, 0.70]),
            size=1.0, scale=np.array([1.1, 2.3, 0.2]), color=self.color_mattress,
        )
        self._add_furniture_box(
            prim_path="/World/Hospital/Furniture/PAT103_SideTable",
            position=np.array([-25.2, -10.5, 0.40]),
            scale=np.array([0.6, 0.6, 0.7]),
            color=self.color_cabinet,
        )

        # ── 29. Inpatient Patient Room 104 (PAT-104, 4.5m x 7.7m) ───────────
        self._build_room(
            "PAT-104", "Patient Room 104",
            xmin=-26.0, xmax=-21.5, ymin=-7.5, ymax=0.2,
            door_wall="east", door_pos=-3.65, door_width=1.8,
            color=self.colors["patient_suite"],
            floating_badge_w=4.2, floating_badge_h=1.4,
        )
        self._add_furniture_box(
            prim_path="/World/Hospital/Furniture/PAT104_Bed",
            position=np.array([-24.5, -3.65, 0.35]),
            scale=np.array([1.2, 2.4, 0.6]),
            color=self.color_bed_frame,
        )
        VisualCuboid(
            prim_path="/World/Hospital/Furniture/PAT104_Matt",
            position=np.array([-24.5, -3.65, 0.70]),
            size=1.0, scale=np.array([1.1, 2.3, 0.2]), color=self.color_mattress,
        )
        self._add_furniture_box(
            prim_path="/World/Hospital/Furniture/PAT104_SideTable",
            position=np.array([-25.2, -1.8, 0.40]),
            scale=np.array([0.6, 0.6, 0.7]),
            color=self.color_cabinet,
        )

        # ── 30. Inpatient Patient Room 105 (PAT-105, 6.0m x 7.7m) ───────────
        self._build_room(
            "PAT-105", "Patient Room 105",
            xmin=-18.5, xmax=-12.5, ymin=-16.2, ymax=-8.5,
            door_wall="west", door_pos=-12.35, door_width=1.8,
            color=self.colors["patient_suite"],
            floating_badge_w=4.2, floating_badge_h=1.4,
        )
        self._add_furniture_box(
            prim_path="/World/Hospital/Furniture/PAT105_Bed",
            position=np.array([-14.5, -12.35, 0.35]),
            scale=np.array([1.2, 2.4, 0.6]),
            color=self.color_bed_frame,
        )
        VisualCuboid(
            prim_path="/World/Hospital/Furniture/PAT105_Matt",
            position=np.array([-14.5, -12.35, 0.70]),
            size=1.0, scale=np.array([1.1, 2.3, 0.2]), color=self.color_mattress,
        )
        self._add_furniture_box(
            prim_path="/World/Hospital/Furniture/PAT105_SideTable",
            position=np.array([-13.8, -10.5, 0.40]),
            scale=np.array([0.6, 0.6, 0.7]),
            color=self.color_cabinet,
        )

        # ── 31. Inpatient Patient Room 106 (PAT-106, 6.0m x 7.7m) ───────────
        self._build_room(
            "PAT-106", "Patient Room 106",
            xmin=-18.5, xmax=-12.5, ymin=-7.5, ymax=0.2,
            door_wall="west", door_pos=-3.65, door_width=1.8,
            color=self.colors["patient_suite"],
            floating_badge_w=4.2, floating_badge_h=1.4,
        )
        self._add_furniture_box(
            prim_path="/World/Hospital/Furniture/PAT106_Bed",
            position=np.array([-14.5, -3.65, 0.35]),
            scale=np.array([1.2, 2.4, 0.6]),
            color=self.color_bed_frame,
        )
        VisualCuboid(
            prim_path="/World/Hospital/Furniture/PAT106_Matt",
            position=np.array([-14.5, -3.65, 0.70]),
            size=1.0, scale=np.array([1.1, 2.3, 0.2]), color=self.color_mattress,
        )
        self._add_furniture_box(
            prim_path="/World/Hospital/Furniture/PAT106_SideTable",
            position=np.array([-13.8, -1.8, 0.40]),
            scale=np.array([0.6, 0.6, 0.7]),
            color=self.color_cabinet,
        )

        # ═════════════════════════════════════════════════════════════════════
        # Architectural Landmarks & Extended Semantic Stations
        # ═════════════════════════════════════════════════════════════════════
        # Dedicated Robot Medicine Pickup in Pharmacy (ROB-01)
        self.semantic_locations["ROB-01"] = {
            "pos": np.array([14.0, 23.2, 0.0]),
            "door": np.array([14.0, 21.8, 0.0]),
            "corridor_wp": np.array([14.0, 20.0, 0.0]),
            "bounds": (8.0, 20.0, 21.8, 37.2),
            "label": "Robot Medicine Pickup Station",
        }
        self.semantic_locations["ROBOT_PICKUP"] = self.semantic_locations["ROB-01"]
        self.semantic_locations["MEDICINE_PICKUP"] = self.semantic_locations["ROB-01"]

        # Central Atrium Elevator Lobby (ELV-01) & Staircase (STAIR-01)
        self.semantic_locations["ELV-01"] = {
            "pos": np.array([8.5, -5.5, 0.0]),
            "door": np.array([0.0, 0.2, 0.0]),
            "corridor_wp": np.array([0.0, 2.0, 0.0]),
            "bounds": (7.0, 11.0, -9.0, 0.2),
            "label": "Elevator Lobby Concourse",
        }
        self.semantic_locations["ELEVATOR"] = self.semantic_locations["ELV-01"]
        self.semantic_locations["ELEVATORS"] = self.semantic_locations["ELV-01"]

        self.semantic_locations["STAIR-01"] = {
            "pos": np.array([8.5, -13.5, 0.0]),
            "door": np.array([0.0, 0.2, 0.0]),
            "corridor_wp": np.array([0.0, 2.0, 0.0]),
            "bounds": (7.0, 11.0, -16.2, -9.2),
            "label": "Stairwell A Concourse",
        }
        self.semantic_locations["STAIRS"] = self.semantic_locations["STAIR-01"]
        self.semantic_locations["STAIRCASE"] = self.semantic_locations["STAIR-01"]

        # ICU Bed 3 alias (P003 Clinical Destination)
        if "ICU-BED-03" in self.semantic_locations:
            self.semantic_locations["ICU-03"] = self.semantic_locations["ICU-BED-03"]
            self.semantic_locations["ICU_BED_03"] = self.semantic_locations["ICU-BED-03"]
            self.semantic_locations["ICU-01-BED-03"] = self.semantic_locations["ICU-BED-03"]

        # ═════════════════════════════════════════════════════════════════════
        # Backward-Compatible Semantic Aliases
        # ═════════════════════════════════════════════════════════════════════
        self.semantic_locations["ICU"] = self.semantic_locations["ICU-01"]
        self.semantic_locations["EMERGENCY"] = self.semantic_locations["EMR-01"]
        self.semantic_locations["TRM-01"] = self.semantic_locations["EMR-01"]
        self.semantic_locations["PHARMACY"] = self.semantic_locations["PHM-01"]
        self.semantic_locations["LABORATORY"] = self.semantic_locations["LAB-01"]
        self.semantic_locations["RADIOLOGY"] = self.semantic_locations["RAD-01"]
        self.semantic_locations["OPERATING_THEATER"] = self.semantic_locations["OT-01"]
        self.semantic_locations["OT"] = self.semantic_locations["OT-01"]
        self.semantic_locations["GENERAL_WARD"] = self.semantic_locations["GW-01"]
        self.semantic_locations["RECEPTION"] = self.semantic_locations["RCT-01"]
        self.semantic_locations["WAITING_AREA"] = self.semantic_locations["WAT-01"]
        self.semantic_locations["ROBOT_CHARGING"] = self.semantic_locations["CHG-01"]
        self.semantic_locations["CHARGING_DOCK"] = self.semantic_locations["CHG-01"]
        self.semantic_locations["MAIN_ENTRANCE"] = self.semantic_locations["ENT-01"]
        self.semantic_locations["OPD"] = self.semantic_locations["OPD-01"]
        self.semantic_locations["NURSE_STATION"] = self.semantic_locations["NST-01"]
        self.semantic_locations["BLOOD_BANK"] = self.semantic_locations["BLB-01"]
        self.semantic_locations["PEDIATRICS"] = self.semantic_locations["PED-01"]
        self.semantic_locations["AMBULANCE"] = self.semantic_locations["AMB-01"]
        self.semantic_locations["SANITIZATION"] = self.semantic_locations["SAN-01"]
        self.semantic_locations["PAT-101"] = self.semantic_locations["PAT-01"]
        self.semantic_locations["PAT-102"] = self.semantic_locations["PAT-02"]

    def build_static_obstacles(self) -> None:
        """Register any standalone static obstacles, clinical furniture, and visual amenities."""
        try:
            from environments.hospital_furniture import HospitalFurniture
            furniture = HospitalFurniture(self.stage, collision_boxes=self.collision_boxes)
            furniture.build_all()
        except Exception as e:
            print(f"[HospitalEnv] Furniture build notice: {e}")


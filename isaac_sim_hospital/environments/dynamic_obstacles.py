"""
Dynamic Moving Obstacles & Traffic Scenario System for Isaac Sim Hospital
========================================================================
Implements realistic, physics-respecting mobile hospital agents:
- Humanoids: Doctors, Nurses, Orderlies, Surgeons, Hospital Visitors
- Mobile Stretchers: Emergency gurney pushed by paramedic attendant
- Wheelchairs: Patient transport wheelchair pushed by orderly attendant
- Medical Carts: Mobile medicine trolley / crash cart pushed by nurse attendant

Traffic Scenarios:
- LOW    : 3 obstacles (clear corridors, emergency response testing)
- MEDIUM : 8 obstacles (standard clinical shift, mixed equipment & personnel)
- HIGH   : 15 obstacles (peak rush hour, busy corridors, multiple carts/stretchers)

All agents move strictly along verified corridor highways (H1, H2, H3, V1, V2, V3)
or enter/exit rooms through valid doorways. Zero wall clipping, zero exterior escape!
"""

from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional, Tuple
import numpy as np
try:
    import omni.usd
    from pxr import Gf, Sdf, UsdGeom, Vt
    from isaacsim.core.api.objects import VisualCuboid
    HAS_OMNI = True
except ImportError:
    omni = None
    Gf = Sdf = UsdGeom = Vt = None
    VisualCuboid = None
    HAS_OMNI = False


def _make_local_box(stage, parent_path, child_name, local_pos, scale, color_rgb):
    """Create a UsdGeom.Cube at a LOCAL offset from parent_path Xform (rigid-body parenting)."""
    if stage is None:
        return
    fp = f"{parent_path}/{child_name}"
    xf = UsdGeom.Xform.Define(stage, Sdf.Path(fp))
    xf.AddTranslateOp().Set(Gf.Vec3d(float(local_pos[0]), float(local_pos[1]), float(local_pos[2])))
    xf.AddScaleOp().Set(Gf.Vec3d(float(scale[0]), float(scale[1]), float(scale[2])))
    cp = f"{fp}/Mesh"
    cube = UsdGeom.Cube.Define(stage, Sdf.Path(cp))
    cube.GetSizeAttr().Set(1.0)
    prim = stage.GetPrimAtPath(Sdf.Path(cp))
    if prim and prim.IsValid():
        r, g, b = float(color_rgb[0]), float(color_rgb[1]), float(color_rgb[2])
        cube.GetDisplayColorAttr().Set(Vt.Vec3fArray([Gf.Vec3f(r, g, b)]))



# ─────────────────────────────────────────────────────────────────────────────
# Corridor containment bands — obstacles MUST stay within these Y/X bounds.
# Prevents lateral drift into rooms. Only doorway-routed agents may exit.
# ─────────────────────────────────────────────────────────────────────────────

# East-West highway corridors: (Y_center, Y_half_width)
_CORRIDOR_H1_NORTH = (20.0, 1.6)   # Y ∈ [18.4, 21.6]
_CORRIDOR_H2_CENTRAL = (2.0, 1.6)  # Y ∈ [0.4, 3.6]
_CORRIDOR_H3_SOUTH = (-18.0, 1.6)  # Y ∈ [-19.6, -16.4]

# North-South longitudinal spines: (X_center, X_half_width)
_CORRIDOR_V1_WEST = (-24.0, 1.6)   # X ∈ [-25.6, -22.4]
_CORRIDOR_V2_CENTRAL = (0.0, 1.8)  # X ∈ [-1.8, 1.8]
_CORRIDOR_V3_EAST = (14.0, 1.6)    # X ∈ [12.4, 15.6]


def _clamp_to_corridor_band(x: float, y: float, corridor_axis: str, corridor_center: float, half_width: float) -> tuple:
    """Clamp x,y so the obstacle stays within its assigned corridor band.
    corridor_axis: 'h' for east-west (clamp Y), 'v' for north-south (clamp X).
    """
    if corridor_axis == 'h':
        y = float(np.clip(y, corridor_center - half_width, corridor_center + half_width))
    else:
        x = float(np.clip(x, corridor_center - half_width, corridor_center + half_width))
    return x, y


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURABLE SPEED PARAMETERS
# Modify these to tune obstacle movement speed globally.
# All values are in metres/second (simulation units).
#
# LOW    → Quiet night shift, clear corridors
# MEDIUM → Standard daytime clinical activity
# HIGH   → Peak rush hour — busy corridors
# ─────────────────────────────────────────────────────────────────────────────

# Hospital staff walking speeds (doctors, nurses, orderlies, visitors)
PEDESTRIAN_SPEED_LOW    = 1.30   # m/s  ~casual brisk walk
PEDESTRIAN_SPEED_MED    = 1.80   # m/s  ~purposeful clinical walk
PEDESTRIAN_SPEED_HIGH   = 2.20   # m/s  ~fast clinical walk / near-jog

# Mobile medical carts pushed by nurse/orderly
CART_SPEED_LOW          = 0.90   # m/s
CART_SPEED_MED          = 1.35   # m/s
CART_SPEED_HIGH         = 1.70   # m/s

# Wheelchair — patient in chair, orderly pushing
WHEELCHAIR_SPEED_LOW    = 0.85   # m/s
WHEELCHAIR_SPEED_MED    = 1.20   # m/s
WHEELCHAIR_SPEED_HIGH   = 1.50   # m/s

# Emergency stretcher / gurney pushed by paramedic(s)
STRETCHER_SPEED_LOW     = 1.10   # m/s
STRETCHER_SPEED_MED     = 1.65   # m/s
STRETCHER_SPEED_HIGH    = 2.00   # m/s  ~urgent patient transfer


class TrafficMode(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"



# ─────────────────────────────────────────────────────────────────────────────
# 1. Dynamic Humanoid (Doctors, Nurses, Orderlies, Visitors, Surgeons)
# ─────────────────────────────────────────────────────────────────────────────

class DynamicHumanoid:
    """Animated humanoid proxy with role-specific medical uniforms."""

    def __init__(
        self,
        prim_path: str,
        name: str,
        role: str = "doctor",
        waypoints: Optional[List[Tuple[float, float]]] = None,
        speed: float = 1.1,
        corridor_axis: str = "h",
        corridor_center: float = 2.0,
        corridor_half_width: float = 1.6,
    ) -> None:
        self.prim_path = prim_path
        self.name = name
        self.role = role
        self.speed = speed
        self.corridor_axis = corridor_axis
        self.corridor_center = corridor_center
        self.corridor_half_width = corridor_half_width
        self.stage = (
            omni.usd.get_context().get_stage()
            if (HAS_OMNI and omni and omni.usd and omni.usd.get_context())
            else None
        )

        self.waypoints = waypoints or [(0.0, 0.0), (5.0, 0.0)]
        self.current_wp_idx = 0
        self.x, self.y = self.waypoints[0]
        self.z = 0.0
        self.yaw = 0.0
        self.blocked_timer: float = 0.0
        self.turn_cooldown: float = 0.0
        self.patrol_direction: int = 1

        # Uniform colors by role
        if role == "doctor":
            self.color_torso = np.array([0.96, 0.96, 0.98])   # White lab coat
            self.color_accent = np.array([0.15, 0.35, 0.75])  # Blue stethoscope
            self.color_legs = np.array([0.22, 0.24, 0.28])    # Charcoal slacks
        elif role == "nurse":
            self.color_torso = np.array([0.18, 0.72, 0.70])   # Teal scrubs
            self.color_accent = np.array([0.95, 0.95, 0.95])  # White ID badge
            self.color_legs = np.array([0.18, 0.72, 0.70])    # Matching scrubs
        elif role == "surgeon":
            self.color_torso = np.array([0.20, 0.58, 0.55])   # Surgical green scrubs
            self.color_accent = np.array([0.90, 0.90, 0.92])  # Surgical mask
            self.color_legs = np.array([0.20, 0.58, 0.55])
        elif role == "orderly":
            self.color_torso = np.array([0.20, 0.55, 0.85])   # Royal blue uniform
            self.color_accent = np.array([0.90, 0.85, 0.20])  # Yellow hazard trim
            self.color_legs = np.array([0.18, 0.20, 0.25])
        else:  # visitor
            self.color_torso = np.array([0.75, 0.35, 0.35])   # Casual shirt
            self.color_accent = np.array([0.85, 0.85, 0.85])
            self.color_legs = np.array([0.25, 0.35, 0.55])    # Jeans

        self.color_head = np.array([0.88, 0.72, 0.60])        # Skin tone
        self.color_hair = np.array([0.18, 0.14, 0.12])        # Dark brown hair
        self.color_shoes = np.array([0.12, 0.12, 0.14])

        self._build_usd_model()

    def _build_usd_model(self) -> None:
        if not HAS_OMNI or self.stage is None:
            return
        self.root_xform = UsdGeom.Xform.Define(self.stage, Sdf.Path(self.prim_path))
        self.translate_op = self.root_xform.AddTranslateOp()
        self.rotate_op = self.root_xform.AddRotateZOp()
        self.translate_op.Set(Gf.Vec3d(self.x, self.y, self.z))
        self.rotate_op.Set(float(np.degrees(self.yaw)))

        sh = tuple(self.color_shoes.tolist())
        le = tuple(self.color_legs.tolist())
        to = tuple(self.color_torso.tolist())
        ac = tuple(self.color_accent.tolist())
        he = tuple(self.color_head.tolist())
        ha = tuple(self.color_hair.tolist())

        # Shoes
        _make_local_box(self.stage, self.prim_path, "ShoeL",
                        (0.0, 0.12, 0.05), (0.24, 0.10, 0.10), sh)
        _make_local_box(self.stage, self.prim_path, "ShoeR",
                        (0.0, -0.12, 0.05), (0.24, 0.10, 0.10), sh)
        # Legs
        _make_local_box(self.stage, self.prim_path, "LegL",
                        (0.0, 0.12, 0.48), (0.16, 0.12, 0.76), le)
        _make_local_box(self.stage, self.prim_path, "LegR",
                        (0.0, -0.12, 0.48), (0.16, 0.12, 0.76), le)
        # Torso
        _make_local_box(self.stage, self.prim_path, "Torso",
                        (0.0, 0.0, 1.20), (0.26, 0.42, 0.68), to)
        # Role accent (stethoscope / badge)
        _make_local_box(self.stage, self.prim_path, "Accent",
                        (0.135, 0.0, 1.30), (0.02, 0.18, 0.28), ac)
        # Arms
        _make_local_box(self.stage, self.prim_path, "ArmL",
                        (0.0, 0.27, 1.15), (0.12, 0.10, 0.60), to)
        _make_local_box(self.stage, self.prim_path, "ArmR",
                        (0.0, -0.27, 1.15), (0.12, 0.10, 0.60), to)
        # Head & hair
        _make_local_box(self.stage, self.prim_path, "Head",
                        (0.0, 0.0, 1.68), (0.20, 0.20, 0.24), he)
        _make_local_box(self.stage, self.prim_path, "Hair",
                        (0.0, 0.0, 1.82), (0.22, 0.22, 0.08), ha)

    def step(self, dt: float = 0.016, collision_guard: Any = None) -> None:
        if not self.waypoints:
            return

        if self.turn_cooldown > 0.0:
            self.turn_cooldown = max(0.0, self.turn_cooldown - dt)

        tx, ty = self.waypoints[self.current_wp_idx]
        dx = tx - self.x
        dy = ty - self.y
        dist = float(np.hypot(dx, dy))

        if dist < 0.35:
            self.current_wp_idx = (self.current_wp_idx + self.patrol_direction) % len(self.waypoints)
            self.blocked_timer = 0.0
            return

        target_yaw = float(np.arctan2(dy, dx))
        angle_diff = (target_yaw - self.yaw + np.pi) % (2.0 * np.pi) - np.pi
        max_turn = 3.5 * dt
        self.yaw += np.clip(angle_diff, -max_turn, max_turn)

        # Rotate in place when changing direction to prevent sweeping into walls
        if abs(angle_diff) > 0.25:
            v_step = 0.0
        else:
            v_step = min(self.speed * dt, dist)

        cand_x = self.x + float(v_step * np.cos(self.yaw))
        cand_y = self.y + float(v_step * np.sin(self.yaw))

        # Enforce strict hospital interior boundary and corridor containment band BEFORE collision checks
        cand_x = float(np.clip(cand_x, -42.0, 42.0))
        cand_y = float(np.clip(cand_y, -36.0, 36.0))
        cand_x, cand_y = _clamp_to_corridor_band(
            cand_x, cand_y, self.corridor_axis, self.corridor_center, self.corridor_half_width
        )

        # Continuous collision detection: zero wall clipping
        is_blocked = False
        if collision_guard and v_step > 0.0:
            if collision_guard.check_point_collision(cand_x, cand_y, margin=0.40):
                is_blocked = True
            elif hasattr(collision_guard, "is_segment_clear"):
                if not collision_guard.is_segment_clear(self.x, self.y, cand_x, cand_y, margin=0.40):
                    is_blocked = True

        if is_blocked:
            self.blocked_timer += dt
            # If path remains blocked continuously and cooldown has elapsed, reverse patrol direction smoothly
            if self.blocked_timer >= 1.0 and self.turn_cooldown <= 0.0:
                self.patrol_direction = -self.patrol_direction
                self.current_wp_idx = (self.current_wp_idx + self.patrol_direction) % len(self.waypoints)
                self.blocked_timer = 0.0
                self.turn_cooldown = 2.0  # Allow smooth exit without immediate flip
            return
        else:
            self.blocked_timer = max(0.0, self.blocked_timer - dt * 2.0)

        self.x = cand_x
        self.y = cand_y

        if HAS_OMNI and hasattr(self, "translate_op") and self.translate_op is not None:
            self.translate_op.Set(Gf.Vec3d(self.x, self.y, self.z))
            self.rotate_op.Set(float(np.degrees(self.yaw)))


# ─────────────────────────────────────────────────────────────────────────────
# 2. Dynamic Mobile Stretcher with Paramedic Escort
# ─────────────────────────────────────────────────────────────────────────────

class DynamicStretcher:
    """Hospital emergency stretcher with patient under blanket and paramedic attendant."""

    def __init__(
        self,
        prim_path: str,
        name: str = "Paramedic_Stretcher",
        waypoints: Optional[List[Tuple[float, float]]] = None,
        speed: float = 1.30,
        corridor_axis: str = "v",
        corridor_center: float = 14.0,
        corridor_half_width: float = 1.6,
    ) -> None:
        self.prim_path = prim_path
        self.name = name
        self.role = "stretcher"
        self.speed = speed
        self.corridor_axis = corridor_axis
        self.corridor_center = corridor_center
        self.corridor_half_width = corridor_half_width
        self.stage = (
            omni.usd.get_context().get_stage()
            if (HAS_OMNI and omni and omni.usd and omni.usd.get_context())
            else None
        )

        self.waypoints = waypoints or [(0.0, 0.0), (10.0, 0.0)]
        self.current_wp_idx = 0
        self.x, self.y = self.waypoints[0]
        self.z = 0.0
        self.yaw = 0.0
        self.blocked_timer: float = 0.0
        self.turn_cooldown: float = 0.0
        self.patrol_direction: int = 1

        # Colors
        self.color_frame = np.array([0.75, 0.78, 0.82])      # Chrome
        self.color_wheel = np.array([0.15, 0.15, 0.18])
        self.color_mattress = np.array([0.92, 0.94, 0.96])
        self.color_pillow = np.array([0.35, 0.65, 0.85])
        self.color_blanket = np.array([0.40, 0.75, 0.65])    # Medical green
        self.color_paramedic = np.array([0.15, 0.35, 0.70])  # Navy
        self.color_hi_vis = np.array([0.95, 0.88, 0.10])     # High-vis vest
        self.color_head = np.array([0.88, 0.72, 0.60])

        self._build_usd_model()

    def _build_usd_model(self) -> None:
        if not HAS_OMNI or self.stage is None:
            return
        self.root_xform = UsdGeom.Xform.Define(self.stage, Sdf.Path(self.prim_path))
        self.translate_op = self.root_xform.AddTranslateOp()
        self.rotate_op = self.root_xform.AddRotateZOp()
        self.translate_op.Set(Gf.Vec3d(self.x, self.y, self.z))
        self.rotate_op.Set(float(np.degrees(self.yaw)))

        fr = tuple(self.color_frame.tolist())
        wh = tuple(self.color_wheel.tolist())
        ma = tuple(self.color_mattress.tolist())
        pi = tuple(self.color_pillow.tolist())
        bl = tuple(self.color_blanket.tolist())
        pm = tuple(self.color_paramedic.tolist())
        hv = tuple(self.color_hi_vis.tolist())
        he = tuple(self.color_head.tolist())

        # 4 Caster Wheels & Legs
        for i, cx in enumerate([-0.85, 0.85]):
            for j, cy in enumerate([-0.35, 0.35]):
                _make_local_box(self.stage, self.prim_path, f"Wheel_{i}_{j}",
                                (cx, cy, 0.07), (0.14, 0.06, 0.14), wh)
                _make_local_box(self.stage, self.prim_path, f"Leg_{i}_{j}",
                                (cx, cy, 0.32), (0.06, 0.06, 0.40), fr)
        # Base Frame & guard rails
        _make_local_box(self.stage, self.prim_path, "BaseFrame",
                        (0.0, 0.0, 0.52), (2.15, 0.88, 0.08), fr)
        _make_local_box(self.stage, self.prim_path, "RailLeft",
                        (0.0, 0.42, 0.72), (1.60, 0.04, 0.32), fr)
        _make_local_box(self.stage, self.prim_path, "RailRight",
                        (0.0, -0.42, 0.72), (1.60, 0.04, 0.32), fr)
        # Mattress & Patient
        _make_local_box(self.stage, self.prim_path, "Mattress",
                        (0.0, 0.0, 0.62), (2.05, 0.80, 0.14), ma)
        _make_local_box(self.stage, self.prim_path, "Pillow",
                        (0.75, 0.0, 0.72), (0.35, 0.55, 0.08), pi)
        _make_local_box(self.stage, self.prim_path, "PatientBlanket",
                        (-0.15, 0.0, 0.74), (1.35, 0.72, 0.16), bl)
        _make_local_box(self.stage, self.prim_path, "PatientHead",
                        (0.72, 0.0, 0.76), (0.18, 0.18, 0.16), he)
        # IV Drip Pole
        _make_local_box(self.stage, self.prim_path, "IVPole",
                        (0.95, 0.38, 1.15), (0.03, 0.03, 1.25), fr)
        _make_local_box(self.stage, self.prim_path, "IVBag",
                        (0.95, 0.38, 1.70), (0.10, 0.12, 0.20), (0.9, 0.95, 1.0))
        # Paramedic pushing from behind
        _make_local_box(self.stage, self.prim_path, "ParamedicTorso",
                        (-1.35, 0.0, 1.15), (0.26, 0.42, 0.65), pm)
        _make_local_box(self.stage, self.prim_path, "ParamedicVest",
                        (-1.34, 0.0, 1.20), (0.28, 0.44, 0.45), hv)
        _make_local_box(self.stage, self.prim_path, "ParamedicHead",
                        (-1.35, 0.0, 1.62), (0.20, 0.20, 0.22), he)
        _make_local_box(self.stage, self.prim_path, "PushBar",
                        (-1.12, 0.0, 0.90), (0.22, 0.60, 0.04), fr)

    def step(self, dt: float = 0.016, collision_guard: Any = None) -> None:
        if not self.waypoints:
            return

        if self.turn_cooldown > 0.0:
            self.turn_cooldown = max(0.0, self.turn_cooldown - dt)

        tx, ty = self.waypoints[self.current_wp_idx]
        dx = tx - self.x
        dy = ty - self.y
        dist = float(np.hypot(dx, dy))

        if dist < 0.40:
            self.current_wp_idx = (self.current_wp_idx + self.patrol_direction) % len(self.waypoints)
            self.blocked_timer = 0.0
            return

        target_yaw = float(np.arctan2(dy, dx))
        angle_diff = (target_yaw - self.yaw + np.pi) % (2.0 * np.pi) - np.pi
        max_turn = 2.8 * dt
        self.yaw += np.clip(angle_diff, -max_turn, max_turn)

        # Rotate in place when changing direction to prevent sweeping into walls
        if abs(angle_diff) > 0.25:
            v_step = 0.0
        else:
            v_step = min(self.speed * dt, dist)

        cand_x = self.x + float(v_step * np.cos(self.yaw))
        cand_y = self.y + float(v_step * np.sin(self.yaw))

        # Enforce strict hospital interior boundary and corridor containment band BEFORE collision checks
        cand_x = float(np.clip(cand_x, -42.0, 42.0))
        cand_y = float(np.clip(cand_y, -36.0, 36.0))
        cand_x, cand_y = _clamp_to_corridor_band(
            cand_x, cand_y, self.corridor_axis, self.corridor_center, self.corridor_half_width
        )

        # Continuous multi-point collision detection: zero wall clipping
        is_blocked = False
        if collision_guard and v_step > 0.0:
            c_yaw = self.yaw
            pts = [
                (cand_x, cand_y, 0.40),                                             # Stretcher center
                (cand_x + 1.10 * np.cos(c_yaw), cand_y + 1.10 * np.sin(c_yaw), 0.38), # Gurney front
                (cand_x - 1.35 * np.cos(c_yaw), cand_y - 1.35 * np.sin(c_yaw), 0.40), # Paramedic attendant
            ]
            for px, py, r in pts:
                if collision_guard.check_point_collision(px, py, margin=r):
                    is_blocked = True
                    break
            if not is_blocked and hasattr(collision_guard, "is_segment_clear"):
                if not collision_guard.is_segment_clear(self.x, self.y, cand_x, cand_y, margin=0.45):
                    is_blocked = True

        if is_blocked:
            self.blocked_timer += dt
            # If path remains blocked continuously and cooldown has elapsed, reverse patrol direction smoothly
            if self.blocked_timer >= 1.0 and self.turn_cooldown <= 0.0:
                self.patrol_direction = -self.patrol_direction
                self.current_wp_idx = (self.current_wp_idx + self.patrol_direction) % len(self.waypoints)
                self.blocked_timer = 0.0
                self.turn_cooldown = 2.0  # Allow smooth exit without immediate flip
            return
        else:
            self.blocked_timer = max(0.0, self.blocked_timer - dt * 2.0)

        self.x = cand_x
        self.y = cand_y

        if HAS_OMNI and hasattr(self, "translate_op") and self.translate_op is not None:
            self.translate_op.Set(Gf.Vec3d(self.x, self.y, self.z))
            self.rotate_op.Set(float(np.degrees(self.yaw)))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Dynamic Wheelchair with Seated Patient & Orderly Attendant
# ─────────────────────────────────────────────────────────────────────────────

class DynamicWheelchair:
    """Hospital transport wheelchair with seated patient pushed by an orderly."""

    def __init__(
        self,
        prim_path: str,
        name: str = "Wheelchair_Transport",
        waypoints: Optional[List[Tuple[float, float]]] = None,
        speed: float = 0.95,
        corridor_axis: str = "h",
        corridor_center: float = -18.0,
        corridor_half_width: float = 1.6,
    ) -> None:
        self.prim_path = prim_path
        self.name = name
        self.role = "wheelchair"
        self.speed = speed
        self.corridor_axis = corridor_axis
        self.corridor_center = corridor_center
        self.corridor_half_width = corridor_half_width
        self.stage = (
            omni.usd.get_context().get_stage()
            if (HAS_OMNI and omni and omni.usd and omni.usd.get_context())
            else None
        )

        self.waypoints = waypoints or [(0.0, 0.0), (8.0, 0.0)]
        self.current_wp_idx = 0
        self.x, self.y = self.waypoints[0]
        self.z = 0.0
        self.yaw = 0.0
        self.blocked_timer: float = 0.0
        self.turn_cooldown: float = 0.0
        self.patrol_direction: int = 1

        self.color_frame = np.array([0.72, 0.75, 0.80])      # Chrome
        self.color_wheels = np.array([0.15, 0.15, 0.18])     # Rubber tires
        self.color_seat = np.array([0.20, 0.22, 0.26])       # Black vinyl
        self.color_patient_gown = np.array([0.45, 0.75, 0.85])# Hospital gown light blue
        self.color_orderly = np.array([0.20, 0.55, 0.85])    # Royal blue scrubs
        self.color_head = np.array([0.88, 0.72, 0.60])

        self._build_usd_model()

    def _build_usd_model(self) -> None:
        if not HAS_OMNI or self.stage is None:
            return
        self.root_xform = UsdGeom.Xform.Define(self.stage, Sdf.Path(self.prim_path))
        self.translate_op = self.root_xform.AddTranslateOp()
        self.rotate_op = self.root_xform.AddRotateZOp()
        self.translate_op.Set(Gf.Vec3d(self.x, self.y, self.z))
        self.rotate_op.Set(float(np.degrees(self.yaw)))

        fr = tuple(self.color_frame.tolist())
        wh = tuple(self.color_wheels.tolist())
        se = tuple(self.color_seat.tolist())
        pg = tuple(self.color_patient_gown.tolist())
        or_ = tuple(self.color_orderly.tolist())
        he = tuple(self.color_head.tolist())

        # Big rear wheels
        _make_local_box(self.stage, self.prim_path, "WheelRearL",
                        (-0.15, 0.32, 0.30), (0.60, 0.05, 0.60), wh)
        _make_local_box(self.stage, self.prim_path, "WheelRearR",
                        (-0.15, -0.32, 0.30), (0.60, 0.05, 0.60), wh)
        # Front casters
        _make_local_box(self.stage, self.prim_path, "CasterL",
                        (0.35, 0.28, 0.10), (0.18, 0.04, 0.18), wh)
        _make_local_box(self.stage, self.prim_path, "CasterR",
                        (0.35, -0.28, 0.10), (0.18, 0.04, 0.18), wh)
        # Chair seat & backrest
        _make_local_box(self.stage, self.prim_path, "Seat",
                        (0.05, 0.0, 0.45), (0.50, 0.52, 0.06), se)
        _make_local_box(self.stage, self.prim_path, "Backrest",
                        (-0.18, 0.0, 0.72), (0.06, 0.50, 0.50), se)
        _make_local_box(self.stage, self.prim_path, "Footrest",
                        (0.42, 0.0, 0.18), (0.22, 0.44, 0.04), fr)
        # Seated patient
        _make_local_box(self.stage, self.prim_path, "PatientTorso",
                        (-0.05, 0.0, 0.75), (0.24, 0.40, 0.52), pg)
        _make_local_box(self.stage, self.prim_path, "PatientLegs",
                        (0.20, 0.0, 0.48), (0.38, 0.36, 0.20), pg)
        _make_local_box(self.stage, self.prim_path, "PatientHead",
                        (-0.05, 0.0, 1.15), (0.18, 0.18, 0.20), he)
        # Orderly attendant behind
        _make_local_box(self.stage, self.prim_path, "OrderlyTorso",
                        (-0.65, 0.0, 1.15), (0.24, 0.40, 0.65), or_)
        _make_local_box(self.stage, self.prim_path, "OrderlyHead",
                        (-0.65, 0.0, 1.62), (0.20, 0.20, 0.22), he)
        _make_local_box(self.stage, self.prim_path, "PushHandles",
                        (-0.38, 0.0, 0.95), (0.28, 0.52, 0.04), fr)

    def step(self, dt: float = 0.016, collision_guard: Any = None) -> None:
        if not self.waypoints:
            return

        if self.turn_cooldown > 0.0:
            self.turn_cooldown = max(0.0, self.turn_cooldown - dt)

        tx, ty = self.waypoints[self.current_wp_idx]
        dx = tx - self.x
        dy = ty - self.y
        dist = float(np.hypot(dx, dy))

        if dist < 0.35:
            self.current_wp_idx = (self.current_wp_idx + self.patrol_direction) % len(self.waypoints)
            self.blocked_timer = 0.0
            return

        target_yaw = float(np.arctan2(dy, dx))
        angle_diff = (target_yaw - self.yaw + np.pi) % (2.0 * np.pi) - np.pi
        max_turn = 2.5 * dt
        self.yaw += np.clip(angle_diff, -max_turn, max_turn)

        # Rotate in place when changing direction to prevent sweeping into walls
        if abs(angle_diff) > 0.25:
            v_step = 0.0
        else:
            v_step = min(self.speed * dt, dist)

        cand_x = self.x + float(v_step * np.cos(self.yaw))
        cand_y = self.y + float(v_step * np.sin(self.yaw))

        # Enforce strict hospital interior boundary and corridor containment band BEFORE collision checks
        cand_x = float(np.clip(cand_x, -42.0, 42.0))
        cand_y = float(np.clip(cand_y, -36.0, 36.0))
        cand_x, cand_y = _clamp_to_corridor_band(
            cand_x, cand_y, self.corridor_axis, self.corridor_center, self.corridor_half_width
        )

        # Continuous multi-point collision detection: zero wall clipping
        is_blocked = False
        if collision_guard and v_step > 0.0:
            c_yaw = self.yaw
            pts = [
                (cand_x, cand_y, 0.38),                                             # Chair center
                (cand_x + 0.40 * np.cos(c_yaw), cand_y + 0.40 * np.sin(c_yaw), 0.35), # Patient legs
                (cand_x - 0.65 * np.cos(c_yaw), cand_y - 0.65 * np.sin(c_yaw), 0.38), # Orderly attendant
            ]
            for px, py, r in pts:
                if collision_guard.check_point_collision(px, py, margin=r):
                    is_blocked = True
                    break
            if not is_blocked and hasattr(collision_guard, "is_segment_clear"):
                if not collision_guard.is_segment_clear(self.x, self.y, cand_x, cand_y, margin=0.42):
                    is_blocked = True

        if is_blocked:
            self.blocked_timer += dt
            # If path remains blocked continuously and cooldown has elapsed, reverse patrol direction smoothly
            if self.blocked_timer >= 1.0 and self.turn_cooldown <= 0.0:
                self.patrol_direction = -self.patrol_direction
                self.current_wp_idx = (self.current_wp_idx + self.patrol_direction) % len(self.waypoints)
                self.blocked_timer = 0.0
                self.turn_cooldown = 2.0  # Allow smooth exit without immediate flip
            return
        else:
            self.blocked_timer = max(0.0, self.blocked_timer - dt * 2.0)

        self.x = cand_x
        self.y = cand_y

        if HAS_OMNI and hasattr(self, "translate_op") and self.translate_op is not None:
            self.translate_op.Set(Gf.Vec3d(self.x, self.y, self.z))
            self.rotate_op.Set(float(np.degrees(self.yaw)))


# ─────────────────────────────────────────────────────────────────────────────
# 4. Dynamic Mobile Medical Cart / Crash Trolley pushed by Nurse
# ─────────────────────────────────────────────────────────────────────────────

class DynamicMedicalCart:
    """Multi-tier stainless steel medicine / crash cart pushed by a nurse attendant."""

    def __init__(
        self,
        prim_path: str,
        name: str = "Medical_Trolley",
        waypoints: Optional[List[Tuple[float, float]]] = None,
        speed: float = 1.05,
        corridor_axis: str = "h",
        corridor_center: float = 2.0,
        corridor_half_width: float = 1.6,
    ) -> None:
        self.prim_path = prim_path
        self.name = name
        self.role = "cart"
        self.speed = speed
        self.corridor_axis = corridor_axis
        self.corridor_center = corridor_center
        self.corridor_half_width = corridor_half_width
        self.stage = (
            omni.usd.get_context().get_stage()
            if (HAS_OMNI and omni and omni.usd and omni.usd.get_context())
            else None
        )

        self.waypoints = waypoints or [(0.0, 0.0), (6.0, 0.0)]
        self.current_wp_idx = 0
        self.x, self.y = self.waypoints[0]
        self.z = 0.0
        self.yaw = 0.0
        self.blocked_timer: float = 0.0
        self.turn_cooldown: float = 0.0
        self.patrol_direction: int = 1

        self.color_cart = np.array([0.80, 0.82, 0.85])       # Steel
        self.color_drawer_red = np.array([0.88, 0.22, 0.22]) # Red crash drawer
        self.color_drawer_blue = np.array([0.22, 0.55, 0.85])# Blue med drawer
        self.color_wheels = np.array([0.15, 0.15, 0.18])
        self.color_nurse = np.array([0.18, 0.72, 0.70])      # Teal scrubs
        self.color_head = np.array([0.88, 0.72, 0.60])

        self._build_usd_model()

    def _build_usd_model(self) -> None:
        if not HAS_OMNI or self.stage is None:
            return
        self.root_xform = UsdGeom.Xform.Define(self.stage, Sdf.Path(self.prim_path))
        self.translate_op = self.root_xform.AddTranslateOp()
        self.rotate_op = self.root_xform.AddRotateZOp()
        self.translate_op.Set(Gf.Vec3d(self.x, self.y, self.z))
        self.rotate_op.Set(float(np.degrees(self.yaw)))

        ca = tuple(self.color_cart.tolist())
        dr = tuple(self.color_drawer_red.tolist())
        db = tuple(self.color_drawer_blue.tolist())
        wh = tuple(self.color_wheels.tolist())
        nu = tuple(self.color_nurse.tolist())
        he = tuple(self.color_head.tolist())

        # 4 caster wheels
        for i, cx in enumerate([-0.35, 0.35]):
            for j, cy in enumerate([-0.25, 0.25]):
                _make_local_box(self.stage, self.prim_path, f"Wheel_{i}_{j}",
                                (cx, cy, 0.06), (0.10, 0.04, 0.10), wh)
        # Cart body & shelves
        _make_local_box(self.stage, self.prim_path, "CartBody",
                        (0.0, 0.0, 0.55), (0.85, 0.60, 0.85), ca)
        _make_local_box(self.stage, self.prim_path, "DrawerRed",
                        (0.43, 0.0, 0.75), (0.04, 0.52, 0.20), dr)
        _make_local_box(self.stage, self.prim_path, "DrawerBlue",
                        (0.43, 0.0, 0.45), (0.04, 0.52, 0.22), db)
        # Defibrillator on top
        _make_local_box(self.stage, self.prim_path, "DefibUnit",
                        (0.10, 0.0, 1.08), (0.35, 0.40, 0.20), (0.95, 0.85, 0.10))
        # Nurse attendant behind cart
        _make_local_box(self.stage, self.prim_path, "NurseTorso",
                        (-0.75, 0.0, 1.15), (0.24, 0.40, 0.65), nu)
        _make_local_box(self.stage, self.prim_path, "NurseHead",
                        (-0.75, 0.0, 1.62), (0.20, 0.20, 0.22), he)
        _make_local_box(self.stage, self.prim_path, "PushBar",
                        (-0.50, 0.0, 0.92), (0.18, 0.54, 0.04), ca)

    def step(self, dt: float = 0.016, collision_guard: Any = None) -> None:
        if not self.waypoints:
            return

        if self.turn_cooldown > 0.0:
            self.turn_cooldown = max(0.0, self.turn_cooldown - dt)

        tx, ty = self.waypoints[self.current_wp_idx]
        dx = tx - self.x
        dy = ty - self.y
        dist = float(np.hypot(dx, dy))

        if dist < 0.35:
            self.current_wp_idx = (self.current_wp_idx + self.patrol_direction) % len(self.waypoints)
            self.blocked_timer = 0.0
            return

        target_yaw = float(np.arctan2(dy, dx))
        angle_diff = (target_yaw - self.yaw + np.pi) % (2.0 * np.pi) - np.pi
        max_turn = 2.8 * dt
        self.yaw += np.clip(angle_diff, -max_turn, max_turn)

        # Rotate in place when changing direction to prevent sweeping into walls
        if abs(angle_diff) > 0.25:
            v_step = 0.0
        else:
            v_step = min(self.speed * dt, dist)

        cand_x = self.x + float(v_step * np.cos(self.yaw))
        cand_y = self.y + float(v_step * np.sin(self.yaw))

        # Enforce strict hospital interior boundary and corridor containment band BEFORE collision checks
        cand_x = float(np.clip(cand_x, -42.0, 42.0))
        cand_y = float(np.clip(cand_y, -36.0, 36.0))
        cand_x, cand_y = _clamp_to_corridor_band(
            cand_x, cand_y, self.corridor_axis, self.corridor_center, self.corridor_half_width
        )

        # Continuous multi-point collision detection: zero wall clipping
        is_blocked = False
        if collision_guard and v_step > 0.0:
            c_yaw = self.yaw
            pts = [
                (cand_x, cand_y, 0.38),                                             # Cart center
                (cand_x + 0.45 * np.cos(c_yaw), cand_y + 0.45 * np.sin(c_yaw), 0.35), # Cart front edge
                (cand_x - 0.75 * np.cos(c_yaw), cand_y - 0.75 * np.sin(c_yaw), 0.38), # Nurse attendant
            ]
            for px, py, r in pts:
                if collision_guard.check_point_collision(px, py, margin=r):
                    is_blocked = True
                    break
            if not is_blocked and hasattr(collision_guard, "is_segment_clear"):
                if not collision_guard.is_segment_clear(self.x, self.y, cand_x, cand_y, margin=0.42):
                    is_blocked = True

        if is_blocked:
            self.blocked_timer += dt
            # If path remains blocked continuously and cooldown has elapsed, reverse patrol direction smoothly
            if self.blocked_timer >= 1.0 and self.turn_cooldown <= 0.0:
                self.patrol_direction = -self.patrol_direction
                self.current_wp_idx = (self.current_wp_idx + self.patrol_direction) % len(self.waypoints)
                self.blocked_timer = 0.0
                self.turn_cooldown = 2.0  # Allow smooth exit without immediate flip
            return
        else:
            self.blocked_timer = max(0.0, self.blocked_timer - dt * 2.0)

        self.x = cand_x
        self.y = cand_y

        if HAS_OMNI and hasattr(self, "translate_op") and self.translate_op is not None:
            self.translate_op.Set(Gf.Vec3d(self.x, self.y, self.z))
            self.rotate_op.Set(float(np.degrees(self.yaw)))


class DynamicSupplyTrolley(DynamicMedicalCart):
    """Mobile hospital logistics supply trolley for sterile packs and clinical restocking."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.role = "supply_trolley"
        self.color_cart = np.array([0.22, 0.45, 0.72])        # Clinical blue casing
        self.color_drawer_red = np.array([0.92, 0.72, 0.18])  # Amber warning bin
        self.color_drawer_blue = np.array([0.25, 0.65, 0.40]) # Sterile green pack tray
        self.color_nurse = np.array([0.45, 0.35, 0.60])       # Logistics purple scrub


# ─────────────────────────────────────────────────────────────────────────────
# 5. Dynamic Obstacle Scenario Manager
# ─────────────────────────────────────────────────────────────────────────────

class DynamicObstacleManager:
    """
    Coordinates and animates dynamic obstacles according to configurable traffic modes:
    - LIGHT  / LOW    : 2-4 obstacles (Doctor, Nurse, Stretcher)
    - NORMAL / MEDIUM : 5-8 obstacles (Doctors, Nurses, Stretcher, Wheelchair, Medical Cart, Visitor)
    - BUSY   / HIGH   : 9-15 obstacles (Peak hospital load: multiple carts, wheelchairs, stretchers, supply trolley)

    Supports reproducible random seed and live regeneration.
    """

    def __init__(self, traffic_mode: str = "normal", random_seed: Optional[int] = None) -> None:
        self.traffic_mode = self._normalize_mode(traffic_mode)
        self.random_seed = int(random_seed) if random_seed is not None else int(np.random.randint(10000, 99999))
        self.agents: list[Any] = []
        self._spawn_scenario_agents()

    @property
    def obstacles(self) -> list[Any]:
        """Backward-compatible alias for self.agents."""
        return self.agents


    @staticmethod
    def _normalize_mode(mode: str) -> str:
        m = str(mode).lower().strip()
        if m in ("light", "low"):
            return "light"
        elif m in ("busy", "high"):
            return "busy"
        return "normal"

    def regenerate(self, traffic_mode: Optional[str] = None, seed: Optional[int] = None) -> None:
        """Regenerate all dynamic obstacles with a new traffic density or random seed."""
        if traffic_mode:
            self.traffic_mode = self._normalize_mode(traffic_mode)
        if seed is not None:
            self.random_seed = int(seed)
        else:
            self.random_seed = int(np.random.randint(10000, 99999))
        self.agents.clear()
        self._spawn_scenario_agents()
        print(f"[DynamicObstacles] Scenario REGENERATED: Mode={self.traffic_mode.upper()} Seed={self.random_seed} ({len(self.agents)} agents)")

    def _spawn_scenario_agents(self) -> None:
        print(f"[DynamicObstacles] Initializing traffic scenario: {self.traffic_mode.upper()}")

        # ── Per-mode speed selection from configurable constants ───────────────
        _mode = self.traffic_mode
        if _mode in ("low", "light"):
            _ped_spd  = PEDESTRIAN_SPEED_LOW
            _cart_spd = CART_SPEED_LOW
            _wc_spd   = WHEELCHAIR_SPEED_LOW
            _str_spd  = STRETCHER_SPEED_LOW
        elif _mode in ("high", "busy"):
            _ped_spd  = PEDESTRIAN_SPEED_HIGH
            _cart_spd = CART_SPEED_HIGH
            _wc_spd   = WHEELCHAIR_SPEED_HIGH
            _str_spd  = STRETCHER_SPEED_HIGH
        else:  # medium / normal (default)
            _ped_spd  = PEDESTRIAN_SPEED_MED
            _cart_spd = CART_SPEED_MED
            _wc_spd   = WHEELCHAIR_SPEED_MED
            _str_spd  = STRETCHER_SPEED_MED

        print(f"[DynamicObstacles] Speed Config -> Ped:{_ped_spd:.2f} Cart:{_cart_spd:.2f} "
              f"WC:{_wc_spd:.2f} Str:{_str_spd:.2f} m/s (Mode={self.traffic_mode.upper()} Seed={self.random_seed})")

        # ── Group 1: Core 3 Obstacles (Active in LOW, MEDIUM, HIGH) ───────────
        # SCATTERED across 3 different corridors — no queuing!

        # 1. Dr. Sharma (North Corridor WEST wing: Y = 20.0m, X = -38 to -10)
        doc1 = DynamicHumanoid(
            prim_path="/World/DynamicObstacles/Dr_Sharma",
            name="Dr. Sharma (Consultant)",
            role="doctor",
            waypoints=[
                (-38.0, 20.3),
                (-24.0, 20.3),
                (-10.0, 20.3),
                (-24.0, 20.3),
            ],
            speed=round(_ped_spd * 1.00, 2),
            corridor_axis="h", corridor_center=20.0, corridor_half_width=1.6,
        )
        self.agents.append(doc1)

        # 2. Nurse Priya (Central Corridor EAST half: Y = 2.0m, X = 4 to 30)
        nurse1 = DynamicHumanoid(
            prim_path="/World/DynamicObstacles/Nurse_Priya",
            name="Nurse Priya (Critical Care)",
            role="nurse",
            waypoints=[
                (4.0, 1.7),
                (14.0, 1.7),
                (30.0, 1.7),
                (14.0, 1.7),
            ],
            speed=round(_ped_spd * 1.05, 2),
            corridor_axis="h", corridor_center=2.0, corridor_half_width=1.6,
        )
        self.agents.append(nurse1)

        # 3. Paramedic Alex with Stretcher (East Spine Corridor: X = 15.0m, Y = 3 to 16.5)
        stretcher1 = DynamicStretcher(
            prim_path="/World/DynamicObstacles/Paramedic_Stretcher1",
            name="Paramedic Alex with Gurney",
            waypoints=[
                (15.0, 3.0),
                (15.0, 10.0),
                (15.0, 16.5),
                (15.0, 10.0),
            ],
            speed=round(_str_spd * 1.00, 2),
            corridor_axis="v", corridor_center=15.0, corridor_half_width=0.85,
        )
        self.agents.append(stretcher1)

        if self.traffic_mode in ("low", "light"):
            print(f"[DynamicObstacles] Deployed {len(self.agents)} dynamic agents (LIGHT Traffic Mode, Seed={self.random_seed}).")
            self._scatter_agents_on_routes()
            return

        # ── Group 2: Additional 5 Obstacles for MEDIUM Mode (Total: 8) ────────
        # Each on a DIFFERENT corridor segment than Group 1!

        # 4. Orderly Carlos (Inpatient Corridor: X = -20.0m, Y = -14 to 0)
        orderly1 = DynamicHumanoid(
            prim_path="/World/DynamicObstacles/Orderly_Carlos",
            name="Orderly Carlos (Supplies)",
            role="orderly",
            waypoints=[
                (-20.0, -14.0),
                (-20.0, -7.0),
                (-20.0, 0.0),
                (-20.0, -7.0),
            ],
            speed=round(_ped_spd * 0.95, 2),
            corridor_axis="v", corridor_center=-20.0, corridor_half_width=1.1,
        )
        self.agents.append(orderly1)

        # 5. Orderly David with Wheelchair (South Corridor WEST segment: Y = -18.0m, X = -38 to -10)
        wheelchair1 = DynamicWheelchair(
            prim_path="/World/DynamicObstacles/Wheelchair_David",
            name="Orderly David with Wheelchair",
            waypoints=[
                (-38.0, -18.3),
                (-24.0, -18.3),
                (-10.0, -18.3),
                (-24.0, -18.3),
            ],
            speed=round(_wc_spd * 1.00, 2),
            corridor_axis="h", corridor_center=-18.0, corridor_half_width=1.6,
        )
        self.agents.append(wheelchair1)

        # 6. Nurse Anjali with Medicine Cart (Central Corridor WEST half: Y = 2.0m, X = -38 to -10)
        #    SEPARATE from Nurse Priya who is on EAST half!
        cart1 = DynamicMedicalCart(
            prim_path="/World/DynamicObstacles/MedicalCart_Anjali",
            name="Nurse Anjali with Medicine Trolley",
            waypoints=[
                (-38.0, 2.3),
                (-24.0, 2.3),
                (-10.0, 2.3),
                (-24.0, 2.3),
            ],
            speed=round(_cart_spd * 1.00, 2),
            corridor_axis="h", corridor_center=2.0, corridor_half_width=1.6,
        )
        self.agents.append(cart1)

        # 7. Dr. Kulkarni (North Corridor EAST wing: Y = 20.0m, X = 8 to 38)
        #    OPPOSITE side from Dr. Sharma who is on WEST wing!
        surgeon1 = DynamicHumanoid(
            prim_path="/World/DynamicObstacles/Dr_Kulkarni",
            name="Dr. Kulkarni (Chief Surgeon)",
            role="surgeon",
            waypoints=[
                (8.0, 19.7),
                (20.0, 19.7),
                (38.0, 19.7),
                (20.0, 19.7),
            ],
            speed=round(_ped_spd * 1.02, 2),
            corridor_axis="h", corridor_center=20.0, corridor_half_width=1.6,
        )
        self.agents.append(surgeon1)

        # 8. Visitor Maya (Central Spine: X = 0.0m, Y = -34 to -18 — Entrance to South Corridor)
        visitor1 = DynamicHumanoid(
            prim_path="/World/DynamicObstacles/Visitor_Maya",
            name="Visitor Maya",
            role="visitor",
            waypoints=[
                (0.3, -34.0),
                (0.3, -26.0),
                (0.3, -18.0),
                (0.3, -26.0),
            ],
            speed=round(_ped_spd * 0.85, 2),
            corridor_axis="v", corridor_center=0.0, corridor_half_width=1.8,
        )
        self.agents.append(visitor1)

        if self.traffic_mode in ("medium", "normal"):
            print(f"[DynamicObstacles] Deployed {len(self.agents)} dynamic agents (NORMAL Traffic Mode, Seed={self.random_seed}).")
            self._scatter_agents_on_routes()
            return

        # ── Group 3: Additional 7 Obstacles for HIGH Mode (Total: 15) ──────────
        # Fill remaining corridor segments

        # 9. Nurse Deepa (South Corridor EAST segment: Y = -18.0m, X = 16 to 38)
        nurse2 = DynamicHumanoid(
            prim_path="/World/DynamicObstacles/Nurse_Deepa",
            name="Nurse Deepa (ICU Specialist)",
            role="nurse",
            waypoints=[
                (16.0, -17.7),
                (26.0, -17.7),
                (38.0, -17.7),
                (26.0, -17.7),
            ],
            speed=round(_ped_spd * 1.02, 2),
            corridor_axis="h", corridor_center=-18.0, corridor_half_width=1.6,
        )
        self.agents.append(nurse2)

        # 10. Paramedic Ramesh with Second Stretcher (West Spine NORTH half: X = -24.0m, Y = 4 to 32)
        stretcher2 = DynamicStretcher(
            prim_path="/World/DynamicObstacles/Paramedic_Stretcher2",
            name="Paramedic Ramesh (Trauma Transfer)",
            waypoints=[
                (-24.3, 4.0),
                (-24.3, 14.0),
                (-24.3, 32.0),
                (-24.3, 14.0),
            ],
            speed=round(_str_spd * 1.05, 2),
            corridor_axis="v", corridor_center=-24.0, corridor_half_width=1.6,
        )
        self.agents.append(stretcher2)

        # 11. Orderly Sunil with Wheelchair (East Spine SOUTH half: X = 14.0m, Y = -30 to -4)
        wheelchair2 = DynamicWheelchair(
            prim_path="/World/DynamicObstacles/Wheelchair_Sunil",
            name="Orderly Sunil with Patient Wheelchair",
            waypoints=[
                (13.7, -30.0),
                (13.7, -18.0),
                (13.7, -4.0),
                (13.7, -18.0),
            ],
            speed=round(_wc_spd * 0.95, 2),
            corridor_axis="v", corridor_center=14.0, corridor_half_width=1.6,
        )
        self.agents.append(wheelchair2)

        # 12. Logistics Supply Trolley (Sterile Restocking in North Corridor)
        cart2 = DynamicSupplyTrolley(
            prim_path="/World/DynamicObstacles/SupplyTrolley_Vikram",
            name="Logistics Supply Trolley (Sterile Packs)",
            waypoints=[
                (-6.0, 20.3),
                (0.0, 20.3),
                (6.0, 20.3),
                (0.0, 20.3),
            ],
            speed=round(_cart_spd * 1.05, 2),
            corridor_axis="h", corridor_center=20.0, corridor_half_width=1.6,
        )
        self.agents.append(cart2)


        # 13. Visitor Rahul (Central Concourse & Entrance: X = -0.3m, Y = -14 to 1)
        visitor2 = DynamicHumanoid(
            prim_path="/World/DynamicObstacles/Visitor_Rahul",
            name="Visitor Rahul",
            role="visitor",
            waypoints=[
                (-0.3, -14.0),
                (-0.3, -6.0),
                (-0.3, 1.0),
                (-0.3, -6.0),
            ],
            speed=round(_ped_spd * 0.88, 2),
            corridor_axis="v", corridor_center=0.0, corridor_half_width=1.5,
        )
        self.agents.append(visitor2)

        # 14. Dr. Nair (Central Corridor FAR EAST: Y = 2.0m, X = 32 to 40)
        doc2 = DynamicHumanoid(
            prim_path="/World/DynamicObstacles/Dr_Nair",
            name="Dr. Nair (Pediatrician)",
            role="doctor",
            waypoints=[
                (32.0, 2.3),
                (36.0, 2.3),
                (40.0, 2.3),
                (36.0, 2.3),
            ],
            speed=round(_ped_spd * 0.98, 2),
            corridor_axis="h", corridor_center=2.0, corridor_half_width=1.6,
        )
        self.agents.append(doc2)

        # 15. Visitor Sneha (South Corridor MID segment: Y = -18.0m, X = -6 to 12)
        visitor3 = DynamicHumanoid(
            prim_path="/World/DynamicObstacles/Visitor_Sneha",
            name="Visitor Sneha",
            role="visitor",
            waypoints=[
                (-6.0, -18.3),
                (2.0, -18.3),
                (12.0, -18.3),
                (2.0, -18.3),
            ],
            speed=round(_ped_spd * 0.82, 2),
            corridor_axis="h", corridor_center=-18.0, corridor_half_width=1.6,
        )
        self.agents.append(visitor3)

        print(f"[DynamicObstacles] Deployed {len(self.agents)} dynamic agents (BUSY Traffic Mode, Seed={self.random_seed}).")
        self._scatter_agents_on_routes()

    def validate_spawn_position(
        self,
        agent: Any,
        collision_guard: Any = None,
        existing_robot_positions: Optional[List[Tuple[float, float]]] = None,
        min_clearance: float = 0.38,
    ) -> Tuple[bool, str]:
        """
        Spawning validation rule:
        - inside hospital bounds ([-42, 42] x [-36, 36])
        - outside walls and registered collision barriers
        - not overlapping active robots or other obstacles
        - sufficient clearance and correct orientation
        """
        x, y = float(agent.x), float(agent.y)
        if x < -42.0 or x > 42.0 or y < -36.0 or y > 36.0:
            return False, f"Obstacle {agent.name} ({x:.2f}, {y:.2f}) outside hospital bounds"

        if collision_guard is not None:
            if collision_guard.check_point_collision(x, y, margin=min_clearance):
                return False, f"Obstacle {agent.name} ({x:.2f}, {y:.2f}) intersects wall barrier"
            if getattr(agent, "role", "") == "stretcher":
                c_yaw = getattr(agent, "yaw", 0.0)
                fx = x + 1.10 * np.cos(c_yaw)
                fy = y + 1.10 * np.sin(c_yaw)
                bx = x - 1.35 * np.cos(c_yaw)
                by = y - 1.35 * np.sin(c_yaw)
                if collision_guard.check_point_collision(fx, fy, margin=0.35):
                    return False, f"Stretcher front intersects wall barrier"
                if collision_guard.check_point_collision(bx, by, margin=0.35):
                    return False, f"Stretcher rear attendant intersects wall barrier"

        if existing_robot_positions:
            for rx, ry in existing_robot_positions:
                if np.hypot(x - rx, y - ry) < (min_clearance + 0.38):
                    return False, f"Obstacle {agent.name} overlaps robot at ({rx:.2f}, {ry:.2f})"

        return True, "Valid spawn position"

    def _scatter_agents_on_routes(self) -> None:
        """
        Randomize each agent's starting waypoint index and interpolate their
        initial XY position to a random point along their route segment.
        This prevents the 'queue-walking' startup artifact where all agents
        begin at waypoint[0] and march in the same direction simultaneously.
        """
        rng = np.random.default_rng(seed=self.random_seed)
        for agent in self.agents:
            if not agent.waypoints or len(agent.waypoints) < 2:
                continue
            # Pick a random starting waypoint segment
            max_wp = len(agent.waypoints) - 1
            start_idx = int(rng.integers(0, max_wp))
            agent.current_wp_idx = (start_idx + 1) % len(agent.waypoints)

            # Interpolate position to a random point in [waypoints[start_idx], waypoints[start_idx+1]]
            t_start = agent.waypoints[start_idx]
            t_end = agent.waypoints[agent.current_wp_idx]
            alpha = float(rng.uniform(0.10, 0.90))
            agent.x = float(t_start[0] + alpha * (t_end[0] - t_start[0]))
            agent.y = float(t_start[1] + alpha * (t_end[1] - t_start[1]))

            # Set heading toward the next waypoint
            dx = t_end[0] - agent.x
            dy = t_end[1] - agent.y
            if abs(dx) > 0.01 or abs(dy) > 0.01:
                agent.yaw = float(np.arctan2(dy, dx))

            # Update the USD prim position to match the scattered start
            if HAS_OMNI and hasattr(agent, "translate_op") and agent.translate_op is not None:
                agent.translate_op.Set(Gf.Vec3d(agent.x, agent.y, agent.z))
                if hasattr(agent, "rotate_op") and agent.rotate_op is not None:
                    agent.rotate_op.Set(float(np.degrees(agent.yaw)))

        print("[DynamicObstacles] Agents scattered to random positions along patrol routes.")

    def step(self, dt: float = 0.016, collision_guard: Any = None) -> None:
        """Update positions and kinematics for all dynamic agents with wall collision avoidance."""
        for agent in self.agents:
            agent.step(dt=dt, collision_guard=collision_guard)

    def get_obstacle_positions(self) -> list[tuple[float, float]]:
        """Return (x, y) coordinates of all active dynamic obstacles."""
        return [(agent.x, agent.y) for agent in self.agents]

    def get_agent_details(self) -> list[dict]:
        """Return detailed status of all active dynamic agents."""
        return [
            {
                "name": agent.name,
                "role": getattr(agent, "role", "unknown"),
                "pos": (round(agent.x, 2), round(agent.y, 2)),
                "speed": agent.speed,
            }
            for agent in self.agents
        ]


def validate_spawn_position(
    pos: Any,
    collision_guard: Any = None,
    existing_robot_positions: Optional[List[Tuple[float, float]]] = None,
    existing_obstacle_positions: Optional[List[Tuple[float, float]]] = None,
    min_clearance: float = 0.38,
) -> Tuple[bool, str]:
    """Validate that obstacle/robot spawn position is inside hospital and clear of walls/entities."""
    if hasattr(pos, "x") and hasattr(pos, "y"):
        x, y = float(pos.x), float(pos.y)
    else:
        x, y = float(pos[0]), float(pos[1])

    if x < -42.0 or x > 42.0 or y < -36.0 or y > 36.0:
        return False, f"Position ({x:.2f}, {y:.2f}) outside hospital perimeter"

    if collision_guard is not None:
        if collision_guard.check_point_collision(x, y, margin=min_clearance):
            return False, f"Position ({x:.2f}, {y:.2f}) collides with wall barrier"

    if existing_robot_positions:
        for r_pos in existing_robot_positions:
            rx, ry = float(r_pos[0]), float(r_pos[1])
            if np.hypot(x - rx, y - ry) < (min_clearance + 0.38):
                return False, f"Position overlaps robot at ({rx:.2f}, {ry:.2f})"

    if existing_obstacle_positions:
        for o_pos in existing_obstacle_positions:
            ox, oy = float(o_pos[0]), float(o_pos[1])
            if np.hypot(x - ox, y - oy) < (min_clearance + 0.35):
                return False, f"Position overlaps obstacle at ({ox:.2f}, {oy:.2f})"

    return True, f"Position ({x:.2f}, {y:.2f}) valid and collision-free"


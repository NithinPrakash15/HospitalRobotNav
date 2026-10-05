"""
Hospital Route Visualizer — 3D USD Floor Path & Waypoint Rendering
===================================================================
Renders real-time, high-visibility 3D navigation paths directly on the
hospital floor in NVIDIA Isaac Sim:
- Planned waypoints as glowing floor discs
- Continuous route ribbon segments between adjacent waypoints
- Distinct Start (Emerald) and Destination (Cyan/Gold) beacons
- Active waypoint highlighted in vibrant yellow
- Completed waypoints visually distinguished from remaining waypoints
- Dynamic obstacle blockage marker (Red hazard beacon) and replanned
  local A* detour ribbons (Amber/Magenta)
"""

from __future__ import annotations

import math
from typing import Any, List, Optional, Tuple
import numpy as np

try:
    import omni.usd
    from pxr import Gf, Sdf, UsdGeom, UsdShade
    HAS_OMNI = True
except ImportError:
    HAS_OMNI = False
    omni = Gf = Sdf = UsdGeom = UsdShade = None


def _create_floor_box(
    stage: Any,
    parent_path: str,
    name: str,
    pos: Tuple[float, float, float],
    size: Tuple[float, float, float],
    color: Tuple[float, float, float],
    yaw_rad: float = 0.0,
) -> Any:
    """Create an oriented box prim directly on the USD stage."""
    if not HAS_OMNI or stage is None:
        return None
    prim_path = f"{parent_path}/{name}"
    cube_geom = UsdGeom.Cube.Define(stage, Sdf.Path(prim_path))
    cube_prim = cube_geom.GetPrim()

    # Base cube size is 2x2x2; scale to exact dimensions
    xformable = UsdGeom.Xformable(cube_prim)
    xformable.ClearXformOpOrder()
    t_op = xformable.AddTranslateOp()
    r_op = xformable.AddRotateZOp()
    s_op = xformable.AddScaleOp()

    t_op.Set(Gf.Vec3d(float(pos[0]), float(pos[1]), float(pos[2])))
    r_op.Set(float(np.degrees(yaw_rad)))
    s_op.Set(Gf.Vec3f(float(size[0]) / 2.0, float(size[1]) / 2.0, float(size[2]) / 2.0))

    cube_geom.CreateDisplayColorAttr([Gf.Vec3f(float(color[0]), float(color[1]), float(color[2]))])
    return cube_geom


class HospitalRouteVisualizer:
    """
    Manages 3D path visualization prims on the Isaac Sim stage.
    Synchronized directly with the route planner and robot navigation.
    """

    ROOT_PRIM = "/World/Visuals/PlannedRoute"
    OBSTACLE_PRIM = "/World/Visuals/ObstacleBlocked"

    def __init__(self, stage: Any = None) -> None:
        self.stage = stage
        if self.stage is None and HAS_OMNI:
            try:
                self.stage = omni.usd.get_context().get_stage()
            except Exception:
                self.stage = None

        self.current_waypoints: List[np.ndarray] = []
        self.active_waypoint_idx: int = 0
        self.robot_name: str = ""
        self.destination_name: str = ""
        self.is_emergency: bool = False
        self._init_root_prims()

    def _init_root_prims(self) -> None:
        """Ensure root visual hierarchy exists in USD stage."""
        if not HAS_OMNI or self.stage is None:
            return
        try:
            UsdGeom.Xform.Define(self.stage, Sdf.Path("/World/Visuals"))
            UsdGeom.Xform.Define(self.stage, Sdf.Path(self.ROOT_PRIM))
            UsdGeom.Xform.Define(self.stage, Sdf.Path(self.OBSTACLE_PRIM))
        except Exception:
            pass

    def clear(self) -> None:
        """Remove all active route visual prims from the stage."""
        if not HAS_OMNI or self.stage is None:
            return
        try:
            for root in (self.ROOT_PRIM, self.OBSTACLE_PRIM):
                prim = self.stage.GetPrimAtPath(Sdf.Path(root))
                if prim.IsValid():
                    for child in list(prim.GetChildren()):
                        self.stage.RemovePrim(child.GetPath())
        except Exception:
            pass
        self.current_waypoints = []
        self.active_waypoint_idx = 0

    def visualize_route(
        self,
        robot_name: str,
        waypoints: List[np.ndarray | Tuple[float, float, float] | Tuple[float, float]],
        destination_name: str = "",
        is_emergency: bool = False,
    ) -> None:
        """
        Render real-time planned path onto the hospital floor.
        
        Args:
            robot_name: Name of the assigned AMR.
            waypoints: List of [X, Y] or [X, Y, Z] path coordinates.
            destination_name: Semantic name of target room/bed.
            is_emergency: If True, uses high-urgency emergency crimson/amber styling.
        """
        self.clear()
        if not waypoints or len(waypoints) < 1:
            return

        self.robot_name = robot_name
        self.destination_name = destination_name
        self.is_emergency = is_emergency
        self.current_waypoints = [np.array(wp, dtype=float) for wp in waypoints]
        self.active_waypoint_idx = 0

        if not HAS_OMNI or self.stage is None:
            return

        # Palette definition
        route_color = (1.0, 0.25, 0.20) if is_emergency else (0.0, 0.88, 1.0)       # Alert Red or Bright Cyan
        active_color = (1.0, 0.95, 0.10)                                              # Vibrant Yellow
        dest_color = (0.95, 0.85, 0.15) if is_emergency else (0.15, 0.95, 0.85)     # Gold or Cyan Diamond
        start_color = (0.10, 0.90, 0.40)                                             # Emerald Green

        n_pts = len(self.current_waypoints)

        # 1. Draw connecting path ribbons between consecutive waypoints
        for i in range(n_pts - 1):
            p1 = self.current_waypoints[i]
            p2 = self.current_waypoints[i + 1]
            dx = float(p2[0] - p1[0])
            dy = float(p2[1] - p1[1])
            length = float(np.hypot(dx, dy))
            if length < 0.05:
                continue

            mid_x = float(p1[0] + dx / 2.0)
            mid_y = float(p1[1] + dy / 2.0)
            yaw = float(math.atan2(dy, dx))

            _create_floor_box(
                self.stage,
                self.ROOT_PRIM,
                f"Seg_{i:03d}",
                pos=(mid_x, mid_y, 0.016),
                size=(length, 0.16, 0.012),
                color=route_color,
                yaw_rad=yaw,
            )

        # 2. Draw waypoint floor markers
        for i, wp in enumerate(self.current_waypoints):
            col = start_color if i == 0 else (dest_color if i == n_pts - 1 else route_color)
            if i == 0:
                # Start Beacon (Disc + Pillar)
                _create_floor_box(
                    self.stage, self.ROOT_PRIM, f"WP_{i:03d}_Disc",
                    pos=(float(wp[0]), float(wp[1]), 0.020),
                    size=(0.65, 0.65, 0.020),
                    color=start_color,
                )
            elif i == n_pts - 1:
                # Destination Beacon (Diamond / Pillar)
                _create_floor_box(
                    self.stage, self.ROOT_PRIM, f"WP_{i:03d}_Dest",
                    pos=(float(wp[0]), float(wp[1]), 0.025),
                    size=(0.75, 0.75, 0.030),
                    color=dest_color,
                    yaw_rad=math.pi / 4.0,  # 45 deg rotation for diamond look
                )
                _create_floor_box(
                    self.stage, self.ROOT_PRIM, f"WP_{i:03d}_Pillar",
                    pos=(float(wp[0]), float(wp[1]), 0.35),
                    size=(0.14, 0.14, 0.60),
                    color=dest_color,
                )
            else:
                # Standard Waypoint Marker
                _create_floor_box(
                    self.stage, self.ROOT_PRIM, f"WP_{i:03d}",
                    pos=(float(wp[0]), float(wp[1]), 0.018),
                    size=(0.32, 0.32, 0.015),
                    color=col,
                )

        # Highlight first target waypoint
        self.update_progress(0)

    def update_progress(self, current_waypoint_idx: int) -> None:
        """Update visual state of waypoints as AMR navigates along the route."""
        self.active_waypoint_idx = current_waypoint_idx
        if not HAS_OMNI or self.stage is None or not self.current_waypoints:
            return

        completed_color = Gf.Vec3f(0.15, 0.60, 0.30)  # Muted Green
        active_color = Gf.Vec3f(1.0, 0.95, 0.10)     # Vibrant Yellow
        remaining_color = Gf.Vec3f(1.0, 0.3, 0.2) if self.is_emergency else Gf.Vec3f(0.0, 0.88, 1.0)

        for i in range(len(self.current_waypoints)):
            prim_name = f"WP_{i:03d}" if i < len(self.current_waypoints) - 1 else f"WP_{i:03d}_Dest"
            prim_path = Sdf.Path(f"{self.ROOT_PRIM}/{prim_name}")
            prim = self.stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
                continue

            geom = UsdGeom.Cube(prim)
            if i < current_waypoint_idx:
                geom.CreateDisplayColorAttr([completed_color])
            elif i == current_waypoint_idx:
                geom.CreateDisplayColorAttr([active_color])
            else:
                geom.CreateDisplayColorAttr([remaining_color])

    def visualize_obstacle_blockage_and_replan(
        self,
        obstacle_pos: Tuple[float, float],
        old_route: List[np.ndarray],
        detour_route: List[np.ndarray],
    ) -> None:
        """
        Visually represent dynamic obstacle blockage and the resulting local A* detour.
        - Hazard cross beacon at obstacle location.
        - Replanned detour path rendered in high-contrast amber/gold ribbons.
        """
        if not HAS_OMNI or self.stage is None:
            return

        try:
            # 1. Place Obstacle Hazard Beacon at blockage coordinate
            ox, oy = float(obstacle_pos[0]), float(obstacle_pos[1])
            hazard_color = (1.0, 0.15, 0.15)  # Crimson Red

            _create_floor_box(
                self.stage, self.OBSTACLE_PRIM, "HazardDisc",
                pos=(ox, oy, 0.030), size=(1.20, 1.20, 0.025), color=hazard_color,
            )
            _create_floor_box(
                self.stage, self.OBSTACLE_PRIM, "HazardCross1",
                pos=(ox, oy, 0.040), size=(1.0, 0.18, 0.030), color=(1.0, 1.0, 1.0),
                yaw_rad=math.pi / 4.0,
            )
            _create_floor_box(
                self.stage, self.OBSTACLE_PRIM, "HazardCross2",
                pos=(ox, oy, 0.040), size=(1.0, 0.18, 0.030), color=(1.0, 1.0, 1.0),
                yaw_rad=-math.pi / 4.0,
            )

            # 2. Render replanned detour route in bright Amber Gold
            detour_color = (1.0, 0.70, 0.10)
            detour_pts = [np.array(p, dtype=float) for p in detour_route]

            for i in range(len(detour_pts) - 1):
                p1 = detour_pts[i]
                p2 = detour_pts[i + 1]
                dx = float(p2[0] - p1[0])
                dy = float(p2[1] - p1[1])
                length = float(np.hypot(dx, dy))
                if length < 0.05:
                    continue

                mid_x = float(p1[0] + dx / 2.0)
                mid_y = float(p1[1] + dy / 2.0)
                yaw = float(math.atan2(dy, dx))

                _create_floor_box(
                    self.stage,
                    self.OBSTACLE_PRIM,
                    f"Detour_{i:03d}",
                    pos=(mid_x, mid_y, 0.022),
                    size=(length, 0.20, 0.016),
                    color=detour_color,
                    yaw_rad=yaw,
                )

                _create_floor_box(
                    self.stage,
                    self.OBSTACLE_PRIM,
                    f"DetourWP_{i:03d}",
                    pos=(float(p1[0]), float(p1[1]), 0.025),
                    size=(0.36, 0.36, 0.020),
                    color=detour_color,
                )

        except Exception as e:
            print(f"[VISUAL ERROR] Could not render dynamic obstacle visual: {e}")

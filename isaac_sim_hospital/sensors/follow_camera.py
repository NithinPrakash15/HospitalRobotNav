"""
Internal Isaac Sim Follow Camera Controller for AAROGYA Autonomous Fleet
========================================================================
Implements User Requirements 8-12:
- Operates directly INSIDE NVIDIA Isaac Sim viewport (/OmniverseKit_Persp)
- Dynamic camera states: OVERVIEW, FOLLOW_ROBOT, MISSION_FOLLOW, IDLE, MISSION_COMPLETE
- Smooth cinematic 3rd-person follow tracking behind active robot
- Smooth exponential moving average (EMA) interpolation to avoid shaking and teleportation
- Mission-aware switching when a mission is assigned to MITHRA, AR-02, Arogya_Delivery, etc.
- Automatic smooth return to OVERVIEW when mission completes.
"""

from __future__ import annotations

import math
import time
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

try:
    from isaacsim.core.utils.viewports import set_camera_view
    HAS_VIEWPORT = True
except ImportError:
    try:
        from omni.isaac.core.utils.viewports import set_camera_view
        HAS_VIEWPORT = True
    except ImportError:
        set_camera_view = None
        HAS_VIEWPORT = False


class CameraState(Enum):
    OVERVIEW = auto()
    FOLLOW_ROBOT = auto()
    MISSION_FOLLOW = auto()
    IDLE = auto()
    MISSION_COMPLETE = auto()


class IsaacSimFollowCamera:
    """
    Controls Isaac Sim's viewport camera (/OmniverseKit_Persp) to provide
    professional robotics demonstration camera tracking directly inside the simulator.
    """

    def __init__(
        self,
        camera_prim_path: str = "/OmniverseKit_Persp",
        overview_eye: Tuple[float, float, float] = (0.0, -56.0, 48.0),
        overview_target: Tuple[float, float, float] = (0.0, 1.0, 0.0),
        follow_distance: float = 4.5,
        follow_height: float = 3.0,
        interpolation_alpha: float = 0.08,
    ) -> None:
        self.camera_prim_path = camera_prim_path
        self.overview_eye = np.array(overview_eye, dtype=float)
        self.overview_target = np.array(overview_target, dtype=float)
        self.follow_distance = follow_distance
        self.follow_height = follow_height
        self.alpha = interpolation_alpha

        self.current_state = CameraState.OVERVIEW
        self.tracked_robot_name: Optional[str] = None
        self.current_eye = np.array(overview_eye, dtype=float)
        self.current_target = np.array(overview_target, dtype=float)

        self._mission_complete_start_time: float = 0.0
        self._last_update_time: float = time.time()
        self._step_counter: int = 0

    def set_overview(self) -> None:
        """Switch camera state to OVERVIEW."""
        self.current_state = CameraState.OVERVIEW
        self.tracked_robot_name = None

    def track_robot(self, robot_name: str, is_mission: bool = True) -> None:
        """Dynamically track an assigned robot inside Isaac Sim."""
        self.tracked_robot_name = robot_name
        self.current_state = CameraState.MISSION_FOLLOW if is_mission else CameraState.FOLLOW_ROBOT

    def notify_mission_complete(self, robot_name: str) -> None:
        """Called when active robot completes its mission."""
        if self.tracked_robot_name == robot_name:
            self.current_state = CameraState.MISSION_COMPLETE
            self._mission_complete_start_time = time.time()

    def update(self, fleet_robots: Dict[str, Any], dt: float = 0.016) -> None:
        """
        Update camera position each simulation frame with smooth interpolation.
        Applies directly to Isaac Sim's viewport camera (/OmniverseKit_Persp).
        """
        self._step_counter += 1
        now = time.time()

        # 1. State-dependent target calculation
        if self.current_state == CameraState.MISSION_COMPLETE:
            # Dwell on robot for 3.5s celebrating delivery completion, then return to OVERVIEW
            if now - self._mission_complete_start_time > 3.5:
                self.current_state = CameraState.OVERVIEW
                self.tracked_robot_name = None

        # Check if any robot is actively executing a mission if no tracked robot
        if self.tracked_robot_name is None:
            for name, r in fleet_robots.items():
                if getattr(r, "mission_active", False):
                    st = getattr(getattr(r, "state_machine", None), "state", None)
                    st_name = getattr(st, "name", "")
                    if st_name in ("NAVIGATING", "EXECUTING_TASK", "AVOIDING_OBSTACLE", "REPLANNING"):
                        self.track_robot(name, is_mission=True)
                        break

        # Compute desired eye and target
        if self.current_state in (CameraState.FOLLOW_ROBOT, CameraState.MISSION_FOLLOW, CameraState.MISSION_COMPLETE) and self.tracked_robot_name:
            robot = fleet_robots.get(self.tracked_robot_name)
            if robot is not None and hasattr(robot, "x") and hasattr(robot, "yaw"):
                rx, ry, rz = float(robot.x), float(robot.y), float(robot.z)
                yaw = float(robot.yaw)

                # Look at upper torso/head visor of robot
                desired_target = np.array([rx, ry, rz + 0.85], dtype=float)

                if self.current_state == CameraState.MISSION_COMPLETE:
                    # Orbital panoramic orbit during bedside delivery completion
                    elapsed = now - self._mission_complete_start_time
                    orbit_angle = yaw + elapsed * 0.5
                    desired_eye = np.array([
                        rx - 3.8 * math.cos(orbit_angle),
                        ry - 3.8 * math.sin(orbit_angle),
                        rz + 2.4,
                    ], dtype=float)
                else:
                    # Trailing chase camera behind robot orientation with elevation
                    # Robot moves -> camera moves; robot turns -> camera smoothly orbits
                    desired_eye = np.array([
                        rx - self.follow_distance * math.cos(yaw),
                        ry - self.follow_distance * math.sin(yaw),
                        rz + self.follow_height,
                    ], dtype=float)

                # Prevent camera clipping through hospital perimeter boundaries
                desired_eye[0] = np.clip(desired_eye[0], -43.0, 43.0)
                desired_eye[1] = np.clip(desired_eye[1], -37.0, 37.0)
                desired_eye[2] = max(1.8, desired_eye[2])  # Minimum height above floor
            else:
                desired_eye = self.overview_eye
                desired_target = self.overview_target
                self.current_state = CameraState.OVERVIEW
        else:
            # OVERVIEW state
            desired_eye = self.overview_eye
            desired_target = self.overview_target

        # 2. Smooth exponential moving average (EMA) interpolation
        alpha = self.alpha
        self.current_eye = (1.0 - alpha) * self.current_eye + alpha * desired_eye
        self.current_target = (1.0 - alpha) * self.current_target + alpha * desired_target

        # 3. Apply directly to Isaac Sim viewport camera
        if HAS_VIEWPORT and set_camera_view is not None:
            try:
                set_camera_view(
                    eye=self.current_eye.tolist(),
                    target=self.current_target.tolist(),
                )
            except Exception:
                try:
                    set_camera_view(
                        eye=self.current_eye.tolist(),
                        target=self.current_target.tolist(),
                        camera_prim_path=self.camera_prim_path,
                    )
                except Exception:
                    pass

"""
Physical Camera Sensor Manager for AROGYA Multi-Agent Hospital Fleet
====================================================================
Attaches real physical cameras to AMRs in NVIDIA Isaac Sim 5.1.0:
- Forward-facing head-mounted UsdGeom.Camera prims at 1.05m height
- Realistic optical intrinsics (24mm focal length, 70 deg H-FOV)
- Dynamic transform tracking with robot rigid-body motion (+X forward, +Z up)
- Offscreen RTX Replicator render pipeline for real RGB frame streaming to browser
- Multi-robot camera switching with zero memory leak and bounded latest-frame buffer
"""

from __future__ import annotations

import io
import math
import queue
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from PIL import Image

try:
    import omni.usd
    from pxr import Gf, Sdf, UsdGeom, Vt
    HAS_OMNI = True
except ImportError:
    omni = None
    Gf = Sdf = UsdGeom = Vt = None
    HAS_OMNI = False

try:
    import omni.replicator.core as rep
    HAS_REPLICATOR = True
except ImportError:
    rep = None
    HAS_REPLICATOR = False


class AMRCameraSensor:
    """Represents a physical camera mounted on a specific Hospital AMR."""

    def __init__(
        self,
        robot_name: str,
        robot_prim_path: str,
        stage: Optional[Any] = None,
        resolution: Tuple[int, int] = (640, 360),
        focal_length_mm: float = 24.0,
        mounting_offset: Tuple[float, float, float] = (0.18, 0.0, 1.05),
    ) -> None:
        self.robot_name = robot_name
        self.robot_prim_path = robot_prim_path
        self.camera_prim_path = f"{robot_prim_path}/HeadVisor/Camera"
        self.resolution = resolution
        self.focal_length = focal_length_mm
        self.mounting_offset = mounting_offset
        self.stage = stage

        # Optical intrinsics (35mm Full-Frame Pinhole model: 36x24mm sensor)
        self.horizontal_aperture = 36.0    # mm
        self.vertical_aperture = 24.0      # mm
        self.hfov_rad = 2.0 * math.atan((self.horizontal_aperture / 2.0) / self.focal_length)
        self.hfov_deg = math.degrees(self.hfov_rad)
        self.clipping_range = (0.1, 100.0)

        # Camera state cache
        self.last_world_pos: Tuple[float, float, float] = (0.0, 0.0, 1.05)
        self.last_yaw_rad: float = 0.0
        self.is_active: bool = False
        self.last_frame_time: float = 0.0
        self.last_error: Optional[str] = None
        self.measured_fps: float = 0.0

        self._usd_camera = None
        self._init_usd_camera()

    def _init_usd_camera(self) -> None:
        """Create or configure the UsdGeom.Camera prim on the USD stage."""
        if not HAS_OMNI or self.stage is None:
            return

        try:
            cam_path = Sdf.Path(self.camera_prim_path)
            self._usd_camera = UsdGeom.Camera.Define(self.stage, cam_path)
            self._usd_camera.GetFocalLengthAttr().Set(self.focal_length)
            self._usd_camera.GetHorizontalApertureAttr().Set(self.horizontal_aperture)
            self._usd_camera.GetVerticalApertureAttr().Set(self.vertical_aperture)
            self._usd_camera.GetClippingRangeAttr().Set(Gf.Vec2f(self.clipping_range[0], self.clipping_range[1]))
            self._usd_camera.GetProjectionAttr().Set(UsdGeom.Tokens.perspective)

            # Local transform relative to parent prim
            # If parent is HeadVisor (which is at z=1.05 relative to robot), offset is (0.18, 0.0, 0.0)
            # In USD camera conventions (-Z forward, +Y up), rotation (90, 0, -90) points along +X forward with +Z up.
            xformable = UsdGeom.Xformable(self._usd_camera.GetPrim())
            xformable.ClearXformOpOrder()
            t_op = xformable.AddTranslateOp()

            # Determine parent offset
            parent_is_head = "headvisor" in self.camera_prim_path.lower()
            if parent_is_head:
                t_op.Set(Gf.Vec3d(float(self.mounting_offset[0]), float(self.mounting_offset[1]), 0.0))
            else:
                t_op.Set(Gf.Vec3d(float(self.mounting_offset[0]), float(self.mounting_offset[1]), float(self.mounting_offset[2])))

            r_op = xformable.AddRotateXYZOp()
            r_op.Set(Gf.Vec3f(90.0, 0.0, -90.0))
        except Exception as e:
            self.last_error = str(e)
            print(f"[CAMERA INIT WARNING] Could not create USD camera for {self.robot_name}: {e}")

    def update_pose(self, robot_x: float, robot_y: float, robot_z: float, robot_yaw_rad: float) -> None:
        """Update world pose coordinates of the mounted camera."""
        cos_y = math.cos(robot_yaw_rad)
        sin_y = math.sin(robot_yaw_rad)
        cam_x = robot_x + self.mounting_offset[0] * cos_y - self.mounting_offset[1] * sin_y
        cam_y = robot_y + self.mounting_offset[0] * sin_y + self.mounting_offset[1] * cos_y
        cam_z = robot_z + self.mounting_offset[2]

        self.last_world_pos = (cam_x, cam_y, cam_z)
        self.last_yaw_rad = robot_yaw_rad

    def project_world_to_image(self, target_world_pos: Tuple[float, float, float]) -> Optional[Tuple[int, int, float]]:
        """
        Project a 3D world coordinate into 2D camera pixel coordinates (u, v) and depth (meters).
        Returns None if target is behind the camera or outside FOV.
        """
        cx, cy, cz = self.last_world_pos
        dx = target_world_pos[0] - cx
        dy = target_world_pos[1] - cy
        dz = target_world_pos[2] - cz

        # Transform into robot/camera frame: X forward, Y left, Z up
        cos_y = math.cos(-self.last_yaw_rad)
        sin_y = math.sin(-self.last_yaw_rad)
        x_cam = dx * cos_y - dy * sin_y  # Forward depth
        y_cam = dx * sin_y + dy * cos_y  # Lateral offset (left positive)
        z_cam = dz                       # Vertical offset

        if x_cam < 0.2:
            return None

        w_px, h_px = self.resolution
        fx_px = (self.focal_length / self.horizontal_aperture) * w_px
        fy_px = (self.focal_length / self.vertical_aperture) * h_px

        u = int(w_px / 2.0 - (y_cam / x_cam) * fx_px)
        v = int(h_px / 2.0 - (z_cam / x_cam) * fy_px)

        if -50 <= u <= w_px + 50 and -50 <= v <= h_px + 50:
            return u, v, float(x_cam)
        return None

    def get_status_dict(self) -> Dict[str, Any]:
        """Return structured sensor telemetry."""
        now = time.time()
        if self.last_error:
            status = "ERROR"
        elif self.is_active:
            if self.last_frame_time > 0:
                status = "STALE" if (now - self.last_frame_time > 2.0) else "ONLINE"
            else:
                status = "INITIALIZING"
        else:
            status = "ONLINE" if self._usd_camera is not None else "STANDBY"

        return {
            "robot": self.robot_name,
            "status": status,
            "error": self.last_error,
            "prim_path": self.camera_prim_path,
            "resolution": f"{self.resolution[0]}x{self.resolution[1]}",
            "fps": round(self.measured_fps or (15.0 if self.is_active else 0.0), 1),
            "focal_length_mm": self.focal_length,
            "hfov_deg": round(self.hfov_deg, 1),
            "world_pos": (round(self.last_world_pos[0], 2), round(self.last_world_pos[1], 2), round(self.last_world_pos[2], 2)),
            "yaw_deg": round(math.degrees(self.last_yaw_rad), 1),
            "active": self.is_active,
            "last_frame_time": self.last_frame_time,
        }


# Global active singleton reference
_ACTIVE_CAMERA_MANAGER: Optional[CameraSensorManager] = None


class CameraSensorManager:
    """
    Manages multi-robot fleet camera sensors, dynamic Sensor Follow Mode,
    and asynchronous offscreen RTX frame capture for live browser POV streaming.
    """
    _active_instance: Optional[CameraSensorManager] = None

    def __init__(self, stage: Optional[Any] = None, resolution: Tuple[int, int] = (640, 360)) -> None:
        global _ACTIVE_CAMERA_MANAGER
        self.stage = stage
        self.resolution = resolution
        self.cameras: Dict[str, AMRCameraSensor] = {}
        self.selected_robot: str = "Arogya_Delivery"
        _ACTIVE_CAMERA_MANAGER = self
        CameraSensorManager._active_instance = self

        # Offscreen Replicator Render Product & Annotator
        self._rp = None
        self._rgb_ann = None
        self._active_cam_path: Optional[str] = None
        self._last_frame_bytes: bytes = b""
        self._last_capture_time: float = 0.0
        self._capture_fps: float = 15.0
        self._capture_interval: float = 1.0 / self._capture_fps
        self._frame_counter: int = 0
        self._last_fps_calc_time: float = time.time()
        self.measured_fps: float = 0.0
        self._has_replicator: bool = False
        self._check_replicator()

        # Asynchronous background thread for non-blocking JPEG encoding
        self._encode_queue: queue.Queue = queue.Queue(maxsize=1)
        self._encode_thread = threading.Thread(
            target=self._jpeg_encoder_worker,
            name="CameraJPEGEncoder",
            daemon=True,
        )
        self._encode_thread.start()

    def _jpeg_encoder_worker(self) -> None:
        """Background thread for PIL JPEG compression off the main simulation thread."""
        while True:
            try:
                rgb_array = self._encode_queue.get()
                if rgb_array is None:
                    break
                img = Image.fromarray(rgb_array)
                buf = io.BytesIO()
                # Enhanced visual quality (quality 85) for crisp, clear perception
                img.save(buf, format="JPEG", quality=85)
                self._last_frame_bytes = buf.getvalue()
                self._encode_queue.task_done()
            except Exception:
                pass

    def _check_replicator(self) -> None:
        global rep, HAS_REPLICATOR
        if rep is None:
            try:
                import omni.replicator.core as rep_mod
                rep = rep_mod
                HAS_REPLICATOR = True
            except ImportError:
                HAS_REPLICATOR = False
        self._has_replicator = HAS_REPLICATOR

    def register_robot_camera(
        self,
        robot_name: str,
        robot_prim_path: str,
        resolution: Optional[Tuple[int, int]] = None,
    ) -> AMRCameraSensor:
        """Register and mount a camera sensor on an AMR."""
        res = resolution or self.resolution
        cam = AMRCameraSensor(
            robot_name=robot_name,
            robot_prim_path=robot_prim_path,
            stage=self.stage,
            resolution=res,
        )
        self.cameras[robot_name] = cam

        # If this is the currently selected robot, attach render product
        if robot_name == self.selected_robot:
            cam.is_active = True
            self._attach_render_product(cam.camera_prim_path)

        return cam

    def _attach_render_product(self, cam_prim_path: str) -> None:
        """Attach offscreen Replicator render product to camera prim."""
        self._check_replicator()
        if not self._has_replicator or rep is None:
            return

        try:
            if self._rgb_ann is not None:
                try:
                    self._rgb_ann.detach()
                except Exception:
                    pass
            if self._rp is not None:
                try:
                    self._rp.destroy()
                except Exception:
                    pass

            self._rp = rep.create.render_product(cam_prim_path, self.resolution)
            self._rgb_ann = rep.AnnotatorRegistry.get_annotator("rgb")
            self._rgb_ann.attach(self._rp)
            self._active_cam_path = cam_prim_path
            self._needs_diag_log = True
            print(f"[CAMERA STREAM] Real Isaac Sim Camera attached: {cam_prim_path} ({self.resolution[0]}x{self.resolution[1]})")

            # Replicator pipeline single warmup step if needed so annotator buffer is initialized
            try:
                data = self._rgb_ann.get_data()
                if data is None or getattr(data, "size", 0) == 0:
                    rep.orchestrator.step(rt_subframes=1, pause_timeline=False, delta_time=0.0)
            except Exception:
                pass
        except Exception as e:
            print(f"[CAMERA STREAM WARNING] Failed to attach render product to {cam_prim_path}: {e}")

    def _select_robot_impl(self, robot_name: str) -> bool:
        matched = None
        for name in self.cameras.keys():
            if name.lower().startswith(robot_name.lower().split("_")[0]):
                matched = name
                break

        if matched:
            if matched != self.selected_robot or self._active_cam_path != self.cameras[matched].camera_prim_path:
                self.selected_robot = matched
                self._needs_diag_log = True
                self._last_frame_bytes = b""
                for name, cam in self.cameras.items():
                    cam.is_active = (name == matched)
                # Thread safety: USD & Replicator APIs must only be invoked from the main simulation thread.
                # If called from a web request worker thread, queue the switch for the next simulation tick.
                target_cam_path = self.cameras[matched].camera_prim_path
                if threading.current_thread() is threading.main_thread():
                    self._attach_render_product(target_cam_path)
                else:
                    self._pending_cam_path = target_cam_path
            return True
        elif not self.cameras:
            self.selected_robot = robot_name
            return True
        return False

    @classmethod
    def select_robot(cls, robot_name_or_self: Any, maybe_robot_name: Optional[str] = None) -> bool:
        """Sensor Follow Mode: switch active camera to chosen robot (class or instance)."""
        if isinstance(robot_name_or_self, CameraSensorManager):
            target = maybe_robot_name or ""
            return robot_name_or_self._select_robot_impl(target)
        else:
            target = str(robot_name_or_self)
            mgr = cls._active_instance or _ACTIVE_CAMERA_MANAGER
            if mgr is not None:
                return mgr._select_robot_impl(target)
        return False

    def get_active_camera(self) -> Optional[AMRCameraSensor]:
        """Get currently selected robot camera."""
        return self.cameras.get(self.selected_robot)

    def get_status_dict(self, robot_name: Optional[str] = None) -> Dict[str, Any]:
        """Get status for a specific robot or the active camera."""
        r_name = robot_name or self.selected_robot
        cam = self.cameras.get(r_name)
        if cam:
            return cam.get_status_dict()
        return {
            "robot": r_name,
            "status": "NO_DATA",
            "resolution": f"{self.resolution[0]}x{self.resolution[1]}",
            "fps": 0.0,
        }

    def get_all_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Return status dict for all registered cameras."""
        return {name: cam.get_status_dict() for name, cam in self.cameras.items()}

    def update_all(self, fleet_robots: Dict[str, Any]) -> None:
        """Update poses for all fleet cameras each simulation step."""
        # Process pending camera switch queued from web thread on the main simulation thread
        pending_path = getattr(self, "_pending_cam_path", None)
        if pending_path:
            self._pending_cam_path = None
            self._attach_render_product(pending_path)

        for r_name, r in fleet_robots.items():
            if r_name in self.cameras:
                self.cameras[r_name].update_pose(r.x, r.y, r.z, r.yaw)

    def capture_frame(self) -> bytes:
        """
        Capture the real RGB frame from Isaac Sim's active robot camera.
        Throttled to ~15 FPS to preserve simulation performance.
        Uses rt_subframes=1 without pausing timeline, and offloads JPEG
        compression to a background worker to avoid main-thread latency.
        """
        # Process pending camera switch if one was queued
        pending_path = getattr(self, "_pending_cam_path", None)
        if pending_path:
            self._pending_cam_path = None
            self._attach_render_product(pending_path)
        now = time.time()
        # Throttling to protect main thread FPS
        if (now - self._last_capture_time) < self._capture_interval and self._last_frame_bytes:
            return self._last_frame_bytes

        self._check_replicator()
        if not self._has_replicator or rep is None or self._rgb_ann is None:
            return self._last_frame_bytes

        try:
            # Fetch RGB frame directly from the annotator populated by the render pipeline.
            # Avoid synchronous rep.orchestrator.step() which blocks the main thread on RTX 4050.
            data = self._rgb_ann.get_data()

            if data is not None and getattr(data, "size", 0) > 0 and len(data.shape) == 3:
                # Actual uint8 RGB frame from Isaac Sim
                rgb = data[:, :, :3]
                if not self._encode_queue.full():
                    try:
                        self._encode_queue.put_nowait(rgb)
                    except queue.Full:
                        pass

                # Synchronously initialize first frame so stream never delivers empty bytes
                if not self._last_frame_bytes:
                    img = Image.fromarray(rgb)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=85)
                    self._last_frame_bytes = buf.getvalue()

                # Track rate & timestamp on active camera
                self._frame_counter += 1
                dt_fps = now - self._last_fps_calc_time
                if dt_fps >= 1.0:
                    self.measured_fps = round(self._frame_counter / max(0.001, dt_fps), 1)
                    self._last_fps_calc_time = now
                    self._frame_counter = 0

                active_cam = self.get_active_camera()
                if active_cam:
                    active_cam.last_frame_time = now
                    active_cam.measured_fps = self.measured_fps

                # Diagnostic telemetry report
                if not getattr(self, "_has_logged_diag", False) or getattr(self, "_needs_diag_log", False):
                    self._has_logged_diag = True
                    self._needs_diag_log = False
                    mean_val = float(np.mean(rgb))
                    min_val = int(np.min(rgb))
                    max_val = int(np.max(rgb))
                    print(
                        f"\n[CAMERA DIAGNOSTIC] Robot: {self.selected_robot}\n"
                        f"  prim_path        = {self._active_cam_path}\n"
                        f"  resolution       = {self.resolution[0]}x{self.resolution[1]}\n"
                        f"  buffer_shape     = {data.shape}\n"
                        f"  pixel_mean       = {mean_val:.2f} (min={min_val}, max={max_val})\n"
                        f"  status           = {'REAL SCENE RGB' if mean_val > 10 else 'BLACK FRAME'}\n",
                        flush=True
                    )

                self._last_capture_time = now
        except Exception as e:
            active_cam = self.get_active_camera()
            if active_cam:
                active_cam.last_error = str(e)

        return self._last_frame_bytes

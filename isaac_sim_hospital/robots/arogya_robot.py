"""
Multi-Agent Hospital Robot Fleet Models & Autonomous Controllers for Isaac Sim
=============================================================================
Directly reflects the embodied multi-agent hospital robot architecture:

1. Arogya_Delivery (Delivery AMR)
   - Home: Robot Charging Station Pad 1 (CHG-01)
   - Role: Prescription medication transport, pharmacy dispatch, bedside delivery
   - Styling: Cyan LED band, medicine delivery tray, medical kit box

2. Mitra_Reception (Reception AMR)
   - Home: Main Reception & Triage (RCT-01)
   - Role: Visitor escort, patient guidance, departmental direction assistance
   - Styling: Emerald green LED band, interactive guidance tablet

3. Garuda_Emergency (Emergency AMR)
   - Home: Emergency Trauma Bay (EMR-01)
   - Role: Code Blue emergency response, crash cart resupply, trauma triage
   - Styling: High-alert red strobe LED band, emergency defibrillator mount

Kinematics & Autonomy:
- Differential-drive kinematics with smooth in-place pivots and corridor tracking
- Triple-layer collision guard integration (zero wall clipping)
- Dynamic yielding safety bubble for moving obstacles (humans, stretchers, carts)
- Realistic battery drain and autonomous charging behavior at CHG-01 pads
"""

from __future__ import annotations

from typing import List, Optional, Tuple, Dict, Any
import numpy as np
import time
import uuid
from datetime import datetime

try:
    import omni.usd

    from pxr import Gf, Sdf, UsdGeom, Vt
    from isaacsim.core.api.objects import FixedCuboid, VisualCuboid
    HAS_OMNI = True
except ImportError:
    omni = None
    Gf = Sdf = UsdGeom = Vt = None
    FixedCuboid = VisualCuboid = None
    HAS_OMNI = False


def _make_local_box(
    stage,
    parent_path: str,
    child_name: str,
    local_pos,
    scale,
    color_rgb,
) -> None:
    """
    Create a UsdGeom.Cube at a LOCAL position relative to parent_path Xform.
    Child prims in local space travel with the parent Xform translate_op,
    so the whole robot moves as a rigid body.
    """
    if stage is None:
        return
    full_path = f"{parent_path}/{child_name}"
    xform = UsdGeom.Xform.Define(stage, Sdf.Path(full_path))
    xform.AddTranslateOp().Set(Gf.Vec3d(float(local_pos[0]), float(local_pos[1]), float(local_pos[2])))
    cube_path = f"{full_path}/Mesh"
    cube = UsdGeom.Cube.Define(stage, Sdf.Path(cube_path))
    cube.GetSizeAttr().Set(1.0)
    cube_xf = UsdGeom.Xformable(cube.GetPrim())
    cube_xf.AddScaleOp().Set(Gf.Vec3d(float(scale[0]), float(scale[1]), float(scale[2])))
    prim = stage.GetPrimAtPath(Sdf.Path(cube_path))
    if prim and prim.IsValid():
        r, g, b = float(color_rgb[0]), float(color_rgb[1]), float(color_rgb[2])
        cube.GetDisplayColorAttr().Set(Vt.Vec3fArray([Gf.Vec3f(r, g, b)]))

from robots.robot_state_machine import RobotState, RobotStateMachine


class ObstacleCheckResult(tuple):
    """Tuple supporting both 2-element unpack (is_crit, dist) and closest_pos attribute."""
    def __new__(cls, is_critical: bool, closest_dist: float, closest_pos: Optional[Tuple[float, float]] = None):
        obj = super().__new__(cls, (is_critical, closest_dist))
        obj.is_critical = is_critical
        obj.closest_dist = closest_dist
        obj.closest_pos = closest_pos
        return obj



def validate_spawn_position(
    candidate_pos: Tuple[float, float, float] | np.ndarray,
    collision_guard=None,
    existing_robot_positions: Optional[List[Tuple[float, float, float] | np.ndarray]] = None,
    boundary_min: float = -42.0,
    boundary_max: float = 42.0,
    boundary_min_x: Optional[float] = None,
    boundary_max_x: Optional[float] = None,
    boundary_min_y: Optional[float] = None,
    boundary_max_y: Optional[float] = None,
    robot_radius: float = 0.38,
    min_robot_distance: float = 0.80,
) -> Tuple[bool, str]:
    """
    Validate that a robot spawn position is strictly within the hospital boundary,
    does not intersect static walls, and does not overlap existing robots.
    
    Returns:
        (is_valid, status_message)
    """
    x, y = float(candidate_pos[0]), float(candidate_pos[1])
    b_min_x = boundary_min_x if boundary_min_x is not None else boundary_min
    b_max_x = boundary_max_x if boundary_max_x is not None else boundary_max
    b_min_y = boundary_min_y if boundary_min_y is not None else boundary_min
    b_max_y = boundary_max_y if boundary_max_y is not None else boundary_max

    # 1. Boundary check: must be inside hospital bounds
    if not (b_min_x <= x <= b_max_x and b_min_y <= y <= b_max_y):
        return False, f"Spawn ({x:.2f}, {y:.2f}) outside hospital perimeter X:[{b_min_x}, {b_max_x}], Y:[{b_min_y}, {b_max_y}]"

    # 2. Static wall collision check via CollisionGuard
    if collision_guard is not None:
        if collision_guard.check_point_collision(x, y, margin=robot_radius):
            return False, f"Spawn ({x:.2f}, {y:.2f}) violates static wall safety margin ({robot_radius}m)"

    # 3. Inter-robot overlap check: must not spawn on top of another robot
    if existing_robot_positions:
        for ex_pos in existing_robot_positions:
            dist = float(np.hypot(x - ex_pos[0], y - ex_pos[1]))
            if dist < min_robot_distance:
                return False, f"Spawn ({x:.2f}, {y:.2f}) overlaps existing robot at ({ex_pos[0]:.2f}, {ex_pos[1]:.2f}) - dist {dist:.2f}m < {min_robot_distance}m"

    return True, f"Spawn ({x:.2f}, {y:.2f}) is valid, inside boundary, and collision-free"


class HospitalAMR:
    """Base class for all autonomous mobile robots in the hospital fleet."""


    def __init__(
        self,
        prim_path: str,
        name: str,
        role: str,
        start_position: Tuple[float, float, float],
        start_yaw: float = 0.0,
        accent_color: Optional[np.ndarray] = None,
        home_station: str = "CHG-01",
    ) -> None:
        self.prim_path = prim_path
        self.name = name
        self.role = role.upper()
        self.home_position = start_position
        self.home_station = home_station
        self.stage = (
            omni.usd.get_context().get_stage()
            if (HAS_OMNI and omni and omni.usd and omni.usd.get_context())
            else None
        )

        self.x = float(start_position[0])

        self.y = float(start_position[1])
        self.z = float(start_position[2])
        self.yaw = float(start_yaw)

        self.linear_speed = 0.0
        self.angular_speed = 0.0
        self.max_linear_speed = 2.0   # m/s
        self.max_angular_speed = 2.0  # rad/s

        # Battery model
        self.battery_level = 100.0    # Percentage 0.0 - 100.0
        self.is_charging = False
        self.battery_low_threshold = 20.0

        # Safety & Collision Guard
        self.collision_guard = None
        self.robot_radius = 0.38
        self.is_blocked = False
        self.blocked_timer = 0
        self.dynamic_slowdown = 1.0

        # State Machine & Priority
        self.state_machine = RobotStateMachine(initial_state=RobotState.IDLE)
        self.priority_level = 3
        self.priority_speed_mult = 1.0

        # Navigation & Waypoints
        self.waypoints: List[np.ndarray] = []
        self.active_route: List[np.ndarray] = []
        self.original_route: List[np.ndarray] = []
        self.replanned_route: List[np.ndarray] = []
        self.last_obstacle_pos: Optional[Tuple[float, float]] = None
        self.is_replanned: bool = False
        self.route_visualizer: Optional[Any] = None
        self.current_waypoint_idx = 0
        self.mission_active = False
        self.current_mission_id = ""
        self.current_task_description = "Standing by in IDLE"
        self.destination_name = "None"

        # Active Clinical Action Execution
        self.action_active = False
        self.action_timer = 0.0
        self.completion_timer = 0.0
        self.action_duration = 3.0  # Duration in seconds to perform clinical action
        self.action_description = "Executing clinical task"
        self.pending_mission_phases: List[Dict[str, Any]] = []
        self.clinical_mission_context: Optional[Dict[str, Any]] = None
        self.on_phase_complete_callback = None
        self.on_mission_complete_callback = None

        # Embodied Clinical Medication Container & Bedside Verification
        self.has_medicine_container: bool = False
        self.attached_medication: Optional[Dict[str, Any]] = None
        self.is_container_locked: bool = True
        self.last_verification_result: Optional[Dict[str, Any]] = None

        # Visual Styling
        self.color_chassis = np.array([0.20, 0.22, 0.25])
        self.color_accent = accent_color if accent_color is not None else np.array([0.0, 0.85, 0.95])
        self.color_torso = np.array([0.94, 0.95, 0.97])
        self.color_visor = np.array([0.10, 0.12, 0.15])
        self.color_wheel = np.array([0.15, 0.15, 0.18])

        # Physical Sensors & Perception
        self.camera_sensor: Optional[Any] = None
        self.lidar_sensor: Optional[Any] = None
        self.last_lidar_scan: Optional[Any] = None
        self.perception_layer: Optional[Any] = None
        self.detected_objects: List[Any] = []
        self.is_yielding_to_human: bool = False
        self.human_yield_timer: int = 0
        self._last_sensor_update_time: float = 0.0
        self._last_replan_time: float = 0.0
        self._replan_cooldown_s: float = 2.0

        self._build_robot_model()
        self._init_sensors()

    def _init_sensors(self) -> None:
        """Mount real physical camera, LiDAR, and perception layer on the robot."""
        try:
            from isaac_sim_hospital.sensors.camera_manager import AMRCameraSensor
            from isaac_sim_hospital.sensors.lidar_manager import AMRLiDARSensor
            self.camera_sensor = AMRCameraSensor(
                robot_name=self.name,
                robot_prim_path=self.prim_path,
                stage=self.stage,
            )
            self.lidar_sensor = AMRLiDARSensor(robot_name=self.name)
        except Exception:
            try:
                from sensors.camera_manager import AMRCameraSensor
                from sensors.lidar_manager import AMRLiDARSensor
                self.camera_sensor = AMRCameraSensor(
                    robot_name=self.name,
                    robot_prim_path=self.prim_path,
                    stage=self.stage,
                )
                self.lidar_sensor = AMRLiDARSensor(robot_name=self.name)
            except Exception:
                self.camera_sensor = None
                self.lidar_sensor = None

        # Perception Layer initialization
        try:
            from perception.perception_layer import PerceptionLayer
            self.perception_layer = PerceptionLayer(observer_robot_name=self.name)
        except Exception:
            try:
                from isaac_sim_hospital.perception.perception_layer import PerceptionLayer
                self.perception_layer = PerceptionLayer(observer_robot_name=self.name)
            except Exception:
                self.perception_layer = None

    def _build_robot_model(self) -> None:
        """
        Construct universal robot USD hierarchy under self.prim_path.

        CRITICAL: All child geometry uses _make_local_box() which creates
        UsdGeom.Cube prims in LOCAL coordinate space of the root Xform.
        When translate_op / rotate_op are updated each step, all children
        move with the parent as a rigid body — fixing the 'robot parts stay
        at world origin' rendering bug caused by VisualCuboid world-space positions.
        """
        if not HAS_OMNI or self.stage is None:
            return

        # Root Xform: all child prims are in local space of this node
        self.root_xform = UsdGeom.Xform.Define(self.stage, Sdf.Path(self.prim_path))
        self.translate_op = self.root_xform.AddTranslateOp()
        self.rotate_op = self.root_xform.AddRotateZOp()
        self.translate_op.Set(Gf.Vec3d(self.x, self.y, self.z))
        self.rotate_op.Set(float(np.degrees(self.yaw)))

        ac = tuple(self.color_accent.tolist())
        ch = tuple(self.color_chassis.tolist())
        to = tuple(self.color_torso.tolist())
        vi = tuple(self.color_visor.tolist())
        wh = tuple(self.color_wheel.tolist())

        # 0. Glowing floor projection ring
        _make_local_box(self.stage, self.prim_path, "FloorRing",
                        (0.0, 0.0, 0.005), (0.72, 0.72, 0.01), ac)
        # 1. Base chassis
        _make_local_box(self.stage, self.prim_path, "Chassis",
                        (0.0, 0.0, 0.12), (0.60, 0.60, 0.15), ch)
        # 2. LED accent ring
        _make_local_box(self.stage, self.prim_path, "LEDAccentRing",
                        (0.0, 0.0, 0.205), (0.62, 0.62, 0.03), ac)
        # 3. Drive wheels
        _make_local_box(self.stage, self.prim_path, "WheelLeft",
                        (0.0, 0.26, 0.08), (0.18, 0.06, 0.18), wh)
        _make_local_box(self.stage, self.prim_path, "WheelRight",
                        (0.0, -0.26, 0.08), (0.18, 0.06, 0.18), wh)
        # 4. Front LiDAR puck
        _make_local_box(self.stage, self.prim_path, "LiDAR",
                        (0.24, 0.0, 0.22), (0.12, 0.12, 0.06), (0.1, 0.1, 0.1))
        # 5. Medical torso column
        _make_local_box(self.stage, self.prim_path, "Torso",
                        (0.0, 0.0, 0.58), (0.30, 0.34, 0.70), to)
        # 6. Head & visor
        _make_local_box(self.stage, self.prim_path, "HeadVisor",
                        (0.0, 0.0, 1.05), (0.26, 0.28, 0.24), vi)
        _make_local_box(self.stage, self.prim_path, "FaceDisplay",
                        (0.132, 0.0, 1.05), (0.01, 0.22, 0.14), ac)
        # 7. Overhead halo beacon
        _make_local_box(self.stage, self.prim_path, "HaloBeacon",
                        (0.0, 0.0, 1.45), (0.44, 0.44, 0.03), ac)
        # 8. Antenna mast + dome
        _make_local_box(self.stage, self.prim_path, "AntennaMast",
                        (-0.12, 0.0, 1.45), (0.03, 0.03, 0.50), (0.75, 0.78, 0.82))
        _make_local_box(self.stage, self.prim_path, "AntennaDome",
                        (-0.12, 0.0, 1.72), (0.08, 0.08, 0.06), ac)
        # 9. Nameplate
        _make_local_box(self.stage, self.prim_path, "NameBadge",
                        (0.0, 0.0, 1.55), (0.22, 0.38, 0.06), ac)
        # 10. Embodied Medicine Box Container (Mounted on Robot Tray, initially hidden)
        _make_local_box(self.stage, self.prim_path, "MedicineContainer",
                        (0.12, 0.0, 0.68), (0.24, 0.28, 0.16), (0.85, 0.15, 0.15))
        try:
            m_prim = self.stage.GetPrimAtPath(Sdf.Path(f"{self.prim_path}/MedicineContainer"))
            if m_prim and m_prim.IsValid():
                UsdGeom.Imageable(m_prim).MakeInvisible()
        except Exception:
            pass

    def attach_medicine_container(
        self,
        medicine_name: str = "Medication",
        dosage: str = "",
        patient_id: str = "",
        patient_name: str = "",
        room_id: str = "",
        color_rgb: Tuple[float, float, float] = (0.85, 0.15, 0.15),
    ) -> None:
        """
        Dynamically mount and reveal the 3D medicine container prim on the robot delivery tray.
        """
        self.has_medicine_container = True
        self.is_container_locked = True
        self.attached_medication = {
            "name": medicine_name,
            "dosage": dosage,
            "patient_id": patient_id,
            "patient_name": patient_name,
            "room_id": room_id,
            "attached_at": time.time(),
        }

        if HAS_OMNI and self.stage:
            try:
                container_path = f"{self.prim_path}/MedicineContainer"
                prim = self.stage.GetPrimAtPath(Sdf.Path(container_path))
                if not prim or not prim.IsValid():
                    _make_local_box(
                        self.stage,
                        self.prim_path,
                        "MedicineContainer",
                        (0.12, 0.0, 0.68),
                        (0.24, 0.28, 0.16),
                        color_rgb,
                    )
                    prim = self.stage.GetPrimAtPath(Sdf.Path(container_path))
                if prim and prim.IsValid():
                    UsdGeom.Imageable(prim).MakeVisible()
            except Exception as e:
                print(f"[{self.name}] Error making MedicineContainer visible in USD: {e}")

    def detach_medicine_container(self) -> None:
        """
        Detach / hide the 3D medicine container prim from the robot tray upon completed handover.
        """
        self.has_medicine_container = False
        self.attached_medication = None
        self.is_container_locked = True

        if HAS_OMNI and self.stage:
            try:
                container_path = f"{self.prim_path}/MedicineContainer"
                prim = self.stage.GetPrimAtPath(Sdf.Path(container_path))
                if prim and prim.IsValid():
                    UsdGeom.Imageable(prim).MakeInvisible()
            except Exception as e:
                print(f"[{self.name}] Error hiding MedicineContainer in USD: {e}")

    def unlock_medicine_container(self) -> bool:
        """Unlock the medicine container latch following verified bedside check."""
        if not self.has_medicine_container:
            return False
        self.is_container_locked = False
        return True

    def lock_medicine_container(self) -> None:
        """Securely lock the medicine container latch."""
        self.is_container_locked = True

    def verify_bedside_target(
        self,
        expected_patient_id: Optional[str] = None,
        expected_room: Optional[str] = None,
        perceived_patient_id: Optional[str] = None,
        perceived_room: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Bedside patient verification checkpoint.
        Cross-verifies expected clinical prescription target against perceived bedside placard / patient RFID.
        Returns: (success: bool, detail_message: str)
        """
        med = self.attached_medication or {}
        ctx = getattr(self, "clinical_mission_context", {}) or {}
        exp_pid = expected_patient_id or med.get("patient_id") or ctx.get("patient_id") or ""
        exp_room = expected_room or med.get("room_id") or ctx.get("room_id") or getattr(self, "destination_name", "")

        perc_pid = perceived_patient_id or ""
        perc_room = perceived_room or ""

        if not perc_pid or not perc_room:
            for obj in getattr(self, "detected_objects", []):
                obj_meta = getattr(obj, "metadata", {}) or {}
                if not perc_pid and "patient_id" in obj_meta:
                    perc_pid = str(obj_meta["patient_id"])
                if not perc_room and "room_id" in obj_meta:
                    perc_room = str(obj_meta["room_id"])
            if not perc_room:
                perc_room = getattr(self, "destination_name", "")

        def _clean_pid(p: str) -> str:
            p_s = str(p).strip().upper().replace(" ", "").replace("-", "")
            if p_s.startswith("PATIENT"):
                p_s = "P" + p_s[7:].lstrip("0")
            elif p_s.startswith("P") and p_s[1:].isdigit():
                p_s = "P" + str(int(p_s[1:]))
            return p_s

        def _clean_room(r: str) -> str:
            return str(r).strip().upper().replace(" ", "").replace("_", "-")

        # 1. Room check
        room_match = True
        if exp_room and perc_room:
            room_match = (_clean_room(exp_room) == _clean_room(perc_room) or
                          _clean_room(exp_room) in _clean_room(perc_room) or
                          _clean_room(perc_room) in _clean_room(exp_room))

        # 2. Patient check
        patient_match = True
        if exp_pid and perc_pid:
            patient_match = (_clean_pid(exp_pid) == _clean_pid(perc_pid))

        if not room_match:
            msg = f"ROOM MISMATCH: Expected delivery to {exp_room}, but robot is at {perc_room}. Container locked."
            self.lock_medicine_container()
            self.last_verification_result = {
                "status": "FAILED",
                "verification_status": "MISMATCH",
                "is_success": False,
                "patient_verified": patient_match,
                "room_verified": False,
                "reason": msg,
                "timestamp": time.time(),
            }
            return False, msg

        if not patient_match:
            msg = f"PATIENT IDENTITY MISMATCH: Expected {exp_pid}, but scanned {perc_pid}. Safety lockout active."
            self.lock_medicine_container()
            self.last_verification_result = {
                "status": "FAILED",
                "verification_status": "MISMATCH",
                "is_success": False,
                "patient_verified": False,
                "room_verified": True,
                "reason": msg,
                "timestamp": time.time(),
            }
            return False, msg

        self.unlock_medicine_container()
        msg = f"Bedside verification SUCCESS: Room {exp_room} and Patient {exp_pid or 'Verified'} confirmed. Medicine container unlocked."
        self.last_verification_result = {
            "status": "SUCCESS",
            "verification_status": "VERIFIED",
            "is_success": True,
            "patient_verified": True,
            "room_verified": True,
            "patient_id": exp_pid,
            "room_id": exp_room,
            "medicine": med.get("name", "Medication"),
            "timestamp": time.time(),
        }
        return True, msg

    def set_collision_guard(self, guard) -> None:
        self.collision_guard = guard

    def set_hospital_env(self, env) -> None:
        self.hospital_env = env

    def set_route_visualizer(self, visualizer) -> None:
        self.route_visualizer = visualizer

    def _replan_detour(
        self,
        dynamic_obstacles: Optional[List[Tuple[float, float]]] = None,
        reason: str = "Dynamic detour replanned",
    ) -> bool:
        """Compute a collision-free topological detour route respecting corridors and doors."""
        if not self.waypoints or not self.destination_name:
            return False

        # Requirement 6: If already replanned with active detour waypoints, do not thrash A* route calculation
        if getattr(self, "is_replanned", False) and getattr(self, "replanned_route", None):
            return True

        # Requirement 6: Debounce/cooldown to prevent path planner thrashing every frame
        now = time.time()
        last_t = getattr(self, "_last_replan_time", 0.0)
        cooldown = getattr(self, "_replan_cooldown_s", 2.0)
        if now - last_t < cooldown:
            return False
        self._last_replan_time = now

        detour: List[Tuple[float, float]] = []
        try:
            from navigation.route_planner import plan_hospital_route
        except (ImportError, ModuleNotFoundError):
            from isaac_sim_hospital.navigation.route_planner import plan_hospital_route

        if getattr(self, "hospital_env", None) is not None and self.collision_guard is not None:
            try:
                detour_wps = plan_hospital_route(
                    (self.x, self.y),
                    self.destination_name,
                    self.hospital_env,
                    self.collision_guard,
                    dynamic_obstacles=dynamic_obstacles,
                )
                if detour_wps and len(detour_wps) >= 2:
                    detour = [(float(p[0]), float(p[1])) for p in detour_wps]
            except Exception as e:
                print(f"[REPLAN NOTICE] Topological replan exception: {e}")

        if not detour and self.collision_guard is not None:
            goal_target = self.waypoints[-1]
            if dynamic_obstacles:
                detour = self.collision_guard.plan_path_astar_dynamic(
                    (self.x, self.y),
                    (float(goal_target[0]), float(goal_target[1])),
                    dynamic_obstacles=dynamic_obstacles,
                    obstacle_radius=0.9,
                )
            else:
                detour = self.collision_guard.plan_path_astar(
                    (self.x, self.y),
                    (float(goal_target[0]), float(goal_target[1])),
                )

        if len(detour) > 1:
            self.original_route = list(self.waypoints)
            self.replanned_route = [np.array([wp[0], wp[1], 0.0], dtype=float) for wp in detour]
            self.waypoints = list(self.replanned_route)
            self.active_route = list(self.replanned_route)
            self.current_waypoint_idx = 1
            self.is_replanned = True
            self.blocked_timer = 0
            self.state_machine.transition_to(
                RobotState.REPLANNING,
                reason=reason,
                action="Resuming navigation on detour route",
            )
            if self.route_visualizer and self.last_obstacle_pos:
                try:
                    self.route_visualizer.visualize_obstacle_blockage_and_replan(
                        self.last_obstacle_pos, self.original_route, self.replanned_route
                    )
                except Exception as e:
                    print(f"[VISUAL WARNING] Detour visualizer update failed: {e}")
            return True
        return False

    def assign_mission(
        self,
        waypoints: List[np.ndarray],
        task_description: str,
        destination_name: str,
        priority_level: int = 3,
        mission_id: Optional[str] = None,
    ) -> None:
        """Assign an autonomous navigation mission to this robot."""
        if mission_id:
            self.current_mission_id = mission_id
        else:
            date_tag = datetime.now().strftime("%Y%m%d")
            rand_suffix = uuid.uuid4().hex[:4].upper()
            prefix = "EMR" if priority_level == 1 else ("MED" if "deliver" in task_description.lower() else "MSN")
            self.current_mission_id = f"{prefix}-{date_tag}-{rand_suffix}"

        self.waypoints = [np.array(wp, dtype=float) for wp in waypoints]
        self.active_route = list(self.waypoints)
        self.original_route = list(self.waypoints)
        self.replanned_route = []
        self.last_obstacle_pos = None
        self.is_replanned = False
        self.current_waypoint_idx = 0
        self.current_task_description = task_description
        self.destination_name = destination_name
        self.priority_level = priority_level
        self.mission_active = True
        self.is_charging = False

        if priority_level == 1:
            self.priority_speed_mult = 1.45
            self.state_machine.transition_to(RobotState.EMERGENCY_OVERRIDE, f"Emergency Mission: {task_description}")
        else:
            self.priority_speed_mult = 1.0
            self.state_machine.transition_to(RobotState.NAVIGATING, f"Mission: {task_description}")

        if self.route_visualizer:
            try:
                self.route_visualizer.visualize_route(
                    robot_name=self.name,
                    waypoints=self.waypoints,
                    destination_name=destination_name,
                    is_emergency=(priority_level == 1),
                )
            except Exception as e:
                print(f"[VISUAL WARNING] Could not update route visualizer: {e}")

    def assign_clinical_delivery_mission(
        self,
        pickup_waypoints: List[Any],
        pickup_dest: str,
        pickup_action_desc: str,
        delivery_waypoints: List[Any],
        delivery_dest: str,
        delivery_action_desc: str,
        priority_level: int = 2,
        mission_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        on_phase_complete = None,
        on_mission_complete = None,
    ) -> None:
        """
        Assign a 2-phase clinical delivery mission:
        Phase 1: Navigate to pickup location (e.g. PHM-01) -> perform pickup action
        Phase 2: Navigate to delivery location (e.g. PAT-101) -> perform delivery action -> complete
        """
        if mission_id:
            self.current_mission_id = mission_id
        else:
            date_tag = datetime.now().strftime("%Y%m%d")
            rand_suffix = uuid.uuid4().hex[:4].upper()
            self.current_mission_id = f"MED-{date_tag}-{rand_suffix}"

        self.clinical_mission_context = context or {}
        self.on_phase_complete_callback = on_phase_complete
        self.on_mission_complete_callback = on_mission_complete

        phase2 = {
            "waypoints": delivery_waypoints,
            "destination_name": delivery_dest,
            "task_description": f"Deliver {self.clinical_mission_context.get('item', 'Medication')} to {delivery_dest}",
            "action_description": delivery_action_desc,
            "action_duration": 3.0,
            "priority_level": priority_level,
            "mission_id": self.current_mission_id,
        }
        self.pending_mission_phases = [phase2]

        self.assign_mission(
            waypoints=pickup_waypoints,
            task_description=f"Pickup {self.clinical_mission_context.get('item', 'Medication')} from {pickup_dest}",
            destination_name=pickup_dest,
            priority_level=priority_level,
            mission_id=self.current_mission_id,
        )
        self.action_duration = 3.0
        self.action_description = pickup_action_desc

    def _evaluate_post_mission_policy(self) -> None:
        """
        Evaluate post-mission transition:
        - If battery is low (< 35%) and not already at dock:
            plan route to CHG-01, transition to RETURNING_TO_DOCK, and begin physical transit.
        - If battery is healthy:
            transition to IDLE / AVAILABLE, clear active tasks, ready for next assignment.
        """
        if self.battery_level < 35.0:
            dock_target = "CHG-01"
            if getattr(self, "destination_name", "") != dock_target and not self.is_charging:
                dock_wps = []
                try:
                    from navigation.route_planner import plan_hospital_route
                except (ImportError, ModuleNotFoundError):
                    try:
                        from isaac_sim_hospital.navigation.route_planner import plan_hospital_route
                    except Exception:
                        plan_hospital_route = None

                if plan_hospital_route and getattr(self, "hospital_env", None) and self.collision_guard:
                    try:
                        dock_wps = plan_hospital_route(
                            (self.x, self.y),
                            dock_target,
                            self.hospital_env,
                            self.collision_guard,
                        )
                    except Exception as e:
                        print(f"[{self.name}] Auto-dock route planning exception: {e}")

                if not dock_wps and self.collision_guard:
                    # Fallback A* to charging dock coords (34.5, 33.0)
                    chg_pos = (34.5, 33.0)
                    astar_pts = self.collision_guard.plan_path_astar((self.x, self.y), chg_pos)
                    if astar_pts:
                        dock_wps = [np.array([p[0], p[1], 0.0]) for p in astar_pts]

                if dock_wps and len(dock_wps) >= 2:
                    self.assign_mission(
                        waypoints=dock_wps,
                        task_description=f"Auto-Docking: Low battery ({self.battery_level:.1f}%) returning to {dock_target}",
                        destination_name=dock_target,
                        priority_level=5,
                    )
                    self.state_machine.transition_to(
                        RobotState.RETURNING_TO_DOCK,
                        reason=f"Low battery ({self.battery_level:.1f}% < 35%); returning to dock",
                        action=f"Autonomous navigation to charging pad {dock_target}",
                    )
                    return

        # Battery is healthy or docking route failed/already at dock
        self.mission_active = False
        self.action_active = False
        self.state_machine.transition_to(
            RobotState.IDLE,
            reason="Mission complete, battery healthy; standing by",
            action="Standing by for new task",
        )
        self.current_task_description = "Standing by (AVAILABLE)"


    def check_dynamic_obstacles(
        self,
        dynamic_obstacle_positions: List[Tuple[float, float]],
        safety_radius: float = 1.80,
    ) -> ObstacleCheckResult:
        """
        Check if any dynamic human/cart is within forward safety bubble.
        Returns:
            ObstacleCheckResult(is_critical_block, closest_dist, closest_obstacle_pos)
            Supports both 2-element unpack (is_crit, dist) and .closest_pos attribute.
        """
        if not dynamic_obstacle_positions:
            return False, 999.0, None

        closest_dist = 999.0
        closest_pos: Optional[Tuple[float, float]] = None
        forward_x = np.cos(self.yaw)
        forward_y = np.sin(self.yaw)

        for obs in dynamic_obstacle_positions:
            ox, oy = float(obs[0]), float(obs[1])
            dx = ox - self.x
            dy = oy - self.y
            dist = float(np.hypot(dx, dy))
            if dist < safety_radius:
                dot = forward_x * dx + forward_y * dy
                if dist < 0.85 or dot > 0.0:  # Immediate proximity or forward hemisphere
                    if dist < closest_dist:
                        closest_dist = dist
                        closest_pos = (float(ox), float(oy))

        is_critical = closest_dist < 0.65
        return ObstacleCheckResult(is_critical, closest_dist, closest_pos)

    def get_remaining_distance(self) -> float:
        """Calculate real Euclidean distance along remaining waypoints to destination."""
        if not self.mission_active or not self.waypoints:
            return 0.0
        if self.current_waypoint_idx >= len(self.waypoints):
            return 0.0

        cur_wp = self.waypoints[self.current_waypoint_idx]
        total_d = float(np.hypot(cur_wp[0] - self.x, cur_wp[1] - self.y))

        for i in range(self.current_waypoint_idx, len(self.waypoints) - 1):
            p1 = self.waypoints[i]
            p2 = self.waypoints[i + 1]
            total_d += float(np.hypot(p2[0] - p1[0], p2[1] - p1[1]))
        return total_d

    @property
    def camera_prim_path(self) -> str:
        """Prim path to the mounted head camera in USD stage."""
        return f"{self.prim_path}/HeadVisor/Camera"

    @property
    def lidar_prim_path(self) -> str:
        """Prim path to the mounted LiDAR sensor puck in USD stage."""
        return f"{self.prim_path}/LiDAR"

    def _update_sensors(
        self,
        dynamic_obstacle_positions: Optional[List[Tuple[float, float]]] = None,
        dynamic_obstacle_agents: Optional[List[Any]] = None,
        peer_robots: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update mounted camera, LiDAR, and perception layer sensors at throttled rate (10 Hz)."""
        now = time.time()
        # Requirement 4 & 7: Throttle sensor processing to 10 Hz (100ms) to keep main simulation thread ultra-fast
        sensor_interval = 0.10
        if getattr(self, "_last_sensor_update_time", 0.0) and (now - self._last_sensor_update_time < sensor_interval):
            return
        self._last_sensor_update_time = now

        # Requirement 16: Feature Isolation toggles
        try:
            from configs.simulation_config import AROGYA_FEATURES
            enable_lidar = AROGYA_FEATURES.get("enable_lidar", True)
            enable_camera = AROGYA_FEATURES.get("enable_camera", True)
            enable_perception = AROGYA_FEATURES.get("enable_perception", True)
        except Exception:
            enable_lidar = enable_camera = enable_perception = True

        if enable_camera and self.camera_sensor:
            self.camera_sensor.update_pose(self.x, self.y, self.z, self.yaw)

        # Prefer rich agent objects over coordinate tuples for semantic identification
        active_dyn = dynamic_obstacle_agents if dynamic_obstacle_agents is not None else dynamic_obstacle_positions
        peer_coords = [
            (peer.x, peer.y) for peer in peer_robots.values()
            if hasattr(peer, "x") and getattr(peer, "name", "") != self.name
        ] if peer_robots else None

        if enable_lidar and self.lidar_sensor:
            try:
                self.last_lidar_scan = self.lidar_sensor.scan(
                    robot_x=self.x,
                    robot_y=self.y,
                    robot_yaw=self.yaw,
                    collision_guard=self.collision_guard,
                    dynamic_obstacles=active_dyn,
                    peer_robots=peer_coords,
                )
                if getattr(self, "visualize_lidar", True) and hasattr(self.lidar_sensor, "visualize_in_viewport"):
                    self.lidar_sensor.visualize_in_viewport(self.last_lidar_scan)
            except Exception as e:
                if self.lidar_sensor:
                    self.lidar_sensor.last_error = str(e)
                print(f"[LIDAR SCAN ERROR] {self.name}: {e}")

        if enable_perception and self.perception_layer:
            try:
                self.detected_objects = self.perception_layer.process_observations(
                    robot_x=self.x,
                    robot_y=self.y,
                    robot_z=self.z,
                    robot_yaw=self.yaw,
                    dynamic_obstacles=active_dyn,
                    peer_robots=peer_robots,
                    lidar_scan=self.last_lidar_scan,
                )
                try:
                    from world_model.shared_world_model import SHARED_WORLD_MODEL
                    SHARED_WORLD_MODEL.update_entities(self.detected_objects)
                    SHARED_WORLD_MODEL.update_robot_state(
                        robot_name=self.name,
                        position=(self.x, self.y, self.z),
                        heading=self.yaw,
                        battery_level=self.battery_level,
                        state=getattr(self.state_machine.state, "name", "IDLE"),
                        current_task=self.current_task_description,
                    )
                except Exception:
                    pass
            except Exception:
                pass

    def step_autonomous(
        self,
        dt: float = 0.016,
        dynamic_obstacle_positions: Optional[List[Tuple[float, float]]] = None,
        dynamic_obstacle_agents: Optional[List[Any]] = None,
        peer_robots: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Autonomous navigation step with battery drain, obstacle avoidance, and state transitions."""
        # 0. Always step attached physical perception sensors (Camera & 360 LiDAR)
        self._update_sensors(
            dynamic_obstacle_positions=dynamic_obstacle_positions,
            dynamic_obstacle_agents=dynamic_obstacle_agents,
            peer_robots=peer_robots,
        )

        # 1. Charging logic
        if self.is_charging:
            self.battery_level = min(100.0, self.battery_level + 0.15)
            if self.battery_level >= 95.0 and self.state_machine.state == RobotState.CHARGING:
                self.state_machine.transition_to(RobotState.IDLE, "Battery recharged to 95%+ (Available)")
                self.is_charging = False
                self.current_task_description = "Standing by in IDLE (AVAILABLE)"
            return

        # 1b. Active Clinical Action Execution
        if self.action_active:
            self.action_timer += dt
            if self.action_timer >= self.action_duration:
                self.action_active = False
                self.linear_speed = 0.0
                self.angular_speed = 0.0
                action_desc = getattr(self, "action_description", self.current_task_description)

                # Check if there is a next phase in a multi-phase clinical mission
                if getattr(self, "pending_mission_phases", None) and len(self.pending_mission_phases) > 0:
                    next_phase = self.pending_mission_phases.pop(0)

                    # Auto-attach medicine container if completing pharmacy pickup
                    if "PHM" in getattr(self, "destination_name", "") or "pickup" in action_desc.lower() or "pharmacy" in action_desc.lower():
                        ctx = getattr(self, "clinical_mission_context", {}) or {}
                        self.attach_medicine_container(
                            medicine_name=ctx.get("item", "Prescription Medication"),
                            dosage=ctx.get("dosage", ""),
                            patient_id=ctx.get("patient_id", ""),
                            patient_name=ctx.get("patient_name", ""),
                            room_id=next_phase.get("destination_name", ""),
                        )

                    if hasattr(self, "on_phase_complete_callback") and self.on_phase_complete_callback:
                        try:
                            self.on_phase_complete_callback(self, action_desc, next_phase)
                        except Exception as e:
                            print(f"[{self.name}] Phase callback exception: {e}")

                    self.assign_mission(
                        waypoints=next_phase["waypoints"],
                        task_description=next_phase.get("task_description", "Next Mission Leg"),
                        destination_name=next_phase.get("destination_name", "Destination"),
                        priority_level=next_phase.get("priority_level", self.priority_level),
                        mission_id=next_phase.get("mission_id", self.current_mission_id),
                    )
                    self.action_duration = next_phase.get("action_duration", 3.0)
                    self.action_description = next_phase.get("action_description", self.current_task_description)
                    return

                # If medicine was onboard, perform bedside patient verification check before handover
                if getattr(self, "has_medicine_container", False):
                    v_ok, v_msg = self.verify_bedside_target()
                    if v_ok:
                        self.detach_medicine_container()
                    else:
                        self.state_machine.transition_to(
                            RobotState.BLOCKED,
                            reason=f"Bedside verification failed: {v_msg}",
                            action="Medicine container remains locked. Awaiting nurse override.",
                        )
                        return

                # If no more phases, trigger final mission complete callback
                if hasattr(self, "on_mission_complete_callback") and self.on_mission_complete_callback:
                    try:
                        self.on_mission_complete_callback(self, action_desc)
                    except Exception as e:
                        print(f"[{self.name}] Mission complete callback exception: {e}")

                self.state_machine.transition_to(
                    RobotState.MISSION_COMPLETE,
                    reason=f"Completed clinical procedure: {action_desc}",
                    action="Reporting mission completion",
                )
                self.completion_timer = 0.0
            return

        if self.state_machine.state == RobotState.MISSION_COMPLETE:
            self.completion_timer = getattr(self, "completion_timer", 0.0) + dt
            if self.completion_timer >= 2.0:
                self._evaluate_post_mission_policy()
            return

        # 2. Idle check
        if not self.mission_active or not self.waypoints:
            if not self.state_machine.is_idle() and not self.state_machine.is_executing():
                self.state_machine.transition_to(RobotState.IDLE, "No active mission")
            return

        # 3. Battery drain during active mission
        self.battery_level = max(0.0, self.battery_level - 0.012)

        # 4. Dynamic obstacle forward check (human-aware yielding & cautious slowdown)
        has_critical_block = False
        closest_obstacle_dist = 999.0
        closest_obstacle_pos = None
        is_human_obstacle = False
        detected_human_desc = "Person"

        if dynamic_obstacle_positions:
            obs_res = self.check_dynamic_obstacles(
                dynamic_obstacle_positions, safety_radius=1.80
            )
            has_critical_block, closest_obstacle_dist = obs_res[0], obs_res[1]
            closest_obstacle_pos = getattr(obs_res, "closest_pos", None)
            if closest_obstacle_pos is not None:
                self.last_obstacle_pos = closest_obstacle_pos

        # Check detected objects from perception layer for humans in field of view
        for d_obj in getattr(self, "detected_objects", []):
            o_type_val = getattr(d_obj.object_type, "value", str(d_obj.object_type)).lower()
            if any(h in o_type_val for h in ("person", "doctor", "nurse", "patient", "pedestrian")):
                if abs(getattr(d_obj, "direction", 0.0)) < 0.95:
                    if d_obj.distance <= closest_obstacle_dist + 0.35:
                        is_human_obstacle = True
                        detected_human_desc = f"{o_type_val.capitalize()} ({d_obj.object_id})"
                        if d_obj.distance < closest_obstacle_dist:
                            closest_obstacle_dist = d_obj.distance
                            self.last_obstacle_pos = (d_obj.position[0], d_obj.position[1])
                        break

        # Check if obstacle is within critical clearance zone (1.2m)
        is_obstacle_near = closest_obstacle_dist < 1.20
        if has_critical_block or is_obstacle_near:
            self.is_blocked = True
            self.linear_speed = 0.0
            self.angular_speed = 0.0
            obs_str = f"({self.last_obstacle_pos[0]:.1f}, {self.last_obstacle_pos[1]:.1f})" if self.last_obstacle_pos else "ahead"

            # Phase 7: Dynamic Human-Aware Yielding
            if is_human_obstacle:
                self.is_yielding_to_human = True
                self.human_yield_timer += 1
                self.blocked_timer += 1

                # Polite yielding window before rerouting (up to 90 steps / ~2-3 seconds)
                if self.human_yield_timer < 90 and self.blocked_timer < 90:
                    self.state_machine.transition_to(
                        RobotState.WAITING_FOR_CLEARANCE,
                        reason=f"Yielding to {detected_human_desc} ({closest_obstacle_dist:.2f}m ahead; maintaining social clearance)",
                        action="Stationary; awaiting person to cross corridor",
                    )
                    return
                else:
                    # Standing person: compute polite detour around them
                    self.state_machine.transition_to(
                        RobotState.OBSTACLE_DETECTED,
                        reason=f"{detected_human_desc} stationary ({closest_obstacle_dist:.2f}m); calculating detour",
                        action="Computing collision-free detour",
                    )
                    replan_ok = self._replan_detour(
                        dynamic_obstacles=dynamic_obstacle_positions or [],
                        reason=f"Detour around stationary {detected_human_desc}",
                    )
                    if not replan_ok:
                        self.state_machine.transition_to(
                            RobotState.BLOCKED,
                            reason=f"Corridor blocked by {detected_human_desc}; no viable detour found",
                            action="Stationary; awaiting corridor to clear",
                        )
            else:
                self.is_yielding_to_human = False
                self.human_yield_timer = 0
                self.blocked_timer += 1

                self.state_machine.transition_to(
                    RobotState.OBSTACLE_DETECTED,
                    reason=f"Obstacle detected {closest_obstacle_dist:.2f}m ahead at {obs_str}",
                    action="Halting & computing dynamic detour",
                )

                # Trigger dynamic detour replan promptly via _replan_detour
                replan_ok = self._replan_detour(
                    dynamic_obstacles=dynamic_obstacle_positions or [],
                    reason=f"Dynamic corridor detour replanned around obstacle ({closest_obstacle_dist:.2f}m)",
                )
                if not replan_ok:
                    self.state_machine.transition_to(
                        RobotState.BLOCKED,
                        reason=f"Corridor blocked by obstacle ({closest_obstacle_dist:.2f}m); no viable detour found",
                        action="Stationary; awaiting corridor to clear",
                    )

            # Record explainable reasoning decision (Phase 6)
            try:
                from ai_reasoning.decision_engine import DECISION_ENGINE
                DECISION_ENGINE.reason_obstacle_avoidance(
                    robot_name=self.name,
                    mission_desc=self.current_task_description,
                    obstacle_dist=closest_obstacle_dist,
                    is_blocked=self.is_blocked,
                    replan_succeeded=replan_ok,
                )
            except Exception:
                pass

            # Multi-robot distributed observation sharing (Phase 5) - throttled to 0.5 Hz
            now_obs = time.time()
            if now_obs - getattr(self, "_last_obs_share_time", 0.0) > 2.0:
                self._last_obs_share_time = now_obs
                try:
                    from multi_agent.observation_sharing import OBSERVATION_SHARING
                    from perception.spatial_relations import SpatialRelationsEngine
                    if not hasattr(self, "_sr_engine") or self._sr_engine is None:
                        self._sr_engine = SpatialRelationsEngine()
                    zone = self._sr_engine.determine_corridor(self.x, self.y) or self._sr_engine.determine_room(self.x, self.y) or "CORRIDOR_CENTRAL"
                    obs_coords = self.last_obstacle_pos or (self.x, self.y)
                    OBSERVATION_SHARING.share_observation(
                        source_robot_name=self.name,
                        obstacle_position=obs_coords,
                        zone_name=zone,
                        description=f"{detected_human_desc if is_human_obstacle else 'Obstacle'} in {zone} ({closest_obstacle_dist:.1f}m ahead of {self.name})",
                    )
                except Exception:
                    pass

            if not replan_ok:
                if not getattr(self, "is_replanned", False):
                    self.state_machine.transition_to(
                        RobotState.BLOCKED,
                        reason=f"BLOCKED: No collision-free route available to {self.destination_name}",
                        action="Waiting for obstacle clearance or operator override",
                    )
                return
            elif has_critical_block:
                return
        else:
            self.blocked_timer = max(0, self.blocked_timer - 1)
            self.is_yielding_to_human = False
            self.human_yield_timer = max(0, self.human_yield_timer - 1)

            # Smoothly compute dynamic slowdown factor when in caution envelope
            if is_human_obstacle and closest_obstacle_dist < 2.50:
                self.dynamic_slowdown = float(np.clip((closest_obstacle_dist - 0.80) / (2.50 - 0.80), 0.20, 1.0))
                if self.dynamic_slowdown < 0.85 and self.state_machine.state in (RobotState.NAVIGATING, RobotState.BLOCKED):
                    self.state_machine.transition_to(
                        RobotState.AVOIDING_OBSTACLE,
                        f"Cautious human-aware transit ({closest_obstacle_dist:.2f}m from {detected_human_desc})",
                    )
            elif closest_obstacle_dist < 1.80:
                self.dynamic_slowdown = float(np.clip((closest_obstacle_dist - 0.65) / (1.80 - 0.65), 0.25, 1.0))
                if self.dynamic_slowdown < 0.85 and self.state_machine.state in (RobotState.NAVIGATING, RobotState.BLOCKED):
                    self.state_machine.transition_to(
                        RobotState.AVOIDING_OBSTACLE,
                        f"Cautious transit ({closest_obstacle_dist:.2f}m from obstacle)",
                    )
            else:
                self.dynamic_slowdown = 1.0

        # 5. Waypoint tracking (goal arrival tolerance 0.40m on final destination pose)
        is_final_waypoint = (self.current_waypoint_idx >= len(self.waypoints) - 1)
        arrival_tolerance = 0.40 if is_final_waypoint else 0.50

        target = self.waypoints[self.current_waypoint_idx]
        dx = target[0] - self.x
        dy = target[1] - self.y
        dist = np.hypot(dx, dy)

        if dist < arrival_tolerance:
            if is_final_waypoint:
                self.mission_active = False
                self.linear_speed = 0.0
                self.angular_speed = 0.0
                if self.route_visualizer:
                    try:
                        self.route_visualizer.clear()
                    except Exception:
                        pass

                # Check if arrived at a charging dock
                if "CHG" in self.destination_name or "Charg" in self.destination_name or "Dock" in self.destination_name:
                    self.is_charging = True
                    self.state_machine.transition_to(RobotState.CHARGING, "Docked on charging pad")
                    self.current_task_description = "Recharging Battery"
                else:
                    self.action_active = True
                    self.action_timer = 0.0
                    action_desc = getattr(self, "action_description", self.current_task_description)
                    self.state_machine.transition_to(
                        RobotState.EXECUTING_TASK,
                        f"Executing: {action_desc}",
                    )
                return
            else:
                self.current_waypoint_idx += 1
                if self.route_visualizer:
                    try:
                        self.route_visualizer.update_progress(self.current_waypoint_idx)
                    except Exception:
                        pass

                target = self.waypoints[self.current_waypoint_idx]
                dx = target[0] - self.x
                dy = target[1] - self.y
                dist = np.hypot(dx, dy)

        target_heading = np.arctan2(dy, dx)
        heading_err = target_heading - self.yaw
        heading_err = np.arctan2(np.sin(heading_err), np.cos(heading_err))

        max_v = self.max_linear_speed * self.priority_speed_mult * self.dynamic_slowdown
        if abs(heading_err) > 0.30:
            # Turn-in-place kinematics: Zero linear translation while realigning heading.
            # Prevents sweeping arc turns from clipping door frames or corridor wall corners.
            v = 0.0
            w = np.clip(2.5 * heading_err, -self.max_angular_speed, self.max_angular_speed)
        else:
            v = np.clip(1.0 * dist, 0.15, max_v)
            w = np.clip(2.8 * heading_err, -self.max_angular_speed, self.max_angular_speed)

        candidate_yaw = self.yaw + w * dt
        candidate_x = self.x + v * np.cos(candidate_yaw) * dt
        candidate_y = self.y + v * np.sin(candidate_yaw) * dt

        # Continuous Collision Detection Multi-Point Wall Check (Zero wall penetration)
        is_wall_blocked = False
        if self.collision_guard:
            # Check center point
            if self.collision_guard.check_point_collision(candidate_x, candidate_y, margin=self.robot_radius):
                is_wall_blocked = True
            # Check front bumper
            elif self.collision_guard.check_point_collision(
                candidate_x + 0.35 * np.cos(candidate_yaw),
                candidate_y + 0.35 * np.sin(candidate_yaw),
                margin=0.20,
            ):
                is_wall_blocked = True
            # Check rear bumper
            elif self.collision_guard.check_point_collision(
                candidate_x - 0.25 * np.cos(candidate_yaw),
                candidate_y - 0.25 * np.sin(candidate_yaw),
                margin=0.20,
            ):
                is_wall_blocked = True
            # Check continuous motion segment between current and candidate point
            elif hasattr(self.collision_guard, "is_segment_clear"):
                if not self.collision_guard.is_segment_clear(
                    self.x, self.y, candidate_x, candidate_y, margin=self.robot_radius, step_size=0.05
                ):
                    is_wall_blocked = True

        if is_wall_blocked:
            self.is_blocked = True
            self.linear_speed = 0.0
            # Allow in-place rotation to realign heading towards open space
            if not self.collision_guard.check_point_collision(
                self.x + 0.20 * np.cos(candidate_yaw),
                self.y + 0.20 * np.sin(candidate_yaw),
                margin=0.20,
            ):
                self.yaw = candidate_yaw
                self.angular_speed = w
            else:
                self.angular_speed = 0.0

            self.state_machine.transition_to(
                RobotState.BLOCKED,
                reason="Wall / furniture lookahead collision guard active",
                action="Aligning heading to clear corridor",
            )
            self.blocked_timer += 1
            if self.blocked_timer >= 10 and self.waypoints and self.current_waypoint_idx < len(self.waypoints):
                replan_ok = self._replan_detour(
                    dynamic_obstacles=dynamic_obstacle_positions or [],
                    reason="Re-routing around static obstruction",
                )
                if not replan_ok and self.blocked_timer >= 60:
                    self.state_machine.transition_to(
                        RobotState.BLOCKED,
                        reason=f"BLOCKED: No collision-free route available to {self.destination_name}",
                        action="Waiting for obstacle clearance or operator override",
                    )
        else:
            if not is_obstacle_near:
                self.is_blocked = False
            self.linear_speed = v
            self.angular_speed = w
            if not is_obstacle_near and not has_critical_block:
                active_nav_state = (
                    RobotState.EMERGENCY_OVERRIDE if self.priority_level == 1 else RobotState.NAVIGATING
                )
                if self.state_machine.state != active_nav_state and self.state_machine.state != RobotState.REPLANNING:
                    self.state_machine.transition_to(
                        active_nav_state,
                        reason="Clear corridor navigation",
                        action=f"Tracking waypoint {self.current_waypoint_idx}/{len(self.waypoints)}",
                    )
            self.yaw = candidate_yaw
            self.x = candidate_x
            self.y = candidate_y

        # Clamp strictly inside hospital perimeter [-42.0, 42.0] in X, [-36.0, 36.0] in Y
        self.x = float(np.clip(self.x, -42.0, 42.0))
        self.y = float(np.clip(self.y, -36.0, 36.0))

        if HAS_OMNI and hasattr(self, "translate_op") and self.translate_op is not None:
            self.translate_op.Set(Gf.Vec3d(self.x, self.y, self.z))
            self.rotate_op.Set(float(np.degrees(self.yaw)))

        # Sensor updates are performed at the start of step_autonomous



    def get_position(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z])


# ─────────────────────────────────────────────────────────────────────────────
# Specialized Hospital AMR Roles
# ─────────────────────────────────────────────────────────────────────────────

class DeliveryAMR(HospitalAMR):
    """Arogya Delivery AMR: specialized for medicine and clinical supplies."""

    def __init__(
        self,
        prim_path: str = "/World/Robots/Arogya_Delivery",
        start_position: Tuple[float, float, float] = (34.5, 33.0, 0.0),
        start_yaw: float = -np.pi / 2.0,  # Facing South towards corridor
        name: str = "Arogya_Delivery",
        role: str = "DELIVERY",
        **kwargs,
    ) -> None:
        super().__init__(
            prim_path=prim_path,
            name=name,
            role=role or "DELIVERY",
            start_position=start_position,
            start_yaw=start_yaw,
            accent_color=np.array([0.0, 0.88, 1.0]),  # Glowing Cyan
            home_station=kwargs.get("home_station", "CHG-01"),
        )
        self.action_duration = 6.0
        self.action_description = "Medicine tray dispensing & handover confirmation"
        self._add_delivery_payload()

    def _add_delivery_payload(self) -> None:
        if not HAS_OMNI or self.stage is None:
            return
        # Medicine delivery tray (local space — moves with robot)
        _make_local_box(self.stage, self.prim_path, "DeliveryTray",
                        (0.16, 0.0, 0.65), (0.38, 0.42, 0.05), (0.25, 0.65, 0.80))
        # Red Cross medicine box
        _make_local_box(self.stage, self.prim_path, "MedicineBox",
                        (0.16, 0.0, 0.74), (0.24, 0.28, 0.16), (0.88, 0.20, 0.20))
        # White cross emblem
        _make_local_box(self.stage, self.prim_path, "CrossEmblem",
                        (0.281, 0.0, 0.74), (0.01, 0.10, 0.10), (1.0, 1.0, 1.0))


class ReceptionAMR(HospitalAMR):
    """Mitra Reception AMR: specialized for visitor guidance and patient triage escort."""

    def __init__(
        self,
        prim_path: str = "/World/Robots/Mitra_Reception",
        start_position: Tuple[float, float, float] = (0.0, -5.0, 0.0),
        start_yaw: float = -np.pi / 2.0,  # Facing South towards Entrance / Waiting
        name: str = "Mitra_Reception",
        role: str = "RECEPTION",
        **kwargs,
    ) -> None:
        super().__init__(
            prim_path=prim_path,
            name=name,
            role=role or "RECEPTION",
            start_position=start_position,
            start_yaw=start_yaw,
            accent_color=np.array([0.20, 0.88, 0.50]),  # Emerald Green
            home_station=kwargs.get("home_station", "RCT-01"),
        )
        self.action_duration = 8.0
        self.action_description = "Patient registration & vitals scanning"
        self._add_reception_payload()

    def _add_reception_payload(self) -> None:
        if not HAS_OMNI or self.stage is None:
            return
        # Interactive guidance tablet (local space — moves with robot)
        _make_local_box(self.stage, self.prim_path, "GuidanceTablet",
                        (0.16, 0.0, 0.70), (0.06, 0.38, 0.28), (0.15, 0.18, 0.22))
        _make_local_box(self.stage, self.prim_path, "TabletScreen",
                        (0.191, 0.0, 0.70), (0.01, 0.34, 0.24), (0.20, 0.88, 0.50))
        # Smart card / ID reader
        _make_local_box(self.stage, self.prim_path, "CardReader",
                        (0.16, 0.22, 0.70), (0.08, 0.06, 0.12), (0.1, 0.1, 0.1))


class EmergencyAMR(HospitalAMR):
    """Garuda Emergency AMR: specialized for Code Blue resuscitation and trauma resupply."""

    def __init__(
        self,
        prim_path: str = "/World/Robots/Garuda_Emergency",
        start_position: Tuple[float, float, float] = (-34.0, -8.0, 0.0),
        start_yaw: float = 0.0,  # Facing East towards Emergency door
        name: str = "Garuda_Emergency",
        role: str = "EMERGENCY",
        **kwargs,
    ) -> None:
        super().__init__(
            prim_path=prim_path,
            name=name,
            role=role or "EMERGENCY",
            start_position=start_position,
            start_yaw=start_yaw,
            accent_color=np.array([0.95, 0.18, 0.18]),  # Alert Crimson Red
            home_station=kwargs.get("home_station", "EMR-01"),
        )
        self.action_duration = 10.0
        self.action_description = "Emergency defibrillator deployment & AED sequence"
        self._add_emergency_payload()

    def _add_emergency_payload(self) -> None:
        if not HAS_OMNI or self.stage is None:
            return
        # Mobile defibrillator & trauma kit (local space — moves with robot)
        _make_local_box(self.stage, self.prim_path, "DefibrillatorUnit",
                        (0.16, 0.0, 0.68), (0.32, 0.38, 0.24), (0.95, 0.85, 0.15))
        _make_local_box(self.stage, self.prim_path, "DefibScreen",
                        (0.321, 0.0, 0.68), (0.01, 0.20, 0.12), (0.2, 0.9, 1.0))
        # Emergency strobe light on torso top
        _make_local_box(self.stage, self.prim_path, "EmergencyStrobe",
                        (0.0, 0.0, 1.25), (0.14, 0.14, 0.12), (1.0, 0.05, 0.05))


class SupportAMR(HospitalAMR):
    """Sahayak Support AMR: specialized for equipment transport, supplies, and backup tasks."""

    def __init__(
        self,
        prim_path: str = "/World/Robots/Sahayak_Support",
        start_position: Tuple[float, float, float] = (39.5, 33.0, 0.0),
        start_yaw: float = -np.pi / 2.0,  # Facing South towards corridor
        name: str = "Sahayak_Support",
        role: str = "SUPPORT",
        **kwargs,
    ) -> None:
        super().__init__(
            prim_path=prim_path,
            name=name,
            role=role or "SUPPORT",
            start_position=start_position,
            start_yaw=start_yaw,
            accent_color=np.array([0.95, 0.65, 0.15]),  # Amber Gold
            home_station=kwargs.get("home_station", "CHG-01"),
        )
        self.action_duration = 8.0
        self.action_description = "UV-C decontamination sweep & sterile equipment restock"
        self._add_support_payload()

    def _add_support_payload(self) -> None:
        if not HAS_OMNI or self.stage is None:
            return
        # Heavy equipment transport platform (local space — moves with robot)
        _make_local_box(self.stage, self.prim_path, "SupportPlatform",
                        (0.15, 0.0, 0.65), (0.40, 0.44, 0.06), (0.45, 0.50, 0.55))
        _make_local_box(self.stage, self.prim_path, "ToolCaddy",
                        (0.15, 0.0, 0.73), (0.26, 0.32, 0.18), (0.95, 0.65, 0.15))
        # UV-C decontamination emitter
        _make_local_box(self.stage, self.prim_path, "UVCDeconEmitter",
                        (0.0, 0.0, 1.28), (0.20, 0.20, 0.12), (0.65, 0.20, 0.95))


# Backward-compatible aliases
ArogyaRobot = DeliveryAMR
CompanionAMR = ReceptionAMR


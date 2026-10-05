"""
HospitalRobotNav — Robot Physical Configuration
================================================
Defines the physical and operational parameters of the hospital robot.

Based on realistic mobile hospital robot specifications similar to:
- TUG Autonomous Mobile Robot (Aethon)
- Fetch Freight Base
- PAL Robotics TIAGo
- Toyota HSR

ROS2 Note:
    These values map to the URDF robot description and nav2 parameters:
    robot_radius, max_vel_x, min_vel_x, max_vel_theta, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Tuple


class RobotType(Enum):
    """Supported robot types for future multi-agent deployment."""
    DELIVERY      = auto()   # Medicine / item delivery
    PATIENT_CARE  = auto()   # Patient interaction
    CLEANING      = auto()   # Autonomous cleaning
    SECURITY      = auto()   # Patrol / monitoring
    GENERAL       = auto()   # General-purpose (default)


@dataclass(frozen=True)
class RobotPhysicsConfig:
    """
    Physical robot parameters (differential drive model).

    Units:
        Distances: meters (scaled to grid cells internally)
        Velocities: meters/second
        Angles: radians
    """

    # Robot body radius (meters) — used for collision detection
    RADIUS_METERS: float = 0.35

    # Equivalent in grid cells
    RADIUS_CELLS: float = 0.7   # 0.35 m / 0.5 m per cell

    # Maximum linear velocity (m/s)
    MAX_LINEAR_VELOCITY: float = 1.2

    # Minimum linear velocity (m/s)
    # >0 so the robot always creeps forward while turning instead of
    # appearing frozen until it finishes rotating in place.
    MIN_LINEAR_VELOCITY: float = 0.05

    # Maximum angular velocity (rad/s)
    MAX_ANGULAR_VELOCITY: float = 1.5

    # Linear acceleration (m/s²)
    MAX_LINEAR_ACCEL: float = 0.5

    # Angular acceleration (rad/s²)
    MAX_ANGULAR_ACCEL: float = 1.0

    # Minimum turning radius at max speed (meters)
    MIN_TURNING_RADIUS: float = 0.5

    # Default cruising speed (m/s)
    CRUISE_SPEED: float = 0.8

    # Speed inside rooms (slower for safety)
    ROOM_SPEED: float = 0.4

    # Speed near humans (m/s)
    NEAR_HUMAN_SPEED: float = 0.3

    # Emergency stop deceleration (m/s²)
    EMERGENCY_DECEL: float = 2.0


@dataclass(frozen=True)
class RobotBatteryConfig:
    """Battery and power management parameters."""

    # Maximum battery capacity (Wh)
    MAX_CAPACITY_WH: float = 200.0

    # Starting charge level (fraction 0.0–1.0)
    INITIAL_CHARGE: float = 1.0

    # Power draw while moving (Watts)
    MOVING_POWER_W: float = 150.0

    # Power draw while idle (Watts)
    IDLE_POWER_W: float = 20.0

    # Charging rate (Watts)
    CHARGING_POWER_W: float = 500.0

    # Battery level threshold to trigger return-to-dock
    LOW_BATTERY_THRESHOLD: float = 0.20   # 20%

    # Battery level threshold considered critical
    CRITICAL_BATTERY_THRESHOLD: float = 0.10   # 10%

    # Battery level at which robot resumes normal operation
    RESUME_THRESHOLD: float = 0.90   # 90%


@dataclass(frozen=True)
class RobotSensorConfig:
    """
    Sensor configuration for future perception modules.

    ROS2 Note:
        These map to sensor topics published by hardware drivers:
        /scan (LIDAR), /camera/rgb/image_raw, /camera/depth/image_raw
    """

    # LIDAR range (meters)
    LIDAR_MAX_RANGE: float = 10.0

    # LIDAR angular resolution (degrees)
    LIDAR_ANGULAR_RESOLUTION: float = 1.0

    # LIDAR update rate (Hz)
    LIDAR_UPDATE_RATE: float = 10.0

    # Camera field of view (degrees)
    CAMERA_FOV_DEGREES: float = 60.0

    # Depth camera range (meters)
    DEPTH_CAMERA_RANGE: float = 5.0

    # Obstacle detection range used in simulation (grid cells)
    DETECTION_RADIUS_CELLS: float = 5.0

    # Number of simulated LIDAR rays
    LIDAR_NUM_RAYS: int = 360


@dataclass(frozen=True)
class RobotConfig:
    """
    Master robot configuration object.

    Usage:
        from config.robot_config import ROBOT_CONFIG
        radius = ROBOT_CONFIG.physics.RADIUS_CELLS
    """

    physics: RobotPhysicsConfig = field(default_factory=RobotPhysicsConfig)
    battery: RobotBatteryConfig = field(default_factory=RobotBatteryConfig)
    sensors: RobotSensorConfig  = field(default_factory=RobotSensorConfig)

    # Default robot type
    DEFAULT_TYPE: RobotType = RobotType.GENERAL

    # Robot display name prefix
    ROBOT_ID_PREFIX: str = "HRN"   # Hospital Robot Navigation

    # Maximum mission queue depth
    MAX_MISSION_QUEUE: int = 10

    # Waypoint arrival tolerance (grid cells)
    WAYPOINT_TOLERANCE: float = 0.8

    # Goal arrival tolerance (grid cells)
    GOAL_TOLERANCE: float = 1.0


# Module-level singleton
ROBOT_CONFIG = RobotConfig()
PHYSICS_CONFIG = ROBOT_CONFIG.physics
BATTERY_CONFIG = ROBOT_CONFIG.battery
SENSOR_CONFIG = ROBOT_CONFIG.sensors

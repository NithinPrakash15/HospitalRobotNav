"""
AROGYA Hospital Robotics External Web Subsystems
================================================
Provides two non-blocking external browser web applications:
1. Perception & Robot POV Server (Port 8080): Live RGB camera feed, 360 LiDAR scan radar, explainable reasoning, detection timeline.
2. Hospital Database & Operations Server (Port 8081): Live clinical patient board, status changes, task dispatching, Code Blue emergency workflows.
"""

from .perception_server import (
    start_perception_server,
    stop_perception_server,
    PERCEPTION_BUFFER,
    PerceptionStateBuffer,
)
from .database_server import (
    start_database_server,
    stop_database_server,
    DB_BRIDGE,
    HospitalDatabaseStateBridge,
)
from .browser_launcher import (
    launch_web_interfaces,
    stop_web_interfaces,
)

__all__ = [
    "start_perception_server",
    "stop_perception_server",
    "PERCEPTION_BUFFER",
    "PerceptionStateBuffer",
    "start_database_server",
    "stop_database_server",
    "DB_BRIDGE",
    "HospitalDatabaseStateBridge",
    "launch_web_interfaces",
    "stop_web_interfaces",
]




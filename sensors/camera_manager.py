"""
Proxy module forwarding to isaac_sim_hospital.sensors.camera_manager
"""
import sys
import isaac_sim_hospital.sensors.camera_manager as _orig

# Alias module directly in sys.modules to ensure singleton identity
sys.modules[__name__] = _orig

from isaac_sim_hospital.sensors.camera_manager import (
    AMRCameraSensor,
    CameraSensorManager,
    _ACTIVE_CAMERA_MANAGER,
)

__all__ = [
    "AMRCameraSensor",
    "CameraSensorManager",
    "_ACTIVE_CAMERA_MANAGER",
]


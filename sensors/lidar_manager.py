"""
Proxy module forwarding to isaac_sim_hospital.sensors.lidar_manager
"""
import sys
import isaac_sim_hospital.sensors.lidar_manager as _orig

# Alias module directly in sys.modules to ensure singleton identity
sys.modules[__name__] = _orig

from isaac_sim_hospital.sensors.lidar_manager import (
    AMRLiDARScan,
    AMRLiDARSensor,
    LiDARSensorManager,
    _ACTIVE_LIDAR_MANAGER,
)

__all__ = [
    "AMRLiDARScan",
    "AMRLiDARSensor",
    "LiDARSensorManager",
    "_ACTIVE_LIDAR_MANAGER",
]


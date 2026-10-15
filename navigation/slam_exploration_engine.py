"""
AAROGYA Autonomous Exploration SLAM & Dynamic World Model Engine
Unified Proxy & Re-export from isaac_sim_hospital.navigation.slam_exploration_engine
Ensures both import paths ('navigation.slam_exploration_engine' and
'isaac_sim_hospital.navigation.slam_exploration_engine') reference the exact same
authoritative SLAM exploration engine and singleton instance.
"""

from isaac_sim_hospital.navigation.slam_exploration_engine import *
from isaac_sim_hospital.navigation.slam_exploration_engine import (
    SLAMExplorationEngine,
    OccupancyState,
    FrontierCluster,
    GLOBAL_SLAM_ENGINE,
    SLAM_ENGINE,
    get_slam_engine,
)

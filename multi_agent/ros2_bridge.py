"""Forwarding proxy for ros2_bridge from isaac_sim_hospital.multi_agent"""
import sys
import os

_this_dir = os.path.dirname(os.path.abspath(__file__))
_isaac_multi_agent = os.path.join(os.path.dirname(_this_dir), "isaac_sim_hospital", "multi_agent")
if _isaac_multi_agent not in sys.path:
    sys.path.insert(0, _isaac_multi_agent)

from isaac_sim_hospital.multi_agent.ros2_bridge import *

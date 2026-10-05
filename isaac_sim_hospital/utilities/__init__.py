"""
Utilities package for isaac_sim_hospital
"""
import os, sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_root_util = os.path.join(_root, "utilities")
if os.path.isdir(_root_util) and _root_util not in __path__:
    __path__.append(_root_util)

from isaac_sim_hospital.utilities.performance_profiler import PerformanceProfiler, PERFORMANCE_PROFILER

__all__ = ["PerformanceProfiler", "PERFORMANCE_PROFILER"]

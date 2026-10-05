"""
Proxy metrics package for isaac_sim_hospital
"""
try:
    from metrics.experiment_metrics import ExperimentMetricsRecorder, EXPERIMENT_METRICS, ExperimentMode, MissionMetricsRecord
except ImportError:
    import sys, os
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if root not in sys.path:
        sys.path.insert(0, root)
    from metrics.experiment_metrics import ExperimentMetricsRecorder, EXPERIMENT_METRICS, ExperimentMode, MissionMetricsRecord

__all__ = [
    "ExperimentMetricsRecorder",
    "EXPERIMENT_METRICS",
    "ExperimentMode",
    "MissionMetricsRecord",
]

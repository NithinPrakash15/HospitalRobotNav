"""
Proxy forwarding to multi_agent.observation_sharing
"""
try:
    from multi_agent.observation_sharing import ObservationSharingBridge, OBSERVATION_SHARING, SharedObservation
except ImportError:
    import sys, os
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if root not in sys.path:
        sys.path.insert(0, root)
    from multi_agent.observation_sharing import ObservationSharingBridge, OBSERVATION_SHARING, SharedObservation

__all__ = ["ObservationSharingBridge", "OBSERVATION_SHARING", "SharedObservation"]

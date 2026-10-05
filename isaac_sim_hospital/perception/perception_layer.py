"""Proxy forwarding to perception.perception_layer"""
try:
    from perception.perception_layer import DetectedObject, ObjectType, PerceptionLayer
except ImportError:
    import sys, os
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if root not in sys.path:
        sys.path.insert(0, root)
    from perception.perception_layer import DetectedObject, ObjectType, PerceptionLayer

__all__ = ["DetectedObject", "ObjectType", "PerceptionLayer"]

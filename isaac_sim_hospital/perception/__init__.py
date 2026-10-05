"""
Proxy for perception package in isaac_sim_hospital
"""
try:
    from perception.perception_layer import DetectedObject, ObjectType, PerceptionLayer
    from perception.spatial_relations import SpatialRelationsEngine, SpatialRelationType, SpatialRelation
except ImportError:
    import sys, os
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if root not in sys.path:
        sys.path.insert(0, root)
    from perception.perception_layer import DetectedObject, ObjectType, PerceptionLayer
    from perception.spatial_relations import SpatialRelationsEngine, SpatialRelationType, SpatialRelation

__all__ = [
    "DetectedObject",
    "ObjectType",
    "PerceptionLayer",
    "SpatialRelationsEngine",
    "SpatialRelationType",
    "SpatialRelation",
]

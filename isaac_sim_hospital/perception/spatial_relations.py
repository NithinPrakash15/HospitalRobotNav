"""Proxy forwarding to perception.spatial_relations"""
try:
    from perception.spatial_relations import SpatialRelationsEngine, SpatialRelationType, SpatialRelation
except ImportError:
    import sys, os
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if root not in sys.path:
        sys.path.insert(0, root)
    from perception.spatial_relations import SpatialRelationsEngine, SpatialRelationType, SpatialRelation

__all__ = ["SpatialRelationsEngine", "SpatialRelationType", "SpatialRelation"]

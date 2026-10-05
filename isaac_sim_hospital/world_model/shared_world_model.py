"""Proxy forwarding to parent world_model.shared_world_model"""
import sys
import os
import importlib.util

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root in sys.path:
    sys.path.remove(_root)
sys.path.insert(0, _root)

_parent_path = os.path.join(_root, "world_model", "shared_world_model.py")
if os.path.exists(_parent_path):
    _spec = importlib.util.spec_from_file_location("world_model.shared_world_model", _parent_path)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["world_model.shared_world_model"] = _mod
    _spec.loader.exec_module(_mod)
    SharedWorldModel = _mod.SharedWorldModel
    SHARED_WORLD_MODEL = _mod.SHARED_WORLD_MODEL
    WorldEvent = _mod.WorldEvent
else:
    from world_model.shared_world_model import SharedWorldModel, SHARED_WORLD_MODEL, WorldEvent

__all__ = ["SharedWorldModel", "SHARED_WORLD_MODEL", "WorldEvent"]

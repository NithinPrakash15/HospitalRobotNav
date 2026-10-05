"""
HospitalRobotNav — Core Logic Library (ROS 2 ready)
=====================================================
Pure-Python, ROS 2-independent implementation of the hospital robot
navigation, mission, agent, and speech pipelines.

This package wraps the proven HospitalRobotNav logic modules (located at the
project root) so the ROS 2 nodes can import a stable package namespace::

    from hospital_robot_nav_core import environment, algorithms, language
    from hospital_robot_nav_core.language.intent_parser import IntentParser

How it works
------------
The package locates the HospitalRobotNav project root by walking up from this
file until it finds ``main.py``, then adds that directory to ``sys.path`` so the
existing pure-Python modules (``config/``, ``environment/``, ``algorithms/``,
``robot/``, ``language/``, ``missions/``, ``agents/``, ``speech/``,
``utilities/``) import normally.  Each root module is registered in
``sys.modules`` under ``hospital_robot_nav_core.<name>`` so sub-imports such as
``from hospital_robot_nav_core.language.intent_parser import IntentParser``
resolve to the exact same module objects.

For a standalone robot deployment (no simulator repo), copy the needed
top-level modules into this package directory — the import namespace below
stays identical.

Modules exposed
---------------
config / environment / algorithms / robot / language / missions / agents /
speech / utilities
"""

from __future__ import annotations

import importlib
import os
import sys

__version__ = "0.1.0"

# ─────────────────────────────────────────────────────────────────────────────
# Locate the HospitalRobotNav project root (contains main.py)
# ─────────────────────────────────────────────────────────────────────────────

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))


def _find_project_root(start_dir: str) -> str | None:
    """Walk upward from start_dir until a directory containing requirements.txt and isaac_sim_hospital is found."""
    current = start_dir
    while True:
        if os.path.isdir(os.path.join(current, "isaac_sim_hospital")) and os.path.isfile(os.path.join(current, "requirements.txt")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
    return None


_PROJECT_ROOT = _find_project_root(_THIS_DIR)

if _PROJECT_ROOT is not None and _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Top-level modules that the ROS 2 nodes rely on.  Each is imported from the
# project root and re-registered under the hospital_robot_nav_core namespace.
_SUBMODULES = (
    "config",
    "environment",
    "algorithms",
    "robot",
    "language",
    "missions",
    "agents",
    "speech",
    "utilities",
    "maps",
    "navigation",
    "planning",
    "controllers",
    "metrics",
)

# ─────────────────────────────────────────────────────────────────────────────
# Import root modules and alias them into this package namespace
# ─────────────────────────────────────────────────────────────────────────────

def _register_submodule(name: str) -> None:
    """Import the root-level module `name` and alias it as hospital_robot_nav_core.name."""
    module = importlib.import_module(name)
    sys.modules[f"{__name__}.{name}"] = module
    globals()[name] = module


if _PROJECT_ROOT is not None:
    for _name in _SUBMODULES:
        try:
            _register_submodule(_name)
        except Exception:  # pragma: no cover - best-effort registration
            # Some modules (e.g. simulation, visualization) may require pygame;
            # ROS 2 nodes do not need them.  Skip quietly.
            continue

__all__ = list(_SUBMODULES)


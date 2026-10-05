"""
AI Reasoning & Mission Understanding Package for Isaac Sim Hospital.
"""

from .mission_understander import MissionUnderstander, EmbodiedMissionSpec

try:
    from ai_reasoning.decision_engine import DecisionEngine, DECISION_ENGINE, ExplainableDecision
except ImportError:
    try:
        from isaac_sim_hospital.ai_reasoning.decision_engine import DecisionEngine, DECISION_ENGINE, ExplainableDecision
    except ImportError:
        DecisionEngine = None
        DECISION_ENGINE = None
        ExplainableDecision = None

__all__ = [
    "MissionUnderstander",
    "EmbodiedMissionSpec",
    "DecisionEngine",
    "DECISION_ENGINE",
    "ExplainableDecision",
]

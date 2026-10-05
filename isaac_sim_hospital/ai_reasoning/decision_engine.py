"""
Proxy forwarding to ai_reasoning.decision_engine
"""
try:
    from ai_reasoning.decision_engine import DecisionEngine, DECISION_ENGINE, ExplainableDecision
except ImportError:
    import sys, os
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if root not in sys.path:
        sys.path.insert(0, root)
    from ai_reasoning.decision_engine import DecisionEngine, DECISION_ENGINE, ExplainableDecision

__all__ = ["DecisionEngine", "DECISION_ENGINE", "ExplainableDecision"]

"""
Unit tests for Explainable Decision Engine & 5-Tuple Reasoning
=============================================================
"""

import pytest
from ai_reasoning.decision_engine import DecisionEngine, DECISION_ENGINE, ExplainableDecision


class TestDecisionEngine:

    def test_decision_5_tuple_format(self):
        engine = DecisionEngine()
        dec = engine.reason_obstacle_avoidance(
            robot_name="Arogya_Delivery",
            mission_desc="Medication delivery to PAT-101",
            obstacle_dist=1.65,
            is_blocked=False,
            replan_succeeded=True,
        )

        assert isinstance(dec, ExplainableDecision)
        assert dec.robot_name == "Arogya_Delivery"
        assert dec.decision == "REPLAN_DETOUR"
        assert len(dec.options) >= 3
        assert "situation" in dec.to_dict()
        assert "constraints" in dec.to_dict()
        assert "options" in dec.to_dict()
        assert "decision" in dec.to_dict()
        assert "action" in dec.to_dict()

    def test_task_allocation_reasoning(self):
        engine = DecisionEngine()
        all_bids = [
            {"agent_id": "DEL-01", "score": 0.88, "eta": 15.0},
            {"agent_id": "SUP-01", "score": 0.52, "eta": 35.0},
        ]
        dec = engine.reason_task_allocation(
            mission_desc="Deliver Paracetamol to PAT-101",
            winning_agent_id="DEL-01",
            winning_bid_score=0.88,
            all_bids=all_bids,
        )

        assert dec.decision == "AWARD_MISSION"
        assert "DEL-01" in dec.action
        assert "0.88" in dec.situation

    def test_emergency_preemption_reasoning(self):
        engine = DecisionEngine()
        dec = engine.reason_emergency_preemption(
            emergency_patient_id="P003",
            emergency_room="PAT-103",
            preempted_robot="Arogya_Delivery",
            dispatched_robot="Garuda_Emergency",
        )

        assert dec.decision == "PREEMPT_AND_DISPATCH"
        assert dec.robot_name == "Garuda_Emergency"
        assert "P003" in dec.situation
        assert "Garuda_Emergency" in dec.action

"""
End-to-End Multi-Agent Embodied AI Mission Tests & Benchmark Verification.
"""

import pytest
from metrics.evaluation_framework import EvaluationFramework, EvaluationSummary
from simulation.simulator import Simulator


def test_evaluation_framework_benchmarks_all_pass():
    evaluator = EvaluationFramework()
    summary: EvaluationSummary = evaluator.run_all_experiments()

    assert summary.total_experiments == 6
    assert summary.successful_experiments == 6
    assert summary.task_completion_rate == 1.0
    assert summary.mean_grounding_accuracy >= 0.90
    assert summary.collision_free_rate == 1.0


def test_full_mission_decomposition_and_handoff():
    sim = Simulator()
    sim.initialize()

    # Process a natural language instruction
    accepted = sim.process_spoken_command("Hey Arogya deliver medicine Paracetamol to Room 205")
    assert accepted is True

    # Validate agent registry & assignment
    assert sim._last_assigned_agent is not None
    assert sim._last_assigned_agent.agent_type == "delivery"

    # Step simulation frames to drive the mission state forward
    for _ in range(30):
        sim.step()

    # Robot has an active path or state moving/planning
    assert sim.robot is not None
    assert sim.robot.battery.soc > 0.0

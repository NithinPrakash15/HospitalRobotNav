"""
Unit tests for Mission System (Planner, Executor, Medicine Manager).
"""

import pytest
from missions.mission_types import TaskType, TaskStep, MissionPlan
from missions.mission_planner import MissionPlanner
from missions.medicine_manager import MedicineManager
from environment.semantic_map import SemanticMap
from environment.navigation_graph import NavigationGraph


@pytest.fixture
def semantic_map():
    nav_graph = NavigationGraph().build()
    return SemanticMap(nav_graph)


@pytest.fixture
def mission_planner(semantic_map):
    return MissionPlanner(semantic_map)


@pytest.fixture
def medicine_manager():
    return MedicineManager()


def test_medicine_manager_verification(medicine_manager):
    med = medicine_manager.get_medicine("Paracetamol")
    assert med is not None
    assert med.name == "Paracetamol"
    assert medicine_manager.verify_stock("Paracetamol", quantity=1) is True


def test_mission_planner_medicine_delivery(mission_planner):
    plan = mission_planner.plan_medicine_delivery(
        medicine_name="Paracetamol",
        destination_name="Room 205",
        priority=2,
    )
    assert plan is not None
    assert plan.total_steps >= 3  # Navigate to Pharmacy -> Collect -> Navigate to Room 205 -> Deliver
    assert plan.steps[0].task_type == TaskType.NAVIGATE
    assert plan.steps[1].task_type == TaskType.COLLECT
    assert plan.steps[1].item == "Paracetamol"


def test_mission_plan_progress():
    step1 = TaskStep(description="Step 1", task_type=TaskType.NAVIGATE)
    step2 = TaskStep(description="Step 2", task_type=TaskType.DELIVER)
    plan = MissionPlan(mission_type="TEST", steps=[step1, step2])

    assert plan.progress_percent == 0
    assert plan.is_complete is False

    step1.complete()
    assert plan.progress_percent == 50

    step2.complete()
    assert plan.progress_percent == 100
    assert plan.is_complete is True

"""
Unit tests for VisionLanguageReasoner & Spatial Grounding Engine.
"""

import pytest
from environment.navigation_graph import NavigationGraph
from environment.semantic_map import SemanticMap
from language.vision_language_reasoner import (
    VisionLanguageReasoner,
    SpatialRelationType,
)


@pytest.fixture
def vlr_engine():
    nav_graph = NavigationGraph()
    nav_graph.build()
    sem_map = SemanticMap(nav_graph)
    return VisionLanguageReasoner(sem_map)


def test_vlr_opposite_reasoning(vlr_engine):
    # Test "opposite ICU" or "opposite Ward 101"
    result = vlr_engine.parse_and_ground("Please deliver medicine to the room opposite ICU")
    assert result is not None
    assert result.relation_type == SpatialRelationType.OPPOSITE
    assert result.target_pos is not None
    assert len(result.reasoning_chain) >= 2


def test_vlr_next_to_reasoning(vlr_engine):
    # Test "next to Pharmacy" or "next to Radiology"
    result = vlr_engine.parse_and_ground("Go to the room next to Pharmacy")
    assert result is not None
    assert result.relation_type == SpatialRelationType.NEXT_TO
    assert result.target_pos is not None


def test_vlr_between_reasoning(vlr_engine):
    # Test "between Pharmacy and ICU"
    result = vlr_engine.parse_and_ground("Navigate between Pharmacy and ICU")
    assert result is not None
    assert result.relation_type == SpatialRelationType.BETWEEN
    assert result.target_pos is not None


def test_vlr_nearest_dock_reasoning(vlr_engine):
    result = vlr_engine.parse_and_ground("Find the nearest charging dock", current_robot_pos=(80, 11))
    assert result is not None
    assert result.relation_type == SpatialRelationType.NEAREST
    assert result.target_pos is not None


def test_vlr_least_congested_reasoning(vlr_engine):
    obstacles = [(79, 47), (79, 48), (80, 47)]  # simulate congestion near main pharmacy
    result = vlr_engine.parse_and_ground("Take supplies to the less congested pharmacy", obstacle_positions=obstacles)
    assert result is not None
    assert result.relation_type == SpatialRelationType.LEAST_CONGESTED
    assert result.target_pos is not None

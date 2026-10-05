"""
Unit tests for Hospital NPC Entities (Doctor, Nurse, Patient, Stretcher, Wheelchair, Cart).
"""

import pytest
from environment.occupancy_grid import OccupancyGrid
from maps.hospital.hospital_map import HospitalMap
from environment.hospital_entities import (
    HospitalEntityManager,
    HospitalEntity,
    HospitalEntityRole,
    HospitalEntityState,
)


@pytest.fixture
def entity_manager():
    hmap = HospitalMap().build()
    grid = OccupancyGrid(hmap)
    mgr = HospitalEntityManager(grid)
    mgr.spawn_default_population(10)
    return mgr


def test_npc_population_spawning(entity_manager):
    assert len(entity_manager.entities) == 10
    positions = entity_manager.get_all_positions()
    assert len(positions) == 10
    for r, c in positions:
        assert 0 <= r < 120 and 0 <= c < 120


def test_npc_state_and_update(entity_manager):
    # Test ticking entities
    first_entity = next(iter(entity_manager.entities.values()))
    initial_pos = list(first_entity.pos)
    
    # Tick simulation for 2 seconds
    for _ in range(20):
        entity_manager.update(0.1, robot_pos=(80, 11))

    assert first_entity.state in (
        HospitalEntityState.IDLE,
        HospitalEntityState.WALKING,
        HospitalEntityState.YIELDING,
    )


def test_npc_social_yielding(entity_manager):
    # Put an entity right next to the robot
    first_entity = next(iter(entity_manager.entities.values()))
    first_entity.pos = [80.5, 11.5]
    
    # Update with robot at (80, 11) within social radius
    first_entity.update(0.1, entity_manager.occupancy_grid, robot_pos=(80, 11))
    assert first_entity.state == HospitalEntityState.YIELDING

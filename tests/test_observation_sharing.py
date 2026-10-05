"""
Unit tests for Distributed Multi-Agent Observation Sharing & Shared World Model
==============================================================================
"""

import pytest
from multi_agent.observation_sharing import ObservationSharingBridge, OBSERVATION_SHARING
from world_model.shared_world_model import SHARED_WORLD_MODEL


class TestObservationSharing:

    def test_shared_world_model_hazard_registration(self):
        h = SHARED_WORLD_MODEL.register_hazard(
            source_robot="Arogya_Delivery",
            position=(12.0, 2.0),
            zone_name="CORRIDOR_CENTRAL",
            description="Stretcher obstruction",
            clearance_radius=1.5,
        )

        assert h.is_active is True
        assert h.zone_name == "CORRIDOR_CENTRAL"
        assert h.hazard_id in SHARED_WORLD_MODEL.active_hazards

        # Check route conflict detection
        conflicted_wps = [(10.0, 2.0), (12.0, 2.0), (14.0, 2.0)]
        has_conflict, hazard = SHARED_WORLD_MODEL.is_route_conflicted(conflicted_wps)
        assert has_conflict is True
        assert hazard is not None

        # Check clear route
        clear_wps = [(10.0, 20.0), (12.0, 20.0)]
        has_conflict_clear, _ = SHARED_WORLD_MODEL.is_route_conflicted(clear_wps)
        assert has_conflict_clear is False

        # Cleanup
        SHARED_WORLD_MODEL.clear_hazard(h.hazard_id)
        assert h.hazard_id not in SHARED_WORLD_MODEL.active_hazards

    def test_observation_sharing_bridge_broadcast(self):
        obs = OBSERVATION_SHARING.share_observation(
            source_robot_name="Garuda_Emergency",
            obstacle_position=(5.0, 5.0),
            zone_name="CORRIDOR_CENTRAL",
            description="Medical crash cart blockage",
        )

        assert obs is not None
        assert obs.source_robot == "Garuda_Emergency"
        assert obs.obstacle_pos == (5.0, 5.0)

        # Confirm event was recorded in Shared World Model
        events = [e for e in SHARED_WORLD_MODEL.event_stream if e.source_robot == "Garuda_Emergency"]
        assert len(events) >= 1

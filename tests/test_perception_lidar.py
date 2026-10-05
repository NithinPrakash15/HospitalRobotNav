"""
Unit tests for Perception Layer, Spatial Relations, and Attached Physical Sensors
================================================================================
"""

import math
import pytest
from perception.perception_layer import PerceptionLayer, DetectedObject, ObjectType
from perception.spatial_relations import SpatialRelationsEngine, RelationType
from sensors.lidar_manager import AMRLiDARSensor
from sensors.camera_manager import AMRCameraSensor


class TestPerceptionAndSensors:

    def test_perception_layer_dynamic_agents(self):
        layer = PerceptionLayer(observer_robot_name="Arogya_Delivery")
        dynamic_obstacles = [
            (5.0, 5.0),    # Person
            (10.0, 10.0),  # Medical Cart
            (15.0, 15.0),  # Beyond range (> 12m from (0,0))
        ]
        detected = layer.process_observations(
            robot_x=0.0, robot_y=0.0, robot_z=0.0, robot_yaw=0.0,
            dynamic_obstacles=dynamic_obstacles,
        )

        assert len(detected) == 2  # 15,15 is ~21m away, filtered by range
        assert detected[0].distance == pytest.approx(math.hypot(5.0, 5.0), rel=1e-2)
        assert detected[0].object_type in [ObjectType.PERSON, ObjectType.MEDICAL_CART]
        assert detected[0].confidence is not None
        assert detected[0].confidence > 0.70

    def test_spatial_relations_room_and_corridor(self):
        engine = SpatialRelationsEngine()
        # Test department location
        room = engine.determine_room(33.0, -25.0)  # PAT-101 coordinates
        assert room == "PAT-101"

        # Test corridor location
        corridor = engine.determine_corridor(0.0, 2.0)
        assert corridor == "CORRIDOR_CENTRAL"

    def test_spatial_relations_blocking(self):
        engine = SpatialRelationsEngine()
        target_obj = DetectedObject(
            object_id="OBSTACLE_01",
            object_type=ObjectType.UNKNOWN_OBJECT,
            position=(2.0, 0.0, 0.0),
            distance=2.0,
            direction=0.0,
        )
        planned_wps = [(1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]
        relations = engine.evaluate_all(
            robot_name="Arogya_Delivery",
            robot_x=0.0, robot_y=0.0, robot_yaw=0.0,
            detected_objects=[target_obj],
            planned_waypoints=planned_wps,
        )

        blocking_rel = [r for r in relations if r.relation == RelationType.BLOCKING]
        assert len(blocking_rel) >= 1
        assert blocking_rel[0].object_entity == "OBSTACLE_01"

    def test_lidar_sensor_scan(self):
        sensor = AMRLiDARSensor(robot_name="Arogya_Delivery", num_beams=72)
        scan = sensor.scan(
            robot_x=0.0, robot_y=0.0, robot_yaw=0.0,
            dynamic_obstacles=[(2.0, 0.0)],
        )

        assert scan is not None
        assert scan.success is True
        assert scan.total_points == 72
        # Surface distance from front-mounted LiDAR: 2.0m - 0.24m (offset) - 0.35m (radius) = ~1.41m
        assert scan.min_distance == pytest.approx(1.41, abs=0.25)
        assert scan.has_critical_proximity is False  # 1.41m > 1.2m
        assert scan.has_warning_proximity is True     # 2.0m < 2.5m

    def test_camera_sensor_intrinsics_and_pose(self):
        cam = AMRCameraSensor(robot_name="Arogya_Delivery", robot_prim_path="/World/Robots/Arogya")
        assert cam.focal_length == 24.0
        assert cam.hfov_deg > 60.0  # Approx 70 deg
        cam.update_pose(10.0, 5.0, 0.0, math.pi / 2)
        assert cam.last_world_pos[0] == pytest.approx(10.0, abs=0.2)
        assert cam.last_yaw_rad == pytest.approx(math.pi / 2, abs=1e-3)

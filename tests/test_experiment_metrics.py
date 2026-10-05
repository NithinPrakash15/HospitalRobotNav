"""
Unit tests for Research Experiment Mode & Metrics Recorder
==========================================================
"""

import os
import tempfile
import pytest
from metrics.experiment_metrics import ExperimentMetricsRecorder, ExperimentMode


class TestExperimentMetrics:

    def test_mission_lifecycle_and_efficiency(self):
        recorder = ExperimentMetricsRecorder()
        recorder.set_mode(ExperimentMode.LIVE)

        rec = recorder.start_mission(
            mission_id="MSN-TEST-01",
            robot_name="Arogya_Delivery",
            mission_type="MEDICINE_DELIVERY",
            priority=3,
            planned_path_length_m=20.0,
            initial_battery_pct=100.0,
        )

        # Simulate 5 motion steps
        recorder.record_step("Arogya_Delivery", x=0.0, y=0.0, speed=0.5, battery=99.9, dt=0.1)
        recorder.record_step("Arogya_Delivery", x=5.0, y=0.0, speed=1.0, battery=99.5, dt=0.1)
        recorder.record_step("Arogya_Delivery", x=10.0, y=0.0, speed=1.0, battery=99.0, dt=0.1)
        recorder.record_step("Arogya_Delivery", x=15.0, y=0.0, speed=1.0, battery=98.5, dt=0.1)
        recorder.record_step("Arogya_Delivery", x=20.0, y=0.0, speed=0.8, battery=98.0, dt=0.1)

        recorder.record_replan("Arogya_Delivery")
        recorder.record_obstacle("Arogya_Delivery", is_human=True)

        completed_rec = recorder.complete_mission("MSN-TEST-01", success=True)

        assert completed_rec is not None
        assert completed_rec.success is True
        assert completed_rec.actual_travel_dist_m == pytest.approx(20.0, abs=0.5)
        assert completed_rec.path_efficiency_ratio == pytest.approx(1.0, abs=0.05)
        assert completed_rec.replan_count == 1
        assert completed_rec.obstacles_encountered == 1
        assert completed_rec.human_encounters == 1
        assert completed_rec.max_speed_mps == 1.0

    def test_replay_buffer(self):
        recorder = ExperimentMetricsRecorder()
        recorder.set_mode(ExperimentMode.LIVE)

        recorder.record_snapshot(
            robot_states={"Arogya_Delivery": {"x": 5.0, "y": 10.0, "state": "NAVIGATING"}},
            obstacle_positions=[(6.0, 10.0)],
            active_events=["Obstacle detected"],
        )

        assert len(recorder.replay_buffer) == 1
        snap = recorder.get_replay_frame(0)
        assert snap is not None
        assert snap.robot_states["Arogya_Delivery"]["x"] == 5.0

    def test_export_json_and_csv(self):
        recorder = ExperimentMetricsRecorder()
        recorder.start_mission("MSN-EXP-01", "Mitra_Reception", planned_path_length_m=15.0)
        recorder.record_step("Mitra_Reception", 1.0, 1.0, 0.5, 99.0)
        recorder.complete_mission("MSN-EXP-01", success=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = os.path.join(tmpdir, "metrics.json")
            csv_path = os.path.join(tmpdir, "metrics.csv")

            assert recorder.export_summary_json(json_path) is True
            assert os.path.exists(json_path)

            assert recorder.export_csv(csv_path) is True
            assert os.path.exists(csv_path)

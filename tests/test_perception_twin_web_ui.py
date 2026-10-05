"""
Tests for Phase 6: Perception-Reasoning Twin Web UI and Enriched Telemetry.

Verifies:
1. Perception web template renders 4-Stage Pipeline HUD banner, Bedside Verification card, and Congestion / Fleet Healing elements.
2. Perception state buffer captures enriched telemetry (mission_id, container status, verification, explainable traces, hazards, congestion).
3. Perception server API endpoints correctly serve the enriched telemetry to the frontend.
"""

import json
import os
import sys
import time
import urllib.request
import pytest

from isaac_sim_hospital.web.perception_server import (
    start_perception_server,
    stop_perception_server,
    PERCEPTION_BUFFER,
)
from isaac_sim_hospital.robots.arogya_robot import DeliveryAMR, RobotState


from world_model.shared_world_model import SHARED_WORLD_MODEL


def test_perception_html_template_elements():
    """Verify that perception.html template contains all required Phase 6 UI components."""
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "isaac_sim_hospital",
        "web",
        "templates",
        "perception.html",
    )
    assert os.path.exists(template_path), f"perception.html not found at {template_path}"

    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. 4-Stage Pipeline HUD Banner
    assert "pipeline-hud-banner" in html
    assert "stageSense" in html
    assert "stageUnderstand" in html
    assert "stageReason" in html
    assert "stageAct" in html
    assert "pipelineMissionId" in html

    # 2. Bedside Patient Verification & 3D Medicine Container
    assert "containerPrimBadge" in html
    assert "containerMountBadge" in html
    assert "containerLockBadge" in html
    assert "containerPrimPath" in html
    assert "checkRfidBadge" in html
    assert "checkRoomBadge" in html
    assert "verificationBanner" in html

    # 3. Dynamic Semantic Cost Map & Fleet Self-Healing
    assert "congestionList" in html
    assert "activeHazardsList" in html
    assert "batteryHandoffStatus" in html
    assert "preemptionDepthVal" in html


def test_perception_buffer_enriched_telemetry():
    """Verify that PERCEPTION_BUFFER captures container prim, verification, and congestion states."""
    robot = DeliveryAMR("Arogya_Delivery", (1.0, 2.0, 0.0), role="Clinical Delivery")
    robot.current_mission_id = "MED-20261001-9988"
    robot.attach_medicine_container(
        medicine_name="Paracetamol 500mg",
        dosage="500mg",
        patient_id="P-101",
        room_id="BED-01",
    )

    SHARED_WORLD_MODEL.report_hazard("Arogya_Delivery", (5.0, 2.0), "CORRIDOR_A", "Spill detected")
    SHARED_WORLD_MODEL.add_congestion_penalty(5.0, 2.0, zone_name="CORRIDOR_JUNCTION_1", base_penalty=10.0)

    PERCEPTION_BUFFER.selected_robot = "Arogya_Delivery"
    PERCEPTION_BUFFER.update_telemetry(fleet_robots={"Arogya_Delivery": robot})

    with PERCEPTION_BUFFER._lock:
        telem = dict(PERCEPTION_BUFFER.last_telemetry)

    assert telem["robot"] == "Arogya_Delivery"
    assert telem["mission_id"] == "MED-20261001-9988"
    assert telem["has_medicine_container"] is True
    assert telem["is_container_locked"] is True
    assert telem["attached_medication"]["name"] == "Paracetamol 500mg"
    assert len(telem["active_hazards"]) >= 1
    assert any(h["zone"] == "CORRIDOR_A" for h in telem["active_hazards"])
    assert len(telem["congestion_hotspots"]) >= 1
    assert any(c["zone"] == "CORRIDOR_JUNCTION_1" for c in telem["congestion_hotspots"])


def test_perception_server_api_enriched_telemetry():
    """Verify perception web server serves enriched telemetry with Phase 6 fields."""
    test_port = 8097
    server = start_perception_server(host="127.0.0.1", port=test_port)
    time.sleep(0.3)

    try:
        # Populate buffer with test state
        robot = DeliveryAMR("Arogya_Delivery", (3.0, 4.0, 0.0), role="Clinical Delivery")
        robot.current_mission_id = "MED-20261001-7711"
        robot.attach_medicine_container(medicine_name="Ceftriaxone", dosage="1g", patient_id="P-102", room_id="BED-02")
        robot.verify_bedside_target("P-102", "BED-02", "P-102", "BED-02")
        robot.unlock_medicine_container()

        SHARED_WORLD_MODEL.report_hazard("Garuda_Emergency", (3.0, 4.0), "CORRIDOR_B", "Obstacle in transit")
        SHARED_WORLD_MODEL.add_congestion_penalty(3.0, 4.0, zone_name="CORRIDOR_B", base_penalty=8.0)

        PERCEPTION_BUFFER.selected_robot = "Arogya_Delivery"
        PERCEPTION_BUFFER.update_telemetry(fleet_robots={"Arogya_Delivery": robot})

        # 1. Fetch Root HTML
        with urllib.request.urlopen(f"http://127.0.0.1:{test_port}/", timeout=2.0) as resp:
            assert resp.status == 200
            html = resp.read().decode("utf-8")
            assert "pipeline-hud-banner" in html
            assert "verificationBanner" in html
            assert "congestionList" in html

        # 2. Fetch Telemetry JSON
        with urllib.request.urlopen(f"http://127.0.0.1:{test_port}/api/telemetry", timeout=2.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["mission_id"] == "MED-20261001-7711"
            assert data["has_medicine_container"] is True
            assert data["last_verification_result"]["verification_status"] == "VERIFIED"
            assert data["last_verification_result"]["status"] == "SUCCESS"
            assert len(data["congestion_hotspots"]) >= 1
            assert len(data["active_hazards"]) >= 1

    finally:
        stop_perception_server()

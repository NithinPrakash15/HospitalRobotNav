import sys
import os
import json
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath("."))
from backend.main import app

client = TestClient(app)

print("=== VERIFYING FASTAPI BACKEND API ENDPOINTS ===")

# Test 1: Health endpoint
res = client.get("/api/system/health")
print("\n1. /api/system/health Status:", res.status_code)
assert res.status_code == 200
health = res.json()
print("Hardware Metrics in Health:", json.dumps(health.get("hardware"), indent=2))
assert "hardware" in health
assert "fps" in health["hardware"]
assert "gpu_vram_total_mb" in health["hardware"]

# Test 2: Exploration diagnostics endpoint
res = client.get("/api/simulation/exploration_diagnostics")
print("\n2. /api/simulation/exploration_diagnostics Status:", res.status_code)
assert res.status_code == 200
diag = res.json()
print("Exploration State:", diag.get("exploration_state"))
print("Selected Robot:", diag.get("selected_robot"))
assert "exploration_state" in diag
assert "hardware" in diag

# Test 3: Fleet control (Teleop) endpoint
res = client.post("/api/fleet/control", json={
    "robot_id": "Arogya_Delivery",
    "action": "forward",
    "linear_velocity": 0.75,
    "angular_velocity": 0.0
})
print("\n3. POST /api/fleet/control Status:", res.status_code)
assert res.status_code == 200
ctrl_resp = res.json()
print("Control Response:", ctrl_resp)
assert ctrl_resp.get("status") in ("ok", "SUCCESS")
print("Truthful Isaac Sim Acknowledgment:", ctrl_resp.get("isaac_sim_acknowledged"))

# Test 4: Select Robot endpoint
res = client.post("/api/fleet/select_robot", json={"robot_id": "Mitra_Reception"})
print("\n4. POST /api/fleet/select_robot Status:", res.status_code)
assert res.status_code == 200
sel_resp = res.json()
print("Select Response:", sel_resp)
assert sel_resp.get("status") in ("ok", "SUCCESS")
assert sel_resp.get("active_robot") == "Mitra_Reception"

# Test 5: Authoritative map endpoint
res = client.get("/api/simulation/authoritative_map")
print("\n5. GET /api/simulation/authoritative_map Status:", res.status_code)
assert res.status_code == 200
map_resp = res.json()
print("Authoritative Map status:", map_resp.get("status"))

print("\n=== ALL FASTAPI ENDPOINTS VERIFIED WORKING ===")

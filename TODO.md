# HospitalRobotNav — Professional Audit & Enhancement TODO

## Phase 1 — Realistic Hospital Map
- [x] Design ~45-room realistic hospital layout (zones, wide corridors)
- [x] Rewrite `maps/hospital/room_definitions.py` with all departments
- [x] Rewrite `maps/hospital/hospital_map.py` (wide corridors, robust room-corridor connection)
- [x] Update `environment/navigation_graph.py` junction placement (map-derived)
- [x] Fix hardcoded coordinates in `simulation/simulator.py`
- [x] Fix duplicate method definitions in `environment/occupancy_grid.py`

## Phase 2 — Humanoid Service Robot
- [x] Rewrite `visualization/renderer.py` `draw_robot()` as humanoid hospital robot
- [x] Add digital face, arms, legs, lidar, tray, LEDs, logo, battery strip

## Phase 3 — Smooth Animation & Obstacles
- [x] Continuous obstacle interpolation + obstacle-obstacle separation + wall avoidance
- [x] Frame-independent movement verification

## Phase 4 — Voice & Task Execution
- [x] Make "Hey Arogya" primary wake word
- [x] Wire dialogue confirmation ("Shall I begin?" → "Yes")
- [x] Visible arm/tray attach-detach during COLLECT/DELIVER

## Phase 5 — Verification
- [x] `py_compile` all modified files
- [x] Run `pytest tests/`
- [x] Add `verify_audit.py` / `verify_fixes.py` (graph connectivity, map join, no duplicate methods)


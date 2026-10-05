# AAROGYA Refactor — Baseline & Cleanup Log

Baseline snapshot: git commit `32c3e51` and `C:\AarogyaBackup\HospitalRobotNav_baseline_32c3e51.zip`.
(`models/` and `stt_env/` are intentionally untracked: runtime dependencies, not in the snapshot.)

## Baseline test status (before any code change)

33 test files: 30 pass, 3 report failures.

| Test | Baseline | Cause |
|---|---|---|
| `tests/test_complete_faster_whisper_voice_replacement.py::test_stage_2_phone_wss_audio_pipeline` | FAIL | Environmental: `WinError 10054` on the local WSS/STT socket during teardown. Not a logic regression. |
| `isaac_sim_hospital/tests/test_master_correction_features.py` | FLAKY | Failed once in the full sweep, passed 5/5 on isolated rerun. Order/state dependent. |
| `isaac_sim_hospital/tests/test_navigation_correction_e2e.py::test_c_robot_robot_mutual_avoidance` | FAIL | Pre-existing: robot-robot mutual avoidance oscillates OBSTACLE_DETECTED <-> REPLANNING. Must be fixed in the Isaac navigation phase (Phase 9). |

## Phase 1 — completed so far

- Removed regenerable/generated output: `hospital_robot_nav_ws/{build,install,log}`, `log/`, `logs/` (20 MB of rotating logs; `utilities/logger.py` and `speech/stt_supervisor.py` recreate `logs/`), `.pytest_cache`, all `__pycache__`.
- Repo size excluding `stt_env`: 129 MB -> 75 MB.

## Verified keep-decisions (dependency-checked)

- `stt_env/` — **KEEP**: `speech/stt_supervisor.py` launches the faster-whisper worker from `stt_env/Scripts/python.exe` (Isaac's Python cannot host it). To be made configurable (`AAROGYA_STT_PYTHON`).
- `hospital_robot_nav_core` — **KEEP, rewrite**: locates the project root by `main.py`; must be re-pointed before `main.py` is deleted.
- `metrics/`, `world_state/`, `tests/test_{simulation,integration,end_to_end_missions,robot}.py` import the legacy `simulation` package — must be re-pointed before `simulation/` is deleted.

## Next (in order)

1. Collapse the proxy/duplicate packages (`ai_reasoning`, `multi_agent`, `sensors`, `perception`, `world_model`, `metrics`, `utilities`, `navigation`) into one canonical home each.
2. Extract reusable logic from `simulation/`, `environment/`, `maps/`, `algorithms/`, `missions/` into `robotics/` and `hospital/`.
3. Delete the Pygame stack (`main.py`, `visualization/`, `dashboard/`, `simulation/`, `scratch_test_ui.py`), `hospital_sim_node`, ROS speech nodes and ops scripts, once tests pass without them.

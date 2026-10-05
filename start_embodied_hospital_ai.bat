@echo off
title Multi-Agent Embodied AI Hospital Robot
echo ========================================================================
echo   Launching Multi-Agent Embodied AI Hospital Robot in NVIDIA Isaac Sim
echo   Project: Autonomous Hospital Assistance using Vision-Language Reasoning
echo ========================================================================
echo.
echo Note: If an old Isaac Sim window is currently open, please close it
echo to ensure full GPU memory is available.
echo.
"C:\isaacsim\python.bat" "%~dp0isaac_sim_hospital\scripts\run_embodied_hospital_ai.py" %*
pause

@echo off
title Multi-Agent Embodied AI Hospital Robot
echo ========================================================================
echo   Launching Multi-Agent Embodied AI Hospital Robot in NVIDIA Isaac Sim
echo   Project: Autonomous Hospital Assistance using Vision-Language Reasoning
echo ========================================================================
echo.
"C:\isaacsim\python.bat" "%~dp0scripts\run_embodied_hospital_ai.py" %*
pause

@echo off
title AAROGYA Hospital Autonomous Assistance Platform
echo ========================================================================
echo   AAROGYA — Hospital Autonomous Assistance Platform
echo   Multi-Agent Embodied AI Robot Platform with NVIDIA Isaac Sim
echo ========================================================================
echo.
echo Starting FastAPI Backend Server on http://localhost:8000 ...
start "" http://localhost:8000
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
pause

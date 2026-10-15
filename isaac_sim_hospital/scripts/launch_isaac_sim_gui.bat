@echo off
title NVIDIA Isaac Sim 5.1 — AAROGYA Autonomous Hospital Simulation
cls
echo ===============================================================================
echo   AAROGYA — NVIDIA Isaac Sim 5.1 Hospital Embodied AI Simulation
echo ===============================================================================
echo   Application : Multi-Agent Autonomous Hospital Robotics Platform
echo   Environment : Grand Digital Twin (88m x 76m, 28 Expansive Departments)
echo   Fleet AMRs  : Arogya_Delivery, Mitra_Reception, Garuda_Emergency, Sahayak_Support
echo   Perception  : Head Visor Camera Stream (Port 8080) + 2D LiDAR Scan
echo   Navigation  : Authoritative SLAM Grid + Nav2 Route Planner + Triple Collision Guard
echo ===============================================================================
echo.
echo   [*] Initializing Omniverse Kit and Python Runtime...
echo   [*] Loading Full GUI Experience: C:\isaacsim\apps\isaacsim.exp.full.kit
echo   [*] Initializing RTX Ray-Traced Real-Time Renderer on NVIDIA RTX GPU...
echo.
echo   Keep this terminal window open while simulation is active.
echo ===============================================================================
echo.

set SCRIPT_DIR=%~dp0
set REPO_ROOT=%SCRIPT_DIR%..\..
cd /d "%REPO_ROOT%"

call "C:\isaacsim\python.bat" "%SCRIPT_DIR%run_embodied_hospital_ai.py" %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ===============================================================================
    echo [ERROR] NVIDIA Isaac Sim exited with error code %ERRORLEVEL%.
    echo Please inspect isaac_sim_hospital\diagnostics\sim_runtime.log for details.
    echo ===============================================================================
    pause
)

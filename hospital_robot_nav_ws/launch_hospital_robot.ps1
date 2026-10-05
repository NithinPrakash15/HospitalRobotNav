# Launch the full hospital robot system via WSL (Ubuntu-24.04).
# Usage (from PowerShell):
#   .\launch_hospital_robot.ps1              # full system
#   .\launch_hospital_robot.ps1 speech       # speech pipeline only
param([string]$Mode = "full")

$ws = "C:\Users\nithi\OneDrive\Desktop\Main Project for vs\HospitalRobotNav\hospital_robot_nav_ws"
$scriptPath = "`/mnt/c/Users/nithi/OneDrive/Desktop/Main Project for vs/HospitalRobotNav/hospital_robot_nav_ws/launch_hospital_robot.sh"

if ($Mode -eq "speech") {
    Write-Host "Launching SPEECH PIPELINE via WSL..." -ForegroundColor Cyan
    wsl -d Ubuntu-24.04 -- bash $scriptPath speech
} else {
    Write-Host "Launching FULL HOSPITAL ROBOT SYSTEM via WSL..." -ForegroundColor Cyan
    wsl -d Ubuntu-24.04 -- bash $scriptPath full
}


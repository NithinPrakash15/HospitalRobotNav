import subprocess
import os
import tempfile
import time

views = ["dashboard", "simulation", "map", "robots", "tasks", "emergency"]
artifact_dir = r"C:\Users\nithi\.gemini\antigravity-ide\brain\397b2a39-0e9f-4cfe-9dad-7de51c79b8f9"
temp_profile = tempfile.mkdtemp(prefix="chrome_shot_")

for v in views:
    target = os.path.join(artifact_dir, f"page_{v}.png")
    url = f"http://127.0.0.1:8000/?view={v}"
    try:
        res = subprocess.run([
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            f"--user-data-dir={temp_profile}",
            "--window-size=1600,1000",
            f"--screenshot={target}",
            url
        ], capture_output=True, text=True, timeout=10)
        size = os.path.getsize(target) if os.path.exists(target) else 0
        print(f"Captured {v}: {size} bytes")
    except Exception as e:
        print(f"Error capturing {v}: {e}")

"""
Isaac Sim Hospital Robot — Simulation Configuration
=====================================================
VRAM-optimized settings for RTX 4050 Laptop GPU (6 GB).

All simulation scripts import these settings to ensure consistent,
stable performance on the target hardware.

Usage:
    from configs.simulation_config import SIM_CONFIG, get_app_config
    app = SimulationApp(get_app_config())
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# Application Launch Settings (passed to SimulationApp constructor)
# ─────────────────────────────────────────────────────────────────────────────

def get_app_config(headless: bool = False) -> dict:
    """Return SimulationApp configuration optimized for RTX 4050 Laptop.

    Args:
        headless: If True, run without GUI (for automated testing).

    Returns:
        Configuration dict for SimulationApp().
    """
    return {
        "headless": headless,
        "width": 1280,
        "height": 720,
        "multi_gpu": False,
        "active_gpu": 0,
        "physics_gpu": 0,
        "extra_args": [
            "--/app/vulkan=false",
            "--/renderer/multiGpu/enabled=false",
        ],
        "anti_aliasing": 0,           # Disable AA to save VRAM
        "renderer": "RayTracedLighting",  # RTX Real-Time (not PathTracing)
        "max_bounces": 1,             # Minimal ray bounces
        "max_specular_transmission_bounces": 0,
        "denoiser": True,             # Denoiser helps with fewer samples
        "subdiv_refinement_level": 0, # No subdivision
    }


# ─────────────────────────────────────────────────────────────────────────────
# Simulation Parameters
# ─────────────────────────────────────────────────────────────────────────────

SIM_CONFIG = {
    # Physics
    "physics_dt": 1.0 / 60.0,        # 60 Hz physics
    "rendering_dt": 1.0 / 30.0,      # 30 Hz rendering (saves GPU)
    "stage_units_in_meters": 1.0,     # 1 USD unit = 1 meter

    # Hospital environment scale
    "hospital_width_m": 20.0,         # 20 meters wide
    "hospital_depth_m": 15.0,         # 15 meters deep
    "wall_height_m": 2.8,            # 2.8 meter walls
    "wall_thickness_m": 0.15,        # 15 cm thick walls
    "door_width_m": 1.2,             # 1.2 meter doorways
    "corridor_width_m": 2.5,         # 2.5 meter corridors

    # Lighting (lightweight)
    "distant_light_intensity": 500,
    "point_light_intensity": 200,
    "point_light_radius": 5.0,

    # Robot
    "robot_start_position": [0.0, 0.0, 0.0],
    "robot_max_speed_mps": 1.0,      # 1 m/s max speed

    # Colours (RGB 0-1 float for USD materials) — Professional Hospital Palette
    "colors": {
        "floor":        (0.88, 0.89, 0.91),   # Medical Terrazzo grey
        "wall":         (0.94, 0.95, 0.96),   # Architectural Off-White
        "baseboard":    (0.22, 0.25, 0.28),   # Dark Slate kickplate
        "atrium":       (0.92, 0.91, 0.88),   # Warm Porcelain Ivory
        "corridor":     (0.88, 0.89, 0.91),   # Polished Terrazzo
        "reception":    (0.42, 0.35, 0.28),   # Warm Wood & Slate
        "pharmacy":     (0.92, 0.93, 0.94),   # Clean Clinical White
        "patient_room": (0.92, 0.93, 0.94),   # Calming Pale Vinyl
        "icu":          (0.91, 0.93, 0.95),   # Clinical Ice-White
        "emergency":    (0.91, 0.91, 0.93),   # Clean Trauma Vinyl
        "door":         (0.35, 0.38, 0.42),   # Architectural Steel
        "charging_pad": (0.00, 0.90, 1.00),   # Glowing Tech Cyan
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# AROGYA Subsystem Feature Flags & Performance Throttling
# ─────────────────────────────────────────────────────────────────────────────

AROGYA_FEATURES = {
    # Subsystem toggles (Requirement 16: Feature Isolation)
    "enable_voice": True,
    "enable_camera": True,
    "enable_lidar": True,
    "enable_perception": True,
    "enable_reasoning": True,
    "enable_database": True,
    "enable_ros2": True,
    "enable_research_logging": False,
    "enable_hud": True,

    # Frequency throttles (Hz) - keeps UI thread 100% responsive (Requirement 4)
    "dashboard_update_hz": 8.0,       # Throttled HUD update (8 Hz = 125ms)
    "sensor_update_hz": 10.0,         # Throttled sensor processing (10 Hz = 100ms)
    "ros2_publish_hz": 10.0,          # ROS2 telemetry heartbeat (10 Hz)
    "diagnostics_sample_hz": 0.5,     # Performance diagnostics sampled every 2.0s
    "replan_cooldown_s": 2.0,         # Minimum interval between A* replans per robot
}

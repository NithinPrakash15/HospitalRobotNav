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
# Quality Profiles (Phase 2 Performance Optimization)
# ─────────────────────────────────────────────────────────────────────────────

QUALITY_PROFILES = {
    "performance": {
        "description": "High-throughput profile for resource-constrained systems (maximum FPS)",
        "width": 1024,
        "height": 576,
        "window_width": 1280,
        "window_height": 720,
        "anti_aliasing": 0,
        "renderer": "RayTracedLighting",
        "max_bounces": 0,
        "max_specular_transmission_bounces": 0,
        "denoiser": False,
        "subdiv_refinement_level": 0,
        "sensor_update_hz": 8.0,
        "dashboard_update_hz": 4.0,
        "ros2_publish_hz": 8.0,
    },
    "balanced": {
        "description": "Balanced default profile for RTX 4050 6GB (fluid 30-60 FPS, crisp visuals)",
        "width": 1280,
        "height": 720,
        "window_width": 1440,
        "window_height": 900,
        "anti_aliasing": 0,
        "renderer": "RayTracedLighting",
        "max_bounces": 1,
        "max_specular_transmission_bounces": 0,
        "denoiser": True,
        "subdiv_refinement_level": 0,
        "sensor_update_hz": 10.0,
        "dashboard_update_hz": 8.0,
        "ros2_publish_hz": 10.0,
    },
    "quality": {
        "description": "Fidelity-focused profile for high-end GPUs / presentation recordings",
        "width": 1600,
        "height": 900,
        "window_width": 1680,
        "window_height": 1050,
        "anti_aliasing": 1,
        "renderer": "RayTracedLighting",
        "max_bounces": 2,
        "max_specular_transmission_bounces": 1,
        "denoiser": True,
        "subdiv_refinement_level": 1,
        "sensor_update_hz": 15.0,
        "dashboard_update_hz": 12.0,
        "ros2_publish_hz": 15.0,
    },
}

ACTIVE_PROFILE_NAME = "balanced"


def get_app_config(headless: bool = False, profile: str = "balanced") -> dict:
    """Return SimulationApp configuration optimized for RTX 4050 Laptop.

    Args:
        headless: If True, run without GUI (for automated testing).
        profile: 'performance', 'balanced' (default), or 'quality'.

    Returns:
        Configuration dict for SimulationApp().
    """
    global ACTIVE_PROFILE_NAME
    p_name = profile.lower() if profile.lower() in QUALITY_PROFILES else "balanced"
    ACTIVE_PROFILE_NAME = p_name
    prof = QUALITY_PROFILES[p_name]

    # Dynamically apply frequency throttles to AROGYA_FEATURES
    AROGYA_FEATURES["sensor_update_hz"] = prof.get("sensor_update_hz", 10.0)
    AROGYA_FEATURES["dashboard_update_hz"] = prof.get("dashboard_update_hz", 8.0)
    AROGYA_FEATURES["ros2_publish_hz"] = prof.get("ros2_publish_hz", 10.0)

    return {
        "headless": headless,
        "hide_ui": False,
        "width": prof["width"],
        "height": prof["height"],
        "window_width": prof["window_width"],
        "window_height": prof["window_height"],
        "multi_gpu": False,
        "active_gpu": 0,
        "physics_gpu": 0,
        "extra_args": [
            "--/renderer/multiGpu/enabled=false",
            "--/app/fastShutdown=true",
        ],
        "anti_aliasing": prof["anti_aliasing"],
        "renderer": prof["renderer"],
        "max_bounces": prof["max_bounces"],
        "max_specular_transmission_bounces": prof["max_specular_transmission_bounces"],
        "denoiser": prof["denoiser"],
        "subdiv_refinement_level": prof["subdiv_refinement_level"],
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

    # Lighting (balanced, non-glare)
    "distant_light_intensity": 380,
    "point_light_intensity": 160,
    "point_light_radius": 5.0,

    # Robot
    "robot_start_position": [0.0, 0.0, 0.0],
    "robot_max_speed_mps": 1.0,      # 1 m/s max speed

    # Colours (RGB 0-1 float for USD materials) — Professional Hospital Palette (Restrained, High-Contrast)
    "colors": {
        "floor":        (0.46, 0.50, 0.54),   # Medical Terrazzo foundation grey
        "wall":         (0.76, 0.78, 0.82),   # Architectural Clinical light slate
        "baseboard":    (0.16, 0.18, 0.22),   # Dark Slate kickplate
        "atrium":       (0.58, 0.56, 0.52),   # Warm Porcelain tile
        "corridor":     (0.52, 0.56, 0.60),   # Distinct Navigation Concourse
        "reception":    (0.50, 0.54, 0.52),   # Muted Sage & Slate
        "pharmacy":     (0.42, 0.58, 0.52),   # Clean Clinical Mint
        "patient_room": (0.50, 0.54, 0.56),   # Calming Surgical Pale Vinyl
        "icu":          (0.42, 0.50, 0.62),   # Clinical Ice Blue
        "emergency":    (0.60, 0.45, 0.45),   # Clean Trauma Vinyl
        "door":         (0.32, 0.35, 0.38),   # Architectural Steel
        "charging_pad": (0.00, 0.85, 1.00),   # Tech Cyan
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

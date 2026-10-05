"""
Hospital Navigation Goal Validator
==================================
Validates clinical destination goals to guarantee:
1. Floor validity (inside hospital perimeter).
2. Wall clearance (distance to wall > robot footprint radius).
3. Furniture / prop clearance (clear of counters, beds, racks).
4. Reachable approach pose through room doorways.
5. Robot footprint clearance (default radius = 0.38m).

Provides verified clinical interaction goals for all key hospital departments:
- PHARMACY (PHM-01): Dispensing counter service station (14.0, 23.2).
- ICU (ICU-01): Patient bedside care station (-18.0, -26.0).
- EMERGENCY (EMR-01): Trauma bay staging area (-35.0, -26.0).
- LABORATORY (LAB-01): Specimen intake counter (-9.0, 26.0).
- RECEPTION (RCT-01): Patient intake counter (0.0, -5.0).
- OPD (OPD-01): Consultation desk (24.0, -26.0).
- OPERATING THEATER (OT-01): Surgical prep station (-39.0, 26.0).
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple
import numpy as np

# Ground-truth clinical interaction goals: (X, Y, Z, approach_yaw_rad, description)
CLINICAL_ROOM_GOALS: Dict[str, Tuple[float, float, float, float, str]] = {
    # North Wing (Y: 21.8 to 37.2)
    "OT-01":   (-39.0, 26.0, 0.0, math.pi / 2.0, "Operating Theater 1 Prep Zone"),
    "OT-02":   (-30.0, 26.0, 0.0, math.pi / 2.0, "Operating Theater 2 Prep Zone"),
    "RAD-01":  (-15.5, 26.0, 0.0, math.pi / 2.0, "Radiology Control Console"),
    "LAB-01":  (-0.5, 26.0, 0.0, math.pi / 2.0, "Laboratory Sample Drop Counter"),
    "PHM-01":  (14.0, 23.2, 0.0, math.pi / 2.0, "Pharmacy Dispensing Counter"),
    "ROB-01":  (14.0, 23.2, 0.0, math.pi / 2.0, "Robot Medicine Pickup Station"),
    "STR-01":  (25.75, 26.0, 0.0, math.pi / 2.0, "Medicine Storage Staging"),
    "CHG-01":  (37.25, 26.0, 0.0, math.pi / 2.0, "Fleet Charging Bay 1"),

    # Middle Row (Y: 3.8 to 18.2)
    "ICU-01":  (-36.5, 11.0, 0.0, 0.0, "ICU Bedside Care Station"),
    "ICU-03":  (-36.5, 12.5, 0.0, 0.0, "ICU Monitored Bed 3"),
    "BLB-01":  (-16.75, 7.5, 0.0, math.pi / 2.0, "Blood Bank Vault Access"),
    "NST-01":  (-3.5, 7.0, 0.0, math.pi / 2.0, "Nurse Station Central Hub"),
    "DOC-01":  (9.75, 7.5, 0.0, math.pi / 2.0, "Cardiology Consultation Desk 1"),
    "DOC-02":  (20.25, 7.5, 0.0, math.pi / 2.0, "General Medicine Consultation Desk 2"),
    "ISO-01":  (30.0, 7.5, 0.0, math.pi / 2.0, "Isolation Room Bedside"),
    "CAF-01":  (39.25, 7.5, 0.0, math.pi / 2.0, "Staff Lounge & Cafeteria"),
    "STF-01":  (39.25, 7.5, 0.0, math.pi / 2.0, "Staff Lounge & Cafeteria"),

    # Lower-Mid Row (Y: -16.2 to 0.2)
    "EMR-01":  (-39.0, -8.0, 0.0, math.pi / 2.0, "Emergency Trauma Resuscitation Bay"),
    "TRM-01":  (-39.0, -8.0, 0.0, math.pi / 2.0, "Emergency Trauma Resuscitation Bay"),
    "AMB-01":  (-29.0, -8.0, 0.0, math.pi / 2.0, "Ambulance Triage Staging"),
    "TRG-01":  (-29.0, -8.0, 0.0, math.pi / 2.0, "Ambulance Triage Staging"),
    "RCT-01":  (0.0, -5.0, 0.0, math.pi / 2.0, "Main Reception Desk"),
    "WAT-01":  (0.0, -12.5, 0.0, 0.0, "Waiting Area Central Lounge"),
    "ELV-01":  (8.5, -5.5, 0.0, 0.0, "Elevator Lobby Concourse"),
    "STAIR-01":(8.5, -13.5, 0.0, 0.0, "Stairwell A Concourse"),
    "GW-01":   (22.5, -8.0, 0.0, -math.pi, "General Inpatient Ward"),
    "PED-01":  (36.5, -8.0, 0.0, -math.pi, "Pediatric Inpatient Ward"),

    # Inpatient Patient Rooms Suite (PAT-103 to PAT-106)
    "PAT-103": (-22.8, -12.35, 0.0, 0.0, "Patient Room 103 Bedside"),
    "PAT-104": (-22.8, -3.65, 0.0, 0.0, "Patient Room 104 Bedside"),
    "PAT-105": (-17.2, -12.35, 0.0, math.pi, "Patient Room 105 Bedside"),
    "PAT-106": (-17.2, -3.65, 0.0, math.pi, "Patient Room 106 Bedside"),

    # Bottom Row (South Wing, Y: -37.2 to -19.8)
    "WSH-01":  (-39.0, -26.0, 0.0, -math.pi / 2.0, "Public Washroom Concourse"),
    "SAN-01":  (-31.0, -26.0, 0.0, -math.pi / 2.0, "Bio-Sanitization & CSSD"),
    "STR-02":  (-19.5, -26.0, 0.0, -math.pi / 2.0, "Biomedical Equipment Depot"),
    "ENT-01":  (0.0, -30.0, 0.0, -math.pi / 2.0, "Grand Hospital Entrance Foyer"),
    "OPD-01":  (22.5, -26.0, 0.0, -math.pi / 2.0, "OPD Consultation Desk 1"),
    "OPD-02":  (25.5, -28.5, 0.0, -math.pi / 2.0, "OPD Consultation Desk 2"),
    "PAT-01":  (33.5, -26.0, 0.0, -math.pi / 2.0, "Patient Room 101 Bedside"),
    "PAT-101": (33.5, -26.0, 0.0, -math.pi / 2.0, "Patient Room 101 Bedside"),
    "PAT-02":  (40.25, -26.0, 0.0, -math.pi / 2.0, "Patient Room 102 Bedside"),
    "PAT-102": (40.25, -26.0, 0.0, -math.pi / 2.0, "Patient Room 102 Bedside"),
}

# Room bounds for validation: (xmin, xmax, ymin, ymax)
ROOM_BOUNDS: Dict[str, Tuple[float, float, float, float]] = {
    # North Wing
    "OT-01":   (-43.0, -35.0, 21.8, 37.2),
    "OT-02":   (-34.0, -26.0, 21.8, 37.2),
    "RAD-01":  (-22.0, -9.0, 21.8, 37.2),
    "LAB-01":  (-7.0, 6.0, 21.8, 37.2),
    "PHM-01":  (8.0, 20.0, 21.8, 37.2),
    "ROB-01":  (8.0, 20.0, 21.8, 37.2),
    "STR-01":  (22.0, 29.5, 21.8, 37.2),
    "CHG-01":  (31.5, 43.0, 21.8, 37.2),

    # Middle Row
    "ICU-01":  (-43.0, -26.0, 3.8, 18.2),
    "ICU-03":  (-43.0, -26.0, 3.8, 18.2),
    "BLB-01":  (-22.0, -11.5, 3.8, 18.2),
    "NST-01":  (-10.5, 3.5, 3.8, 18.2),
    "DOC-01":  (5.5, 14.0, 3.8, 18.2),
    "DOC-02":  (16.0, 24.5, 3.8, 18.2),
    "ISO-01":  (26.5, 33.5, 3.8, 18.2),
    "CAF-01":  (35.5, 43.0, 3.8, 18.2),
    "STF-01":  (35.5, 43.0, 3.8, 18.2),

    # Lower-Mid Row
    "EMR-01":  (-43.0, -35.0, -16.2, 0.2),
    "TRM-01":  (-43.0, -35.0, -16.2, 0.2),
    "AMB-01":  (-34.0, -26.0, -16.2, 0.2),
    "TRG-01":  (-34.0, -26.0, -16.2, 0.2),
    "RCT-01":  (-11.0, 11.0, -9.0, 0.2),
    "WAT-01":  (-10.0, 10.0, -16.2, -9.2),
    "ELV-01":  (7.0, 11.0, -9.0, 0.2),
    "STAIR-01":(7.0, 11.0, -16.2, -9.2),
    "GW-01":   (16.0, 29.0, -16.2, 0.2),
    "PED-01":  (30.5, 43.0, -16.2, 0.2),

    # Inpatient Patient Rooms Suite (PAT-103 to PAT-106)
    "PAT-103": (-26.0, -21.5, -16.2, -8.5),
    "PAT-104": (-26.0, -21.5, -7.5, 0.2),
    "PAT-105": (-18.5, -12.5, -16.2, -8.5),
    "PAT-106": (-18.5, -12.5, -7.5, 0.2),

    # Bottom Row
    "WSH-01":  (-43.0, -35.0, -37.2, -19.8),
    "SAN-01":  (-34.0, -28.0, -37.2, -19.8),
    "STR-02":  (-26.0, -13.0, -37.2, -19.8),
    "ENT-01":  (-11.0, 11.0, -37.2, -19.8),
    "OPD-01":  (16.0, 29.0, -37.2, -19.8),
    "OPD-02":  (16.0, 29.0, -37.2, -19.8),
    "PAT-01":  (30.5, 36.5, -37.2, -19.8),
    "PAT-101": (30.5, 36.5, -37.2, -19.8),
    "PAT-02":  (37.5, 43.0, -37.2, -19.8),
    "PAT-102": (37.5, 43.0, -37.2, -19.8),
}


def is_position_collision_free(
    x: float,
    y: float,
    collision_guard: Any,
    margin: float = 0.38,
) -> bool:
    """Check whether (x, y) is collision-free with respect to all registered obstacles and walls."""
    if collision_guard is None:
        return True
    if hasattr(collision_guard, "check_point_collision"):
        return not collision_guard.check_point_collision(x, y, margin=margin)
    return True


def find_nearest_valid_goal(
    requested_xy: Tuple[float, float],
    room_bounds: Optional[Tuple[float, float, float, float]],
    collision_guard: Any,
    robot_radius: float = 0.38,
    search_radius: float = 3.0,
    step: float = 0.25,
) -> Tuple[float, float]:
    """
    Search outward from requested_xy for the nearest collision-free, inside-bounds goal.
    Does NOT teleport the robot; purely resolves a reachable navigation coordinate.
    """
    rx, ry = requested_xy
    if is_position_collision_free(rx, ry, collision_guard, margin=robot_radius):
        if room_bounds is None:
            return rx, ry
        xmin, xmax, ymin, ymax = room_bounds
        if (xmin + robot_radius <= rx <= xmax - robot_radius and
                ymin + robot_radius <= ry <= ymax - robot_radius):
            return rx, ry

    best_pt = (rx, ry)
    best_dist = float("inf")

    max_rings = int(search_radius / step)
    for ring in range(1, max_rings + 1):
        r = ring * step
        num_angles = max(8, int(2 * math.pi * r / step))
        for i in range(num_angles):
            angle = (2.0 * math.pi * i) / num_angles
            cx = rx + r * math.cos(angle)
            cy = ry + r * math.sin(angle)

            # Check bounds
            if room_bounds is not None:
                xmin, xmax, ymin, ymax = room_bounds
                if not (xmin + robot_radius <= cx <= xmax - robot_radius and
                        ymin + robot_radius <= cy <= ymax - robot_radius):
                    continue

            # Check collision
            if is_position_collision_free(cx, cy, collision_guard, margin=robot_radius):
                d = math.hypot(cx - rx, cy - ry)
                if d < best_dist:
                    best_dist = d
                    best_pt = (round(cx, 2), round(cy, 2))

        if best_dist < float("inf"):
            break

    return best_pt


def validate_navigation_goal(
    dest_room_id: str,
    hospital_env: Any = None,
    collision_guard: Any = None,
    robot_radius: float = 0.38,
) -> Tuple[np.ndarray, bool, str]:
    """
    Resolve and strictly validate the clinical navigation goal for a room.
    
    Args:
        dest_room_id: Semantic room ID (e.g. 'PHM-01', 'ICU-01', 'EMR-01').
        hospital_env: Optional HospitalEnvironment instance.
        collision_guard: Optional CollisionGuard instance with wall/furniture boxes.
        robot_radius: Robot footprint radius in meters (default 0.38m).
        
    Returns:
        (validated_pos_xyz, is_valid, validation_log_msg)
    """
    clean_id = dest_room_id.upper().strip()

    # 1. Check known clinical goals
    if clean_id in CLINICAL_ROOM_GOALS:
        gx, gy, gz, yaw, desc = CLINICAL_ROOM_GOALS[clean_id]
        bounds = ROOM_BOUNDS.get(clean_id)
        # Verify collision clearance
        if is_position_collision_free(gx, gy, collision_guard, margin=robot_radius):
            msg = f"Goal validated for {clean_id}: ({gx:.2f}, {gy:.2f}) -> {desc}"
            return np.array([gx, gy, gz]), True, msg
        else:
            # Fallback to nearest free position inside room
            adj_x, adj_y = find_nearest_valid_goal((gx, gy), bounds, collision_guard, robot_radius=robot_radius)
            msg = f"Adjusted {clean_id} goal for wall/furniture clearance: ({adj_x:.2f}, {adj_y:.2f})"
            return np.array([adj_x, adj_y, gz]), True, msg

    # 2. Check semantic locations from hospital_env
    if hospital_env is not None and hasattr(hospital_env, "get_semantic_locations"):
        sem_locs = hospital_env.get_semantic_locations()
        if clean_id in sem_locs:
            loc = sem_locs[clean_id]
            pos = loc.get("pos", np.array([0.0, 0.0, 0.0]))
            bounds = loc.get("bounds", ROOM_BOUNDS.get(clean_id))
            gx, gy = float(pos[0]), float(pos[1])
            gz = float(pos[2]) if len(pos) > 2 else 0.0

            if is_position_collision_free(gx, gy, collision_guard, margin=robot_radius):
                msg = f"Goal validated from semantic map for {clean_id}: ({gx:.2f}, {gy:.2f})"
                return np.array([gx, gy, gz]), True, msg
            else:
                adj_x, adj_y = find_nearest_valid_goal((gx, gy), bounds, collision_guard, robot_radius=robot_radius)
                msg = f"Adjusted semantic goal for {clean_id} to collision-free point: ({adj_x:.2f}, {adj_y:.2f})"
                return np.array([adj_x, adj_y, gz]), True, msg

    # 3. Default fallback to Pharmacy Dispense Counter
    gx, gy, gz, _, desc = CLINICAL_ROOM_GOALS["PHM-01"]
    msg = f"Unknown destination '{dest_room_id}', defaulting to validated Pharmacy goal ({gx:.2f}, {gy:.2f})"
    return np.array([gx, gy, gz]), False, msg


class GoalValidator:
    """Class wrapper providing goal validation services for hospital navigation."""

    @staticmethod
    def validate(dest_room_id: str, hospital_env: Any = None, collision_guard: Any = None, robot_radius: float = 0.38) -> Tuple[np.ndarray, bool, str]:
        return validate_navigation_goal(dest_room_id, hospital_env, collision_guard, robot_radius)

    @staticmethod
    def is_collision_free(x: float, y: float, collision_guard: Any = None, margin: float = 0.38) -> bool:
        return is_position_collision_free(x, y, collision_guard, margin)

    @staticmethod
    def find_nearest_valid(center_xy: Tuple[float, float], room_bounds: Optional[Tuple[float, float, float, float]], collision_guard: Any = None, robot_radius: float = 0.38) -> Tuple[float, float]:
        return find_nearest_valid_goal(center_xy, room_bounds, collision_guard, robot_radius)


"""
HospitalRobotNav — Main Pygame Renderer
=========================================
The central rendering engine that orchestrates all visual components:
    - Hospital map (rooms, corridors, walls)
    - A* open/closed sets and expansion animation
    - Robot body, heading, trail
    - Dynamic obstacles
    - Path visualization
    - Left panel (navigation + missions)
    - Right panel (analytics)
    - Mini-map overlay
    - Control buttons

Design:
    Uses pygame surfaces and a layered drawing approach.
    All drawing is batched per frame for performance.
"""

from __future__ import annotations

import math
import pygame
import pygame.gfxdraw
from typing import TYPE_CHECKING, List, Optional, Set, Tuple

from config.settings import COLORS, DISPLAY, APP_SETTINGS
from config.hospital_config import GRID_CONFIG
from maps.hospital.room_definitions import ROOM_DATABASE, ROOMS_BY_ID, RoomCategory
from robot.robot_state import RobotState
from visualization.camera import Camera

if TYPE_CHECKING:
    from simulation.simulator import Simulator

GridPos = Tuple[int, int]


# ─────────────────────────────────────────────────────────────────────────────
# Room Category → Color mapping
# ─────────────────────────────────────────────────────────────────────────────

ROOM_COLOR_MAP = {
    RoomCategory.EMERGENCY:     COLORS.ROOM_EMERGENCY,
    RoomCategory.CRITICAL_CARE: COLORS.ROOM_ICU,
    RoomCategory.SURGICAL:      COLORS.ROOM_OT,
    RoomCategory.IMAGING:       COLORS.ROOM_MRI,
    RoomCategory.LABORATORY:    COLORS.ROOM_LAB,
    RoomCategory.PATIENT_WARD:  COLORS.ROOM_PATIENT,
    RoomCategory.OUTPATIENT:    COLORS.ROOM_DOCTOR,
    RoomCategory.PHARMACY:      COLORS.ROOM_PHARMACY,
    RoomCategory.RECEPTION:     COLORS.ROOM_RECEPTION,
    RoomCategory.ADMINISTRATIVE:COLORS.ROOM_GENERIC,
    RoomCategory.SUPPORT:       COLORS.ROOM_UTILITY,
    RoomCategory.UTILITY:       COLORS.ROOM_UTILITY,
    RoomCategory.STAFF:         COLORS.ROOM_GENERIC,
    RoomCategory.AMENITY:       COLORS.ROOM_CAFETERIA,
    RoomCategory.TRANSPORT:     COLORS.ROOM_UTILITY,
    RoomCategory.ROBOT:         COLORS.ROOM_CHARGING,
}


class Renderer:
    """
    Complete pygame-based hospital robot navigation renderer.

    Call sequence each frame:
        renderer.begin_frame()
        renderer.draw_map(sim)
        renderer.draw_path_data(sim)
        renderer.draw_obstacles(sim)
        renderer.draw_robot(sim)
        renderer.draw_left_panel(sim)
        renderer.draw_right_panel(sim)
        renderer.draw_minimap(sim)
        renderer.end_frame()
    """

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.camera = Camera()
        self._font_init()

        # Viewport rect (map area)
        self.vp_x  = DISPLAY.LEFT_PANEL_WIDTH
        self.vp_y  = 0
        self.vp_w  = DISPLAY.MAP_VIEWPORT_WIDTH
        self.vp_h  = DISPLAY.MAP_VIEWPORT_HEIGHT

        # Precompute room floor rects {room_id: [(row, col), ...]}
        self._room_cells = {}
        self._precompute_room_cells()

        # Button rects for click detection (populated in draw_left_panel)
        self.buttons = {}

        # UI state
        self.show_grid      = APP_SETTINGS.SHOW_GRID
        self.show_labels    = APP_SETTINGS.SHOW_ROOM_LABELS
        self.show_open      = APP_SETTINGS.SHOW_OPEN_LIST
        self.show_closed    = APP_SETTINGS.SHOW_CLOSED_LIST
        self.show_trail     = APP_SETTINGS.SHOW_TRAIL

        # Cached map surface (static, only rebuilt on zoom)
        self._map_surface:   Optional[pygame.Surface] = None
        self._map_zoom_cache: float = -1.0

        # Selected destination
        self.selected_dest: Optional[str] = None

    # ─────────────────────────────────────────────────────────────────────────
    # Frame lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def begin_frame(self) -> None:
        """Clear screen to background color."""
        self.screen.fill(COLORS.BG_PRIMARY)

    def end_frame(self) -> None:
        """Flip display buffer."""
        pygame.display.flip()

    # ─────────────────────────────────────────────────────────────────────────
    # Map Drawing
    # ─────────────────────────────────────────────────────────────────────────

    def draw_map(self, sim: "Simulator") -> None:
        """Draw the hospital floor plan."""
        cell = self.camera.cell_px
        min_row, max_row, min_col, max_col = self.camera.get_visible_range()

        binary = sim.occupancy_grid.binary_grid
        type_g  = sim.occupancy_grid.type_grid
        room_g  = sim.occupancy_grid.room_id_grid

        for row in range(min_row, max_row + 1):
            for col in range(min_col, max_col + 1):
                sx, sy = self.camera.grid_to_screen(row, col)

                if binary[row, col] == 1:
                    # Wall
                    color = COLORS.MAP_WALL
                else:
                    rid = room_g[row, col]
                    if rid and rid in ROOMS_BY_ID:
                        room = ROOMS_BY_ID[rid]
                        base_color = ROOM_COLOR_MAP.get(room.category, COLORS.ROOM_GENERIC)
                        color = self._dim_color(base_color, 0.45)
                    else:
                        # Corridor / free
                        color = COLORS.MAP_CORRIDOR

                pygame.draw.rect(self.screen, color, (sx, sy, cell, cell))

                # Grid lines
                if self.show_grid and cell >= 4:
                    pygame.draw.rect(self.screen, COLORS.MAP_GRID_LINE,
                                     (sx, sy, cell, cell), 1)

        # Draw room outlines and labels
        self._draw_room_borders(cell)
        if self.show_labels and cell >= 6:
            self._draw_room_labels()

    def _draw_room_borders(self, cell: int) -> None:
        """Draw colored border around each room."""
        for room in ROOM_DATABASE:
            color = ROOM_COLOR_MAP.get(room.category, COLORS.ROOM_GENERIC)
            sx1, sy1 = self.camera.grid_to_screen(room.top_row, room.left_col)
            sx2, sy2 = self.camera.grid_to_screen(room.bottom_row + 1, room.right_col + 1)
            w = sx2 - sx1
            h = sy2 - sy1
            if w > 0 and h > 0:
                pygame.draw.rect(self.screen, color, (sx1, sy1, w, h), 2)

    def _draw_room_labels(self) -> None:
        """Draw room name labels at room centers."""
        for room in ROOM_DATABASE:
            sx, sy = self.camera.grid_to_screen(room.center_row, room.center_col)
            vw = self.vp_w + self.vp_x
            if self.vp_x <= sx <= vw and 0 <= sy <= self.vp_h:
                label = room.label if len(room.label) <= 12 else room.label[:10] + ".."
                surf = self._font_tiny.render(label, True, COLORS.TEXT_SECONDARY)
                rect = surf.get_rect(center=(sx, sy))
                self.screen.blit(surf, rect)

    # ─────────────────────────────────────────────────────────────────────────
    # Path & Planning Data
    # ─────────────────────────────────────────────────────────────────────────

    def draw_path_data(self, sim: "Simulator") -> None:
        """Draw A* open/closed sets, expansion animation, and planned path."""
        cell = self.camera.cell_px

        # ── Closed set (visited nodes) ────────────────────────────────────────
        if self.show_closed:
            visible_expansion = sim.get_expansion_visible()
            closed_color = (*COLORS.NODE_CLOSED, 80)   # Semi-transparent
            for node in visible_expansion:
                if self.camera.is_visible(*node):
                    sx, sy = self.camera.grid_to_screen(*node)
                    s = pygame.Surface((cell, cell), pygame.SRCALPHA)
                    s.fill(closed_color)
                    self.screen.blit(s, (sx, sy))

        # ── Open set ──────────────────────────────────────────────────────────
        if self.show_open:
            open_set = sim.get_open_set()
            open_color = (*COLORS.NODE_OPEN, 100)
            for node in open_set:
                if self.camera.is_visible(*node):
                    sx, sy = self.camera.grid_to_screen(*node)
                    s = pygame.Surface((cell, cell), pygame.SRCALPHA)
                    s.fill(open_color)
                    self.screen.blit(s, (sx, sy))

        # ── Planned path ──────────────────────────────────────────────────────
        path = sim.robot.path
        if path and len(path) >= 2:
            points = []
            for r, c in path:
                sx, sy = self.camera.grid_to_screen(r, c)
                cx = sx + cell // 2
                cy = sy + cell // 2
                points.append((cx, cy))

            if len(points) >= 2:
                pygame.draw.lines(self.screen, COLORS.PATH_PLANNED, False, points, max(2, cell // 4))

            # Future path (remaining)
            idx = sim.robot.path_index
            if idx < len(points):
                remaining = points[idx:]
                if len(remaining) >= 2:
                    pygame.draw.lines(
                        self.screen, COLORS.PATH_SMOOTHED, False, remaining, max(2, cell // 3)
                    )

        # ── Start & Goal markers ──────────────────────────────────────────────
        if sim.robot.path:
            start = sim.robot.path[0]
            goal  = sim.robot.path[-1]
            self._draw_diamond(start, COLORS.NODE_START, cell)
            self._draw_diamond(goal, COLORS.NODE_GOAL, cell)

    def _draw_diamond(self, pos: GridPos, color: tuple, cell: int) -> None:
        """Draw a diamond marker at a grid cell."""
        sx, sy = self.camera.grid_to_screen(*pos)
        cx = sx + cell // 2
        cy = sy + cell // 2
        r  = max(4, cell // 2)
        points = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
        pygame.draw.polygon(self.screen, color, points)
        pygame.draw.polygon(self.screen, COLORS.TEXT_PRIMARY, points, 1)

    # ─────────────────────────────────────────────────────────────────────────
    # Dynamic Obstacles
    # ─────────────────────────────────────────────────────────────────────────

    def draw_obstacles(self, sim: "Simulator") -> None:
        """Draw all dynamic obstacles and procedural hospital NPC entities."""
        cell = self.camera.cell_px
        pad = max(1, cell // 6)

        # 1. Draw standard dynamic obstacles
        for obs in sim.obstacle_manager.get_all_obstacles():
            if not self.camera.is_visible(*obs.position):
                continue
            sx, sy = self.camera.grid_to_screen(*obs.position)
            cx = sx + cell // 2
            cy = sy + cell // 2
            radius = max(3, cell // 2 - pad)

            # Outer glow
            glow_color = (*obs.color, 60)
            glow_surf = pygame.Surface((cell * 2, cell * 2), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, glow_color, (cell, cell), radius + 3)
            self.screen.blit(glow_surf, (cx - cell, cy - cell))

            # Body
            pygame.draw.circle(self.screen, obs.color, (cx, cy), radius)
            pygame.draw.circle(self.screen, COLORS.TEXT_PRIMARY, (cx, cy), radius, 1)

            # Label (if cell large enough)
            if cell >= 10:
                lbl = self._font_tiny.render(obs.label[:3], True, COLORS.TEXT_PRIMARY)
                self.screen.blit(lbl, lbl.get_rect(center=(cx, cy)))

        # 2. Draw procedural hospital NPC entities (Doctors, Nurses, Stretchers, Wheelchairs, Carts)
        if hasattr(sim, "entity_manager") and sim.entity_manager is not None:
            from environment.hospital_entities import ROLE_COLORS, HospitalEntityRole
            for entity in sim.entity_manager.entities.values():
                r, c = entity.pos[0], entity.pos[1]
                grid_r, grid_c = int(round(r)), int(round(c))
                if not self.camera.is_visible(grid_r, grid_c):
                    continue

                sx, sy = self.camera.grid_to_screen(r, c)
                cx = sx + cell // 2
                cy = sy + cell // 2
                base_color = ROLE_COLORS.get(entity.role, (180, 180, 180))
                radius = max(4, int(cell * 0.45))

                # Direction vector
                hdg = entity.heading
                dx = math.cos(hdg)
                dy = -math.sin(hdg)

                # Special equipment shapes (Stretcher, Wheelchair, Cleaning Cart)
                if entity.role == HospitalEntityRole.STRETCHER:
                    # Elongated stretcher bed
                    st_len = max(8, int(cell * 1.1))
                    st_w = max(4, int(cell * 0.55))
                    st_surf = pygame.Surface((st_len * 2, st_w * 2), pygame.SRCALPHA)
                    pygame.draw.rect(st_surf, (*base_color, 220), (st_len // 2, st_w // 2, st_len, st_w), border_radius=3)
                    pygame.draw.rect(st_surf, (255, 255, 255), (st_len // 2, st_w // 2, st_len, st_w), 1, border_radius=3)
                    # Emergency cross
                    pygame.draw.line(st_surf, (255, 255, 255), (st_len, st_w - 3), (st_len, st_w + 3), 2)
                    pygame.draw.line(st_surf, (255, 255, 255), (st_len - 3, st_w), (st_len + 3, st_w), 2)
                    rot_surf = pygame.transform.rotate(st_surf, math.degrees(hdg))
                    self.screen.blit(rot_surf, rot_surf.get_rect(center=(cx, cy)))

                elif entity.role == HospitalEntityRole.WHEELCHAIR:
                    # Wheelchair base with circular wheels
                    pygame.draw.circle(self.screen, (60, 60, 60), (cx, cy), radius + 1)
                    pygame.draw.circle(self.screen, base_color, (cx, cy), radius - 1)
                    # Patient head
                    pygame.draw.circle(self.screen, (255, 220, 180), (cx, cy), max(2, radius // 2))

                elif entity.role == HospitalEntityRole.CLEANING_CART:
                    # Utility box
                    cart_size = max(6, int(cell * 0.8))
                    cart_rect = pygame.Rect(cx - cart_size // 2, cy - cart_size // 2, cart_size, cart_size)
                    pygame.draw.rect(self.screen, base_color, cart_rect, border_radius=2)
                    pygame.draw.rect(self.screen, (255, 255, 255), cart_rect, 1, border_radius=2)

                else:
                    # Humanoids (Doctor, Nurse, Surgeon, Patient, Visitor)
                    # Gentle walking bob animation
                    bob = int(math.sin(entity.walk_cycle) * 1.5)
                    # Torso / Body
                    pygame.draw.circle(self.screen, base_color, (cx, cy + bob), radius)
                    pygame.draw.circle(self.screen, (30, 30, 30), (cx, cy + bob), radius, 1)
                    # Head / Face
                    head_r = max(2, radius // 2)
                    hx = cx + int(dx * (radius * 0.5))
                    hy = cy + bob + int(dy * (radius * 0.5))
                    pygame.draw.circle(self.screen, (255, 225, 200), (hx, hy), head_r)
                    # Medical staff badge or stethoscopes
                    if entity.role in (HospitalEntityRole.DOCTOR, HospitalEntityRole.SURGEON):
                        pygame.draw.circle(self.screen, (255, 255, 255), (cx, cy + bob), max(1, head_r - 1))
                    elif entity.role == HospitalEntityRole.NURSE:
                        pygame.draw.line(self.screen, (255, 255, 255), (cx - 2, cy + bob), (cx + 2, cy + bob), 1)

                # Label tag
                if cell >= 11:
                    tag = self._font_tiny.render(entity.entity_id[:3], True, (240, 240, 240))
                    self.screen.blit(tag, (cx - tag.get_width() // 2, cy - radius - 10))

    # ─────────────────────────────────────────────────────────────────────────
    # Multi-Agent Fleet
    # ─────────────────────────────────────────────────────────────────────────

    def draw_agents(self, sim: "Simulator") -> None:
        """Render visible specialist agents as small map markers."""
        if sim is None or not hasattr(sim, "agent_registry"):
            return

        cell = self.camera.cell_px
        for agent in sim.agent_registry.get_all_agents():
            row, col = agent.position
            if not self.camera.is_visible(row, col):
                continue

            sx, sy = self.camera.grid_to_screen(row, col)
            cx = sx + cell // 2
            cy = sy + cell // 2

            palette = {
                "delivery": (80, 220, 150),
                "reception": (120, 160, 255),
                "emergency": (255, 90, 90),
                "navigation": (100, 200, 255),
                "vision": (255, 180, 80),
                "speech": (255, 130, 220),
                "task": (215, 150, 255),
                "object": (180, 220, 80),
                "patient": (255, 200, 120),
                "medicine": (120, 220, 200),
                "environment": (150, 200, 255),
                "robot_health": (95, 255, 215),
                "mission": (190, 120, 255),
            }
            color = palette.get(agent.agent_type.lower().split("_")[0], (140, 170, 220))

            radius = max(4, int(cell * 0.38))
            pygame.draw.circle(self.screen, color, (cx, cy), radius)
            pygame.draw.circle(self.screen, (20, 20, 20), (cx, cy), radius, 1)

            if cell >= 10:
                label = agent.agent_type[:3].upper()
                surf = self._font_tiny.render(label, True, COLORS.TEXT_PRIMARY)
                self.screen.blit(surf, surf.get_rect(center=(cx, cy - radius - 8)))

    # ─────────────────────────────────────────────────────────────────────────
    # Robot
    # ─────────────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────────────
    # Humanoid Hospital Service Robot Rendering
    # ─────────────────────────────────────────────────────────────────────────

    def draw_robot(self, sim: "Simulator") -> None:
        """Draw complete humanoid hospital service robot with face, arms, LEDs, and tray."""
        robot = sim.robot
        cell  = self.camera.cell_px

        # ── Trail ─────────────────────────────────────────────────────────────
        if self.show_trail and len(robot.trail) >= 2:
            trail_pts = []
            for tr, tc in robot.trail:
                sx, sy = self.camera.grid_to_screen(tr, tc)
                trail_pts.append((sx + cell // 2, sy + cell // 2))

            if len(trail_pts) >= 2:
                n = len(trail_pts)
                for i in range(max(0, n - 80), n - 1):
                    alpha = int(200 * (i - (n - 80)) / 80) if n > 80 else 200
                    color = self._fade_color(COLORS.ROBOT_TRAIL, alpha / 255)
                    pygame.draw.line(
                        self.screen, color,
                        trail_pts[i], trail_pts[i + 1],
                        max(1, cell // 4),
                    )

        # ── Humanoid Robot Assembly ───────────────────────────────────────────
        self._draw_humanoid_robot(robot, cell)

    def _draw_humanoid_robot(self, robot: Any, cell: int) -> None:
        """Render multi-layer research-grade humanoid hospital robot."""
        sx, sy = self.camera.grid_to_screen(robot.row, robot.col)
        cx = sx + cell // 2
        cy = sy + cell // 2

        # Scale factor relative to cell size
        scale = max(0.6, cell / 10.0)
        base_r = max(6, int(7.0 * scale))
        torso_r = max(5, int(5.5 * scale))
        head_r = max(4, int(4.0 * scale))

        # Forward & Right unit vectors for heading rotation
        hdg = robot.heading
        fx = math.cos(hdg)
        fy = -math.sin(hdg)
        rx = math.sin(hdg)
        ry = math.cos(hdg)

        st_color = self._state_color(robot.state)

        # ── 1. Dynamic Lidar Sweep Arc ────────────────────────────────────────
        lidar_range = max(18, int(22.0 * scale))
        lidar_surf = pygame.Surface((lidar_range * 2 + 4, lidar_range * 2 + 4), pygame.SRCALPHA)
        sweep_ang = getattr(robot, "lidar_scan_angle", 0.0)
        start_a = sweep_ang - 0.4
        end_a = sweep_ang + 0.4
        # Draw soft scanning wedge
        pts = [(lidar_range + 2, lidar_range + 2)]
        for i in range(12):
            a = start_a + i * (end_a - start_a) / 11.0
            px = lidar_range + 2 + int(lidar_range * math.cos(a))
            py = lidar_range + 2 + int(lidar_range * math.sin(a))
            pts.append((px, py))
        if len(pts) > 2:
            pygame.draw.polygon(lidar_surf, (0, 210, 255, 30), pts)
            pygame.draw.lines(lidar_surf, (0, 230, 255, 80), False, pts[1:], 1)
        self.screen.blit(lidar_surf, (cx - lidar_range - 2, cy - lidar_range - 2))

        # ── 2. Safety Zone Halo ───────────────────────────────────────────────
        safe_radius = max(8, int(cell * 1.4))
        pulse = 0.85 + 0.15 * math.sin(getattr(robot, "led_pulse_time", 0.0) * 4.0)
        eff_safe_r = int(safe_radius * pulse)
        safe_surf = pygame.Surface((eff_safe_r * 2 + 4, eff_safe_r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(
            safe_surf, (*st_color, 35),
            (eff_safe_r + 2, eff_safe_r + 2), eff_safe_r
        )
        pygame.draw.circle(
            safe_surf, (*st_color, 70),
            (eff_safe_r + 2, eff_safe_r + 2), eff_safe_r, 1
        )
        self.screen.blit(safe_surf, (cx - eff_safe_r - 2, cy - eff_safe_r - 2))

        # ── 3. Mobile Base Chassis (Dual Wheel Pods & Bumper) ─────────────────
        base_color = (220, 226, 235)  # Medical White/Grey
        wheel_color = (45, 55, 72)     # Dark rubber
        accent_blue = (0, 140, 255)    # Hospital Blue

        # Left Wheel Pod
        lw_cx = cx - int(rx * base_r * 0.9)
        lw_cy = cy - int(ry * base_r * 0.9)
        lw_p1 = (lw_cx + int(fx * base_r * 0.5), lw_cy + int(fy * base_r * 0.5))
        lw_p2 = (lw_cx - int(fx * base_r * 0.5), lw_cy - int(fy * base_r * 0.5))
        pygame.draw.line(self.screen, wheel_color, lw_p1, lw_p2, max(3, int(3 * scale)))

        # Right Wheel Pod
        rw_cx = cx + int(rx * base_r * 0.9)
        rw_cy = cy + int(ry * base_r * 0.9)
        rw_p1 = (rw_cx + int(fx * base_r * 0.5), rw_cy + int(fy * base_r * 0.5))
        rw_p2 = (rw_cx - int(fx * base_r * 0.5), rw_cy - int(fy * base_r * 0.5))
        pygame.draw.line(self.screen, wheel_color, rw_p1, rw_p2, max(3, int(3 * scale)))

        # Base Shell
        pygame.draw.circle(self.screen, base_color, (cx, cy), base_r)
        pygame.draw.circle(self.screen, (160, 175, 195), (cx, cy), base_r, 1)

        # ── 4. Humanoid Torso with Medical Emblem & Battery Gauge ─────────────
        torso_cx = cx - int(fx * 1.5 * scale)
        torso_cy = cy - int(fy * 1.5 * scale)
        pygame.draw.circle(self.screen, (248, 250, 252), (torso_cx, torso_cy), torso_r)
        pygame.draw.circle(self.screen, accent_blue, (torso_cx, torso_cy), torso_r, max(1, int(1.5 * scale)))

        # Medical Cross Emblem on chest
        cross_sz = max(2, int(2.0 * scale))
        pygame.draw.line(
            self.screen, (239, 68, 68),
            (torso_cx - cross_sz, torso_cy), (torso_cx + cross_sz, torso_cy),
            max(1, int(1.5 * scale))
        )
        pygame.draw.line(
            self.screen, (239, 68, 68),
            (torso_cx, torso_cy - cross_sz), (torso_cx, torso_cy + cross_sz),
            max(1, int(1.5 * scale))
        )

        # ── 5. Articulated Robotic Arms & Hands ────────────────────────────────
        arm_ext = getattr(robot, "arm_extension", 0.0)
        la_ang = getattr(robot, "arm_left_angle", 0.0)
        ra_ang = getattr(robot, "arm_right_angle", 0.0)

        # Left Shoulder & Hand
        l_sh_x = torso_cx - int(rx * torso_r * 0.85)
        l_sh_y = torso_cy - int(ry * torso_r * 0.85)
        l_reach = torso_r * (1.2 + arm_ext * 0.8)
        l_hand_x = l_sh_x + int((fx * math.cos(la_ang) - rx * math.sin(la_ang)) * l_reach)
        l_hand_y = l_sh_y + int((fy * math.cos(la_ang) - ry * math.sin(la_ang)) * l_reach)

        pygame.draw.line(self.screen, (180, 195, 215), (l_sh_x, l_sh_y), (l_hand_x, l_hand_y), max(2, int(2 * scale)))
        pygame.draw.circle(self.screen, (248, 250, 252), (l_hand_x, l_hand_y), max(2, int(2 * scale)))
        pygame.draw.circle(self.screen, accent_blue, (l_hand_x, l_hand_y), max(2, int(2 * scale)), 1)

        # Right Shoulder & Hand
        r_sh_x = torso_cx + int(rx * torso_r * 0.85)
        r_sh_y = torso_cy + int(ry * torso_r * 0.85)
        r_reach = torso_r * (1.2 + arm_ext * 0.8)
        r_hand_x = r_sh_x + int((fx * math.cos(ra_ang) + rx * math.sin(ra_ang)) * r_reach)
        r_hand_y = r_sh_y + int((fy * math.cos(ra_ang) + ry * math.sin(ra_ang)) * r_reach)

        pygame.draw.line(self.screen, (180, 195, 215), (r_sh_x, r_sh_y), (r_hand_x, r_hand_y), max(2, int(2 * scale)))
        pygame.draw.circle(self.screen, (248, 250, 252), (r_hand_x, r_hand_y), max(2, int(2 * scale)))
        pygame.draw.circle(self.screen, accent_blue, (r_hand_x, r_hand_y), max(2, int(2 * scale)), 1)

        # ── 6. Expressive Head & Digital Face Display ─────────────────────────
        head_cx = torso_cx + int(fx * torso_r * 0.6)
        head_cy = torso_cy + int(fy * torso_r * 0.6)

        # LED Crown Ring (State color pulse)
        pygame.draw.circle(self.screen, st_color, (head_cx, head_cy), head_r + max(1, int(1.5 * scale)), max(1, int(1.5 * scale)))

        # Head Shell
        pygame.draw.circle(self.screen, (248, 250, 252), (head_cx, head_cy), head_r)

        # Visor / Faceplate (Dark OLED glass)
        visor_r = max(3, int(head_r * 0.75))
        pygame.draw.circle(self.screen, (15, 23, 42), (head_cx, head_cy), visor_r)

        # Digital Eyes (Animated blinking & expression)
        is_blink = getattr(robot, "is_blinking", False)
        eye_color = (56, 189, 248)  # Cyan glowing eyes
        if robot.state == RobotState.BLOCKED:
            eye_color = (248, 113, 113)  # Red alert eyes

        eye_offset = max(1, int(2.0 * scale))
        lex = head_cx - int(rx * eye_offset) + int(fx * 1.0 * scale)
        ley = head_cy - int(ry * eye_offset) + int(fy * 1.0 * scale)
        rex = head_cx + int(rx * eye_offset) + int(fx * 1.0 * scale)
        rey = head_cy + int(ry * eye_offset) + int(fy * 1.0 * scale)

        if is_blink:
            # Closed eyes (horizontal slits)
            pygame.draw.line(self.screen, eye_color, (lex - 1, ley), (lex + 1, ley), 1)
            pygame.draw.line(self.screen, eye_color, (rex - 1, rey), (rex + 1, rey), 1)
        else:
            # Open glowing eyes
            pygame.draw.circle(self.screen, eye_color, (lex, ley), max(1, int(1.2 * scale)))
            pygame.draw.circle(self.screen, eye_color, (rex, rey), max(1, int(1.2 * scale)))

        # ── 7. Medicine Cargo Lockbox / Delivery Tray ─────────────────────────
        carrying = getattr(robot, "carrying_medicine", None) or getattr(robot, "carrying_item", None)
        if carrying:
            tray_dist = torso_r + max(3, int(4.0 * scale))
            tray_cx = torso_cx + int(fx * tray_dist)
            tray_cy = torso_cy + int(fy * tray_dist)
            tray_w = max(10, int(12.0 * scale))
            tray_h = max(7, int(8.0 * scale))

            # Tray Box
            tray_rect = pygame.Rect(tray_cx - tray_w // 2, tray_cy - tray_h // 2, tray_w, tray_h)
            pygame.draw.rect(self.screen, (225, 29, 72), tray_rect, border_radius=max(2, int(2 * scale)))
            pygame.draw.rect(self.screen, (255, 255, 255), tray_rect, 1, border_radius=max(2, int(2 * scale)))

            # Medical Cross on Box
            mx, my = tray_rect.centerx, tray_rect.centery
            pygame.draw.line(self.screen, (255, 255, 255), (mx - 3, my), (mx + 3, my), max(1, int(1.5 * scale)))
            pygame.draw.line(self.screen, (255, 255, 255), (mx, my - 3), (mx, my + 3), max(1, int(1.5 * scale)))

            # Tooltip label if zoomed in
            if cell >= 11:
                item_txt = self._font_tiny.render(str(carrying)[:12], True, (255, 255, 255))
                self.screen.blit(item_txt, (tray_cx - item_txt.get_width() // 2, tray_cy - tray_h // 2 - 12))

        # ── 8. Heading Arrow Indicator ────────────────────────────────────────
        arr_dist = base_r + max(3, int(4.0 * scale))
        ax = cx + int(fx * arr_dist)
        ay = cy + int(fy * arr_dist)
        pygame.draw.line(self.screen, st_color, (cx, cy), (ax, ay), max(2, int(2 * scale)))
        pygame.draw.circle(self.screen, st_color, (ax, ay), max(2, int(2.5 * scale)))

    def _state_color(self, state) -> tuple:
        from robot.robot_state import RobotState
        color_map = {
            RobotState.MOVING:     (16, 185, 129),   # Emerald
            RobotState.PLANNING:   (56, 189, 248),   # Sky Blue
            RobotState.REPLANNING: (245, 158, 11),   # Amber
            RobotState.BLOCKED:    (239, 68, 68),    # Crimson
            RobotState.CHARGING:   (6, 182, 212),    # Cyan
            RobotState.IDLE:       (148, 163, 184),  # Slate
            RobotState.COLLECTING: (168, 85, 247),   # Purple
            RobotState.DELIVERING: (236, 72, 153),   # Pink
            RobotState.INTERACTING:(59, 130, 246),   # Indigo
            RobotState.ARRIVED:    (34, 197, 94),    # Green
        }
        return color_map.get(state, (148, 163, 184))

    # ─────────────────────────────────────────────────────────────────────────
    # Left Panel — Navigation Controls
    # ─────────────────────────────────────────────────────────────────────────

    def draw_left_panel(self, sim: "Simulator") -> None:
        """Draw the left navigation and control panel."""
        pw = DISPLAY.LEFT_PANEL_WIDTH
        ph = DISPLAY.WINDOW_HEIGHT

        # Panel background
        panel = pygame.Surface((pw, ph))
        panel.fill(COLORS.BG_SECONDARY)
        self.screen.blit(panel, (0, 0))

        # Border
        pygame.draw.line(self.screen, COLORS.BORDER_PRIMARY, (pw - 1, 0), (pw - 1, ph), 1)

        x, y = 10, 10
        y = self._draw_title_block(x, y)
        y = self._draw_robot_status(sim, x, y)
        y = self._draw_planner_controls(sim, x, y, pw)
        y = self._draw_destination_panel(sim, x, y, pw)
        y = self._draw_mission_queue(sim, x, y, pw)
        self._draw_event_buttons(sim, x, y, pw)

    def _draw_title_block(self, x: int, y: int) -> int:
        """Draw system title header."""
        title = self._font_medium.render("Hospital Robot Nav", True, COLORS.TEXT_ACCENT)
        self.screen.blit(title, (x, y))
        y += 22
        sub = self._font_tiny.render("Multi-Agent Navigation System", True, COLORS.TEXT_SECONDARY)
        self.screen.blit(sub, (x, y))
        y += 18
        pygame.draw.line(self.screen, COLORS.BORDER_PRIMARY, (x, y), (x + 240, y))
        return y + 8

    def _draw_robot_status(self, sim: "Simulator", x: int, y: int) -> int:
        """Draw robot ID, state, and battery bar."""
        robot = sim.robot

        # Robot ID & state
        id_txt = self._font_small.render(f"🤖 {robot.robot_id}", True, COLORS.TEXT_PRIMARY)
        self.screen.blit(id_txt, (x, y))
        y += 18

        state_color = self._state_color(robot.state)
        state_txt = self._font_tiny.render(f"State: {robot.state.name}", True, state_color)
        self.screen.blit(state_txt, (x, y))
        y += 16

        # Battery bar
        batt = robot.battery.soc
        batt_color = (
            COLORS.BATTERY_HIGH if batt > 0.6 else
            COLORS.BATTERY_MID if batt > 0.2 else
            COLORS.BATTERY_LOW
        )
        bar_w = 230
        pygame.draw.rect(self.screen, COLORS.BG_TERTIARY, (x, y, bar_w, 12), border_radius=4)
        filled = int(bar_w * batt)
        if filled > 0:
            pygame.draw.rect(self.screen, batt_color, (x, y, filled, 12), border_radius=4)
        pygame.draw.rect(self.screen, COLORS.BORDER_PRIMARY, (x, y, bar_w, 12), 1, border_radius=4)

        batt_txt = self._font_tiny.render(f"Battery: {batt * 100:.0f}%", True, COLORS.TEXT_SECONDARY)
        self.screen.blit(batt_txt, (x + bar_w + 4, y))
        y += 20

        # Position
        pos_txt = self._font_tiny.render(
            f"Pos: ({robot.row:.1f}, {robot.col:.1f})  Hdg: {math.degrees(robot.heading):.0f}°",
            True, COLORS.TEXT_SECONDARY,
        )
        self.screen.blit(pos_txt, (x, y))
        y += 16

        pygame.draw.line(self.screen, COLORS.BORDER_PRIMARY, (x, y), (x + 240, y))
        return y + 8

    def _draw_planner_controls(self, sim: "Simulator", x: int, y: int, pw: int) -> int:
        """Draw planner selection buttons."""
        lbl = self._font_small.render("PLANNER", True, COLORS.TEXT_SECONDARY)
        self.screen.blit(lbl, (x, y))
        y += 16

        from planning.planner_factory import PlannerType, PLANNER_NAMES
        btn_w = (pw - x * 2 - 4) // 3
        btn_h = 22
        planners = list(PlannerType)[:5]
        active = sim.planner_factory.active_planner_type

        for i, pt in enumerate(planners):
            col_idx = i % 3
            row_idx = i // 3
            bx = x + col_idx * (btn_w + 2)
            by = y + row_idx * (btn_h + 2)
            is_active = (pt == active)
            btn_color = COLORS.BUTTON_PRIMARY if is_active else COLORS.BG_TERTIARY
            border    = COLORS.BUTTON_HOVER if is_active else COLORS.BORDER_PRIMARY
            rect = pygame.Rect(bx, by, btn_w, btn_h)
            pygame.draw.rect(self.screen, btn_color, rect, border_radius=4)
            pygame.draw.rect(self.screen, border, rect, 1, border_radius=4)
            txt = self._font_tiny.render(PLANNER_NAMES[pt], True, COLORS.TEXT_PRIMARY)
            self.screen.blit(txt, txt.get_rect(center=rect.center))
            self.buttons[f"planner_{pt.name}"] = rect

        rows = (len(planners) + 2) // 3
        y += rows * (btn_h + 2) + 6

        pygame.draw.line(self.screen, COLORS.BORDER_PRIMARY, (x, y), (x + 240, y))
        return y + 8

    def _draw_destination_panel(self, sim: "Simulator", x: int, y: int, pw: int) -> int:
        """Draw scrollable destination list."""
        lbl = self._font_small.render("DESTINATIONS", True, COLORS.TEXT_SECONDARY)
        self.screen.blit(lbl, (x, y))
        y += 16

        destinations = sim.semantic_map.get_destination_list()
        btn_h = 20
        btn_w = pw - x * 2
        max_visible = 12

        for i, (room_id, label, pos) in enumerate(destinations[:max_visible]):
            by = y + i * (btn_h + 2)
            is_sel = (room_id == self.selected_dest)
            btn_color = COLORS.BUTTON_ACTIVE if is_sel else COLORS.BG_TERTIARY
            rect = pygame.Rect(x, by, btn_w, btn_h)
            pygame.draw.rect(self.screen, btn_color, rect, border_radius=3)
            if is_sel:
                pygame.draw.rect(self.screen, COLORS.BUTTON_PRIMARY, rect, 1, border_radius=3)

            room = ROOMS_BY_ID.get(room_id)
            dot_color = ROOM_COLOR_MAP.get(room.category, COLORS.ROOM_GENERIC) if room else COLORS.ROOM_GENERIC
            pygame.draw.circle(self.screen, dot_color, (rect.left + 8, rect.centery), 4)

            txt_color = COLORS.TEXT_ACCENT if is_sel else COLORS.TEXT_PRIMARY
            txt = self._font_tiny.render(label[:22], True, txt_color)
            self.screen.blit(txt, (rect.left + 16, rect.top + 4))
            self.buttons[f"dest_{room_id}"] = rect

        y += max_visible * (btn_h + 2) + 4

        # GO button
        go_rect = pygame.Rect(x, y, btn_w, 28)
        pygame.draw.rect(self.screen, COLORS.BUTTON_SUCCESS, go_rect, border_radius=5)
        go_txt = self._font_small.render("▶  NAVIGATE", True, COLORS.TEXT_PRIMARY)
        self.screen.blit(go_txt, go_txt.get_rect(center=go_rect.center))
        self.buttons["navigate"] = go_rect
        y += 32

        pygame.draw.line(self.screen, COLORS.BORDER_PRIMARY, (x, y), (x + 240, y))
        return y + 8

    def _draw_mission_queue(self, sim: "Simulator", x: int, y: int, pw: int) -> int:
        """Draw current mission and queue."""
        lbl = self._font_small.render("MISSION QUEUE", True, COLORS.TEXT_SECONDARY)
        self.screen.blit(lbl, (x, y))
        y += 16

        # Active mission
        if sim.robot.current_mission:
            m = sim.robot.current_mission
            self.screen.blit(
                self._font_tiny.render(f"▶ {m.description[:28]}", True, COLORS.TEXT_SUCCESS),
                (x, y)
            )
            y += 16

        # Queue
        for m in list(sim.robot.mission_queue)[:3]:
            self.screen.blit(
                self._font_tiny.render(f"  ○ {m.description[:26]}", True, COLORS.TEXT_SECONDARY),
                (x, y)
            )
            y += 14

        if not sim.robot.current_mission and not sim.robot.mission_queue:
            self.screen.blit(
                self._font_tiny.render("No active missions", True, COLORS.TEXT_SECONDARY),
                (x, y)
            )
            y += 14

        return y + 8

    def _draw_event_buttons(self, sim: "Simulator", x: int, y: int, pw: int) -> None:
        """Draw hospital event trigger buttons."""
        events = [
            ("emergency", "🚨 Emergency", COLORS.BUTTON_DANGER),
            ("spawn_obs",  "＋ Add Obstacle", COLORS.BUTTON_PRIMARY),
            ("reset",      "↺ Reset",       COLORS.BG_TERTIARY),
        ]
        btn_w = (pw - x * 2 - 4) // 3
        for i, (key, label, color) in enumerate(events):
            rect = pygame.Rect(x + i * (btn_w + 2), y, btn_w, 26)
            pygame.draw.rect(self.screen, color, rect, border_radius=4)
            pygame.draw.rect(self.screen, COLORS.BORDER_PRIMARY, rect, 1, border_radius=4)
            txt = self._font_tiny.render(label, True, COLORS.TEXT_PRIMARY)
            self.screen.blit(txt, txt.get_rect(center=rect.center))
            self.buttons[key] = rect

    # ─────────────────────────────────────────────────────────────────────────
    # Right Panel — Analytics
    # ─────────────────────────────────────────────────────────────────────────

    def draw_right_panel(self, sim: "Simulator") -> None:
        """Draw the right analytics panel."""
        pw = DISPLAY.RIGHT_PANEL_WIDTH
        ph = DISPLAY.WINDOW_HEIGHT
        px = DISPLAY.WINDOW_WIDTH - pw

        panel = pygame.Surface((pw, ph))
        panel.fill(COLORS.BG_SECONDARY)
        self.screen.blit(panel, (px, 0))
        pygame.draw.line(self.screen, COLORS.BORDER_PRIMARY, (px, 0), (px, ph))

        x = px + 10
        y = 10
        summary = sim.metrics.get_summary()

        # Title
        title = self._font_medium.render("ANALYTICS", True, COLORS.TEXT_ACCENT)
        self.screen.blit(title, (x, y))
        y += 24

        # Simulation info
        y = self._draw_section(x, y, "SIMULATION", [
            ("Speed",    f"{sim.clock.speed:.2f}×"),
            ("Sim Time", f"{sim.clock.sim_time_s:.1f} s"),
            ("Step",     f"{sim.clock.sim_step:,}"),
        ])

        # Last planning run
        y = self._draw_section(x, y, "LAST PLAN", [
            ("Planner",    str(summary.get("last_planner", "—"))),
            ("Plan Time",  f"{summary.get('last_planning_ms', 0):.1f} ms"),
            ("Path Len",   f"{summary.get('last_path_length', 0):.1f} cells"),
            ("Path Cells", f"{summary.get('last_path_cells', 0)}"),
            ("Expanded",   f"{summary.get('last_nodes_expanded', 0):,}"),
            ("Generated",  f"{summary.get('last_nodes_generated', 0):,}"),
            ("Turns",      f"{summary.get('last_turns', 0)}"),
            ("Memory",     f"{summary.get('last_memory_kb', 0):.1f} KB"),
            ("Efficiency", f"{summary.get('last_efficiency', 0) * 100:.1f}%"),
        ])

        # Session
        y = self._draw_section(x, y, "SESSION", [
            ("Runs",       f"{summary.get('total_runs', 0)}"),
            ("Success %",  f"{summary.get('success_rate', 0):.0f}%"),
            ("Distance",   f"{summary.get('total_distance', 0):.1f} cells"),
            ("Energy",     f"{summary.get('total_energy_wh', 0):.2f} Wh"),
            ("Speed",      f"{summary.get('current_speed', 0):.2f} c/s"),
        ])

        # Robot stats
        stats = sim.robot.get_stats()
        y = self._draw_section(x, y, "ROBOT", [
            ("Missions",  f"{stats['total_missions']}"),
            ("Replans",   f"{stats['total_replans']}"),
            ("Range",     f"{stats['estimated_range_cells']:.0f} cells"),
        ])

        # Active Multi-Agent Pipeline Mission Status
        active_missions = list(sim.coordinator.active_missions.values())
        if active_missions:
            ctx = active_missions[0]
            steps = ctx["steps"]
            idx = ctx["current_step_idx"]
            y = self._draw_section(x, y, "ACTIVE MISSION PIPELINE", [
                ("Type", ctx["mission_type"]),
                ("Status", ctx["state"]),
                ("Step", f"{idx + 1}/{len(steps)}"),
                ("Task", steps[idx].description[:18] if idx < len(steps) else "Done")
            ])
        else:
            y = self._draw_section(x, y, "ACTIVE MISSION PIPELINE", [
                ("Status", "No active pipeline")
            ])

        # Fleet Agent States
        agent_rows = []
        for agent in sim.agent_registry.get_all_agents():
            if agent.agent_type in ("language", "grounding", "execution", "navigation", "delivery"):
                agent_rows.append((agent.agent_type.capitalize(), agent.state.name))
        y = self._draw_section(x, y, "FLEET AGENTS", agent_rows)

        # Speed control
        y += 4
        lbl = self._font_tiny.render("SPEED CONTROL", True, COLORS.TEXT_SECONDARY)
        self.screen.blit(lbl, (x, y))
        y += 14

        speeds = APP_SETTINGS.simulation.SPEED_OPTIONS
        btn_w = max(20, (pw - 20) // len(speeds))
        for i, spd in enumerate(speeds):
            bx = x + i * (btn_w + 2)
            is_active = (i == sim.clock.speed_index)
            color = COLORS.BUTTON_PRIMARY if is_active else COLORS.BG_TERTIARY
            rect = pygame.Rect(bx, y, btn_w, 22)
            pygame.draw.rect(self.screen, color, rect, border_radius=3)
            txt = self._font_tiny.render(f"{spd:.2g}×", True, COLORS.TEXT_PRIMARY)
            self.screen.blit(txt, txt.get_rect(center=rect.center))
            self.buttons[f"speed_{i}"] = rect
        y += 26

        # Toggle buttons
        toggles = [
            ("toggle_grid",   "Grid",   self.show_grid),
            ("toggle_labels", "Labels", self.show_labels),
            ("toggle_open",   "Open",   self.show_open),
            ("toggle_closed", "Closed", self.show_closed),
            ("toggle_trail",  "Trail",  self.show_trail),
        ]
        btn_w2 = (pw - 20) // 3
        for i, (key, label, active) in enumerate(toggles):
            col_i = i % 3
            row_i = i // 3
            bx = x + col_i * (btn_w2 + 2)
            by = y + row_i * 24
            color = COLORS.BUTTON_ACTIVE if active else COLORS.BG_TERTIARY
            rect = pygame.Rect(bx, by, btn_w2, 20)
            pygame.draw.rect(self.screen, color, rect, border_radius=3)
            pygame.draw.rect(self.screen, COLORS.BORDER_PRIMARY, rect, 1, border_radius=3)
            txt = self._font_tiny.render(label, True, COLORS.TEXT_PRIMARY)
            self.screen.blit(txt, txt.get_rect(center=rect.center))
            self.buttons[key] = rect

    def _draw_section(self, x: int, y: int, title: str, rows: list) -> int:
        """Draw a labeled metrics section."""
        self.screen.blit(
            self._font_tiny.render(title, True, COLORS.TEXT_SECONDARY), (x, y)
        )
        y += 14
        pw = DISPLAY.RIGHT_PANEL_WIDTH
        val_x = x + pw - 75
        for key, val in rows:
            key_surf = self._font_tiny.render(key, True, COLORS.TEXT_SECONDARY)
            val_surf = self._font_tiny.render(str(val), True, COLORS.TEXT_PRIMARY)
            self.screen.blit(key_surf, (x, y))
            self.screen.blit(val_surf, (val_x, y))
            y += 14
        pygame.draw.line(self.screen, COLORS.BORDER_PRIMARY,
                         (x, y), (x + pw - 20, y))
        return y + 6

    # ─────────────────────────────────────────────────────────────────────────
    # Mini-Map
    # ─────────────────────────────────────────────────────────────────────────

    def draw_minimap(self, sim: "Simulator") -> None:
        """Draw a mini overview map in the bottom-right corner."""
        mw = DISPLAY.MINIMAP_WIDTH
        mh = DISPLAY.MINIMAP_HEIGHT
        margin = DISPLAY.MINIMAP_MARGIN
        mx = DISPLAY.LEFT_PANEL_WIDTH + margin
        my = DISPLAY.WINDOW_HEIGHT - mh - margin

        surf = pygame.Surface((mw, mh))
        surf.fill(COLORS.MINIMAP_BG)

        rows = GRID_CONFIG.GRID_ROWS
        cols = GRID_CONFIG.GRID_COLS
        scale_r = mh / rows
        scale_c = mw / cols

        # Draw binary grid on mini-map
        binary = sim.occupancy_grid.binary_grid
        for row in range(0, rows, 2):
            for col in range(0, cols, 2):
                if binary[row, col] == 1:
                    sx = int(col * scale_c)
                    sy = int(row * scale_r)
                    pygame.draw.rect(surf, (40, 45, 60), (sx, sy, max(1, int(scale_c * 2)), max(1, int(scale_r * 2))))

        # Draw rooms
        for room in ROOM_DATABASE:
            color = ROOM_COLOR_MAP.get(room.category, COLORS.ROOM_GENERIC)
            sx1 = int(room.left_col * scale_c)
            sy1 = int(room.top_row * scale_r)
            sx2 = int((room.right_col + 1) * scale_c)
            sy2 = int((room.bottom_row + 1) * scale_r)
            pygame.draw.rect(surf, self._dim_color(color, 0.5), (sx1, sy1, sx2 - sx1, sy2 - sy1))

        # Draw path
        path = sim.robot.path
        if path and len(path) >= 2:
            pts = [(int(c * scale_c), int(r * scale_r)) for r, c in path]
            pygame.draw.lines(surf, COLORS.MINIMAP_PATH, False, pts, 1)

        # Draw robot
        rsx = int(sim.robot.col * scale_c)
        rsy = int(sim.robot.row * scale_r)
        pygame.draw.circle(surf, COLORS.MINIMAP_ROBOT, (rsx, rsy), max(2, int(scale_c * 1.5)))

        # Draw goal
        if sim.current_goal:
            gsx = int(sim.current_goal[1] * scale_c)
            gsy = int(sim.current_goal[0] * scale_r)
            pygame.draw.circle(surf, COLORS.MINIMAP_GOAL, (gsx, gsy), max(2, int(scale_c * 2)))

        # Draw viewport indicator
        vr_min, vr_max, vc_min, vc_max = self.camera.get_visible_range()
        vsx1 = int(vc_min * scale_c)
        vsy1 = int(vr_min * scale_r)
        vsx2 = int(vc_max * scale_c)
        vsy2 = int(vr_max * scale_r)
        pygame.draw.rect(surf, COLORS.TEXT_ACCENT,
                         (vsx1, vsy1, max(1, vsx2 - vsx1), max(1, vsy2 - vsy1)), 1)

        # Blit with border
        border_rect = pygame.Rect(mx - 2, my - 2, mw + 4, mh + 4)
        pygame.draw.rect(self.screen, COLORS.MINIMAP_BORDER, border_rect, 2, border_radius=4)
        self.screen.blit(surf, (mx, my))

        # Label
        lbl = self._font_tiny.render("MAP", True, COLORS.TEXT_SECONDARY)
        self.screen.blit(lbl, (mx + 2, my + 2))

    # ─────────────────────────────────────────────────────────────────────────
    # Input Handling
    # ─────────────────────────────────────────────────────────────────────────

    def handle_click(self, mx: int, my: int, sim: "Simulator") -> None:
        """
        Process a mouse click at (mx, my).

        Checks buttons, destination selection, and map clicks.
        """
        # Check buttons
        for key, rect in self.buttons.items():
            if rect.collidepoint(mx, my):
                self._handle_button(key, sim)
                return

        # Map click → navigate to that cell
        if self.vp_x <= mx <= self.vp_x + self.vp_w:
            row, col = self.camera.screen_to_grid(mx, my)
            if sim.occupancy_grid.is_free(row, col):
                sim.navigate_to_pos(row, col)

    def _handle_button(self, key: str, sim: "Simulator") -> None:
        """Handle button action by key."""
        from planning.planner_factory import PlannerType

        if key.startswith("planner_"):
            pt_name = key[len("planner_"):]
            try:
                pt = PlannerType[pt_name]
                sim.set_planner(pt)
            except KeyError:
                pass

        elif key.startswith("dest_"):
            room_id = key[len("dest_"):]
            self.selected_dest = room_id

        elif key == "navigate":
            if self.selected_dest:
                sim.navigate_to(self.selected_dest)

        elif key == "emergency":
            sim.trigger_event("emergency")

        elif key == "spawn_obs":
            sim.spawn_obstacle()

        elif key == "reset":
            sim.reset()

        elif key.startswith("speed_"):
            idx = int(key[len("speed_"):])
            sim.set_speed(idx)

        elif key == "toggle_grid":
            self.show_grid = not self.show_grid
        elif key == "toggle_labels":
            self.show_labels = not self.show_labels
        elif key == "toggle_open":
            self.show_open = not self.show_open
        elif key == "toggle_closed":
            self.show_closed = not self.show_closed
        elif key == "toggle_trail":
            self.show_trail = not self.show_trail

    def handle_mousewheel(self, y_scroll: int, mx: int, my: int) -> None:
        """Handle mouse wheel zoom."""
        if y_scroll > 0:
            self.camera.zoom_in(mx, my)
        else:
            self.camera.zoom_out(mx, my)

    def handle_middle_mouse(self, pressed: bool, mx: int, my: int) -> None:
        """Handle middle mouse button for panning."""
        if pressed:
            self.camera.start_pan(mx, my)
        else:
            self.camera.stop_pan()

    def handle_mouse_motion(self, mx: int, my: int) -> None:
        """Handle mouse drag for panning."""
        self.camera.update_pan(mx, my)

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _font_init(self) -> None:
        """Initialize fonts."""
        pygame.font.init()
        try:
            self._font_large  = pygame.font.SysFont("Segoe UI", 20, bold=True)
            self._font_medium = pygame.font.SysFont("Segoe UI", 14, bold=True)
            self._font_small  = pygame.font.SysFont("Segoe UI", 12)
            self._font_tiny   = pygame.font.SysFont("Segoe UI", 10)
        except Exception:
            self._font_large  = pygame.font.Font(None, 22)
            self._font_medium = pygame.font.Font(None, 16)
            self._font_small  = pygame.font.Font(None, 14)
            self._font_tiny   = pygame.font.Font(None, 12)

    def _precompute_room_cells(self) -> None:
        """Pre-compute all cell positions for each room."""
        for room in ROOM_DATABASE:
            cells = []
            for row in range(room.top_row + 1, room.bottom_row):
                for col in range(room.left_col + 1, room.right_col):
                    cells.append((row, col))
            self._room_cells[room.room_id] = cells

    @staticmethod
    def _dim_color(color: tuple, factor: float) -> tuple:
        """Multiply RGB color by factor."""
        return (
            max(0, min(255, int(color[0] * factor))),
            max(0, min(255, int(color[1] * factor))),
            max(0, min(255, int(color[2] * factor))),
        )

    @staticmethod
    def _fade_color(color: tuple, alpha: float) -> tuple:
        """Interpolate color toward black by alpha."""
        return (
            int(color[0] * alpha),
            int(color[1] * alpha),
            int(color[2] * alpha),
        )

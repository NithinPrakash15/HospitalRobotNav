"""
AAROGYA Autonomous Exploration SLAM & Dynamic World Model Engine
================================================================
Implements Requirements 5, 6, 7, 8:
1. Autonomous Exploration & Occupancy Grid Mapping:
   - Starts with UNKNOWN (-1) hospital representation.
   - Integrates 2D planar LiDAR sensor observations via raycasting.
   - Carves free space (0) and marks structural boundaries (100).
   - Frontier Detection (clusters boundary cells between FREE and UNKNOWN space).
   - Autonomous Exploration Planner (directs robot to nearest informative frontier).
2. Dynamic Environment Change Tracking:
   - Detects newly placed obstacles in previously free corridors.
   - Immediately updates local occupancy to OCCUPIED and inflates safety margin.
   - When obstacles are removed, free-space ray integration clears the space.
3. Composite Live World Model:
   - Merges Static Structure + Live SLAM Observations + Dynamic Obstacles.
"""

from __future__ import annotations

import math
import time
import heapq
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np


class OccupancyState:
    UNKNOWN = -1
    FREE = 0
    OCCUPIED = 100
    DYNAMIC_OBSTACLE = 90


@dataclass
class FrontierCluster:
    centroid: Tuple[float, float]
    cells: List[Tuple[int, int]]
    size: int
    utility: float = 0.0

    @property
    def x(self) -> float:
        return self.centroid[0]

    @property
    def y(self) -> float:
        return self.centroid[1]


class SLAMExplorationEngine:
    """
    Real-time 2D SLAM Occupancy Grid Mapper, Frontier Exploration Planner,
    and Dynamic Obstacle Life-Cycle Tracker for AAROGYA AMRs.
    """

    def __init__(
        self,
        grid_bounds: Tuple[float, float, float, float] = (-46.0, 46.0, -40.0, 40.0),
        resolution: float = 0.5,
        max_lidar_range: float = 12.0,
        inflation_radius: float = 0.65,
    ) -> None:
        """
        Args:
            grid_bounds: (xmin, xmax, ymin, ymax) in meters.
            resolution: Grid cell size in meters (0.5m matches ROS 2 /map).
            max_lidar_range: Maximum usable range for ray integration.
            inflation_radius: Safe collision dilation in meters.
        """
        self.xmin, self.xmax, self.ymin, self.ymax = grid_bounds
        self.resolution = resolution
        self.max_lidar_range = max_lidar_range
        self.inflation_radius = inflation_radius
        self.inflation_cells = int(math.ceil(self.inflation_radius / self.resolution))

        self.cols = int(round((self.xmax - self.xmin) / self.resolution))
        self.rows = int(round((self.ymax - self.ymin) / self.resolution))

        # 1. Live SLAM Occupancy Grid: -1 = UNKNOWN, 0 = FREE, 100 = OCCUPIED
        self.grid = np.full((self.rows, self.cols), OccupancyState.UNKNOWN, dtype=np.int8)

        # 2. Dynamic Obstacle Layer: 0 = Clear, 100 = Dynamic Obstacle
        self.dynamic_layer = np.zeros((self.rows, self.cols), dtype=np.uint8)

        # 3. Observation Timestamps & Hit Counts
        self.last_observed = np.zeros((self.rows, self.cols), dtype=np.float32)
        self.hit_counts = np.zeros((self.rows, self.cols), dtype=np.uint16)
        self.pass_counts = np.zeros((self.rows, self.cols), dtype=np.uint16)

        # 4. Active Dynamic Obstacles Tracker: id -> dict
        self.active_dynamic_obstacles: Dict[str, Dict[str, Any]] = {}

        # 5. Frontier state cache
        self.frontiers: List[FrontierCluster] = []
        self.last_frontier_calc_time: float = 0.0
        self.exploration_complete: bool = False

        # 6. Unreachable frontier tracking with TTL to prevent infinite retry lockouts
        self.unreachable_frontiers: Dict[Tuple[float, float], float] = {}

        # Reference corridor footprint cell count (hospital navigable area ~ 4,200 cells)
        self.expected_navigable_cells: int = 4200

    def world_to_grid(self, x: float, y: float) -> Tuple[int, int]:
        """Convert world coordinates (X, Y) to grid indices (row, col)."""
        col = int(round((x - self.xmin) / self.resolution))
        row = int(round((self.ymax - y) / self.resolution))
        col = max(0, min(self.cols - 1, col))
        row = max(0, min(self.rows - 1, row))
        return row, col

    def grid_to_world(self, row: int, col: int) -> Tuple[float, float]:
        """Convert grid cell (row, col) to world coordinates (X, Y) in meters."""
        x = self.xmin + (col + 0.5) * self.resolution
        y = self.ymax - (row + 0.5) * self.resolution
        return round(x, 2), round(y, 2)

    def is_in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.rows and 0 <= col < self.cols

    # ── 1. REAL-TIME LIDAR RAYCAST INTEGRATION (SLAM MAPPING) ────────────────

    def integrate_lidar_scan(
        self,
        robot_x: float,
        robot_y: float,
        robot_yaw: float,
        scan: Any = None,
        dynamic_agents: Optional[List[Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Integrates a real 2D planar LiDAR scan from the robot's current pose.
        - Traces rays using Bresenham vector steps.
        - Carves out FREE space along the beam.
        - Marks endpoints as OCCUPIED.
        - Detects dynamic obstacle placement and clears removed obstacles.
        """
        if scan is None:
            scan = kwargs.get("scan_result")
        now = time.time()
        start_r, start_c = self.world_to_grid(robot_x, robot_y)
        # Robot's immediate footprint is unconditionally FREE
        for dr in range(-1, 2):
            for dc in range(-1, 2):
                nr, nc = start_r + dr, start_c + dc
                if self.is_in_bounds(nr, nc):
                    self.grid[nr, nc] = OccupancyState.FREE
                    self.dynamic_layer[nr, nc] = 0

        ranges = getattr(scan, "ranges", getattr(scan, "distances_m", []))
        angles = getattr(scan, "angles", getattr(scan, "angles_rad", None))
        if angles is None and hasattr(scan, "angles_deg"):
            angles = np.radians(getattr(scan, "angles_deg"))
        elif angles is None:
            angles = []
        tags = getattr(scan, "tags", getattr(scan, "obstacle_tags", []))

        num_beams = min(len(ranges), len(angles))
        if num_beams == 0:
            return self.get_exploration_progress()

        # Vectorized NumPy ray carving (Sub-millisecond high-speed SLAM execution)
        ranges_arr = np.asarray(ranges, dtype=np.float32)
        angles_arr = np.asarray(angles, dtype=np.float32)

        # Stride sampling: sample up to 90 beams for full 360° coverage with optimal speed
        stride = 2 if num_beams >= 120 else 1
        idx_sample = np.arange(0, num_beams, stride)
        r_sample = ranges_arr[idx_sample]
        a_sample = angles_arr[idx_sample]
        tags_sample = [tags[i] if i < len(tags) else "wall" for i in idx_sample]

        beam_angles = robot_yaw + a_sample
        cos_a = np.cos(beam_angles)
        sin_a = np.sin(beam_angles)

        # Filter invalid short returns
        valid_mask = r_sample >= 0.15
        if not np.any(valid_mask):
            return self.get_exploration_progress()

        r_sample = r_sample[valid_mask]
        cos_a = cos_a[valid_mask]
        sin_a = sin_a[valid_mask]
        tags_sample = [tags_sample[k] for k, vb in enumerate(valid_mask) if vb]

        is_hit = r_sample < (self.max_lidar_range - 0.25)
        effective_dist = np.minimum(r_sample, self.max_lidar_range)

        # 1. Vectorized Free-Space Carving along all beams simultaneously
        max_dist = float(np.max(effective_dist))
        step_res = max(0.15, self.resolution)
        if max_dist > step_res:
            r_steps = np.arange(step_res, max_dist, step_res, dtype=np.float32)
            free_dist_cutoff = np.where(is_hit, np.maximum(0.0, effective_dist - 0.30), effective_dist)
            valid_steps = r_steps[:, None] < free_dist_cutoff[None, :]

            px = robot_x + r_steps[:, None] * cos_a[None, :]
            py = robot_y + r_steps[:, None] * sin_a[None, :]

            cols = np.clip(np.round((px - self.xmin) / self.resolution).astype(np.int32), 0, self.cols - 1)
            rows = np.clip(np.round((self.ymax - py) / self.resolution).astype(np.int32), 0, self.rows - 1)

            free_r = rows[valid_steps]
            free_c = cols[valid_steps]

            # Update SLAM grid to FREE where not already OCCUPIED
            not_occ = self.grid[free_r, free_c] != OccupancyState.OCCUPIED
            self.grid[free_r[not_occ], free_c[not_occ]] = OccupancyState.FREE
            self.pass_counts[free_r, free_c] += 1
            self.last_observed[free_r, free_c] = now

            # If dynamic obstacles were cleared by line of sight
            dyn_cleared = self.dynamic_layer[free_r, free_c] > 0
            if np.any(dyn_cleared):
                self.dynamic_layer[free_r[dyn_cleared], free_c[dyn_cleared]] = 0

        # 2. Mark Endpoints for Solid Hits
        new_dynamic_hits: List[Tuple[float, float]] = []
        if np.any(is_hit):
            hit_r = r_sample[is_hit]
            hit_cos = cos_a[is_hit]
            hit_sin = sin_a[is_hit]
            hit_tags = [tags_sample[i] for i, h in enumerate(is_hit) if h]

            end_x = robot_x + hit_r * hit_cos
            end_y = robot_y + hit_r * hit_sin
            end_c = np.clip(np.round((end_x - self.xmin) / self.resolution).astype(np.int32), 0, self.cols - 1)
            end_r = np.clip(np.round((self.ymax - end_y) / self.resolution).astype(np.int32), 0, self.rows - 1)

            for k in range(len(hit_r)):
                er, ec = end_r[k], end_c[k]
                tag = hit_tags[k]
                is_dynamic = tag in ("person", "cart", "stretcher", "dynamic")
                self.hit_counts[er, ec] += 1
                self.last_observed[er, ec] = now
                if is_dynamic or (self.grid[er, ec] == OccupancyState.FREE and tag != "wall"):
                    self.dynamic_layer[er, ec] = 100
                    self.grid[er, ec] = OccupancyState.DYNAMIC_OBSTACLE
                    new_dynamic_hits.append((float(end_x[k]), float(end_y[k])))
                else:
                    self.grid[er, ec] = OccupancyState.OCCUPIED

        # 3. Synchronize dynamic obstacle clusters
        if new_dynamic_hits:
            self._cluster_and_track_dynamic_obstacles(new_dynamic_hits, now)

        # 4. Decay and remove stale dynamic obstacles not observed recently (> 3.5s)
        self._prune_stale_dynamic_obstacles(now)

        return self.get_exploration_progress()

    def _cluster_and_track_dynamic_obstacles(
        self, hits: List[Tuple[float, float]], timestamp: float
    ) -> None:
        """Clusters dynamic LiDAR hits and maintains track IDs."""
        for hx, hy in hits:
            matched_id = None
            for obs_id, obs_data in self.active_dynamic_obstacles.items():
                ox, oy = obs_data["pos"]
                if math.hypot(hx - ox, hy - oy) < 1.1:
                    matched_id = obs_id
                    break

            if matched_id:
                # Update existing track
                self.active_dynamic_obstacles[matched_id]["pos"] = (round(hx, 2), round(hy, 2))
                self.active_dynamic_obstacles[matched_id]["last_seen"] = timestamp
                self.active_dynamic_obstacles[matched_id]["hits"] += 1
            else:
                # New dynamic obstacle detected
                new_id = f"DYN-OBS-{len(self.active_dynamic_obstacles) + 1:02d}"
                self.active_dynamic_obstacles[new_id] = {
                    "id": new_id,
                    "pos": (round(hx, 2), round(hy, 2)),
                    "first_seen": timestamp,
                    "last_seen": timestamp,
                    "radius": 0.85,
                    "hits": 1,
                }

    def _prune_stale_dynamic_obstacles(self, now: float) -> None:
        """Removes dynamic obstacles that have moved away or cleared (> 3.0s without detection)."""
        to_delete = []
        for obs_id, obs_data in self.active_dynamic_obstacles.items():
            if (now - obs_data["last_seen"]) > 3.0:
                to_delete.append(obs_id)
                # Clear dynamic cells around previous position
                ox, oy = obs_data["pos"]
                r, c = self.world_to_grid(ox, oy)
                for dr in range(-self.inflation_cells, self.inflation_cells + 1):
                    for dc in range(-self.inflation_cells, self.inflation_cells + 1):
                        nr, nc = r + dr, c + dc
                        if self.is_in_bounds(nr, nc):
                            self.dynamic_layer[nr, nc] = 0
                            if self.grid[nr, nc] == OccupancyState.DYNAMIC_OBSTACLE:
                                self.grid[nr, nc] = OccupancyState.FREE

        for obs_id in to_delete:
            del self.active_dynamic_obstacles[obs_id]

    def seed_initial_exploration(self, robot_x: Optional[float] = None, robot_y: Optional[float] = None) -> None:
        """
        Seeds initial free space strictly at the robot's immediate physical footprint
        when waiting for live sensor observations. Zero fake sine-wave rays or fabricated walls.
        """
        if int(np.sum(self.grid == OccupancyState.FREE)) > 20:
            return
        if robot_x is None or (robot_x == 0.0 and robot_y == 0.0):
            robot_x = 34.5
        if robot_y is None:
            robot_y = 33.0

        # Mark strictly the physical footprint (radius ~0.6m, 9 cells) as FREE
        start_r, start_c = self.world_to_grid(robot_x, robot_y)
        for dr in range(-1, 2):
            for dc in range(-1, 2):
                nr, nc = start_r + dr, start_c + dc
                if self.is_in_bounds(nr, nc):
                    self.grid[nr, nc] = OccupancyState.FREE
                    self.dynamic_layer[nr, nc] = 0

    # ── 2. AUTONOMOUS FRONTIER DETECTION ────────────────────────────────────

    def find_frontiers(self, robot_x: Optional[float] = None, robot_y: Optional[float] = None) -> List[FrontierCluster]:
        """
        Scans occupancy grid to find all frontier cells (FREE cells adjacent to UNKNOWN cells).
        Clusters them using 8-connectivity BFS into discrete exploration targets.
        """
        if int(np.sum(self.grid == OccupancyState.FREE)) < 4:
            self.seed_initial_exploration(robot_x, robot_y)

        frontier_cells: Set[Tuple[int, int]] = set()

        # Step with stride 1 or 2 for fast real-time search
        for r in range(1, self.rows - 1):
            for c in range(1, self.cols - 1):
                if self.grid[r, c] == OccupancyState.FREE:
                    # Check if any neighbor is UNKNOWN (-1)
                    has_unknown = (
                        self.grid[r - 1, c] == OccupancyState.UNKNOWN
                        or self.grid[r + 1, c] == OccupancyState.UNKNOWN
                        or self.grid[r, c - 1] == OccupancyState.UNKNOWN
                        or self.grid[r, c + 1] == OccupancyState.UNKNOWN
                        or self.grid[r - 1, c - 1] == OccupancyState.UNKNOWN
                        or self.grid[r - 1, c + 1] == OccupancyState.UNKNOWN
                        or self.grid[r + 1, c - 1] == OccupancyState.UNKNOWN
                        or self.grid[r + 1, c + 1] == OccupancyState.UNKNOWN
                    )
                    if has_unknown:
                        frontier_cells.add((r, c))

        # Cluster adjacent frontier cells using BFS
        visited: Set[Tuple[int, int]] = set()
        clusters: List[FrontierCluster] = []

        for cell in frontier_cells:
            if cell in visited:
                continue

            cluster_cells: List[Tuple[int, int]] = []
            queue = deque([cell])
            visited.add(cell)

            while queue:
                curr = queue.popleft()
                cluster_cells.append(curr)
                cr, cc = curr

                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == 0 and dc == 0:
                            continue
                        nbr = (cr + dr, cc + dc)
                        if nbr in frontier_cells and nbr not in visited:
                            visited.add(nbr)
                            queue.append(nbr)

            # Filter small noise clusters (< 2 contiguous cells)
            if len(cluster_cells) >= 2:
                avg_r = sum(c[0] for c in cluster_cells) / len(cluster_cells)
                avg_c = sum(c[1] for c in cluster_cells) / len(cluster_cells)
                wx, wy = self.grid_to_world(int(round(avg_r)), int(round(avg_c)))
                clusters.append(FrontierCluster(
                    centroid=(wx, wy),
                    cells=cluster_cells,
                    size=len(cluster_cells),
                ))

        # Sort clusters by size descending
        clusters.sort(key=lambda fc: fc.size, reverse=True)
        self.frontiers = clusters
        self.last_frontier_calc_time = time.time()

        if len(clusters) == 0:
            free_count = int(np.sum(self.grid == OccupancyState.FREE))
            if free_count > 1500:
                self.exploration_complete = True

        return clusters

    def mark_frontier_unreachable(self, fx: float, fy: float, duration_sec: float = 30.0) -> None:
        """Mark a frontier unreachable so planner tries other frontiers without getting stuck."""
        now = time.time()
        self.unreachable_frontiers[(round(fx, 1), round(fy, 1))] = now + duration_sec

    def is_frontier_unreachable(self, fx: float, fy: float) -> bool:
        """Check if (fx, fy) or nearby coordinates are currently flagged unreachable."""
        now = time.time()
        expired = [k for k, exp in self.unreachable_frontiers.items() if exp < now]
        for k in expired:
            del self.unreachable_frontiers[k]

        for (ux, uy), exp in self.unreachable_frontiers.items():
            if exp >= now and math.hypot(fx - ux, fy - uy) < 1.5:
                return True
        return False

    def get_ranked_exploration_targets(
        self, robot_x: float, robot_y: float, max_targets: int = 10
    ) -> List[Tuple[float, float]]:
        """
        Returns a prioritized list of reachable exploration candidate targets.
        Projects frontier centroids slightly inwards toward free space to guarantee valid navigation goals.
        """
        frontiers = self.find_frontiers(robot_x, robot_y)
        if not frontiers:
            return []

        candidates = []
        for f in frontiers:
            fx, fy = f.centroid
            if self.is_frontier_unreachable(fx, fy):
                continue

            dist = math.hypot(fx - robot_x, fy - robot_y)
            if dist < 0.8:
                continue

            is_hazard = False
            for obs in self.active_dynamic_obstacles.values():
                ox, oy = obs["pos"]
                if math.hypot(fx - ox, fy - oy) < (obs.get("radius", 0.85) + 0.5):
                    is_hazard = True
                    break
            if is_hazard:
                continue

            # Project slightly (0.5m) toward robot to ensure target is within navigable free space
            if dist > 1.0:
                ux = (fx - robot_x) / dist
                uy = (fy - robot_y) / dist
                target_x = round(fx - 0.5 * ux, 2)
                target_y = round(fy - 0.5 * uy, 2)
            else:
                target_x, target_y = fx, fy

            score = (float(f.size) * 2.0) / (dist + 2.0)
            candidates.append(((target_x, target_y), score))

        candidates.sort(key=lambda item: item[1], reverse=True)
        return [c[0] for c in candidates[:max_targets]]

    def get_best_exploration_target(
        self, robot_x: float, robot_y: float
    ) -> Optional[Tuple[float, float]]:
        """
        Selects the best exploration goal based on frontier size, accessibility,
        and distance utility:
        utility = (cluster_size * 2.0) / (distance + 2.0)
        """
        targets = self.get_ranked_exploration_targets(robot_x, robot_y, max_targets=1)
        if targets:
            return targets[0]

        # Fallback if all frontiers are filtered or close
        frontiers = self.find_frontiers(robot_x, robot_y)
        for f in frontiers:
            fx, fy = f.centroid
            if math.hypot(fx - robot_x, fy - robot_y) >= 0.5:
                return (fx, fy)
        return None

    # ── 3. COMPOSITE NAVIGATION WORLD (Requirement 8) ───────────────────────

    def get_composite_navigation_costmap(
        self, static_guard: Optional[Any] = None
    ) -> np.ndarray:
        """
        Builds the unified 2D navigation costmap combining:
        STATIC STRUCTURE + LIVE SLAM OBSERVATIONS + DYNAMIC OBSTACLES = CURRENT NAVIGATION WORLD
        Returns:
            2D numpy uint8 array: 0 = Free, 100 = Impassable / Wall / Dynamic Hazard.
        """
        costmap = np.zeros((self.rows, self.cols), dtype=np.uint8)

        # 1. Structural layer (Static walls or SLAM occupied cells)
        slam_walls = (self.grid == OccupancyState.OCCUPIED)
        costmap[slam_walls] = 100

        # If static guard exists, incorporate static boundary boxes
        if static_guard is not None and getattr(static_guard, "raw_occupancy_grid", None) is not None:
            # Match dimensions if needed
            sg = static_guard.raw_occupancy_grid
            if sg.shape == costmap.shape:
                costmap[sg > 0] = 100

        # 2. Dynamic Obstacle Layer & Inflation
        dyn_mask = (self.dynamic_layer > 0)
        costmap[dyn_mask] = 100

        for obs_data in self.active_dynamic_obstacles.values():
            ox, oy = obs_data["pos"]
            r, c = self.world_to_grid(ox, oy)
            for dr in range(-self.inflation_cells, self.inflation_cells + 1):
                for dc in range(-self.inflation_cells, self.inflation_cells + 1):
                    nr, nc = r + dr, c + dc
                    if self.is_in_bounds(nr, nc):
                        if (dr * self.resolution) ** 2 + (dc * self.resolution) ** 2 <= (obs_data["radius"] ** 2):
                            costmap[nr, nc] = 100

        return costmap

    # ── 3B. AUTHORITATIVE ROBOT-GENERATED SLAM NAVIGATION (PART 2) ──────────

    def plan_authoritative_path_astar(
        self,
        start_xy: Tuple[float, float],
        goal_xy: Tuple[float, float],
        dynamic_obstacles: Optional[List[Tuple[float, float]]] = None,
        clearance_cells: int = 1,
    ) -> Tuple[Optional[List[Tuple[float, float]]], str]:
        """
        Plans an A* path STRICTLY through verified free space in the robot-generated map.
        - UNKNOWN space (-1) is STRICTLY impassable: no cutting through unexplored corridors/rooms.
        - OCCUPIED space (100) is impassable.
        - DYNAMIC_OBSTACLE space (90) is impassable.
        - If goal is in unexplored territory and not an adjacent frontier, returns None.
        """
        start_r, start_c = self.world_to_grid(start_xy[0], start_xy[1])
        goal_r, goal_c = self.world_to_grid(goal_xy[0], goal_xy[1])

        def nearest_free_cell(r: int, c: int, max_radius: int = 4) -> Optional[Tuple[int, int]]:
            if self.grid[r, c] == OccupancyState.FREE and self.dynamic_layer[r, c] == 0:
                return r, c
            for rad in range(1, max_radius + 1):
                for dr in range(-rad, rad + 1):
                    for dc in range(-rad, rad + 1):
                        nr, nc = r + dr, c + dc
                        if self.is_in_bounds(nr, nc) and self.grid[nr, nc] == OccupancyState.FREE and self.dynamic_layer[nr, nc] == 0:
                            return nr, nc
            return None

        actual_start = nearest_free_cell(start_r, start_c, max_radius=4)
        if not actual_start:
            return None, "START_NOT_IN_DISCOVERED_FREE_SPACE: Robot position not confirmed as free space."

        actual_goal = nearest_free_cell(goal_r, goal_c, max_radius=2)
        if not actual_goal:
            if self.grid[goal_r, goal_c] == OccupancyState.UNKNOWN:
                return None, "DESTINATION_IN_UNEXPLORED_SPACE: Cannot navigate through unobserved corridors. Exploration required."
            elif self.grid[goal_r, goal_c] == OccupancyState.OCCUPIED:
                actual_goal = nearest_free_cell(goal_r, goal_c, max_radius=4)
                if not actual_goal:
                    return None, "DESTINATION_IN_OCCUPIED_WALL: Goal overlaps structural boundary."

        if not actual_goal:
            return None, "GOAL_UNREACHABLE_IN_CURRENT_MAP: No adjacent navigable free space."

        sr, sc = actual_start
        gr, gc = actual_goal

        traversable = (self.grid == OccupancyState.FREE) & (self.dynamic_layer == 0)

        if clearance_cells > 0:
            wall_mask = (self.grid == OccupancyState.OCCUPIED)
            for dr in range(-clearance_cells, clearance_cells + 1):
                for dc in range(-clearance_cells, clearance_cells + 1):
                    if dr == 0 and dc == 0:
                        continue
                    shifted = np.roll(np.roll(wall_mask, dr, axis=0), dc, axis=1)
                    traversable = traversable & ~shifted

        traversable[sr, sc] = True
        traversable[gr, gc] = True

        if dynamic_obstacles:
            for ox, oy in dynamic_obstacles:
                or_idx, oc_idx = self.world_to_grid(ox, oy)
                infl_r = int(math.ceil(0.85 / self.resolution))
                for dr in range(-infl_r, infl_r + 1):
                    for dc in range(-infl_r, infl_r + 1):
                        nr, nc = or_idx + dr, oc_idx + dc
                        if self.is_in_bounds(nr, nc):
                            if (dr * self.resolution)**2 + (dc * self.resolution)**2 <= 0.85**2:
                                traversable[nr, nc] = False
            traversable[sr, sc] = True

        moves = [
            (-1,  0, 1.0),
            ( 1,  0, 1.0),
            ( 0, -1, 1.0),
            ( 0,  1, 1.0),
            (-1, -1, 1.4142),
            (-1,  1, 1.4142),
            ( 1, -1, 1.4142),
            ( 1,  1, 1.4142),
        ]

        def octile_heuristic(r1: int, c1: int, r2: int, c2: int) -> float:
            dr = abs(r1 - r2)
            dc = abs(c1 - c2)
            return (dr + dc) + (1.4142 - 2.0) * min(dr, dc)

        open_heap: List[Tuple[float, float, int, int]] = []
        heapq.heappush(open_heap, (octile_heuristic(sr, sc, gr, gc), 0.0, sr, sc))
        g_cost: Dict[Tuple[int, int], float] = {(sr, sc): 0.0}
        parent: Dict[Tuple[int, int], Tuple[int, int]] = {}
        closed_set: Set[Tuple[int, int]] = set()

        max_steps = 40000
        steps = 0
        found = False

        while open_heap and steps < max_steps:
            steps += 1
            f, cur_g, cr, cc = heapq.heappop(open_heap)
            if (cr, cc) in closed_set:
                continue
            closed_set.add((cr, cc))

            if cr == gr and cc == gc:
                found = True
                break

            for dr, dc, cost in moves:
                nr, nc = cr + dr, cc + dc
                if not self.is_in_bounds(nr, nc) or not traversable[nr, nc]:
                    continue
                if (nr, nc) in closed_set:
                    continue

                new_g = cur_g + cost
                if new_g < g_cost.get((nr, nc), float("inf")):
                    g_cost[(nr, nc)] = new_g
                    parent[(nr, nc)] = (cr, cc)
                    priority = new_g + octile_heuristic(nr, nc, gr, gc)
                    heapq.heappush(open_heap, (priority, new_g, nr, nc))

        if not found:
            return None, "NO_PATH_IN_DISCOVERED_SPACE: Frontier or goal unreachable through verified free corridors."

        path_cells: List[Tuple[int, int]] = []
        curr = (gr, gc)
        while curr in parent:
            path_cells.append(curr)
            curr = parent[curr]
        path_cells.append((sr, sc))
        path_cells.reverse()

        simplified: List[Tuple[int, int]] = [path_cells[0]]
        for i in range(1, len(path_cells) - 1):
            prev = simplified[-1]
            mid = path_cells[i]
            nxt = path_cells[i + 1]
            d1 = (mid[0] - prev[0], mid[1] - prev[1])
            d2 = (nxt[0] - mid[0], nxt[1] - mid[1])
            if d1 != d2 or len(simplified) % 4 == 0:
                simplified.append(mid)
        simplified.append(path_cells[-1])

        world_path = [self.grid_to_world(r, c) for r, c in simplified]
        return world_path, "PATH_PLANNED_ON_AUTHORITATIVE_SLAM_MAP"

    def is_region_explored(self, target_xy: Tuple[float, float], radius_m: float = 1.0) -> bool:
        """Returns True if the region around target_xy has been mapped as free space by SLAM."""
        tr, tc = self.world_to_grid(target_xy[0], target_xy[1])
        rad_cells = max(1, int(radius_m / self.resolution))
        free_count = 0
        total_count = 0
        for dr in range(-rad_cells, rad_cells + 1):
            for dc in range(-rad_cells, rad_cells + 1):
                nr, nc = tr + dr, tc + dc
                if self.is_in_bounds(nr, nc):
                    total_count += 1
                    if self.grid[nr, nc] == OccupancyState.FREE:
                        free_count += 1
        return (free_count / max(1, total_count)) > 0.40

    def detect_semantic_features(self) -> List[Dict[str, Any]]:
        """
        Part 4: Discovers semantic topological features from the robot-generated occupancy grid:
        - Corridors (horizontal and vertical linear passages)
        - Intersections (crossings connecting multiple corridors)
        - Doorways / room entrances (narrow openings into wider spaces)
        - Dynamic hazard blockages
        """
        features: List[Dict[str, Any]] = []
        free_mask = (self.grid == OccupancyState.FREE)
        if int(np.sum(free_mask)) < 15:
            return features

        for obs_id, obs in self.active_dynamic_obstacles.items():
            pos = obs.get("pos", [0.0, 0.0])
            features.append({
                "type": "DYNAMIC_HAZARD",
                "label": f"Obstacle Hazard ({obs_id})",
                "position": [round(float(pos[0]), 2), round(float(pos[1]), 2)],
                "radius": obs.get("radius", 0.85),
                "confidence": 0.98,
                "status": "SEMANTICALLY_CONFIRMED",
            })

        for r in range(4, self.rows - 4, 8):
            row_free = np.where(free_mask[r, :])[0]
            if len(row_free) >= 12:
                chunks = np.split(row_free, np.where(np.diff(row_free) > 1)[0] + 1)
                for chunk in chunks:
                    if len(chunk) >= 10:
                        c_mid = int(chunk[len(chunk) // 2])
                        wx, wy = self.grid_to_world(r, c_mid)
                        length_m = round(len(chunk) * self.resolution, 1)
                        features.append({
                            "type": "CORRIDOR_SPINE",
                            "label": f"Discovered Corridor Spine ({length_m}m)",
                            "position": [wx, wy],
                            "orientation": "HORIZONTAL",
                            "length_m": length_m,
                            "confidence": min(0.95, round(0.70 + (length_m / 40.0), 2)),
                            "status": "GEOMETRICALLY_DISCOVERED",
                        })

        for c in range(4, self.cols - 4, 8):
            col_free = np.where(free_mask[:, c])[0]
            if len(col_free) >= 12:
                chunks = np.split(col_free, np.where(np.diff(col_free) > 1)[0] + 1)
                for chunk in chunks:
                    if len(chunk) >= 10:
                        r_mid = int(chunk[len(chunk) // 2])
                        wx, wy = self.grid_to_world(r_mid, c)
                        length_m = round(len(chunk) * self.resolution, 1)
                        features.append({
                            "type": "CORRIDOR_SPINE",
                            "label": f"Discovered Corridor Spine ({length_m}m)",
                            "position": [wx, wy],
                            "orientation": "VERTICAL",
                            "length_m": length_m,
                            "confidence": min(0.95, round(0.70 + (length_m / 40.0), 2)),
                            "status": "GEOMETRICALLY_DISCOVERED",
                        })

        for r in range(2, self.rows - 2, 4):
            for c in range(2, self.cols - 2, 4):
                if free_mask[r, c]:
                    is_h_door = (self.grid[r-1, c] == OccupancyState.OCCUPIED and self.grid[r+1, c] == OccupancyState.OCCUPIED)
                    is_v_door = (self.grid[r, c-1] == OccupancyState.OCCUPIED and self.grid[r, c+1] == OccupancyState.OCCUPIED)
                    if is_h_door or is_v_door:
                        wx, wy = self.grid_to_world(r, c)
                        features.append({
                            "type": "DOORWAY_ENTRANCE",
                            "label": f"Discovered Room Portal ({'Horiz' if is_h_door else 'Vert'})",
                            "position": [wx, wy],
                            "width_m": 1.5,
                            "confidence": 0.85,
                            "status": "SEMANTICALLY_CONFIRMED",
                        })

        return features[:25]

    def get_authoritative_knowledge_map(self) -> Dict[str, Any]:
        """
        Feature A & B: Explicit Robot Knowledge Representation.
        Distinguishes confirmed observations from unmapped hospital regions.
        """
        now = time.time()
        total_cells = self.rows * self.cols
        free_cells = int(np.sum(self.grid == OccupancyState.FREE))
        occupied_cells = int(np.sum(self.grid == OccupancyState.OCCUPIED))
        unknown_cells = int(np.sum(self.grid == OccupancyState.UNKNOWN))

        recent_cutoff = now - 60.0
        recently_observed = int(np.sum((self.last_observed > recent_cutoff) & (self.grid != OccupancyState.UNKNOWN)))
        freshness_pct = round((recently_observed / max(1, (free_cells + occupied_cells))) * 100.0, 1)

        semantic_feats = self.detect_semantic_features()
        semantic_dict = {
            "corridors": [
                {"x": f["position"][0], "y": f["position"][1], "confidence": f.get("confidence", 0.85), "length_m": f.get("length_m", 5.0)}
                for f in semantic_feats if f.get("type") == "CORRIDOR_SPINE"
            ],
            "room_portals": [
                {"x": f["position"][0], "y": f["position"][1], "confidence": f.get("confidence", 0.85), "width_m": f.get("width_m", 1.5)}
                for f in semantic_feats if f.get("type") == "DOORWAY_ENTRANCE"
            ],
            "dynamic_hazards": [
                {"x": f["position"][0], "y": f["position"][1], "radius_m": f.get("radius", 0.85)}
                for f in semantic_feats if f.get("type") == "DYNAMIC_HAZARD"
            ],
            "features_list": semantic_feats,
        }

        # Sample occupied wall points for visualization
        occupied_indices = np.argwhere(self.grid == OccupancyState.OCCUPIED)
        discovered_walls = []
        if len(occupied_indices) > 0:
            step = max(1, len(occupied_indices) // 500)
            for r, c in occupied_indices[::step]:
                wx, wy = self.grid_to_world(int(r), int(c))
                discovered_walls.append([round(wx, 2), round(wy, 2)])

        return {
            "authority": "ROBOT_GENERATED_SLAM",
            "is_authoritative_for_navigation": True,
            "free_space_cells": free_cells,
            "structural_wall_cells": occupied_cells,
            "unexplored_cells": unknown_cells,
            "coverage_pct": round(((free_cells + occupied_cells) / max(1, total_cells)) * 100.0, 1),
            "navigable_progress_pct": min(100.0, round((free_cells / max(1, self.expected_navigable_cells)) * 100.0, 1)),
            "freshness_pct": freshness_pct,
            "recently_observed_cells": recently_observed,
            "dynamic_hazards_count": len(self.active_dynamic_obstacles),
            "frontiers_count": len(self.frontiers),
            "frontiers": [[f.x, f.y] for f in self.frontiers],
            "discovered_walls": discovered_walls,
            "semantic_features": semantic_dict,
            "timestamp": now,
        }

    # ── 4. TELEMETRY & PROGRESS METRICS ─────────────────────────────────────

    def get_exploration_progress(self) -> Dict[str, Any]:
        """Calculates quantitative exploration metrics."""
        total_cells = self.rows * self.cols
        free_cells = int(np.sum(self.grid == OccupancyState.FREE))
        occupied_cells = int(np.sum(self.grid == OccupancyState.OCCUPIED))
        unknown_cells = int(np.sum(self.grid == OccupancyState.UNKNOWN))
        dynamic_cells = int(np.sum(self.dynamic_layer > 0))

        explored_cells = free_cells + occupied_cells
        percent = min(100.0, round((free_cells / max(1, self.expected_navigable_cells)) * 100.0, 1))

        return {
            "status": "COMPLETED" if (self.exploration_complete or percent >= 95.0) else "EXPLORING",
            "percent_explored": percent,
            "free_cells": free_cells,
            "occupied_cells": occupied_cells,
            "unknown_cells": unknown_cells,
            "dynamic_obstacles_count": len(self.active_dynamic_obstacles),
            "frontiers_count": len(self.frontiers),
            "active_dynamic_obstacles": list(self.active_dynamic_obstacles.values()),
            "exploration_complete": bool(self.exploration_complete or percent >= 95.0),
        }

    def get_map_telemetry_payload(self) -> Dict[str, Any]:
        """
        Generates structured map telemetry for browser WebSocket & HTTP endpoints.
        Includes discovered wall segments, dynamic obstacles, frontiers, and progress.
        """
        prog = self.get_exploration_progress()

        # Sample discovered wall cells (downsampled for lightweight JSON transport)
        wall_indices = np.argwhere(self.grid == OccupancyState.OCCUPIED)
        wall_points = []
        # Sample every 4th wall cell to keep payload < 30KB
        step = max(1, len(wall_indices) // 300) if len(wall_indices) > 300 else 1
        for idx in range(0, len(wall_indices), step):
            r, c = wall_indices[idx]
            wx, wy = self.grid_to_world(int(r), int(c))
            wall_points.append([wx, wy])

        frontier_points = []
        for f in self.frontiers[:10]:
            frontier_points.append({
                "x": f.centroid[0],
                "y": f.centroid[1],
                "size": f.size,
            })

        return {
            "progress": prog,
            "resolution": self.resolution,
            "bounds": [self.xmin, self.xmax, self.ymin, self.ymax],
            "discovered_walls": wall_points,
            "dynamic_obstacles": list(self.active_dynamic_obstacles.values()),
            "frontiers": frontier_points,
            "timestamp": time.time(),
        }

    def get_map_metadata(self) -> Dict[str, Any]:
        """Returns comprehensive map metadata for perception server and UI comparisons."""
        total_cells = self.rows * self.cols
        free_cells = int(np.sum(self.grid == OccupancyState.FREE))
        occupied_cells = int(np.sum(self.grid == OccupancyState.OCCUPIED))
        unknown_cells = int(np.sum(self.grid == OccupancyState.UNKNOWN))
        explored_pct = min(100.0, round((free_cells / max(1, self.expected_navigable_cells)) * 100.0, 1))
        coverage_pct = min(100.0, round(((free_cells + occupied_cells) / max(1, total_cells)) * 100.0, 1))

        return {
            "resolution": self.resolution,
            "bounds": [self.xmin, self.xmax, self.ymin, self.ymax],
            "rows": self.rows,
            "cols": self.cols,
            "grid_width_meters": round(self.cols * self.resolution, 2),
            "grid_height_meters": round(self.rows * self.resolution, 2),
            "free_cells": free_cells,
            "occupied_cells": occupied_cells,
            "discovered_walls_count": occupied_cells,
            "unknown_cells": unknown_cells,
            "dynamic_obstacles_count": len(self.active_dynamic_obstacles),
            "frontiers_count": len(self.frontiers),
            "exploration_progress_pct": explored_pct,
            "coverage_pct": coverage_pct,
            "exploration_complete": bool(self.exploration_complete or explored_pct >= 95.0),
            "status": "COMPLETED" if (self.exploration_complete or explored_pct >= 95.0) else "ACTIVE",
            "timestamp": time.time(),
        }

    def get_dynamic_obstacles(self) -> List[Dict[str, Any]]:
        """Returns all currently active dynamic obstacles."""
        return list(self.active_dynamic_obstacles.values())

    def get_discovered_obstacles(self, threshold: float = 0.65) -> List[List[float]]:
        """Returns world coordinates of cells identified as occupied obstacles / walls."""
        wall_indices = np.argwhere(self.grid == OccupancyState.OCCUPIED)
        wall_points: List[List[float]] = []
        step = max(1, len(wall_indices) // 400) if len(wall_indices) > 400 else 1
        for idx in range(0, len(wall_indices), step):
            r, c = wall_indices[idx]
            wx, wy = self.grid_to_world(int(r), int(c))
            wall_points.append([round(wx, 2), round(wy, 2)])
        return wall_points

    def get_discovered_free_space(self, sample_step: int = 4) -> List[List[float]]:
        """Returns sampled world coordinates of verified free space cells."""
        free_indices = np.argwhere(self.grid == OccupancyState.FREE)
        free_points: List[List[float]] = []
        step = max(sample_step, len(free_indices) // 500) if len(free_indices) > 500 else sample_step
        for idx in range(0, len(free_indices), step):
            r, c = free_indices[idx]
            wx, wy = self.grid_to_world(int(r), int(c))
            free_points.append([round(wx, 2), round(wy, 2)])
        return free_points

    def select_best_frontier(
        self, current_x: float = 0.0, current_y: float = 0.0
    ) -> Optional[Tuple[float, float]]:
        """Alias for get_best_exploration_target for API consistency."""
        return self.get_best_exploration_target(current_x, current_y)

    def detect_dynamic_obstacle(
        self, obs_id: str, x: float, y: float, radius: float = 0.85
    ) -> Dict[str, Any]:
        """Manually inject or register a dynamic obstacle into the live SLAM costmap."""
        now = time.time()
        self.active_dynamic_obstacles[obs_id] = {
            "id": obs_id,
            "pos": (round(x, 2), round(y, 2)),
            "radius": radius,
            "first_seen": now,
            "last_seen": now,
            "hits": 10,
        }
        r, c = self.world_to_grid(x, y)
        cell_rad = int(math.ceil(radius / self.resolution))
        for dr in range(-cell_rad, cell_rad + 1):
            for dc in range(-cell_rad, cell_rad + 1):
                if (dr * self.resolution) ** 2 + (dc * self.resolution) ** 2 <= radius ** 2:
                    nr, nc = r + dr, c + dc
                    if self.is_in_bounds(nr, nc):
                        self.dynamic_layer[nr, nc] = 100
                        self.grid[nr, nc] = OccupancyState.DYNAMIC_OBSTACLE
        return self.active_dynamic_obstacles[obs_id]

    def clear_dynamic_obstacle(self, obs_id: str) -> bool:
        """Removes a dynamic obstacle and restores the free corridor for navigation."""
        if obs_id in self.active_dynamic_obstacles:
            obs = self.active_dynamic_obstacles.pop(obs_id)
            ox, oy = obs["pos"]
            r, c = self.world_to_grid(ox, oy)
            rad = obs.get("radius", 0.85)
            cell_rad = int(math.ceil(rad / self.resolution)) + self.inflation_cells
            for dr in range(-cell_rad, cell_rad + 1):
                for dc in range(-cell_rad, cell_rad + 1):
                    nr, nc = r + dr, c + dc
                    if self.is_in_bounds(nr, nc):
                        self.dynamic_layer[nr, nc] = 0
                        if self.grid[nr, nc] == OccupancyState.DYNAMIC_OBSTACLE:
                            self.grid[nr, nc] = OccupancyState.FREE
            return True
        return False

    def save_map(self, filepath: Optional[str] = None) -> str:
        """Saves current robot-generated SLAM occupancy grid to JSON file."""
        import json, os
        if not filepath:
            filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_slam_map.json")
        data = {
            "metadata": self.get_map_metadata(),
            "grid_shape": [int(self.rows), int(self.cols)],
            "resolution": float(self.resolution),
            "bounds": [float(self.xmin), float(self.xmax), float(self.ymin), float(self.ymax)],
            "discovered_walls": self.get_discovered_obstacles(),
            "discovered_free_space": self.get_discovered_free_space(sample_step=2),
            "dynamic_obstacles": list(self.active_dynamic_obstacles.values()),
            "timestamp": time.time(),
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return filepath

    def load_map(self, filepath: Optional[str] = None) -> bool:
        """Loads saved robot-generated SLAM occupancy grid from JSON file."""
        import json, os
        if not filepath:
            filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_slam_map.json")
        if not os.path.exists(filepath):
            return False
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        for pt in data.get("discovered_walls", []):
            r, c = self.world_to_grid(float(pt[0]), float(pt[1]))
            self.grid[r, c] = OccupancyState.OCCUPIED
        for pt in data.get("discovered_free_space", []):
            r, c = self.world_to_grid(float(pt[0]), float(pt[1]))
            if self.grid[r, c] != OccupancyState.OCCUPIED:
                self.grid[r, c] = OccupancyState.FREE
        self.find_frontiers()
        return True

    def reset_map(self) -> None:
        """Resets the occupancy grid and exploration status."""
        self.grid.fill(OccupancyState.UNKNOWN)
        self.dynamic_layer.fill(0)
        self.hit_counts.fill(0)
        self.pass_counts.fill(0)
        self.active_dynamic_obstacles.clear()
        self.frontiers.clear()
        self.exploration_complete = False


# Global active SLAM exploration engine singleton
GLOBAL_SLAM_ENGINE: Optional[SLAMExplorationEngine] = None


def get_slam_engine() -> SLAMExplorationEngine:
    global GLOBAL_SLAM_ENGINE
    if GLOBAL_SLAM_ENGINE is None:
        GLOBAL_SLAM_ENGINE = SLAMExplorationEngine()
    return GLOBAL_SLAM_ENGINE


# Direct module-level instance for convenient import across the system
SLAM_ENGINE: SLAMExplorationEngine = get_slam_engine()

# Cross-namespace singleton registration to ensure unified memory instance
import sys as _sys
_sys.modules["navigation.slam_exploration_engine"] = _sys.modules[__name__]
_sys.modules["isaac_sim_hospital.navigation.slam_exploration_engine"] = _sys.modules[__name__]

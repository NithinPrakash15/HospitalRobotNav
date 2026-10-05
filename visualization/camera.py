"""
HospitalRobotNav — Camera (Zoom & Pan)
=========================================
Manages the viewport transformation for the hospital map.

Supports:
    - Smooth zoom (mouse wheel)
    - Pan (middle mouse drag)
    - Cell-to-screen and screen-to-cell coordinate transforms
    - Boundary clamping to prevent scrolling off-map
"""

from __future__ import annotations

from config.settings import DISPLAY
from config.hospital_config import GRID_CONFIG


class Camera:
    """
    2D camera with zoom and pan for the hospital map viewport.

    The camera transforms grid coordinates to screen coordinates:
        screen_x = (col - offset_col) * cell_px
        screen_y = (row - offset_row) * cell_px

    Where cell_px = base_cell_size * zoom_level.
    """

    MIN_ZOOM: float = 0.3
    MAX_ZOOM: float = 4.0
    ZOOM_STEP: float = 0.15

    def __init__(self) -> None:
        self.viewport_x = DISPLAY.LEFT_PANEL_WIDTH    # Left edge of map viewport (pixels)
        self.viewport_y = 0

        self._base_cell_px = GRID_CONFIG.CELL_SIZE_PIXELS
        self._zoom         = 1.0
        self._offset_col   = 0.0    # Grid column of viewport top-left
        self._offset_row   = 0.0    # Grid row of viewport top-left

        # Pan state
        self._panning       = False
        self._pan_start_x   = 0
        self._pan_start_y   = 0
        self._pan_start_col = 0.0
        self._pan_start_row = 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # Properties
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def cell_px(self) -> int:
        """Current pixel size of one grid cell."""
        return max(1, int(self._base_cell_px * self._zoom))

    @property
    def zoom(self) -> float:
        """Current zoom level."""
        return self._zoom

    # ─────────────────────────────────────────────────────────────────────────
    # Zoom
    # ─────────────────────────────────────────────────────────────────────────

    def zoom_in(self, pivot_x: int = 0, pivot_y: int = 0) -> None:
        """Zoom in, centered on (pivot_x, pivot_y) in screen pixels."""
        old_zoom = self._zoom
        self._zoom = min(self.MAX_ZOOM, self._zoom + self.ZOOM_STEP)
        self._adjust_offset_for_zoom(old_zoom, self._zoom, pivot_x, pivot_y)

    def zoom_out(self, pivot_x: int = 0, pivot_y: int = 0) -> None:
        """Zoom out, centered on (pivot_x, pivot_y)."""
        old_zoom = self._zoom
        self._zoom = max(self.MIN_ZOOM, self._zoom - self.ZOOM_STEP)
        self._adjust_offset_for_zoom(old_zoom, self._zoom, pivot_x, pivot_y)

    def _adjust_offset_for_zoom(
        self,
        old_zoom: float,
        new_zoom: float,
        pivot_x: int,
        pivot_y: int,
    ) -> None:
        """Adjust offsets so pivot point stays fixed during zoom."""
        old_cell = max(1, int(self._base_cell_px * old_zoom))
        new_cell = max(1, int(self._base_cell_px * new_zoom))

        # Grid position at pivot before zoom
        pivot_col = self._offset_col + (pivot_x - self.viewport_x) / old_cell
        pivot_row = self._offset_row + (pivot_y - self.viewport_y) / old_cell

        # Keep same grid position at pivot after zoom
        self._offset_col = pivot_col - (pivot_x - self.viewport_x) / new_cell
        self._offset_row = pivot_row - (pivot_y - self.viewport_y) / new_cell
        self._clamp_offsets()

    def reset_zoom(self) -> None:
        """Reset zoom to 1× and center the map."""
        self._zoom       = 1.0
        self._offset_col = 0.0
        self._offset_row = 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # Pan
    # ─────────────────────────────────────────────────────────────────────────

    def start_pan(self, mouse_x: int, mouse_y: int) -> None:
        """Begin panning (mouse button pressed)."""
        self._panning       = True
        self._pan_start_x   = mouse_x
        self._pan_start_y   = mouse_y
        self._pan_start_col = self._offset_col
        self._pan_start_row = self._offset_row

    def update_pan(self, mouse_x: int, mouse_y: int) -> None:
        """Update pan offset (mouse dragging)."""
        if not self._panning:
            return
        dx = mouse_x - self._pan_start_x
        dy = mouse_y - self._pan_start_y
        self._offset_col = self._pan_start_col - dx / self.cell_px
        self._offset_row = self._pan_start_row - dy / self.cell_px
        self._clamp_offsets()

    def stop_pan(self) -> None:
        """End panning."""
        self._panning = False

    # ─────────────────────────────────────────────────────────────────────────
    # Coordinate Transforms
    # ─────────────────────────────────────────────────────────────────────────

    def grid_to_screen(self, row: float, col: float):
        """
        Convert grid (row, col) to screen (sx, sy) pixel coordinates.

        Args:
            row: Grid row (float for sub-cell precision).
            col: Grid column.

        Returns:
            (sx, sy) integer screen coordinates.
        """
        cell = self.cell_px
        sx = int((col - self._offset_col) * cell) + self.viewport_x
        sy = int((row - self._offset_row) * cell) + self.viewport_y
        return sx, sy

    def screen_to_grid(self, sx: int, sy: int):
        """
        Convert screen (sx, sy) to grid (row, col) float coordinates.

        Args:
            sx: Screen X pixel.
            sy: Screen Y pixel.

        Returns:
            (row, col) integer grid cell.
        """
        cell = self.cell_px
        col = int((sx - self.viewport_x) / cell + self._offset_col)
        row = int((sy - self.viewport_y) / cell + self._offset_row)
        return row, col

    def is_visible(self, row: int, col: int, margin: int = 2) -> bool:
        """
        Return True if grid cell (row, col) is within the visible viewport.

        Args:
            row:    Grid row.
            col:    Grid column.
            margin: Extra cells beyond viewport edge to include.

        Returns:
            True if visible.
        """
        vw = DISPLAY.MAP_VIEWPORT_WIDTH
        vh = DISPLAY.MAP_VIEWPORT_HEIGHT
        cell = self.cell_px

        sx, sy = self.grid_to_screen(row, col)
        return (
            -cell * margin <= sx - self.viewport_x <= vw + cell * margin and
            -cell * margin <= sy - self.viewport_y <= vh + cell * margin
        )

    def get_visible_range(self):
        """
        Return (min_row, max_row, min_col, max_col) of visible grid cells.

        Returns:
            Tuple of 4 ints.
        """
        cell = max(1, self.cell_px)
        vw = DISPLAY.MAP_VIEWPORT_WIDTH
        vh = DISPLAY.MAP_VIEWPORT_HEIGHT

        rows = GRID_CONFIG.GRID_ROWS
        cols = GRID_CONFIG.GRID_COLS

        min_row = max(0, int(self._offset_row) - 1)
        max_row = min(rows - 1, int(self._offset_row + vh / cell) + 2)
        min_col = max(0, int(self._offset_col) - 1)
        max_col = min(cols - 1, int(self._offset_col + vw / cell) + 2)

        return min_row, max_row, min_col, max_col

    def center_on(self, row: float, col: float) -> None:
        """
        Center the viewport on a specific grid position.

        Args:
            row: Grid row to center on.
            col: Grid column to center on.
        """
        vw = DISPLAY.MAP_VIEWPORT_WIDTH
        vh = DISPLAY.MAP_VIEWPORT_HEIGHT
        cell = self.cell_px
        self._offset_col = col - vw / (2 * cell)
        self._offset_row = row - vh / (2 * cell)
        self._clamp_offsets()

    # ─────────────────────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────────────────────

    def _clamp_offsets(self) -> None:
        """Clamp offsets to prevent scrolling beyond map boundaries."""
        rows = GRID_CONFIG.GRID_ROWS
        cols = GRID_CONFIG.GRID_COLS
        vw = DISPLAY.MAP_VIEWPORT_WIDTH
        vh = DISPLAY.MAP_VIEWPORT_HEIGHT
        cell = max(1, self.cell_px)

        max_col = max(0.0, cols - vw / cell)
        max_row = max(0.0, rows - vh / cell)

        self._offset_col = max(0.0, min(max_col, self._offset_col))
        self._offset_row = max(0.0, min(max_row, self._offset_row))

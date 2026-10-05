"""
Unit tests for utilities/geometry.py
"""

import math
import unittest
from utilities.geometry import (
    euclidean_distance, manhattan_distance, bresenham_cells,
    line_of_sight, normalize_angle, angle_difference
)

class TestGeometry(unittest.TestCase):

    def test_euclidean_distance(self):
        self.assertAlmostEqual(euclidean_distance((0, 0), (3, 4)), 5.0)
        self.assertAlmostEqual(euclidean_distance((1, 1), (1, 1)), 0.0)

    def test_manhattan_distance(self):
        self.assertEqual(manhattan_distance((0, 0), (3, 4)), 7)
        self.assertEqual(manhattan_distance((10, 5), (5, 10)), 10)

    def test_normalize_angle(self):
        self.assertAlmostEqual(normalize_angle(math.pi * 3), math.pi)
        self.assertAlmostEqual(normalize_angle(-math.pi * 3), math.pi)
        self.assertAlmostEqual(normalize_angle(0.5), 0.5)

    def test_angle_difference(self):
        self.assertAlmostEqual(angle_difference(math.pi / 2, 0), math.pi / 2)
        self.assertAlmostEqual(angle_difference(0, math.pi / 2), -math.pi / 2)

    def test_bresenham_cells(self):
        cells = bresenham_cells((0, 0), (0, 3))
        self.assertEqual(cells, [(0, 0), (0, 1), (0, 2), (0, 3)])

    def test_line_of_sight(self):
        blocked_fn = lambda r, c: (r == 0 and c == 2)
        self.assertFalse(line_of_sight((0, 0), (0, 4), blocked_fn))
        self.assertTrue(line_of_sight((1, 0), (1, 4), blocked_fn))

if __name__ == "__main__":
    unittest.main()

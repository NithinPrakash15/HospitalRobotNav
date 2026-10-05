"""
Unit tests for environment/occupancy_grid.py and maps/hospital/hospital_map.py
"""

import unittest
from maps.hospital.hospital_map import HospitalMap
from environment.occupancy_grid import OccupancyGrid

class TestOccupancyGrid(unittest.TestCase):

    def setUp(self):
        self.map = HospitalMap().build()
        self.grid = OccupancyGrid(self.map)

    def test_map_building(self):
        self.assertEqual(self.map.binary_grid.shape, (120, 120))
        self.assertGreater(len(self.map.rooms), 15)

    def test_grid_free_query(self):
        # Corridors should have free cells
        free_cell = self.grid.find_nearest_free(50, 50)
        self.assertIsNotNone(free_cell)
        self.assertTrue(self.grid.is_free(*free_cell))

    def test_dynamic_obstacle_injection(self):
        r, c = self.grid.find_nearest_free(20, 20)
        self.grid.add_dynamic_obstacle(r, c)
        self.assertFalse(self.grid.is_free(r, c))

        self.grid.remove_dynamic_obstacle(r, c)
        self.assertTrue(self.grid.is_free(r, c))

    def test_get_neighbors(self):
        r, c = self.grid.find_nearest_free(30, 30)
        neighbors_8 = self.grid.get_neighbors_8(r, c)
        self.assertGreater(len(neighbors_8), 0)

if __name__ == "__main__":
    unittest.main()

"""
Unit tests for algorithms layer (A*, Dijkstra, Theta*, Hybrid A*, D* Lite)
"""

import unittest
from maps.hospital.hospital_map import HospitalMap
from environment.occupancy_grid import OccupancyGrid
from algorithms.astar import AStarPlanner
from algorithms.dijkstra import DijkstraPlanner
from algorithms.theta_star import ThetaStarPlanner
from algorithms.hybrid_astar import HybridAStarPlanner
from algorithms.dstar_lite import DStarLitePlanner

class TestPlanners(unittest.TestCase):

    def setUp(self):
        self.map = HospitalMap().build()
        self.grid = OccupancyGrid(self.map)
        self.start = self.grid.find_nearest_free(80, 11)
        self.goal = self.grid.find_nearest_free(18, 60)

    def test_astar_planner(self):
        planner = AStarPlanner(self.grid)
        res = planner.plan(self.start, self.goal)
        self.assertTrue(res.success)
        self.assertGreater(len(res.path), 0)

    def test_dijkstra_planner(self):
        planner = DijkstraPlanner(self.grid)
        res = planner.plan(self.start, self.goal)
        self.assertTrue(res.success)
        self.assertGreater(len(res.path), 0)

    def test_theta_star_planner(self):
        planner = ThetaStarPlanner(self.grid)
        res = planner.plan(self.start, self.goal)
        self.assertTrue(res.success)
        self.assertGreater(len(res.path), 0)

    def test_hybrid_astar_planner(self):
        planner = HybridAStarPlanner(self.grid, max_iterations=50000)
        goal = self.grid.find_nearest_free(70, 20)
        res = planner.plan(self.start, goal)
        self.assertTrue(res.success)
        self.assertGreater(len(res.path), 0)

    def test_dstar_lite_planner(self):
        planner = DStarLitePlanner(self.grid)
        res = planner.plan(self.start, self.goal)
        self.assertTrue(res.success)
        self.assertGreater(len(res.path), 0)

if __name__ == "__main__":
    unittest.main()


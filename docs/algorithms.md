# Algorithm Reference — Path Planning Suite

This document provides a complete technical reference for all five path planning algorithms implemented in this system. Each algorithm is documented to IEEE Robotics and Automation Letters (RA-L) / ICRA standards.

---

## 1. A* Search Algorithm

**File:** [`algorithms/astar.py`](../algorithms/astar.py)

### Theoretical Basis
A* is a best-first search algorithm that finds the optimal path by combining the actual cost from start *g(n)* with an admissible heuristic estimate to the goal *h(n)*:

$$f(n) = g(n) + h(n)$$

**Optimality Condition:** A* is complete and optimal if *h(n)* is admissible (never overestimates actual cost).

### Implementation Details
- **Data Structure:** Binary min-heap with lazy deletion O(log n) push/pop
- **Connectivity:** 8-directional (diagonal cost = √2 ≈ 1.414)
- **Heuristics:** Configurable (Manhattan, Euclidean, Diagonal/Octile, Chebyshev)
- **Tie-breaking:** Monotone counter to resolve equal-f nodes deterministically

### Complexity
| Metric         | Value                |
| :------------- | :------------------- |
| Time Worst     | O(b^d)               |
| Space Worst    | O(b^d)               |
| Optimal?       | Yes (admissible h)   |
| Complete?      | Yes                  |

### Performance (100×100 hospital grid, dock→ICU)
| Heuristic   | Plan Time | Nodes Expanded | Path Length |
| :---------- | :-------- | :------------- | :---------- |
| Manhattan   | ~820 ms   | 2,890          | 102 cells   |
| Diagonal    | ~610 ms   | 2,240          | 100 cells   |
| Euclidean   | ~590 ms   | 2,180          | 100 cells   |

---

## 2. Dijkstra's Algorithm

**File:** [`algorithms/dijkstra.py`](../algorithms/dijkstra.py)

### Theoretical Basis
Dijkstra's algorithm computes the shortest path tree from a source node using a greedy priority-queue based expansion. It is equivalent to A* with h(n) = 0.

$$f(n) = g(n)$$

### Implementation Details
- **Use case:** Guaranteed optimal path on weighted graphs; used as baseline comparison
- **Flood-fill mode:** Computes full distance map from a source — used for heatmap visualization
- **Connectivity:** 8-directional with costmap-weighted edge costs

### Complexity
| Metric        | Value            |
| :------------ | :--------------- |
| Time          | O((V+E) log V)   |
| Space         | O(V)             |
| Optimal?      | Yes              |
| Complete?     | Yes              |

---

## 3. Theta* (Any-Angle Path Planner)

**File:** [`algorithms/theta_star.py`](../algorithms/theta_star.py)

### Theoretical Basis
Theta* (Theta-star) is an any-angle path planning algorithm that produces shorter, more natural-looking paths than A* by allowing edges between non-adjacent nodes when line-of-sight exists.

**Key Innovation:** At each expansion, instead of connecting nodes through their parent on the grid, Theta* checks if the grandparent has line-of-sight to the current node. If so, it bypasses the parent:

```
if line_of_sight(grandparent, s):
    if g(grandparent) + dist(grandparent, s) < g(s):
        parent(s) = grandparent
        g(s) = g(grandparent) + dist(grandparent, s)
```

### Lazy Theta* Optimization
This implementation uses **Lazy Theta*** which defers line-of-sight checks to expansion time (rather than generation time), reducing expensive raycast calls by ~40%.

### Complexity
| Metric         | Value              |
| :------------- | :----------------- |
| Time Avg       | O(b^d) ≈ A*        |
| Path Quality   | Near-optimal        |
| LoS Check      | Bresenham O(n)     |
| Optimal?       | Approximately Yes  |

---

## 4. Hybrid A* (Kinematically Feasible Planner)

**File:** [`algorithms/hybrid_astar.py`](../algorithms/hybrid_astar.py)

### Theoretical Basis
Hybrid A* extends A* to a continuous 3D state space (x, y, θ) by simulating a non-holonomic differential-drive robot using a **bicycle kinematics model**:

$$x_{t+1} = x_t + v \cos(\theta_t) \cdot dt$$
$$y_{t+1} = y_t + v \sin(\theta_t) \cdot dt$$
$$\theta_{t+1} = \theta_t + \frac{v \tan(\delta)}{L} \cdot dt$$

Where δ is steering angle and L is wheelbase.

### State Discretization
The continuous state (x, y, θ) is discretized for duplicate detection:
- Position: 1.0 cell resolution
- Heading: π/8 (22.5°) resolution = 16 heading bins

### Application
Hybrid A* is critical for real hospital deployment where the robot must plan physically realizable trajectories (no spin-in-place, bounded curvature).

### Complexity
| Metric       | Value                 |
| :----------- | :-------------------- |
| State Space  | O(W × H × θ_bins)    |
| Completeness | Yes (for non-narrow)  |
| Path Type    | Kinematically feasible|

---

## 5. D* Lite (Dynamic Replanning)

**File:** [`algorithms/dstar_lite.py`](../algorithms/dstar_lite.py)

### Theoretical Basis
D* Lite (Dynamic A* Lite) is an incremental search algorithm designed for replanning in dynamic environments. When obstacles move, D* Lite efficiently repairs the existing path rather than replanning from scratch.

**Key operations:**
- `initialize()`: Sets up backward search from goal
- `compute_shortest_path()`: Computes or repairs path
- `update_vertex(u)`: Updates a vertex when edge cost changes

**Two-key priority:**
Each vertex u maintains two keys:
$$k(u) = [k_1(u), k_2(u)]$$
$$k_1(u) = \min(g(u), rhs(u)) + h(u, s_{start})$$
$$k_2(u) = \min(g(u), rhs(u))$$

**rhs-value (lookahead):**
$$rhs(u) = \begin{cases} 0 & \text{if } u = s_{goal} \\ \min_{s' \in Succ(u)} [c(u, s') + g(s')] & \text{otherwise} \end{cases}$$

### Replanning Efficiency
When k obstacles change, D* Lite repairs the path in O(k log V) time vs O(V log V) for full replanning — critical for real-time hospital navigation.

### Complexity
| Metric          | Value              |
| :-------------- | :----------------- |
| Initial Plan    | O(V log V)         |
| Replan (k changes)| O(k log V)       |
| Optimal?        | Yes                |
| Complete?       | Yes                |

---

## Comparative Performance Summary

Results averaged over 50 planning trials, start=(80,11) → goal=(18,60), 100×100 hospital grid:

| Algorithm   | Avg Time (ms) | Nodes Expanded | Path Length (cells) | Path Quality |
| :---------- | :------------ | :------------- | :------------------ | :----------- |
| A* Diagonal | 610           | 2,240          | 100                 | Optimal grid |
| Dijkstra    | 1,176         | 4,731          | 100                 | Optimal      |
| Theta*      | 1,230         | 1,996          | 95 (any-angle)      | Near-optimal |
| Hybrid A*   | 5             | 13             | Short-range only    | Kinematic    |
| D* Lite     | 8,038         | 2,089          | 100                 | Optimal      |

> **Note:** D* Lite's initial plan is slower but subsequent replans after obstacle changes are O(k log V) ≈ 5-50ms.

---

## Heuristic Functions

**File:** [`algorithms/heuristics.py`](../algorithms/heuristics.py)

| Heuristic | Formula | Admissible | 8-Dir |
| :-------- | :------ | :--------- | :---- |
| Manhattan | `|Δr| + |Δc|` | Yes (4-dir) | No |
| Euclidean | `√(Δr² + Δc²)` | Yes | Yes |
| Diagonal  | `max(|Δr|,|Δc|) + (√2-1)·min(|Δr|,|Δc|)` | Yes | Yes |
| Chebyshev | `max(|Δr|, |Δc|)` | Yes | Yes |
| Weighted  | `w × h(n)` (w>1) | No (inadmissible) | Any |

> **Recommended for hospital environment:** Diagonal (Octile) heuristic — perfectly admissible for 8-connected grids and provides the tightest bound.

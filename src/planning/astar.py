"""Hand-crafted A* Search Algorithm and Dijkstra baseline.

This implementation uses python's `heapq` for priority queue management.
Heuristic: Straight-line physical distance divided by theoretical max speed.
Admissibility:
  h(n) = (euclidean_distance_km(n, goal) / max_speed_kmh) * 60.0
  Since straight-line distance <= road network distance, and road speeds <= max_speed_kmh
  with delay_factor >= 1.0, h(n) <= optimal cost to goal.
  Therefore, h(n) is strictly admissible and consistent (monotone).
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Set
from src.city import CityNetwork


@dataclass
class SearchResult:
    """Outcome of graph pathfinding search."""
    algorithm: str
    path: List[str]
    cost_minutes: float
    nodes_expanded: int
    explored_nodes: List[str]
    heuristic_at_start: float = 0.0

    @property
    def hop_count(self) -> int:
        return max(0, len(self.path) - 1)


def heuristic_travel_time(network: CityNetwork, current_node: str, goal_node: str) -> float:
    """Compute admissible heuristic: optimistic minimum travel time in minutes.

    h(n) = (euclidean_dist / max_speed) * 60.
    """
    if current_node == goal_node:
        return 0.0
    dist_km = network.euclidean_distance_km(current_node, goal_node)
    # Optimistic speed without traffic delay
    max_speed = max(1.0, network.max_speed_kmh)
    return (dist_km / max_speed) * 60.0


def astar_search(
    network: CityNetwork,
    start: str,
    goal: str,
) -> SearchResult:
    """Find the fastest route from start to goal using hand-written A* with heapq.

    Args:
        network: CityNetwork providing topology, coordinates, and traffic edge costs.
        start: Origin node ID.
        goal: Destination node ID.

    Returns:
        SearchResult containing optimal path, cost in minutes, and node expansion statistics.
    """
    if start not in network.nodes or goal not in network.nodes:
        raise ValueError(f"Unknown node ID: start='{start}', goal='{goal}'")

    if start == goal:
        return SearchResult(
            algorithm="A*",
            path=[start],
            cost_minutes=0.0,
            nodes_expanded=0,
            explored_nodes=[start],
            heuristic_at_start=0.0,
        )

    # Priority queue holds tuples: (f_score, counter, current_node)
    # Counter breaks ties deterministically
    counter = 0
    h_start = heuristic_travel_time(network, start, goal)
    open_heap: List[Tuple[float, int, str]] = []
    heapq.heappush(open_heap, (h_start, counter, start))

    # g_score[node] = cheapest cost from start to node currently found
    g_score: Dict[str, float] = {start: 0.0}
    came_from: Dict[str, str] = {}
    closed_set: Set[str] = set()
    explored_nodes_order: List[str] = []
    nodes_expanded = 0

    while open_heap:
        current_f, _, current = heapq.heappop(open_heap)

        if current in closed_set:
            continue

        closed_set.add(current)
        explored_nodes_order.append(current)
        nodes_expanded += 1

        if current == goal:
            # Reconstruct path
            path = [goal]
            curr = goal
            while curr in came_from:
                curr = came_from[curr]
                path.append(curr)
            path.reverse()
            return SearchResult(
                algorithm="A*",
                path=path,
                cost_minutes=g_score[goal],
                nodes_expanded=nodes_expanded,
                explored_nodes=explored_nodes_order,
                heuristic_at_start=h_start,
            )

        for neighbor in network.graph.neighbors(current):
            edge_time = network.get_edge_travel_time(current, neighbor)
            tentative_g = g_score[current] + edge_time

            if tentative_g < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                h_val = heuristic_travel_time(network, neighbor, goal)
                f_val = tentative_g + h_val
                counter += 1
                heapq.heappush(open_heap, (f_val, counter, neighbor))

    # Path not found
    return SearchResult(
        algorithm="A*",
        path=[],
        cost_minutes=float("inf"),
        nodes_expanded=nodes_expanded,
        explored_nodes=explored_nodes_order,
        heuristic_at_start=h_start,
    )


def dijkstra_search(
    network: CityNetwork,
    start: str,
    goal: str,
) -> SearchResult:
    """Baseline Dijkstra search (A* with h(n) = 0) for verification and comparison."""
    if start not in network.nodes or goal not in network.nodes:
        raise ValueError(f"Unknown node ID: start='{start}', goal='{goal}'")

    if start == goal:
        return SearchResult(
            algorithm="Dijkstra",
            path=[start],
            cost_minutes=0.0,
            nodes_expanded=0,
            explored_nodes=[start],
        )

    counter = 0
    open_heap: List[Tuple[float, int, str]] = []
    heapq.heappush(open_heap, (0.0, counter, start))

    g_score: Dict[str, float] = {start: 0.0}
    came_from: Dict[str, str] = {}
    closed_set: Set[str] = set()
    explored_nodes_order: List[str] = []
    nodes_expanded = 0

    while open_heap:
        current_g, _, current = heapq.heappop(open_heap)

        if current in closed_set:
            continue

        closed_set.add(current)
        explored_nodes_order.append(current)
        nodes_expanded += 1

        if current == goal:
            path = [goal]
            curr = goal
            while curr in came_from:
                curr = came_from[curr]
                path.append(curr)
            path.reverse()
            return SearchResult(
                algorithm="Dijkstra",
                path=path,
                cost_minutes=g_score[goal],
                nodes_expanded=nodes_expanded,
                explored_nodes=explored_nodes_order,
            )

        for neighbor in network.graph.neighbors(current):
            edge_time = network.get_edge_travel_time(current, neighbor)
            tentative_g = g_score[current] + edge_time

            if tentative_g < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                counter += 1
                heapq.heappush(open_heap, (tentative_g, counter, neighbor))

    return SearchResult(
        algorithm="Dijkstra",
        path=[],
        cost_minutes=float("inf"),
        nodes_expanded=nodes_expanded,
        explored_nodes=explored_nodes_order,
    )

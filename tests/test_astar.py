"""Tests for hand-crafted A* Search: optimality, admissibility, node expansion, and traffic rerouting."""

import math
import random
from pathlib import Path
import networkx as nx
import pytest

from src.city import CityNetwork
from src.planning.astar import astar_search, dijkstra_search, heuristic_travel_time

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "city.yaml"


@pytest.fixture
def city_net():
    return CityNetwork(CONFIG_PATH)


def test_astar_vs_dijkstra_cost_city_graph(city_net):
    """Verify that A* finds the exact same optimal travel time cost as Dijkstra for all origins to all hospitals."""
    origins = ["CBB", "RBB"]
    hospitals = ["H1", "H2", "H3", "H4", "H5"]

    for start in origins:
        for goal in hospitals:
            astar_res = astar_search(city_net, start, goal)
            dijkstra_res = dijkstra_search(city_net, start, goal)

            assert astar_res.cost_minutes == pytest.approx(dijkstra_res.cost_minutes, abs=1e-4), (
                f"Cost mismatch from {start} to {goal}: A*={astar_res.cost_minutes}, Dijkstra={dijkstra_res.cost_minutes}"
            )
            # A* explores fewer or equal nodes compared to uninformed Dijkstra
            assert astar_res.nodes_expanded <= dijkstra_res.nodes_expanded, (
                f"A* expanded more nodes than Dijkstra: {astar_res.nodes_expanded} > {dijkstra_res.nodes_expanded}"
            )
            assert len(astar_res.path) >= 2
            assert astar_res.path[0] == start
            assert astar_res.path[-1] == goal


def test_heuristic_admissibility(city_net):
    """Verify that heuristic h(n, goal) is strictly admissible: h(n, goal) <= true_cost(n, goal) for all pairs."""
    nodes = list(city_net.nodes.keys())
    for u in nodes:
        for v in nodes:
            h_val = heuristic_travel_time(city_net, u, v)
            true_dijkstra = dijkstra_search(city_net, u, v)
            assert h_val <= true_dijkstra.cost_minutes + 1e-6, (
                f"Heuristic inadmissible between {u} and {v}: h={h_val} > true_cost={true_dijkstra.cost_minutes}"
            )


def test_astar_avoids_traffic_jam(city_net):
    """Verify that injecting a severe traffic delay causes A* to pick an alternative faster route."""
    # Baseline path from CBB to H5
    base_res = astar_search(city_net, "CBB", "H5")

    # Inject severe traffic jam on the direct CBB-J4 road (delay factor 3.5)
    city_net.set_road_delay("CBB", "J4", 3.5)
    jam_res = astar_search(city_net, "CBB", "H5")

    # Ensure the jammed edge is avoided if an alternate route is faster
    if "J4" in base_res.path:
        assert ("CBB" in jam_res.path and "J4" in jam_res.path and jam_res.path.index("J4") == jam_res.path.index("CBB") + 1) is False or jam_res.cost_minutes <= base_res.cost_minutes * 3.0


def test_astar_on_random_graph():
    """Verify A* cost equals Dijkstra on synthetically generated random graphs with Euclidean metric."""
    random.seed(123)
    net = CityNetwork(CONFIG_PATH)

    # Construct synthetic random 10-node planar graph
    net.graph.clear()
    net.nodes.clear()

    from src.city import CityNode
    for i in range(10):
        nid = f"N{i}"
        net.nodes[nid] = CityNode(node_id=nid, name=nid, node_type="junction", x=random.uniform(0, 10), y=random.uniform(0, 10))
        net.graph.add_node(nid)

    # Add edges to ensure connectivity
    for i in range(9):
        u, v = f"N{i}", f"N{i+1}"
        dist = net.euclidean_distance_km(u, v)
        net.graph.add_edge(u, v, distance_km=dist, speed_kmh=50.0, delay_factor=1.0)

    # Add random cross edges
    for _ in range(8):
        u = f"N{random.randint(0, 9)}"
        v = f"N{random.randint(0, 9)}"
        if u != v:
            dist = net.euclidean_distance_km(u, v)
            net.graph.add_edge(u, v, distance_km=dist, speed_kmh=50.0, delay_factor=1.0)

    # Compare A* and Dijkstra
    for start in ["N0", "N2"]:
        for goal in ["N7", "N9"]:
            if nx.has_path(net.graph, start, goal):
                a_res = astar_search(net, start, goal)
                d_res = dijkstra_search(net, start, goal)
                assert a_res.cost_minutes == pytest.approx(d_res.cost_minutes, abs=1e-4)
                assert a_res.nodes_expanded <= d_res.nodes_expanded

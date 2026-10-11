"""City map and network topology loaded from configuration."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import networkx as nx
import yaml


@dataclass
class CityNode:
    node_id: str
    name: str
    node_type: str  # 'hospital', 'central_bank', 'reserve_bank', 'junction'
    x: float
    y: float
    bed_capacity: Optional[int] = None
    target_stock: Dict[str, int] = field(default_factory=dict)
    initial_stock: Dict[str, int] = field(default_factory=dict)
    initial_inventory: Dict[str, int] = field(default_factory=dict)


@dataclass
class RoadEdge:
    u: str
    v: str
    name: str
    distance_km: float
    speed_kmh: float
    delay_factor: float = 1.0

    @property
    def travel_time_minutes(self) -> float:
        """Calculate effective travel time in minutes incorporating traffic delay."""
        effective_speed = max(5.0, self.speed_kmh / max(0.1, self.delay_factor))
        return (self.distance_km / effective_speed) * 60.0


class CityNetwork:
    """Manages the graph topology and spatial properties of Metropolis AI Health Network."""

    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path)
        self.nodes: Dict[str, CityNode] = {}
        self.graph: nx.Graph = nx.Graph()  # NetworkX used strictly for graph storage
        self.coordinate_scale_km: float = 2.0
        self.default_speed_kmh: float = 45.0
        self.max_speed_kmh: float = 70.0
        self.urgency_weights: Dict[str, float] = {}
        self.rarity_scores: Dict[str, float] = {}
        self.safety_rules: Dict[str, float] = {}
        self.raw_config: Dict[str, Any] = {}
        self.load_from_config(self.config_path)

    def load_from_config(self, config_path: Path) -> None:
        """Load nodes, roads, inventory, and parameters from YAML."""
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self.raw_config = data
        city_info = data.get("city", {})
        self.coordinate_scale_km = float(city_info.get("coordinate_scale_km", 2.0))
        self.default_speed_kmh = float(city_info.get("default_speed_kmh", 45.0))
        self.max_speed_kmh = float(city_info.get("max_speed_kmh", 70.0))
        self.urgency_weights = data.get("urgency_weights", {})
        self.rarity_scores = data.get("rarity_scores", {})
        self.safety_rules = data.get("safety_rules", {})

        # Parse nodes
        self.nodes.clear()
        self.graph.clear()

        for node_id, n_data in data.get("nodes", {}).items():
            node = CityNode(
                node_id=node_id,
                name=n_data.get("name", node_id),
                node_type=n_data.get("type", "junction"),
                x=float(n_data.get("x", 0.0)),
                y=float(n_data.get("y", 0.0)),
                bed_capacity=n_data.get("bed_capacity"),
                target_stock=n_data.get("target_stock", {}),
                initial_stock=n_data.get("initial_stock", {}),
                initial_inventory=n_data.get("initial_inventory", {}),
            )
            self.nodes[node_id] = node
            self.graph.add_node(
                node_id,
                name=node.name,
                node_type=node.node_type,
                x=node.x,
                y=node.y,
            )

        # Parse roads
        for road in data.get("roads", []):
            u = road["u"]
            v = road["v"]
            dist = float(road.get("distance_km", 5.0))
            speed = float(road.get("speed_kmh", self.default_speed_kmh))
            delay = float(road.get("delay_factor", 1.0))
            name = road.get("name", f"{u}-{v}")

            self.graph.add_edge(
                u,
                v,
                name=name,
                distance_km=dist,
                speed_kmh=speed,
                delay_factor=delay,
            )

    def get_node(self, node_id: str) -> Optional[CityNode]:
        return self.nodes.get(node_id)

    def get_coordinates(self, node_id: str) -> Tuple[float, float]:
        node = self.nodes[node_id]
        return (node.x, node.y)

    def euclidean_distance_km(self, u: str, v: str) -> float:
        """Compute straight-line physical distance in km between two nodes."""
        node_u = self.nodes[u]
        node_v = self.nodes[v]
        dx = (node_u.x - node_v.x) * self.coordinate_scale_km
        dy = (node_u.y - node_v.y) * self.coordinate_scale_km
        return math.hypot(dx, dy)

    def get_edge_travel_time(self, u: str, v: str) -> float:
        """Return travel time in minutes along edge (u, v) with current traffic delay."""
        if not self.graph.has_edge(u, v):
            raise KeyError(f"No road between {u} and {v}")
        data = self.graph[u][v]
        effective_speed = max(5.0, data["speed_kmh"] / max(0.1, data["delay_factor"]))
        return (data["distance_km"] / effective_speed) * 60.0

    def set_road_delay(self, u: str, v: str, delay_factor: float) -> None:
        """Update traffic delay factor on a specific bidirectional road."""
        if self.graph.has_edge(u, v):
            self.graph[u][v]["delay_factor"] = max(1.0, float(delay_factor))

    def set_all_traffic_delays(self, delay_multiplier: float) -> None:
        """Scale all traffic delays across the city (e.g. for rush hour)."""
        for u, v in self.graph.edges():
            self.graph[u][v]["delay_factor"] = max(1.0, float(delay_multiplier))

    def get_hospitals(self) -> List[CityNode]:
        return [n for n in self.nodes.values() if n.node_type == "hospital"]

    def get_banks(self) -> List[CityNode]:
        return [n for n in self.nodes.values() if "bank" in n.node_type]

    def get_central_bank(self) -> Optional[CityNode]:
        for n in self.nodes.values():
            if n.node_type == "central_bank":
                return n
        return None

    def get_reserve_bank(self) -> Optional[CityNode]:
        for n in self.nodes.values():
            if n.node_type == "reserve_bank":
                return n
        return None

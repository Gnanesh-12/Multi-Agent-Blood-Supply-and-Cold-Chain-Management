"""Delivery vehicle agent managing routing, physical motion, thermal sensors, and dynamic re-planning."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from src.agents.base import BaseAgent
from src.blood import BloodUnit, BloodUnitStatus
from src.messaging import Message, MessageBus, Performative
from src.planning.astar import astar_search

if TYPE_CHECKING:
    from src.city import CityNetwork


class DeliveryAgent(BaseAgent):
    """Autonomous cold-chain transport vehicle executing routes with active sensory monitoring."""

    def __init__(
        self,
        agent_id: str,
        name: str,
        bus: MessageBus,
        city_network: CityNetwork,
        source_node: str = "CBB",
        destination_node: str = "",
        route: Optional[List[str]] = None,
        cargo_units: Optional[List[BloodUnit]] = None,
        request_id: str = "",
        start_time: float = 0.0,
        is_backup: bool = False,
        status_interval_minutes: float = 2.0,
        t_min: float = 1.0,
        t_max: float = 10.0,
    ):
        super().__init__(agent_id, name, bus)
        self.city_network = city_network
        self.source_node = source_node
        self.destination_node = destination_node
        self.route: List[str] = list(route) if route else []
        self.cargo_units: List[BloodUnit] = cargo_units if cargo_units else []
        self.request_id = request_id
        self.start_time = start_time
        self.is_backup = is_backup
        self.status_interval_minutes = status_interval_minutes
        self.t_min = t_min
        self.t_max = t_max

        # Dispatch & movement lifecycle
        self.is_accepted: bool = False
        self.is_completed: bool = False
        self.is_delivered: bool = False
        self.current_route_index: int = 0
        self.edge_progress: float = 0.0
        self.last_status_update_time: float = -999.0

        # Thermal sensing
        self.current_temp: float = 4.0
        self.temperature_history: List[Tuple[float, float]] = [(start_time, 4.0)]
        self.injected_breach: Optional[str] = None
        self.is_quarantined: bool = False
        self.replan_events: List[Dict[str, Any]] = []

        if self.cargo_units:
            for u in self.cargo_units:
                u.status = BloodUnitStatus.IN_TRANSIT

    @property
    def is_idle(self) -> bool:
        """Vehicle is available for new dispatch if not currently en route."""
        return not self.is_accepted or self.is_completed

    @property
    def current_node(self) -> str:
        if self.current_route_index < len(self.route):
            return self.route[self.current_route_index]
        return self.destination_node or self.source_node

    @property
    def next_node(self) -> Optional[str]:
        if self.current_route_index + 1 < len(self.route):
            return self.route[self.current_route_index + 1]
        return None

    @property
    def current_position_coords(self) -> Tuple[float, float]:
        u_id = self.current_node
        v_id = self.next_node
        u_coords = self.city_network.get_coordinates(u_id)
        if not v_id or self.is_completed:
            return u_coords

        v_coords = self.city_network.get_coordinates(v_id)
        p = max(0.0, min(1.0, self.edge_progress))
        cur_x = (1.0 - p) * u_coords[0] + p * v_coords[0]
        cur_y = (1.0 - p) * u_coords[1] + p * v_coords[1]
        return (cur_x, cur_y)

    def calculate_remaining_eta(self) -> float:
        if self.is_completed or self.current_route_index >= len(self.route) - 1:
            return 0.0

        remaining_time = 0.0
        u = self.route[self.current_route_index]
        v = self.route[self.current_route_index + 1]
        edge_time = self.city_network.get_edge_travel_time(u, v)
        remaining_time += (1.0 - self.edge_progress) * edge_time

        for i in range(self.current_route_index + 1, len(self.route) - 1):
            nu = self.route[i]
            nv = self.route[i + 1]
            remaining_time += self.city_network.get_edge_travel_time(nu, nv)

        return remaining_time

    def format_route_string(self) -> str:
        """Return formatted route string in destination ← ... ← origin notation."""
        if not self.route:
            return ""
        return "←".join(reversed(self.route))

    def inject_breach(self, breach_type: str = "HOT") -> None:
        self.injected_breach = breach_type

    def update_sensor_reading(self, sim_time: float) -> float:
        if self.injected_breach == "HOT":
            self.current_temp = max(11.0, self.current_temp + random.uniform(2.0, 3.2))
        elif self.injected_breach == "COLD":
            self.current_temp = min(-0.5, self.current_temp - random.uniform(1.8, 2.5))
        else:
            target = 4.0
            noise = random.gauss(0.0, 0.25)
            self.current_temp = target + noise

        self.current_temp = round(self.current_temp, 2)
        self.temperature_history.append((sim_time, self.current_temp))
        for u in self.cargo_units:
            u.temperature_readings.append(self.current_temp)

        return self.current_temp

    def check_and_replan_route(self, sim_time: float) -> bool:
        if self.is_completed or self.current_route_index >= len(self.route) - 1:
            return False

        current_head = self.route[self.current_route_index]
        remaining_current_eta = self.calculate_remaining_eta()

        fresh_plan = astar_search(self.city_network, current_head, self.destination_node)

        if fresh_plan.cost_minutes < (remaining_current_eta - 1.5) and fresh_plan.path:
            old_path = list(self.route)
            new_route = self.route[:self.current_route_index] + fresh_plan.path
            self.route = new_route
            event = {
                "time": sim_time,
                "old_path": old_path,
                "new_path": new_route,
                "saved_minutes": round(remaining_current_eta - fresh_plan.cost_minutes, 1),
            }
            self.replan_events.append(event)
            return True

        return False

    def advance_step(self, dt_minutes: float, sim_time: float) -> None:
        """Advance physical movement along the road network. Only runs once dispatch is ACCEPTed."""
        if not self.is_accepted or self.is_completed:
            return

        # 1. Update temperature sensor
        self.update_sensor_reading(sim_time)

        # 2. Check dynamic traffic re-planning
        self.check_and_replan_route(sim_time)

        # 3. Advance movement along current edge
        remaining_dt = dt_minutes
        while remaining_dt > 0 and self.current_route_index < len(self.route) - 1:
            u = self.route[self.current_route_index]
            v = self.route[self.current_route_index + 1]
            edge_time = max(0.1, self.city_network.get_edge_travel_time(u, v))

            progress_step = remaining_dt / edge_time
            if self.edge_progress + progress_step < 1.0:
                self.edge_progress += progress_step
                remaining_dt = 0.0
            else:
                used_dt = (1.0 - self.edge_progress) * edge_time
                remaining_dt -= used_dt
                self.current_route_index += 1
                self.edge_progress = 0.0

        # Check if arrived at final destination
        if self.current_route_index >= len(self.route) - 1:
            self.is_completed = True
            self.is_delivered = True
            for u in self.cargo_units:
                if u.status != BloodUnitStatus.QUARANTINED:
                    u.status = BloodUnitStatus.DELIVERED

            # Send single DELIVERED message to destination hospital with request conversation_id
            b_type = self.cargo_units[0].blood_type if self.cargo_units else "O-"
            self.send(
                receiver=self.destination_node,
                performative=Performative.DELIVERED,
                payload={
                    "vehicle_id": self.agent_id,
                    "request_id": self.request_id,
                    "source_bank": self.source_node,
                    "destination_hospital": self.destination_node,
                    "units": self.cargo_units,
                    "units_count": len(self.cargo_units),
                    "blood_type": b_type,
                    "unit_ids": [u.unit_id for u in self.cargo_units],
                    "temperature": self.current_temp,
                    "temperature_history": list(self.temperature_history),
                    "delivered_at": sim_time,
                    "is_backup": self.is_backup,
                },
                timestamp=sim_time,
                conversation_id=self.request_id,
            )
            return

        # 4. Check if STATUS_UPDATE should be emitted to source bank
        is_temp_warning = (self.current_temp < self.t_min) or (self.current_temp > self.t_max)
        time_elapsed = sim_time - self.last_status_update_time

        if is_temp_warning or time_elapsed >= self.status_interval_minutes:
            self.last_status_update_time = sim_time
            eta = self.calculate_remaining_eta()
            route_str = self.format_route_string()

            self.send(
                receiver=self.source_node,
                performative=Performative.STATUS_UPDATE,
                payload={
                    "vehicle_id": self.agent_id,
                    "current_node": self.current_node,
                    "temperature": self.current_temp,
                    "eta_minutes": round(eta, 0),
                    "route_str": route_str,
                    "request_id": self.request_id,
                    "status": "QUARANTINED" if self.is_quarantined else "EN_ROUTE",
                },
                timestamp=sim_time,
                conversation_id=self.request_id,
            )

    def receive(self, message: Message) -> None:
        """Receive message and trigger immediate perception for dispatch or emergency orders."""
        super().receive(message)
        if message.performative in (Performative.DISPATCH, Performative.QUARANTINE):
            self.perceive(message.timestamp)

    def perceive(self, current_time: float) -> None:
        """Process messages received in inbox (DISPATCH, QUARANTINE)."""
        unhandled = list(self.inbox)
        self.inbox.clear()

        for msg in unhandled:
            if msg.performative == Performative.DISPATCH:
                self._handle_dispatch(msg, current_time)
            elif msg.performative == Performative.QUARANTINE:
                self.is_quarantined = True
                for u in self.cargo_units:
                    u.status = BloodUnitStatus.QUARANTINED

    def _handle_dispatch(self, msg: Message, current_time: float) -> None:
        """Receive dispatch instructions, configure vehicle state, and reply with ACCEPT."""
        p = msg.payload
        self.source_node = p.get("source_bank", self.source_node)
        self.destination_node = p["destination_hospital"]
        self.route = list(p["route"])
        self.cargo_units = list(p.get("units", []))
        self.request_id = msg.conversation_id or p.get("request_id", "")
        self.is_backup = p.get("is_backup", False)
        self.start_time = current_time

        self.current_route_index = 0
        self.edge_progress = 0.0
        self.is_completed = False
        self.is_delivered = False
        self.is_accepted = True
        self.last_status_update_time = current_time

        for u in self.cargo_units:
            u.status = BloodUnitStatus.IN_TRANSIT

        # Send ACCEPT reply back to the dispatching bank with the request's conversation_id
        eta = self.calculate_remaining_eta()
        b_type = p.get("blood_type") or (self.cargo_units[0].blood_type if self.cargo_units else "O-")
        self.send(
            receiver=msg.sender,
            performative=Performative.ACCEPT,
            payload={
                "vehicle_id": self.agent_id,
                "request_id": self.request_id,
                "destination_hospital": self.destination_node,
                "eta_minutes": round(eta, 1),
                "units_count": len(self.cargo_units),
                "blood_type": b_type,
            },
            timestamp=current_time,
            conversation_id=self.request_id,
        )

    def decide(self, current_time: float) -> Any:
        return None

    def act(self, current_time: float) -> None:
        return None

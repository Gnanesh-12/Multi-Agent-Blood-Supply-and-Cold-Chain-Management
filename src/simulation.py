"""SimulationEngine: Core coordinator owning agents, network, rules, message bus, and time."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import pandas as pd

from src.blood import BloodType, BloodUnit, BloodUnitStatus
from src.city import CityNetwork
from src.messaging import Message, MessageBus, Performative
from src.planning.allocation import AllocationDecision, AllocationOutcome, BloodRequirement
from src.planning.astar import astar_search, dijkstra_search
from src.rules import SafetyRuleEngine, RuleFiring
from src.agents.hospital import HospitalAgent
from src.agents.blood_bank import BloodBankAgent
from src.agents.delivery import DeliveryAgent


class SimulationEngine:
    """Headless simulation engine encapsulating all multi-agent behavior and domain state.

    Contains no Streamlit dependencies, ensuring complete testability and modularity.
    """

    def __init__(self, config_path: str | Path, random_seed: int = 42):
        self.config_path = Path(config_path)
        self.random_seed = random_seed
        random.seed(random_seed)

        self.city_network = CityNetwork(self.config_path)
        self.bus = MessageBus()

        # Initialize safety rule engine
        sr = self.city_network.safety_rules
        self.rule_engine = SafetyRuleEngine(
            t_min=sr.get("temp_min_celsius", 1.0),
            t_max=sr.get("temp_max_celsius", 10.0),
            d_consecutive=int(sr.get("breach_consecutive_readings", 3)),
        )

        # Time clock
        self.current_time: float = 0.0
        self.step_size_minutes: float = 1.0

        # Agents
        self.hospitals: Dict[str, HospitalAgent] = {}
        self.central_bank: Optional[BloodBankAgent] = None
        self.reserve_bank: Optional[BloodBankAgent] = None
        self.delivery_agents: Dict[str, DeliveryAgent] = {}
        self._next_delivery_id: int = 1

        # Historical analytics
        self.allocation_history: List[AllocationDecision] = []
        self.request_tracking: Dict[str, Dict[str, Any]] = {}  # {req_id: metadata}

        self._initialize_agents()

    def _initialize_agents(self) -> None:
        """Instantiate hospital, central bank, and reserve bank agents from network config."""
        self.hospitals.clear()
        self.delivery_agents.clear()
        self.allocation_history.clear()
        self.request_tracking.clear()
        self.bus.reset()
        self.rule_engine.reset()
        self.current_time = 0.0

        # 1. Hospital Agents
        for node in self.city_network.get_hospitals():
            h_agent = HospitalAgent(
                agent_id=node.node_id,
                name=node.name,
                bus=self.bus,
                initial_stock=node.initial_stock,
                target_stock=node.target_stock,
                bed_capacity=node.bed_capacity or 300,
            )
            self.hospitals[node.node_id] = h_agent

        # 2. Central Blood Bank
        cbb_node = self.city_network.get_central_bank()
        if cbb_node:
            self.central_bank = BloodBankAgent(
                agent_id=cbb_node.node_id,
                name=cbb_node.name,
                bus=self.bus,
                city_network=self.city_network,
                bank_type="central_bank",
                vehicle_ids=["VAN-01", "VAN-02"],
            )
            self.central_bank.initialize_inventory(cbb_node.initial_inventory, base_shelf_life_mins=360.0)
            self.central_bank.on_allocation = self._record_allocation_decisions

        # 3. Reserve Blood Bank
        rbb_node = self.city_network.get_reserve_bank()
        if rbb_node:
            self.reserve_bank = BloodBankAgent(
                agent_id=rbb_node.node_id,
                name=rbb_node.name,
                bus=self.bus,
                city_network=self.city_network,
                bank_type="reserve_bank",
                vehicle_ids=["VAN-03", "VAN-04"],
            )
            self.reserve_bank.initialize_inventory(rbb_node.initial_inventory, base_shelf_life_mins=480.0)

        # 4. Pre-provisioned Delivery Fleet (Engine only instantiates and steps; messages route peer-to-peer)
        for v_id in ["VAN-01", "VAN-02"]:
            self.delivery_agents[v_id] = DeliveryAgent(
                agent_id=v_id,
                name=f"Central Rapid Delivery {v_id}",
                bus=self.bus,
                city_network=self.city_network,
                source_node="CBB",
                status_interval_minutes=2.0,
            )
        for v_id in ["VAN-03", "VAN-04"]:
            self.delivery_agents[v_id] = DeliveryAgent(
                agent_id=v_id,
                name=f"Reserve Rapid Delivery {v_id}",
                bus=self.bus,
                city_network=self.city_network,
                source_node="RBB",
                status_interval_minutes=2.0,
            )

    def reset(self, new_seed: Optional[int] = None) -> None:
        """Reset entire simulation to initial baseline state."""
        if new_seed is not None:
            self.random_seed = new_seed
        random.seed(self.random_seed)
        self.city_network = CityNetwork(self.config_path)
        self._initialize_agents()

    def submit_hospital_request(
        self,
        hospital_id: str,
        blood_type: str,
        units: int,
        urgency_level: str,
        time_to_need_minutes: float,
        reason: str,
    ) -> BloodRequirement:
        """Raise blood requirement from a hospital agent."""
        if hospital_id not in self.hospitals:
            raise KeyError(f"Hospital {hospital_id} does not exist")
        h_agent = self.hospitals[hospital_id]
        req = h_agent.create_request(
            blood_type=blood_type,
            units=units,
            urgency_level=urgency_level,
            time_to_need_minutes=time_to_need_minutes,
            reason=reason,
            current_time=self.current_time,
            target_bank=self.central_bank.agent_id if self.central_bank else "CBB",
        )
        self.request_tracking[req.request_id] = {
            "request_id": req.request_id,
            "hospital_id": hospital_id,
            "blood_type": blood_type,
            "units_requested": units,
            "urgency": urgency_level,
            "created_at": self.current_time,
            "time_to_need": time_to_need_minutes,
            "deadline": self.current_time + time_to_need_minutes,
            "delivered_at": None,
            "status": "PENDING",
            "allocated": 0,
            "outcome": None,
            "deadline_status": None,
        }
        return req

    def _record_allocation_decisions(self, decisions: List[AllocationDecision]) -> None:
        """Record decisions into allocation history and update request tracking."""
        for d in decisions:
            if d not in self.allocation_history:
                self.allocation_history.append(d)
            if d.request_id in self.request_tracking:
                self.request_tracking[d.request_id]["allocated"] = d.units_allocated
                self.request_tracking[d.request_id]["outcome"] = d.outcome.value
                self.request_tracking[d.request_id]["status"] = d.outcome.value

    def run_allocation(
        self,
        weights: Optional[Dict[str, float]] = None,
        rarity_scores: Optional[Dict[str, float]] = None,
    ) -> List[AllocationDecision]:
        """Trigger blood bank agent to execute greedy priority allocation on pending requests."""
        if not self.central_bank:
            return []

        # Deliver pending requests to bank if not already done
        self.central_bank.perceive(self.current_time)

        decisions = self.central_bank.run_allocation(
            current_time=self.current_time,
            weights=weights,
            rarity_scores=rarity_scores,
        )
        self._record_allocation_decisions(decisions)
        return decisions

    def step(self, dt_minutes: Optional[float] = None) -> None:
        """Advance simulation clock by dt_minutes (default: 1.0 min).

        Workflow order:
          1. Safety Rules evaluated (temperature breach, expiration).
          2. Physical movement & thermal sensory updates of active delivery agents.
          3. Agent perceive -> decide -> act cycles.
          4. Advance clock.
        """
        dt = dt_minutes if dt_minutes is not None else self.step_size_minutes

        # Step 1: Safety Rule Evaluation BEFORE any other decision
        for dev_id, dev in list(self.delivery_agents.items()):
            if dev.is_accepted and not dev.is_completed and not dev.is_quarantined:
                is_breached, firing = self.rule_engine.evaluate_temperature_reading(
                    vehicle_id=dev_id,
                    current_temp=dev.current_temp,
                    cargo_units=dev.cargo_units,
                    sim_time=self.current_time,
                )
                if is_breached:
                    dev.is_quarantined = True
                    # Delivery agent broadcasts BREACH_ALERT directly to source blood bank
                    first_unit = dev.cargo_units[0] if dev.cargo_units else None
                    b_type = first_unit.blood_type if first_unit else "O-"
                    dev.send(
                        receiver=dev.source_node,
                        performative=Performative.BREACH_ALERT,
                        payload={
                            "vehicle_id": dev_id,
                            "destination_hospital": dev.destination_node,
                            "blood_type": b_type,
                            "units_count": len(dev.cargo_units),
                            "unit_ids": [u.unit_id for u in dev.cargo_units],
                            "request_id": dev.request_id,
                            "temperature": dev.current_temp,
                        },
                        timestamp=self.current_time,
                        conversation_id=dev.request_id,
                    )

        # Expiry rule evaluation
        if self.central_bank:
            self.rule_engine.evaluate_expiry(self.central_bank.inventory, self.current_time, "Central Bank")
        if self.reserve_bank:
            self.rule_engine.evaluate_expiry(self.reserve_bank.inventory, self.current_time, "Reserve Bank")

        # Step 2: Physical movement and telemetry of active delivery agents
        for dev_id, dev in list(self.delivery_agents.items()):
            if not dev.is_completed:
                dev.advance_step(dt, self.current_time)
                if dev.is_completed and dev.request_id in self.request_tracking:
                    self.request_tracking[dev.request_id]["delivered_at"] = self.current_time
                    self.request_tracking[dev.request_id]["status"] = "DELIVERED"
                    if not self.request_tracking[dev.request_id].get("outcome"):
                        self.request_tracking[dev.request_id]["outcome"] = (
                            AllocationOutcome.FULFILLED.value
                            if self.request_tracking[dev.request_id].get("allocated", 0) >= self.request_tracking[dev.request_id].get("units_requested", 1)
                            else AllocationOutcome.PARTIAL.value
                        )
                    deadline_status = dev.deadline_status
                    if not deadline_status:
                        dl = self.request_tracking[dev.request_id].get("deadline", dev.deadline)
                        if self.current_time <= dl:
                            deadline_status = "On time"
                        else:
                            late = round(self.current_time - dl, 1)
                            l_str = f"{int(late)}" if late == int(late) else f"{late}"
                            deadline_status = f"Late by {l_str} min"
                    self.request_tracking[dev.request_id]["deadline_status"] = deadline_status
                    for d in self.allocation_history:
                        if d.request_id == dev.request_id:
                            d.deadline_status = deadline_status

        # Step 3: Agent step execution (Hospitals, Blood Banks)
        for h_agent in self.hospitals.values():
            h_agent.step(self.current_time)

        if self.central_bank:
            self.central_bank.step(self.current_time)

        if self.reserve_bank:
            self.reserve_bank.step(self.current_time)

        for dev in self.delivery_agents.values():
            dev.step(self.current_time)

        # Step 4: Advance clock
        self.current_time = round(self.current_time + dt, 1)

    def run_until_idle(self, max_steps: int = 150) -> int:
        """Run simulation steps continuously until all active deliveries finish."""
        steps_taken = 0
        while steps_taken < max_steps:
            active_deliveries = [d for d in self.delivery_agents.values() if not d.is_completed]
            has_pending = (
                bool(self.central_bank and self.central_bank.pending_requests)
                or bool(active_deliveries)
            )
            if not has_pending and steps_taken > 0:
                break
            self.step()
            steps_taken += 1
        return steps_taken

    def inject_delivery_breach(self, vehicle_id: str, breach_type: str = "HOT") -> bool:
        """Inject temperature breach into a specific active delivery vehicle."""
        if vehicle_id in self.delivery_agents:
            self.delivery_agents[vehicle_id].inject_breach(breach_type)
            return True
        return False

    def load_preset_scenario(self, scenario_name: str) -> None:
        """Pre-configure requests, traffic, and inventory for demonstration scenarios."""
        self.reset(self.random_seed)

        if scenario_name == "1. Single Routine Request":
            self.submit_hospital_request(
                hospital_id="H1",
                blood_type="A+",
                units=2,
                urgency_level="Routine",
                time_to_need_minutes=90.0,
                reason="Elective Orthopedic Surgery",
            )

        elif scenario_name == "2. Two Hospitals Competing for Scarce O-":
            # Drain O- stock down to 2 units to create fierce contention
            if self.central_bank:
                o_neg_units = [u for u in self.central_bank.inventory if u.blood_type == "O-"]
                for u in o_neg_units[2:]:
                    u.status = BloodUnitStatus.EXPIRED

            # Also drain O- stock in Reserve Bank so it refuses backup request
            if self.reserve_bank:
                for u in self.reserve_bank.inventory:
                    if u.blood_type == "O-":
                        u.status = BloodUnitStatus.EXPIRED

            # Hospital 1: High emergency surgery needing 2 units O-
            self.submit_hospital_request(
                hospital_id="H1",
                blood_type="O-",
                units=2,
                urgency_level="Emergency",
                time_to_need_minutes=15.0,
                reason="Severe Hemorrhagic Shock",
            )

            # Hospital 3: Routine transfusion needing 2 units O-
            self.submit_hospital_request(
                hospital_id="H3",
                blood_type="O-",
                units=2,
                urgency_level="Routine",
                time_to_need_minutes=120.0,
                reason="Scheduled Sickle Cell Transfusion",
            )

        elif scenario_name == "3. Mass-Casualty Incident (4 Hospitals)":
            requests_data = [
                ("H1", "O-", 3, "Emergency", 15.0, "Major Highway Collision"),
                ("H2", "A+", 4, "Emergency", 20.0, "Factory Blast Trauma"),
                ("H4", "B+", 3, "Urgent", 45.0, "Emergency Obstetric Hemorrhage"),
                ("H5", "O+", 2, "Urgent", 60.0, "Pediatric Critical Surgery"),
            ]
            for h_id, b_type, units, urg, ttn, reason in requests_data:
                self.submit_hospital_request(h_id, b_type, units, urg, ttn, reason)

        elif scenario_name == "4. Temperature Breach Mid-Delivery -> Backup from Reserve":
            # Raise emergency request at Govt Medical College (H4, close to Reserve Bank)
            self.submit_hospital_request(
                hospital_id="H4",
                blood_type="B-",
                units=2,
                urgency_level="Emergency",
                time_to_need_minutes=25.0,
                reason="Severe Polytrauma Need",
            )
            # Run allocation to launch dispatch
            self.run_allocation()
            # Advance 2 steps, then inject breach on active vehicle
            self.step(2.0)
            for dev in self.delivery_agents.values():
                if dev.is_accepted and not dev.is_completed:
                    self.inject_delivery_breach(dev.agent_id, "HOT")
                    break

        elif scenario_name == "5. Traffic Jam (A* Dynamic Re-routing)":
            # Heavy traffic on Central Arterial North (CBB <-> J4)
            self.city_network.set_road_delay("CBB", "J4", 3.0)
            self.submit_hospital_request(
                hospital_id="H5",
                blood_type="AB+",
                units=2,
                urgency_level="Urgent",
                time_to_need_minutes=40.0,
                reason="Cardiovascular Bypass",
            )

        elif scenario_name == "6. Stockout -> Compatible Substitution":
            # Completely deplete B+ in Central Bank to trigger compatible O+ substitution
            if self.central_bank:
                for u in self.central_bank.inventory:
                    if u.blood_type == "B+":
                        u.status = BloodUnitStatus.EXPIRED

            self.submit_hospital_request(
                hospital_id="H2",
                blood_type="B+",
                units=3,
                urgency_level="Urgent",
                time_to_need_minutes=35.0,
                reason="Cancer Chemotherapy Support",
            )

    def get_summary_metrics(self) -> Dict[str, Any]:
        """Compute key operational summary indicators for the dashboard metric cards."""
        total_requests = len(self.request_tracking)
        fulfilled = sum(
            1 for r in self.request_tracking.values()
            if r.get("outcome") == AllocationOutcome.FULFILLED.value
            or r.get("status") == AllocationOutcome.FULFILLED.value
            or (r.get("status") == "DELIVERED" and r.get("allocated", 0) >= r.get("units_requested", 1))
        )
        partial = sum(
            1 for r in self.request_tracking.values()
            if r.get("outcome") == AllocationOutcome.PARTIAL.value
            or r.get("status") == AllocationOutcome.PARTIAL.value
            or (r.get("status") == "DELIVERED" and 0 < r.get("allocated", 0) < r.get("units_requested", 1))
        )
        refused = sum(
            1 for r in self.request_tracking.values()
            if r.get("outcome") == AllocationOutcome.REFUSED.value
            or r.get("status") == AllocationOutcome.REFUSED.value
        )

        # Units delivered
        units_delivered = sum(
            len(h.delivered_records) for h in self.hospitals.values()
        )

        # Breaches / Quarantined
        quarantined_units = sum(
            1 for u in (self.central_bank.inventory if self.central_bank else []) + (self.reserve_bank.inventory if self.reserve_bank else [])
            if u.status == BloodUnitStatus.QUARANTINED
        )
        breach_firings = sum(
            1 for f in self.rule_engine.firings_log
            if "BREACH" in f.rule_id
        )

        # Average fulfillment time for delivered requests
        deliv_times = [
            (r["delivered_at"] - r["created_at"])
            for r in self.request_tracking.values()
            if r["delivered_at"] is not None
        ]
        avg_fulfilment_time = round(sum(deliv_times) / len(deliv_times), 1) if deliv_times else 0.0

        # Deadline tracking metrics
        delivered_reqs = [
            r for r in self.request_tracking.values()
            if r.get("delivered_at") is not None
        ]
        on_time_count = sum(
            1 for r in delivered_reqs
            if r.get("deadline_status") == "On time"
            or (r.get("deadline") is not None and r.get("delivered_at", 0) <= r.get("deadline"))
        )
        late_reqs = [
            r for r in delivered_reqs
            if (r.get("deadline_status") and r.get("deadline_status") != "On time")
            or (r.get("deadline") is not None and r.get("delivered_at", 0) > r.get("deadline"))
        ]
        late_count = len(late_reqs)
        max_late_mins = max([
            round(r["delivered_at"] - r["deadline"], 1)
            for r in late_reqs
            if r.get("deadline") is not None
        ], default=0.0)
        max_late_str = f"{int(max_late_mins)}" if max_late_mins == int(max_late_mins) else f"{max_late_mins}"
        deadline_kpi_text = ""
        if late_count > 0:
            deadline_kpi_text = f"Late by {max_late_str} min"
        elif on_time_count > 0:
            deadline_kpi_text = "On time"

        total_messages = len(self.bus.history)

        return {
            "requests_received": total_requests,
            "fulfilled": fulfilled,
            "partial": partial,
            "refused": refused,
            "partial_or_refused": partial + refused,
            "units_delivered": units_delivered,
            "breaches_quarantined": max(quarantined_units, breach_firings),
            "avg_fulfilment_time_mins": avg_fulfilment_time,
            "total_messages": total_messages,
            "on_time_count": on_time_count,
            "late_count": late_count,
            "max_late_mins": max_late_mins,
            "deadline_kpi_text": deadline_kpi_text,
        }

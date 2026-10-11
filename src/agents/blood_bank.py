"""BloodBankAgent managing blood inventories, priority allocation, vehicle dispatch, and backup sourcing."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from src.agents.base import BaseAgent
from src.blood import (
    BloodType,
    BloodUnit,
    BloodUnitStatus,
    get_compatible_donor_types,
    sort_units_fefo,
)
from src.messaging import Message, MessageBus, Performative
from src.planning.allocation import (
    AllocationDecision,
    AllocationOutcome,
    BloodRequirement,
    greedy_priority_allocation,
)
from src.planning.astar import astar_search

if TYPE_CHECKING:
    from src.city import CityNetwork
    from src.agents.delivery import DeliveryAgent


class BloodBankAgent(BaseAgent):
    """Autonomous Blood Bank agent managing inventory, FEFO allocation, and peer-to-peer backup sourcing."""

    def __init__(
        self,
        agent_id: str,
        name: str,
        bus: MessageBus,
        city_network: CityNetwork,
        bank_type: str = "central_bank",
        vehicle_ids: Optional[List[str]] = None,
    ):
        super().__init__(agent_id, name, bus)
        self.city_network = city_network
        self.bank_type = bank_type  # "central_bank" or "reserve_bank"
        self.inventory: List[BloodUnit] = []
        self.pending_requests: List[BloodRequirement] = []
        self.request_registry: Dict[str, BloodRequirement] = {}
        self.last_allocation_decisions: List[AllocationDecision] = []
        self.active_dispatches: List[Dict[str, Any]] = []

        # Vehicle pool associated with this bank
        if vehicle_ids:
            self.vehicle_ids = list(vehicle_ids)
        elif bank_type == "central_bank":
            self.vehicle_ids = ["VAN-01", "VAN-02"]
        else:
            self.vehicle_ids = ["VAN-03", "VAN-04"]
        self._next_vehicle_idx = 0

    def initialize_inventory(self, initial_counts: Dict[str, int], base_shelf_life_mins: float = 300.0) -> None:
        """Seed initial inventory with staggered expiration times for FEFO testing."""
        self.inventory.clear()
        for b_type, count in initial_counts.items():
            for i in range(count):
                staggered_expiry = base_shelf_life_mins + (i * 15.0) - 40.0
                unit_id = f"U-{self.agent_id}-{b_type.replace('+', 'P').replace('-', 'N')}-{i+1:02d}"
                unit = BloodUnit(
                    unit_id=unit_id,
                    blood_type=b_type,
                    expiry_time=max(60.0, staggered_expiry),
                    status=BloodUnitStatus.IN_STOCK,
                    source_bank=self.agent_id,
                )
                self.inventory.append(unit)

    def get_stock_counts(self) -> Dict[str, int]:
        counts = {bt.value: 0 for bt in BloodType}
        for u in self.inventory:
            if u.status == BloodUnitStatus.IN_STOCK:
                counts[u.blood_type] = counts.get(u.blood_type, 0) + 1
        return counts

    def get_total_stock(self) -> int:
        return sum(1 for u in self.inventory if u.status == BloodUnitStatus.IN_STOCK)

    def get_next_vehicle_id(self) -> str:
        """Select next vehicle from bank pool in round-robin fashion."""
        veh_id = self.vehicle_ids[self._next_vehicle_idx % len(self.vehicle_ids)]
        self._next_vehicle_idx += 1
        return veh_id

    def enqueue_request(self, req: BloodRequirement) -> None:
        self.pending_requests.append(req)
        self.request_registry[req.request_id] = req

    def receive(self, message: Message) -> None:
        """Receive message and trigger perception for interactive negotiation."""
        super().receive(message)
        if message.performative in (
            Performative.REQUEST,
            Performative.BACKUP_REQUEST,
            Performative.PROPOSE,
            Performative.REFUSE,
            Performative.BREACH_ALERT,
        ):
            self.perceive(message.timestamp)

    def perceive(self, current_time: float) -> None:
        """Process incoming messages from hospitals, delivery agents, and peer banks."""
        unhandled = list(self.inbox)
        self.inbox.clear()

        for msg in unhandled:
            if msg.performative == Performative.REQUEST:
                self._handle_request_msg(msg)
            elif msg.performative == Performative.BACKUP_REQUEST:
                self._handle_backup_request(msg, current_time)
            elif msg.performative == Performative.PROPOSE:
                self._handle_propose(msg, current_time)
            elif msg.performative == Performative.REFUSE:
                self._handle_peer_refuse(msg, current_time)
            elif msg.performative == Performative.ACCEPT:
                pass  # Vehicle accepted dispatch
            elif msg.performative == Performative.STATUS_UPDATE:
                pass  # Telemetry logged on bus
            elif msg.performative == Performative.BREACH_ALERT:
                self._handle_breach_alert(msg, current_time)
            elif msg.performative == Performative.ACK:
                pass  # Hospital acknowledged receipt

    def _handle_request_msg(self, msg: Message) -> None:
        p = msg.payload
        req = BloodRequirement(
            request_id=p["request_id"],
            hospital_id=p["hospital_id"],
            hospital_name=p["hospital_name"],
            blood_type=p["blood_type"],
            units_requested=int(p["units"]),
            urgency_level=p.get("urgency", "Routine"),
            time_to_need_minutes=float(p.get("time_to_need", 60.0)),
            reason=p.get("reason", "Surgery"),
            created_at_sim_time=msg.timestamp,
            current_hospital_stock=int(p.get("current_stock", 0)),
            target_hospital_stock=int(p.get("target_stock", 5)),
        )
        self.pending_requests.append(req)
        self.request_registry[req.request_id] = req

    def _handle_backup_request(self, msg: Message, current_time: float) -> None:
        """Reserve Bank processes incoming BACKUP_REQUEST from Central Bank."""
        p = msg.payload
        req_id = msg.conversation_id or p.get("request_id", "")
        dest_hospital = p.get("destination_hospital") or p.get("hospital_id", "")
        blood_type = p["blood_type"]
        needed = int(p.get("units_needed") or p.get("units_count", 1))

        allocated = self.allocate_units_direct(blood_type, needed, current_time)

        if allocated:
            rbb_plan = astar_search(self.city_network, self.agent_id, dest_hospital)
            veh_id = self.get_next_vehicle_id()

            # 1. Reply PROPOSE to CBB
            self.send(
                receiver=msg.sender,
                performative=Performative.PROPOSE,
                payload={
                    "request_id": req_id,
                    "destination_hospital": dest_hospital,
                    "blood_type": blood_type,
                    "units_count": len(allocated),
                    "unit_ids": [u.unit_id for u in allocated],
                    "vehicle_id": veh_id,
                    "eta_minutes": round(rbb_plan.cost_minutes, 1),
                },
                timestamp=current_time,
                conversation_id=req_id,
            )

            # 2. Dispatch vehicle from Reserve Bank
            self.send(
                receiver=veh_id,
                performative=Performative.DISPATCH,
                payload={
                    "request_id": req_id,
                    "destination_hospital": dest_hospital,
                    "source_bank": self.agent_id,
                    "units": allocated,
                    "units_count": len(allocated),
                    "blood_type": blood_type,
                    "unit_ids": [u.unit_id for u in allocated],
                    "route": rbb_plan.path,
                    "eta_minutes": rbb_plan.cost_minutes,
                    "is_backup": True,
                },
                timestamp=current_time,
                conversation_id=req_id,
            )
        else:
            # Reserve Bank cannot fulfill: reply REFUSE to CBB
            self.send(
                receiver=msg.sender,
                performative=Performative.REFUSE,
                payload={
                    "request_id": req_id,
                    "destination_hospital": dest_hospital,
                    "blood_type": blood_type,
                    "reason": f"Reserve Bank stock exhausted for {blood_type} and compatible donors",
                },
                timestamp=current_time,
                conversation_id=req_id,
            )

    def _handle_propose(self, msg: Message, current_time: float) -> None:
        """CBB receives PROPOSE from Reserve Bank and informs hospital of backup fulfillment."""
        p = msg.payload
        req_id = msg.conversation_id or p.get("request_id", "")
        dest_hosp = p.get("destination_hospital", "")
        b_type = p.get("blood_type", "")
        count = p.get("units_count", 1)
        veh_id = p.get("vehicle_id", "")
        eta = p.get("eta_minutes", 0.0)

        # Inform hospital that order is fulfilled from Reserve Bank
        self.send(
            receiver=dest_hosp,
            performative=Performative.INFORM,
            payload={
                "request_id": req_id,
                "status": "FULFILLED_RESERVE",
                "units_allocated": count,
                "blood_type": b_type,
                "vehicle_id": veh_id,
                "eta_minutes": eta,
            },
            timestamp=current_time,
            conversation_id=req_id,
        )

    def _handle_peer_refuse(self, msg: Message, current_time: float) -> None:
        """CBB handles refusal from Reserve Bank: reject emergency or defer non-emergency."""
        p = msg.payload
        req_id = msg.conversation_id or p.get("request_id", "")
        dest_hosp = p.get("destination_hospital", "")

        original_req = self.request_registry.get(req_id)
        is_emergency = original_req and original_req.urgency_level == "Emergency"

        if is_emergency:
            # Emergency cannot be fulfilled: send REFUSE
            self.send(
                receiver=dest_hosp,
                performative=Performative.REFUSE,
                payload={
                    "request_id": req_id,
                    "reason": "Stock exhausted across Central and Reserve Banks",
                },
                timestamp=current_time,
                conversation_id=req_id,
            )
        else:
            # Non-emergency: mark DEFERRED and re-queue with aging priority bonus
            if original_req and original_req not in self.pending_requests:
                # Artificial aging bonus to increase priority in next allocation cycle
                original_req.created_at_sim_time -= 30.0
                self.pending_requests.append(original_req)

            self.send(
                receiver=dest_hosp,
                performative=Performative.INFORM,
                payload={
                    "request_id": req_id,
                    "status": "DEFERRED",
                    "reason": "Stock currently unavailable; re-queued with aging priority bonus",
                },
                timestamp=current_time,
                conversation_id=req_id,
            )

    def _handle_breach_alert(self, msg: Message, current_time: float) -> None:
        """Handle cold chain temperature breach: quarantine units and trigger backup sourcing."""
        p = msg.payload
        req_id = msg.conversation_id or p.get("request_id", "")
        dest_hospital = p.get("destination_hospital") or self.request_registry.get(req_id, BloodRequirement(req_id, "", "", "O-", 1, "Routine", 60.0, "")).hospital_id
        vehicle_id = p.get("vehicle_id") or msg.sender
        blood_type = p.get("blood_type", "O-")
        units_count = int(p.get("units_count", 1))

        # Quarantine internal units if tracked
        quarantined_ids = p.get("unit_ids", [])
        for u in self.inventory:
            if u.unit_id in quarantined_ids:
                u.status = BloodUnitStatus.QUARANTINED
                u.quarantine_reason = f"Temperature breach alert from {vehicle_id}"

        # 1. Send QUARANTINE order to vehicle
        self.send(
            receiver=vehicle_id,
            performative=Performative.QUARANTINE,
            payload={
                "vehicle_id": vehicle_id,
                "request_id": req_id,
                "quarantined_units": quarantined_ids,
                "note": "Units marked quarantined in bank records. Halt clinical distribution.",
            },
            timestamp=current_time,
            conversation_id=req_id,
        )

        # 2. Trigger backup sourcing to deliver replacement units
        # Send BACKUP_REQUEST to peer Reserve Bank
        peer_bank = "RBB" if self.agent_id == "CBB" else "CBB"
        self.send(
            receiver=peer_bank,
            performative=Performative.BACKUP_REQUEST,
            payload={
                "request_id": req_id,
                "destination_hospital": dest_hospital,
                "blood_type": blood_type,
                "units_needed": units_count,
                "units_count": units_count,
                "reason": "Emergency replacement for quarantined cold-chain cargo",
            },
            timestamp=current_time,
            conversation_id=req_id,
        )

    def allocate_units_direct(self, blood_type: str, count: int, current_time: float) -> List[BloodUnit]:
        """Directly allocate units for emergency/backup sourcing using FEFO & compatibility."""
        available = [u for u in self.inventory if u.is_viable(current_time) and u.status == BloodUnitStatus.IN_STOCK]
        allocated: List[BloodUnit] = []

        # 1. Exact match
        exact_units = sort_units_fefo([u for u in available if u.blood_type == blood_type])
        take = min(count, len(exact_units))
        for u in exact_units[:take]:
            u.status = BloodUnitStatus.RESERVED
            allocated.append(u)

        # 2. Compatible substitution if needed
        if len(allocated) < count:
            compat_types = get_compatible_donor_types(blood_type)
            for ct in compat_types:
                if ct == blood_type:
                    continue
                compat_units = sort_units_fefo([u for u in available if u.blood_type == ct and u not in allocated])
                take_c = min(count - len(allocated), len(compat_units))
                for u in compat_units[:take_c]:
                    u.status = BloodUnitStatus.RESERVED
                    allocated.append(u)
                if len(allocated) >= count:
                    break

        return allocated

    def run_allocation(
        self,
        current_time: float,
        weights: Optional[Dict[str, float]] = None,
        rarity_scores: Optional[Dict[str, float]] = None,
    ) -> List[AllocationDecision]:
        """Execute greedy priority allocation over all pending requests and initiate peer communications."""
        if not self.pending_requests:
            return []

        w = weights or self.city_network.urgency_weights
        r = rarity_scores or self.city_network.rarity_scores

        decisions, _ = greedy_priority_allocation(
            requests=self.pending_requests,
            available_units=self.inventory,
            current_sim_time=current_time,
            weights=w,
            rarity_scores=r,
        )

        self.last_allocation_decisions = decisions
        self.pending_requests.clear()

        # Emit peer-to-peer communicative performatives for each decision in score rank order
        for d in decisions:
            if d.outcome in (AllocationOutcome.FULFILLED, AllocationOutcome.PARTIAL):
                # Central Bank fulfilled units!
                astar_plan = astar_search(self.city_network, self.agent_id, d.hospital_id)
                veh_id = self.get_next_vehicle_id()

                # 1. Inform requesting hospital
                self.send(
                    receiver=d.hospital_id,
                    performative=Performative.INFORM,
                    payload={
                        "request_id": d.request_id,
                        "status": "APPROVED",
                        "units_allocated": d.units_allocated,
                        "blood_type": d.blood_type_requested,
                        "rank": d.rank,
                        "score": d.score_breakdown.total_score,
                        "vehicle_id": veh_id,
                        "eta_minutes": round(astar_plan.cost_minutes, 1),
                    },
                    timestamp=current_time,
                    conversation_id=d.request_id,
                )

                # 2. Dispatch specific delivery vehicle
                self.send(
                    receiver=veh_id,
                    performative=Performative.DISPATCH,
                    payload={
                        "request_id": d.request_id,
                        "destination_hospital": d.hospital_id,
                        "source_bank": self.agent_id,
                        "units": d.allocated_units,
                        "units_count": d.units_allocated,
                        "blood_type": d.blood_type_requested,
                        "unit_ids": [u.unit_id for u in d.allocated_units],
                        "route": astar_plan.path,
                        "eta_minutes": astar_plan.cost_minutes,
                        "rank": d.rank,
                        "total_score": d.score_breakdown.total_score,
                    },
                    timestamp=current_time,
                    conversation_id=d.request_id,
                )
            else:
                # Central Bank has shortfall/stockout: initiate backup sourcing to Reserve Bank before refusal
                shortfall = d.units_requested - d.units_allocated
                orig_req = self.request_registry.get(d.request_id)
                urgency = orig_req.urgency_level if orig_req else "Routine"
                ttn = orig_req.time_to_need_minutes if orig_req else 60.0

                self.send(
                    receiver="RBB",
                    performative=Performative.BACKUP_REQUEST,
                    payload={
                        "request_id": d.request_id,
                        "hospital_id": d.hospital_id,
                        "destination_hospital": d.hospital_id,
                        "blood_type": d.blood_type_requested,
                        "units_needed": shortfall,
                        "units_count": shortfall,
                        "urgency": urgency,
                        "time_to_need": ttn,
                    },
                    timestamp=current_time,
                    conversation_id=d.request_id,
                )

        return decisions

    def decide(self, current_time: float) -> Any:
        return None

    def act(self, current_time: float) -> None:
        return None

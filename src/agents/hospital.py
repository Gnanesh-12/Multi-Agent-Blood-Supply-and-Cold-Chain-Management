"""Hospital agent managing clinical inventory, demand requests, and incoming deliveries."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import uuid
from src.agents.base import BaseAgent
from src.blood import BloodUnit, BloodUnitStatus
from src.messaging import Message, MessageBus, Performative
from src.planning.allocation import BloodRequirement


class HospitalAgent(BaseAgent):
    """Represents a hospital consuming blood units and monitoring safety on delivery."""

    def __init__(
        self,
        agent_id: str,
        name: str,
        bus: MessageBus,
        initial_stock: Dict[str, int],
        target_stock: Dict[str, int],
        bed_capacity: int = 300,
        t_min: float = 1.0,
        t_max: float = 10.0,
    ):
        super().__init__(agent_id, name, bus)
        self.stock: Dict[str, int] = dict(initial_stock)
        self.target_stock: Dict[str, int] = dict(target_stock)
        self.bed_capacity = bed_capacity
        self.t_min = t_min
        self.t_max = t_max
        self.active_requests: Dict[str, BloodRequirement] = {}
        self.delivered_records: List[Dict[str, Any]] = []
        self.rejected_records: List[Dict[str, Any]] = []
        self.notifications: List[Dict[str, Any]] = []

    def get_stock(self, blood_type: str) -> int:
        return self.stock.get(blood_type, 0)

    def get_target(self, blood_type: str) -> int:
        return self.target_stock.get(blood_type, 5)

    def get_deficit(self, blood_type: str) -> int:
        return max(0, self.get_target(blood_type) - self.get_stock(blood_type))

    def create_request(
        self,
        blood_type: str,
        units: int,
        urgency_level: str,
        time_to_need_minutes: float,
        reason: str,
        current_time: float,
        target_bank: str = "CBB",
    ) -> BloodRequirement:
        """Create a clinical blood requirement and broadcast REQUEST to Central Blood Bank."""
        req_id = f"REQ-{self.agent_id}-{len(self.active_requests) + 1:03d}-{uuid.uuid4().hex[:4].upper()}"
        req = BloodRequirement(
            request_id=req_id,
            hospital_id=self.agent_id,
            hospital_name=self.name,
            blood_type=blood_type,
            units_requested=units,
            urgency_level=urgency_level,
            time_to_need_minutes=time_to_need_minutes,
            reason=reason,
            created_at_sim_time=current_time,
            current_hospital_stock=self.get_stock(blood_type),
            target_hospital_stock=self.get_target(blood_type),
        )
        self.active_requests[req_id] = req

        payload = {
            "request_id": req_id,
            "hospital_id": self.agent_id,
            "hospital_name": self.name,
            "blood_type": blood_type,
            "units": units,
            "urgency": urgency_level,
            "time_to_need": time_to_need_minutes,
            "reason": reason,
            "current_stock": self.get_stock(blood_type),
            "target_stock": self.get_target(blood_type),
        }
        self.send(
            receiver=target_bank,
            performative=Performative.REQUEST,
            payload=payload,
            timestamp=current_time,
            conversation_id=req_id,
        )
        return req

    def receive(self, message: Message) -> None:
        """Receive message and process delivery inspection and notifications immediately."""
        super().receive(message)
        if message.performative in (Performative.DELIVERED, Performative.INFORM, Performative.REFUSE):
            self.perceive(message.timestamp)

    def perceive(self, current_time: float) -> None:
        """Process messages received in inbox."""
        unhandled = list(self.inbox)
        self.inbox.clear()

        for msg in unhandled:
            if msg.performative == Performative.DELIVERED:
                self._handle_delivery(msg, current_time)
            elif msg.performative == Performative.INFORM:
                self.notifications.append({
                    "time": current_time,
                    "sender": msg.sender,
                    "conversation_id": msg.conversation_id,
                    "payload": msg.payload,
                })
            elif msg.performative == Performative.REFUSE:
                self.notifications.append({
                    "time": current_time,
                    "sender": msg.sender,
                    "conversation_id": msg.conversation_id,
                    "payload": msg.payload,
                })

    def _handle_delivery(self, msg: Message, current_time: float) -> None:
        """Inspect delivered units and transit thermal history against safety rules."""
        units_data = msg.payload.get("units", [])
        vehicle_id = msg.sender
        req_id = msg.conversation_id or msg.payload.get("request_id")
        source_bank = msg.payload.get("source_bank", "CBB")
        temp_history = msg.payload.get("temperature_history", [])

        # Check safety rule: all temperature readings must be within [t_min, t_max]
        has_breach = False
        for entry in temp_history:
            t_val = entry[1] if isinstance(entry, (tuple, list)) else entry
            if t_val < self.t_min or t_val > self.t_max:
                has_breach = True
                break

        for u in units_data:
            status = u.get("status") if isinstance(u, dict) else u.status
            if status in (BloodUnitStatus.QUARANTINED.value, BloodUnitStatus.QUARANTINED):
                has_breach = True
                break

        if has_breach:
            # Temperature safety violation detected upon clinical verification
            self.rejected_records.append({
                "vehicle": vehicle_id,
                "request_id": req_id,
                "time": current_time,
                "reason": "Cold chain safety violation: temperature breached acceptable limits during transit",
            })
            # 1. Send REJECT to delivery vehicle
            self.send(
                receiver=vehicle_id,
                performative=Performative.REJECT,
                payload={
                    "request_id": req_id,
                    "reason": "Cold chain temperature violation detected upon arrival inspection",
                },
                timestamp=current_time,
                conversation_id=req_id,
            )
            # 2. Send BREACH_ALERT to source blood bank
            self.send(
                receiver=source_bank,
                performative=Performative.BREACH_ALERT,
                payload={
                    "request_id": req_id,
                    "vehicle_id": vehicle_id,
                    "reason": "Delivery rejected: Temperature violation detected during transit",
                },
                timestamp=current_time,
                conversation_id=req_id,
            )
        else:
            # Temperature log verified and in range: accept into clinical inventory
            accepted_count = 0
            b_type = ""
            for u in units_data:
                bt = u.get("blood_type") if isinstance(u, dict) else u.blood_type
                uid = u.get("unit_id") if isinstance(u, dict) else u.unit_id
                self.stock[bt] = self.stock.get(bt, 0) + 1
                accepted_count += 1
                b_type = bt
                self.delivered_records.append({
                    "unit_id": uid,
                    "blood_type": bt,
                    "vehicle": vehicle_id,
                    "time": current_time,
                })

            # Send single ACK to source bank
            self.send(
                receiver=source_bank,
                performative=Performative.ACK,
                payload={
                    "request_id": req_id,
                    "accepted_units": accepted_count,
                    "blood_type": b_type,
                    "vehicle_id": vehicle_id,
                },
                timestamp=current_time,
                conversation_id=req_id,
            )

    def decide(self, current_time: float) -> Any:
        return None

    def act(self, current_time: float) -> None:
        return None

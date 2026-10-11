"""FIPA-ACL inspired agent communication messaging system and centralized MessageBus."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import uuid


class Performative(str, Enum):
    REQUEST = "REQUEST"
    INFORM = "INFORM"
    PROPOSE = "PROPOSE"
    ACCEPT = "ACCEPT"
    REFUSE = "REFUSE"
    DISPATCH = "DISPATCH"
    STATUS_UPDATE = "STATUS_UPDATE"
    BREACH_ALERT = "BREACH_ALERT"
    QUARANTINE = "QUARANTINE"
    BACKUP_REQUEST = "BACKUP_REQUEST"
    DELIVERED = "DELIVERED"
    ACK = "ACK"
    REJECT = "REJECT"


@dataclass
class Message:
    """Inter-agent message adhering to ACL communication principles."""
    sender: str
    receiver: str
    performative: Performative
    timestamp: float
    payload: Dict[str, Any] = field(default_factory=dict)
    conversation_id: Optional[str] = None
    sequence_number: int = 0
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def summary(self) -> str:
        """Return clear, human-readable description of message content without raw dict representations."""
        p = self.payload
        perf = self.performative.value if isinstance(self.performative, Performative) else str(self.performative)

        # 1. Custom text override
        if "text" in p and p["text"]:
            return str(p["text"])

        # 2. Performative-specific formatted summaries
        if perf == Performative.REQUEST.value:
            units = p.get("units") or p.get("units_requested", 1)
            b_type = p.get("blood_type", "RBC")
            urg = p.get("urgency", "Routine")
            reason = p.get("reason", "Clinical need")
            ttn = p.get("time_to_need")
            ttn_str = f", TTN {ttn:.0f} min" if ttn is not None else ""
            return f"Need {units}x {b_type} for {reason} ({urg}{ttn_str})"

        elif perf == Performative.INFORM.value:
            status = p.get("status", "")
            b_type = p.get("blood_type", "")
            b_type_display = b_type.replace("-", "−") if "-" in b_type else b_type
            units = p.get("units_allocated", "")
            veh = p.get("vehicle_id", "")
            eta = p.get("eta_minutes")
            rank = p.get("rank")
            score = p.get("score")

            if status == "APPROVED":
                score_str = f" (score {score:.2f})" if score is not None else ""
                rank_str = f"rank #{rank}" if rank is not None else ""
                eta_str = f", ETA {eta:.0f} min" if eta is not None else ""
                parts = [f"Approved {units}x {b_type_display}"]
                if rank_str:
                    parts.append(f"{rank_str}{score_str}")
                if veh:
                    parts.append(f"vehicle {veh}")
                base = ", ".join(parts)
                if eta_str:
                    base += eta_str
                return base
            elif status == "FULFILLED_RESERVE":
                return "Fulfilled from Reserve Bank"
            elif status == "DEFERRED":
                return "Deferred (re-queued with aging bonus)"
            note = p.get("note") or p.get("reason") or "Status update"
            return f"Inform: {note}"

        elif perf == Performative.DISPATCH.value:
            units = p.get("units_count") or len(p.get("unit_ids", [])) or p.get("units", 1)
            b_type = p.get("blood_type", "")
            b_type_display = b_type.replace("-", "−") if "-" in b_type else b_type
            dest = p.get("destination_hospital", "")
            ids = p.get("unit_ids", [])
            ids_str = f" ({', '.join(ids)})" if ids else ""
            return f"{units}x {b_type_display}{ids_str} → {dest}"

        elif perf == Performative.ACCEPT.value:
            dest = p.get("destination_hospital", "")
            veh = p.get("vehicle_id") or self.sender
            eta = p.get("eta_minutes")
            eta_str = f", ETA {eta:.0f} min" if eta is not None else ""
            return f"Accepted dispatch {veh} → {dest}{eta_str}"

        elif perf == Performative.BACKUP_REQUEST.value:
            units = p.get("units_needed") or p.get("units_count") or 1
            b_type = p.get("blood_type", "")
            hosp = p.get("destination_hospital") or p.get("hospital_id", "")
            ttn = p.get("time_to_need")
            ttn_str = f" (TTN {ttn:.0f} min)" if ttn is not None else ""
            return f"Requesting backup {units}x {b_type} for {hosp}{ttn_str}"

        elif perf == Performative.PROPOSE.value:
            units = p.get("units_count", 1)
            b_type = p.get("blood_type", "")
            veh = p.get("vehicle_id", "")
            eta = p.get("eta_minutes", 0.0)
            return f"Propose backup {units}x {b_type} via {veh}, ETA {eta:.1f} min"

        elif perf == Performative.REFUSE.value:
            reason = p.get("reason", "Stock exhausted across Central and Reserve Banks")
            return f"Refused: {reason}"

        elif perf == Performative.STATUS_UPDATE.value:
            node = p.get("current_node", "")
            temp = p.get("temperature", 4.0)
            eta = p.get("eta_minutes", 0.0)
            route_str = p.get("route_str", "")
            route_part = f" | route {route_str}" if route_str else ""
            return f"At {node} | {temp:.1f} °C | ETA {eta:.0f} min{route_part}"

        elif perf == Performative.BREACH_ALERT.value:
            temp = p.get("temperature")
            temp_str = f" ({temp:.1f} °C)" if temp is not None else ""
            reason = p.get("reason") or f"Cold chain temperature breach detected{temp_str}"
            return f"Breach alert: {reason}"

        elif perf == Performative.QUARANTINE.value:
            note = p.get("note", "Cargo locked due to temperature breach")
            ids = p.get("quarantined_units", [])
            ids_str = f" for [{', '.join(ids)}]" if ids else ""
            return f"Quarantine order: {note}{ids_str}"

        elif perf == Performative.DELIVERED.value:
            units = p.get("units_count") or len(p.get("units", [])) or 1
            b_type = p.get("blood_type", "")
            dest = p.get("destination_hospital") or self.receiver
            temp = p.get("temperature")
            temp_str = f" | Temp at arrival {temp:.1f} °C" if temp is not None else ""
            return f"Delivered {units}x {b_type} to {dest}{temp_str}"

        elif perf == Performative.ACK.value:
            units = p.get("accepted_units", 1)
            b_type = p.get("blood_type", "")
            b_str = f" {b_type}" if b_type else ""
            return f"Verified & accepted {units}x{b_str} into clinical inventory"

        elif perf == Performative.REJECT.value:
            reason = p.get("reason", "Cold-chain violation detected upon arrival")
            return f"Rejected delivery: {reason}"

        return f"{perf} message"

    @property
    def summary_text(self) -> str:
        """Backwards-compatible alias for summary()."""
        return self.summary()


class MessageBus:
    """Synchronous message bus facilitating decoupled agent interactions.

    Logs every message with causal sequence numbering for timeline and audit rendering.
    """

    def __init__(self):
        self.history: List[Message] = []
        self._subscribers: Dict[str, List[Callable[[Message], None]]] = {}
        self._sequence_counter: int = 0

    def reset(self) -> None:
        self.history.clear()
        self._subscribers.clear()
        self._sequence_counter = 0

    def subscribe(self, agent_id: str, callback: Callable[[Message], None]) -> None:
        """Register an agent's inbox handler for direct or broadcast delivery."""
        self._subscribers.setdefault(agent_id, []).append(callback)

    def publish(self, message: Message) -> None:
        """Assign monotonic sequence number and route message to recipient."""
        self._sequence_counter += 1
        message.sequence_number = self._sequence_counter
        self.history.append(message)

        # Direct recipient routing
        if message.receiver in self._subscribers:
            for handler in self._subscribers[message.receiver]:
                handler(message)

        # Broadcast routing if receiver is "BROADCAST" or "*"
        if message.receiver in ("BROADCAST", "*"):
            for agent_id, handlers in self._subscribers.items():
                if agent_id != message.sender:
                    for handler in handlers:
                        handler(message)

    def get_messages(self, limit: Optional[int] = None) -> List[Message]:
        # Always return sorted by (timestamp, sequence_number) for causal ordering
        ordered = sorted(self.history, key=lambda m: (m.timestamp, m.sequence_number))
        if limit is None:
            return ordered
        return ordered[-limit:]

    def get_timeline_records(self) -> List[Dict[str, Any]]:
        """Return structured records suited for Plotly timeline charts and UI tables."""
        records = []
        ordered = sorted(self.history, key=lambda m: (m.timestamp, m.sequence_number))
        for msg in ordered:
            records.append({
                "sequence_number": msg.sequence_number,
                "message_id": msg.message_id,
                "timestamp": msg.timestamp,
                "sender": msg.sender,
                "receiver": msg.receiver,
                "performative": msg.performative.value if isinstance(msg.performative, Performative) else str(msg.performative),
                "summary": msg.summary(),
                "conversation_id": msg.conversation_id or "",
                "payload": msg.payload,
            })
        return records

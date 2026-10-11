"""Base agent architecture following Perceive-Decide-Act paradigm."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from src.messaging import Message, MessageBus, Performative


class BaseAgent(ABC):
    """Abstract base class for autonomous agents communicating strictly via MessageBus."""

    def __init__(self, agent_id: str, name: str, bus: MessageBus):
        self.agent_id = agent_id
        self.name = name
        self.bus = bus
        self.inbox: List[Message] = []
        self.bus.subscribe(self.agent_id, self.receive)

    def receive(self, message: Message) -> None:
        """Receive message from bus and enqueue into local inbox."""
        self.inbox.append(message)

    def send(
        self,
        receiver: str,
        performative: Performative,
        payload: Dict[str, Any],
        timestamp: float,
        conversation_id: Optional[str] = None,
    ) -> Message:
        """Construct and publish a message to the MessageBus."""
        msg = Message(
            sender=self.agent_id,
            receiver=receiver,
            performative=performative,
            timestamp=timestamp,
            payload=payload,
            conversation_id=conversation_id,
        )
        self.bus.publish(msg)
        return msg

    def clear_inbox(self) -> None:
        self.inbox.clear()

    @abstractmethod
    def perceive(self, current_time: float) -> None:
        """Perceive environment state and read unhandled inbox messages."""
        pass

    @abstractmethod
    def decide(self, current_time: float) -> Any:
        """Deliberate and formulate decisions based on internal state and perceptions."""
        pass

    @abstractmethod
    def act(self, current_time: float) -> None:
        """Execute selected actions and emit communicative performatives."""
        pass

    def step(self, current_time: float) -> None:
        """Full agent cycle execution for the current simulation tick."""
        self.perceive(current_time)
        self.decide(current_time)
        self.act(current_time)

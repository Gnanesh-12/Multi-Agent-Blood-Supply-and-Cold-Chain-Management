"""Blood unit representations, compatibility rules, and inventory management."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional
import uuid


class BloodType(str, Enum):
    O_NEG = "O-"
    O_POS = "O+"
    A_NEG = "A-"
    A_POS = "A+"
    B_NEG = "B-"
    B_POS = "B+"
    AB_NEG = "AB-"
    AB_POS = "AB+"


# Clinically accurate Red Blood Cell (RBC) compatibility table:
# Key: Recipient Blood Type -> Value: Ordered list of acceptable Donor Blood Types (exact match first)
RBC_COMPATIBILITY: Dict[str, List[str]] = {
    "O-": ["O-"],
    "O+": ["O+", "O-"],
    "A-": ["A-", "O-"],
    "A+": ["A+", "A-", "O+", "O-"],
    "B-": ["B-", "O-"],
    "B+": ["B+", "B-", "O+", "O-"],
    "AB-": ["AB-", "A-", "B-", "O-"],
    "AB+": ["AB+", "AB-", "A+", "A-", "B+", "B-", "O+", "O-"],
}


class BloodUnitStatus(str, Enum):
    IN_STOCK = "IN_STOCK"
    RESERVED = "RESERVED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    QUARANTINED = "QUARANTINED"
    EXPIRED = "EXPIRED"


@dataclass
class BloodUnit:
    """Represents an individual physical bag/unit of blood with cold-chain tracking."""
    unit_id: str
    blood_type: str
    expiry_time: float               # Expiry time in simulation minutes
    status: BloodUnitStatus = BloodUnitStatus.IN_STOCK
    source_bank: str = "CBB"
    temperature_readings: List[float] = field(default_factory=list)
    quarantine_reason: Optional[str] = None
    allocated_to_request_id: Optional[str] = None

    def is_expired(self, current_time: float) -> bool:
        """Check whether unit has surpassed expiration threshold."""
        return current_time >= self.expiry_time

    def is_viable(self, current_time: float) -> bool:
        """Viable if not expired and not quarantined."""
        return (
            self.status in (BloodUnitStatus.IN_STOCK, BloodUnitStatus.RESERVED, BloodUnitStatus.IN_TRANSIT)
            and not self.is_expired(current_time)
            and self.status != BloodUnitStatus.QUARANTINED
        )


def sort_units_fefo(units: List[BloodUnit]) -> List[BloodUnit]:
    """Sort blood units according to First-Expiry-First-Out (FEFO) order."""
    return sorted(units, key=lambda u: u.expiry_time)


def get_compatible_donor_types(recipient_type: str) -> List[str]:
    """Return ordered compatible donor blood types for recipient (exact match first)."""
    return RBC_COMPATIBILITY.get(recipient_type, [recipient_type])


def is_compatible(donor_type: str, recipient_type: str) -> bool:
    """Check if donor blood type is compatible with recipient."""
    allowed = RBC_COMPATIBILITY.get(recipient_type, [])
    return donor_type in allowed

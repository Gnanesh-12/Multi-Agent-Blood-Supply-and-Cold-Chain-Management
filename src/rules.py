"""Horn-clause safety rule engine for cold-chain temperature breaches and product expiry."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Callable
from src.blood import BloodUnit, BloodUnitStatus


class RuleId(str, Enum):
    TEMP_BREACH_HIGH = "RULE_TEMP_BREACH_HIGH"
    TEMP_BREACH_LOW = "RULE_TEMP_BREACH_LOW"
    UNIT_EXPIRED = "RULE_UNIT_EXPIRED"


@dataclass
class RuleFiring:
    """Record of a triggered safety rule firing."""
    rule_id: str
    sim_time: float
    target_id: str             # Vehicle ID or Unit ID
    condition_description: str # Evaluated antecedent
    action_taken: str          # Executed consequent
    severity: str = "CRITICAL" # "CRITICAL" | "WARNING"


class SafetyRuleEngine:
    """Forward-chaining rule engine enforcing medical safety constraints.

    Horn Clauses:
      1. Antecedent: temp > T_MAX for >= D consecutive readings
         Consequent: quarantine(unit) ∧ send(BREACH_ALERT) ∧ trigger(backup_search)
      2. Antecedent: temp < T_MIN for >= D consecutive readings
         Consequent: quarantine(unit) ∧ send(BREACH_ALERT) ∧ trigger(backup_search)
      3. Antecedent: expiry_time <= current_time
         Consequent: mark_status(unit, EXPIRED) ∧ log_waste(unit)
    """

    def __init__(
        self,
        t_min: float = 1.0,
        t_max: float = 10.0,
        d_consecutive: int = 3,
    ):
        self.t_min = float(t_min)
        self.t_max = float(t_max)
        self.d_consecutive = int(d_consecutive)
        self.firings_log: List[RuleFiring] = []
        # Track consecutive readings out of bounds per vehicle: {vehicle_id: count}
        self.vehicle_breach_counts: Dict[str, int] = {}
        # Track whether a breach has already fired for a vehicle to prevent repeated firing
        self.vehicle_breach_fired: Dict[str, bool] = {}

    def reset(self) -> None:
        self.firings_log.clear()
        self.vehicle_breach_counts.clear()
        self.vehicle_breach_fired.clear()

    def update_thresholds(self, t_min: float, t_max: float, d_consecutive: int) -> None:
        self.t_min = float(t_min)
        self.t_max = float(t_max)
        self.d_consecutive = int(d_consecutive)

    def evaluate_temperature_reading(
        self,
        vehicle_id: str,
        current_temp: float,
        cargo_units: List[BloodUnit],
        sim_time: float,
    ) -> Tuple[bool, Optional[RuleFiring]]:
        """Evaluate cold-chain thermal reading for a vehicle in transit.

        Returns (is_breached, optional_rule_firing).
        """
        if self.vehicle_breach_fired.get(vehicle_id, False):
            # Already quarantined
            return False, None

        is_out_of_bounds = (current_temp < self.t_min) or (current_temp > self.t_max)

        if is_out_of_bounds:
            self.vehicle_breach_counts[vehicle_id] = self.vehicle_breach_counts.get(vehicle_id, 0) + 1
        else:
            # Temperature recovered within safe range: reset consecutive counter
            self.vehicle_breach_counts[vehicle_id] = 0

        current_count = self.vehicle_breach_counts.get(vehicle_id, 0)

        if current_count >= self.d_consecutive:
            # Rule fires!
            rule_type = (
                RuleId.TEMP_BREACH_HIGH if current_temp > self.t_max else RuleId.TEMP_BREACH_LOW
            )
            bound_text = f">{self.t_max}°C" if current_temp > self.t_max else f"<{self.t_min}°C"

            condition = (
                f"Reading {current_temp:.1f}°C {bound_text} for {current_count} consecutive readings "
                f"(Threshold: {self.d_consecutive})"
            )
            action = (
                f"Quarantined {len(cargo_units)} units in vehicle {vehicle_id}; "
                f"issued BREACH_ALERT; triggered backup sourcing."
            )

            firing = RuleFiring(
                rule_id=rule_type.value,
                sim_time=sim_time,
                target_id=vehicle_id,
                condition_description=condition,
                action_taken=action,
                severity="CRITICAL",
            )
            self.firings_log.append(firing)
            self.vehicle_breach_fired[vehicle_id] = True

            # Execute consequent: quarantine units
            for u in cargo_units:
                u.status = BloodUnitStatus.QUARANTINED
                u.quarantine_reason = condition

            return True, firing

        return False, None

    def evaluate_expiry(
        self,
        units: List[BloodUnit],
        sim_time: float,
        location_label: str = "Storage",
    ) -> List[RuleFiring]:
        """Evaluate product shelf-life expiry rule for given blood units."""
        new_firings: List[RuleFiring] = []
        for unit in units:
            if unit.status != BloodUnitStatus.EXPIRED and unit.is_expired(sim_time):
                unit.status = BloodUnitStatus.EXPIRED
                condition = f"Sim time {sim_time:.1f} >= Unit expiry time {unit.expiry_time:.1f}"
                action = f"Marked blood unit {unit.unit_id} ({unit.blood_type}) as EXPIRED in {location_label}"
                firing = RuleFiring(
                    rule_id=RuleId.UNIT_EXPIRED.value,
                    sim_time=sim_time,
                    target_id=unit.unit_id,
                    condition_description=condition,
                    action_taken=action,
                    severity="WARNING",
                )
                self.firings_log.append(firing)
                new_firings.append(firing)

        return new_firings

"""Urgency scoring, FEFO selection, compatible substitution, and greedy priority allocation."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from src.blood import (
    BloodUnit,
    BloodUnitStatus,
    get_compatible_donor_types,
    sort_units_fefo,
)


class AllocationOutcome(str, Enum):
    FULFILLED = "FULFILLED"
    PARTIAL = "PARTIAL"
    REFUSED = "REFUSED"
    DEFERRED = "DEFERRED"


@dataclass
class BloodRequirement:
    """Represents a hospital's need for blood units."""
    request_id: str
    hospital_id: str
    hospital_name: str
    blood_type: str
    units_requested: int
    urgency_level: str               # "Emergency", "Urgent", "Routine"
    time_to_need_minutes: float      # e.g., 20.0
    reason: str                      # "Surgery", "Trauma", "Transfusion", "Other"
    created_at_sim_time: float = 0.0
    current_hospital_stock: int = 0
    target_hospital_stock: int = 5


@dataclass
class ScoreBreakdown:
    urgency_term: float
    time_to_need_term: float
    deficit_term: float
    rarity_term: float
    waiting_term: float
    total_score: float


@dataclass
class AllocationDecision:
    rank: int
    request_id: str
    hospital_id: str
    hospital_name: str
    blood_type_requested: str
    units_requested: int
    units_allocated: int
    substituted_type: Optional[str]
    score_breakdown: ScoreBreakdown
    outcome: AllocationOutcome
    reason: str
    allocated_units: List[BloodUnit] = field(default_factory=list)


def calculate_urgency_score(
    req: BloodRequirement,
    current_sim_time: float,
    weights: Dict[str, float],
    rarity_scores: Dict[str, float],
) -> ScoreBreakdown:
    """Calculate multi-criteria urgency score:

    Score = w1*urgency + w2*(1/time_to_need) + w3*deficit_ratio + w4*rarity + w5*waiting_time
    """
    w1 = float(weights.get("w1_urgency_level", 0.35))
    w2 = float(weights.get("w2_time_to_need", 0.25))
    w3 = float(weights.get("w3_deficit_ratio", 0.15))
    w4 = float(weights.get("w4_blood_type_rarity", 0.15))
    w5 = float(weights.get("w5_waiting_time", 0.10))

    # 1. Urgency Level numerical mapping
    urgency_map = {"Emergency": 3.0, "Urgent": 2.0, "Routine": 1.0}
    raw_urgency = urgency_map.get(req.urgency_level, 1.0)
    term1 = w1 * raw_urgency

    # 2. Time until surgery/need: inverse relationship
    # Normalized by scaling 60 / minutes so ~1 hour = 1.0, 15 min = 4.0
    clamped_time = max(5.0, float(req.time_to_need_minutes))
    inv_time_scaled = (60.0 / clamped_time)
    term2 = w2 * inv_time_scaled

    # 3. Hospital Deficit Ratio: (Target - Current) / Target
    target = max(1, req.target_hospital_stock)
    current = max(0, req.current_hospital_stock)
    deficit_ratio = max(0.0, (target - current) / target) * 3.0
    term3 = w3 * deficit_ratio

    # 4. Blood type rarity
    rarity = float(rarity_scores.get(req.blood_type, 0.4)) * 3.0
    term4 = w4 * rarity

    # 5. Aging / Waiting time to prevent starvation
    waiting_mins = max(0.0, current_sim_time - req.created_at_sim_time)
    # 0.1 score boost per 10 minutes waited
    aging_factor = waiting_mins * 0.1
    term5 = w5 * aging_factor

    total = term1 + term2 + term3 + term4 + term5

    return ScoreBreakdown(
        urgency_term=round(term1, 3),
        time_to_need_term=round(term2, 3),
        deficit_term=round(term3, 3),
        rarity_term=round(term4, 3),
        waiting_term=round(term5, 3),
        total_score=round(total, 3),
    )


def greedy_priority_allocation(
    requests: List[BloodRequirement],
    available_units: List[BloodUnit],
    current_sim_time: float,
    weights: Dict[str, float],
    rarity_scores: Dict[str, float],
) -> Tuple[List[AllocationDecision], List[BloodUnit]]:
    """Greedy priority allocation:

    1. Score all requests using multi-criteria formula.
    2. Rank requests in descending score order using heapq.
    3. Allocate available blood units closest to expiry first (FEFO).
    4. If exact match runs out, search medically compatible donor types.
    5. Record detailed decision metrics, outcomes, and reasons.
    """
    if not requests:
        return [], available_units

    # Score requests and push into max-heap (negate total_score)
    scored_heap: List[Tuple[float, int, BloodRequirement, ScoreBreakdown]] = []
    for idx, req in enumerate(requests):
        breakdown = calculate_urgency_score(req, current_sim_time, weights, rarity_scores)
        heapq.heappush(scored_heap, (-breakdown.total_score, idx, req, breakdown))

    # Maintain pool of available units partitioned by blood type
    units_by_type: Dict[str, List[BloodUnit]] = {}
    for unit in available_units:
        if unit.is_viable(current_sim_time) and unit.status == BloodUnitStatus.IN_STOCK:
            units_by_type.setdefault(unit.blood_type, []).append(unit)

    # Sort each type's bucket by FEFO (earliest expiry first)
    for b_type in units_by_type:
        units_by_type[b_type] = sort_units_fefo(units_by_type[b_type])

    decisions: List[AllocationDecision] = []
    remaining_pool: List[BloodUnit] = []
    rank = 1

    while scored_heap:
        _, _, req, breakdown = heapq.heappop(scored_heap)
        needed = req.units_requested
        allocated: List[BloodUnit] = []
        substituted_type_used: Optional[str] = None
        exact_type = req.blood_type

        # 1. Try exact match first (FEFO)
        if exact_type in units_by_type and units_by_type[exact_type]:
            available = units_by_type[exact_type]
            take_count = min(needed, len(available))
            allocated.extend(available[:take_count])
            units_by_type[exact_type] = available[take_count:]

        # 2. If still needed, search compatible types
        if len(allocated) < needed:
            compatible_types = get_compatible_donor_types(exact_type)
            for c_type in compatible_types:
                if c_type == exact_type:
                    continue  # already exhausted exact
                if c_type in units_by_type and units_by_type[c_type]:
                    needed_now = needed - len(allocated)
                    avail_c = units_by_type[c_type]
                    take_count = min(needed_now, len(avail_c))
                    allocated.extend(avail_c[:take_count])
                    units_by_type[c_type] = avail_c[take_count:]
                    substituted_type_used = c_type
                    if len(allocated) >= needed:
                        break

        # Mark allocated units
        for u in allocated:
            u.status = BloodUnitStatus.RESERVED
            u.allocated_to_request_id = req.request_id

        # Determine outcome and explanation
        units_count = len(allocated)
        if units_count == needed:
            outcome = AllocationOutcome.FULFILLED
            if substituted_type_used:
                reason = f"Full allocation ({units_count}u). Partially/fully substituted with compatible {substituted_type_used} (FEFO)."
            else:
                reason = f"Full allocation ({units_count}u) via exact type {exact_type} (FEFO)."
        elif units_count > 0:
            outcome = AllocationOutcome.PARTIAL
            shortfall = needed - units_count
            if substituted_type_used:
                reason = f"Partial allocation: {units_count}/{needed}u allocated with compatible {substituted_type_used}. Shortfall: {shortfall}u."
            else:
                reason = f"Partial allocation: {units_count}/{needed}u allocated. Insufficient stock across compatible types. Shortfall: {shortfall}u."
        else:
            outcome = AllocationOutcome.REFUSED
            reason = f"Stock exhausted for {exact_type} and all compatible donor blood types."

        decision = AllocationDecision(
            rank=rank,
            request_id=req.request_id,
            hospital_id=req.hospital_id,
            hospital_name=req.hospital_name,
            blood_type_requested=exact_type,
            units_requested=needed,
            units_allocated=units_count,
            substituted_type=substituted_type_used,
            score_breakdown=breakdown,
            outcome=outcome,
            reason=reason,
            allocated_units=allocated,
        )
        decisions.append(decision)
        rank += 1

    # Reconstruct remaining unallocated units
    for b_type, u_list in units_by_type.items():
        remaining_pool.extend(u_list)

    return decisions, remaining_pool

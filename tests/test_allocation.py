"""Tests for priority allocation: score ordering, aging, FEFO, and compatible substitutions."""

import pytest
from src.blood import (
    BloodUnit,
    BloodUnitStatus,
    get_compatible_donor_types,
    is_compatible,
    sort_units_fefo,
)
from src.planning.allocation import (
    AllocationOutcome,
    BloodRequirement,
    calculate_urgency_score,
    greedy_priority_allocation,
)


def test_compatibility_table():
    """Verify medical accuracy of RBC compatibility matrix."""
    # O- can only receive O-
    assert get_compatible_donor_types("O-") == ["O-"]
    # AB+ can receive any donor type (universal recipient)
    ab_pos_donors = get_compatible_donor_types("AB+")
    assert set(ab_pos_donors) == {"O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"}
    # A- can receive A- and O-
    assert set(get_compatible_donor_types("A-")) == {"A-", "O-"}
    assert is_compatible("O-", "A-") is True
    assert is_compatible("A+", "A-") is False


def test_fefo_sorting():
    """Verify First-Expiry-First-Out sorts units strictly by expiration timestamp."""
    u1 = BloodUnit(unit_id="U1", blood_type="O+", expiry_time=300.0)
    u2 = BloodUnit(unit_id="U2", blood_type="O+", expiry_time=120.0)
    u3 = BloodUnit(unit_id="U3", blood_type="O+", expiry_time=240.0)

    sorted_units = sort_units_fefo([u1, u2, u3])
    assert [u.unit_id for u in sorted_units] == ["U2", "U3", "U1"]


def test_contention_allocation_score_order():
    """With limited O-, two competing requests are allocated in score order."""
    weights = {
        "w1_urgency_level": 0.35,
        "w2_time_to_need": 0.25,
        "w3_deficit_ratio": 0.15,
        "w4_blood_type_rarity": 0.15,
        "w5_waiting_time": 0.10,
    }
    rarity = {"O-": 1.0, "A+": 0.35}

    # Only 2 units of O- in stock
    units = [
        BloodUnit(unit_id="U-O1", blood_type="O-", expiry_time=200.0),
        BloodUnit(unit_id="U-O2", blood_type="O-", expiry_time=250.0),
    ]

    req_emergency = BloodRequirement(
        request_id="REQ-EMERGENCY",
        hospital_id="H1",
        hospital_name="City General",
        blood_type="O-",
        units_requested=2,
        urgency_level="Emergency",
        time_to_need_minutes=15.0,
        reason="Trauma Hemorrhage",
        created_at_sim_time=0.0,
        current_hospital_stock=0,
        target_hospital_stock=5,
    )

    req_routine = BloodRequirement(
        request_id="REQ-ROUTINE",
        hospital_id="H2",
        hospital_name="St. Mary's",
        blood_type="O-",
        units_requested=2,
        urgency_level="Routine",
        time_to_need_minutes=120.0,
        reason="Scheduled Transfusion",
        created_at_sim_time=0.0,
        current_hospital_stock=2,
        target_hospital_stock=4,
    )

    decisions, remaining = greedy_priority_allocation(
        requests=[req_routine, req_emergency],
        available_units=units,
        current_sim_time=0.0,
        weights=weights,
        rarity_scores=rarity,
    )

    assert len(decisions) == 2
    # Rank 1 must be emergency
    assert decisions[0].request_id == "REQ-EMERGENCY"
    assert decisions[0].outcome == AllocationOutcome.FULFILLED
    assert decisions[0].units_allocated == 2

    # Rank 2 routine is refused because O- was exhausted
    assert decisions[1].request_id == "REQ-ROUTINE"
    assert decisions[1].outcome == AllocationOutcome.REFUSED
    assert decisions[1].units_allocated == 0


def test_aging_prevents_starvation():
    """Verify that as waiting_time accumulates, the aging term boosts score."""
    weights = {"w1_urgency_level": 0.35, "w2_time_to_need": 0.25, "w3_deficit_ratio": 0.15, "w4_blood_type_rarity": 0.15, "w5_waiting_time": 0.20}
    rarity = {"A+": 0.35}

    req = BloodRequirement(
        request_id="REQ-1",
        hospital_id="H1",
        hospital_name="City General",
        blood_type="A+",
        units_requested=1,
        urgency_level="Routine",
        time_to_need_minutes=60.0,
        reason="Routine",
        created_at_sim_time=0.0,
    )

    score_fresh = calculate_urgency_score(req, current_sim_time=0.0, weights=weights, rarity_scores=rarity)
    score_aged = calculate_urgency_score(req, current_sim_time=60.0, weights=weights, rarity_scores=rarity)

    assert score_aged.total_score > score_fresh.total_score
    assert score_aged.waiting_term > score_fresh.waiting_term


def test_compatible_substitution_when_exact_short():
    """Verify that when exact type is short, compatible substitution satisfies demand."""
    weights = {"w1_urgency_level": 0.35, "w2_time_to_need": 0.25, "w3_deficit_ratio": 0.15, "w4_blood_type_rarity": 0.15, "w5_waiting_time": 0.10}
    rarity = {"A-": 0.70, "O-": 1.0}

    # Only 1 unit of A- in stock, but 2 units of O- available
    units = [
        BloodUnit(unit_id="U-A1", blood_type="A-", expiry_time=150.0),
        BloodUnit(unit_id="U-O1", blood_type="O-", expiry_time=200.0),
        BloodUnit(unit_id="U-O2", blood_type="O-", expiry_time=220.0),
    ]

    req = BloodRequirement(
        request_id="REQ-SUB",
        hospital_id="H1",
        hospital_name="City General",
        blood_type="A-",
        units_requested=2,
        urgency_level="Urgent",
        time_to_need_minutes=30.0,
        reason="Urgent surgery",
        created_at_sim_time=0.0,
    )

    decisions, remaining = greedy_priority_allocation(
        requests=[req],
        available_units=units,
        current_sim_time=0.0,
        weights=weights,
        rarity_scores=rarity,
    )

    assert len(decisions) == 1
    d = decisions[0]
    assert d.outcome == AllocationOutcome.FULFILLED
    assert d.units_allocated == 2
    assert d.substituted_type == "O-"
    assert any(u.blood_type == "O-" for u in d.allocated_units)

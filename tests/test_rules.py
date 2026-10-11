"""Tests for Horn-clause SafetyRuleEngine: temperature breach threshold and expiry evaluation."""

import pytest
from src.blood import BloodUnit, BloodUnitStatus
from src.rules import RuleFiring, RuleId, SafetyRuleEngine


def test_temperature_breach_high_consecutive_readings():
    """Breach rule fires strictly after D consecutive readings exceeding T_MAX."""
    engine = SafetyRuleEngine(t_min=1.0, t_max=10.0, d_consecutive=3)
    cargo = [BloodUnit(unit_id="U1", blood_type="O+", expiry_time=300.0)]

    # Reading 1: 11.5°C (out of range, count=1)
    breached, firing = engine.evaluate_temperature_reading("VAN-01", 11.5, cargo, sim_time=1.0)
    assert not breached
    assert firing is None
    assert cargo[0].status == BloodUnitStatus.IN_STOCK

    # Reading 2: 12.0°C (out of range, count=2)
    breached, firing = engine.evaluate_temperature_reading("VAN-01", 12.0, cargo, sim_time=2.0)
    assert not breached
    assert firing is None

    # Reading 3: 12.5°C (out of range, count=3 == D -> FIRES!)
    breached, firing = engine.evaluate_temperature_reading("VAN-01", 12.5, cargo, sim_time=3.0)
    assert breached
    assert firing is not None
    assert firing.rule_id == RuleId.TEMP_BREACH_HIGH.value
    assert cargo[0].status == BloodUnitStatus.QUARANTINED
    assert "quarantined" in cargo[0].quarantine_reason.lower() or "reading" in cargo[0].quarantine_reason.lower()


def test_temperature_breach_low_consecutive_readings():
    """Breach rule fires strictly after D consecutive readings below T_MIN (freezing failure)."""
    engine = SafetyRuleEngine(t_min=1.0, t_max=10.0, d_consecutive=3)
    cargo = [BloodUnit(unit_id="U2", blood_type="A-", expiry_time=300.0)]

    # 3 consecutive readings < 1.0°C
    engine.evaluate_temperature_reading("VAN-02", 0.5, cargo, sim_time=1.0)
    engine.evaluate_temperature_reading("VAN-02", -0.2, cargo, sim_time=2.0)
    breached, firing = engine.evaluate_temperature_reading("VAN-02", -1.0, cargo, sim_time=3.0)

    assert breached
    assert firing.rule_id == RuleId.TEMP_BREACH_LOW.value
    assert cargo[0].status == BloodUnitStatus.QUARANTINED


def test_temperature_intermittent_recovery_resets_counter():
    """Intermittent reading returning to safe band [T_MIN, T_MAX] resets consecutive counter."""
    engine = SafetyRuleEngine(t_min=1.0, t_max=10.0, d_consecutive=3)
    cargo = [BloodUnit(unit_id="U3", blood_type="B+", expiry_time=300.0)]

    # 2 readings hot
    engine.evaluate_temperature_reading("VAN-03", 11.0, cargo, sim_time=1.0)
    engine.evaluate_temperature_reading("VAN-03", 11.2, cargo, sim_time=2.0)

    # 1 reading normal recovers within bounds (e.g. 5.0°C)
    engine.evaluate_temperature_reading("VAN-03", 5.0, cargo, sim_time=3.0)
    assert engine.vehicle_breach_counts.get("VAN-03") == 0

    # Another hot reading (count=1, should NOT fire)
    breached, firing = engine.evaluate_temperature_reading("VAN-03", 11.5, cargo, sim_time=4.0)
    assert not breached
    assert cargo[0].status == BloodUnitStatus.IN_STOCK


def test_inventory_expiry_rule():
    """Verify rule engine marks blood units expired when simulation time reaches expiry."""
    engine = SafetyRuleEngine()
    units = [
        BloodUnit(unit_id="U-VALID", blood_type="O+", expiry_time=120.0),
        BloodUnit(unit_id="U-EXPIRED", blood_type="O+", expiry_time=50.0),
    ]

    firings = engine.evaluate_expiry(units, sim_time=60.0)
    assert len(firings) == 1
    assert firings[0].target_id == "U-EXPIRED"
    assert units[1].status == BloodUnitStatus.EXPIRED
    assert units[0].status == BloodUnitStatus.IN_STOCK

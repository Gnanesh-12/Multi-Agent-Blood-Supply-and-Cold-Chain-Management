"""Integration tests for end-to-end multi-agent execution, breach backup recovery, and determinism."""

from pathlib import Path
import pytest
from src.simulation import SimulationEngine

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "city.yaml"


def test_seed_determinism():
    """Verify that same random seed produces identical simulation behavior."""
    engine1 = SimulationEngine(CONFIG_PATH, random_seed=42)
    engine1.load_preset_scenario("1. Single Routine Request")
    engine1.run_allocation()
    engine1.run_until_idle(max_steps=20)

    engine2 = SimulationEngine(CONFIG_PATH, random_seed=42)
    engine2.load_preset_scenario("1. Single Routine Request")
    engine2.run_allocation()
    engine2.run_until_idle(max_steps=20)

    # Compare message counts and timestamps
    assert len(engine1.bus.history) == len(engine2.bus.history)
    for m1, m2 in zip(engine1.bus.history, engine2.bus.history):
        assert m1.performative == m2.performative
        assert m1.sender == m2.sender
        assert m1.receiver == m2.receiver
        assert m1.timestamp == pytest.approx(m2.timestamp, abs=1e-3)


def test_end_to_end_breach_and_backup_recovery():
    """Verify end-to-end breach scenario:

    1. Initial delivery launched from CBB.
    2. Temperature breach occurs mid-transit.
    3. Unit is quarantined; BREACH_ALERT triggers backup sourcing.
    4. Backup unit dispatched from Reserve Bank.
    5. Replacement unit successfully delivered to hospital.
    """
    engine = SimulationEngine(CONFIG_PATH, random_seed=42)
    engine.load_preset_scenario("4. Temperature Breach Mid-Delivery -> Backup from Reserve")

    # Step until breach triggers and backup completes
    engine.run_until_idle(max_steps=40)

    # Verify at least one breach firing occurred
    breach_firings = [f for f in engine.rule_engine.firings_log if "BREACH" in f.rule_id]
    assert len(breach_firings) >= 1, "Expected at least one cold-chain temperature breach firing"

    # Verify hospital received delivery
    h4 = engine.hospitals["H4"]
    assert len(h4.delivered_records) >= 1, "Hospital H4 should have received the backup replacement delivery"
    assert len(h4.rejected_records) >= 1 or any(dev.is_quarantined for dev in engine.delivery_agents.values())


def test_preset_scenarios_execute():
    """Verify that all predefined scenarios load and step cleanly without raising exceptions."""
    scenarios = [
        "1. Single Routine Request",
        "2. Two Hospitals Competing for Scarce O-",
        "3. Mass-Casualty Incident (4 Hospitals)",
        "4. Temperature Breach Mid-Delivery -> Backup from Reserve",
        "5. Traffic Jam (A* Dynamic Re-routing)",
        "6. Stockout -> Compatible Substitution",
    ]

    for sc_name in scenarios:
        engine = SimulationEngine(CONFIG_PATH, random_seed=99)
        engine.load_preset_scenario(sc_name)
        if sc_name != "4. Temperature Breach Mid-Delivery -> Backup from Reserve":
            engine.run_allocation()
        engine.run_until_idle(max_steps=15)
        metrics = engine.get_summary_metrics()
        assert metrics["total_messages"] > 0


def test_two_hospitals_o_negative_message_flow():
    """Verify exact FIPA-ACL negotiation and message order for two-hospital O- contention scenario:

    H1 REQUEST -> H3 REQUEST -> CBB INFORM(H1) -> CBB DISPATCH(VAN) -> VAN ACCEPT
    -> CBB BACKUP_REQUEST(Reserve) -> Reserve PROPOSE/REFUSE -> ... -> VAN DELIVERED -> H1 ACK
    """
    from src.messaging import Performative

    engine = SimulationEngine(CONFIG_PATH, random_seed=42)
    engine.load_preset_scenario("2. Two Hospitals Competing for Scarce O-")
    engine.run_allocation()
    engine.run_until_idle(max_steps=25)

    all_msgs = engine.bus.get_messages()
    assert len(all_msgs) >= 8

    # 1. H1 REQUEST
    assert all_msgs[0].sender == "H1"
    assert all_msgs[0].receiver == "CBB"
    assert all_msgs[0].performative == Performative.REQUEST
    assert all_msgs[0].conversation_id is not None

    # 2. H3 REQUEST
    assert all_msgs[1].sender == "H3"
    assert all_msgs[1].receiver == "CBB"
    assert all_msgs[1].performative == Performative.REQUEST
    assert all_msgs[1].conversation_id is not None

    # 3. CBB INFORM(H1)
    assert all_msgs[2].sender == "CBB"
    assert all_msgs[2].receiver == "H1"
    assert all_msgs[2].performative == Performative.INFORM
    assert "Approved 2x" in all_msgs[2].summary()

    # 4. CBB DISPATCH(VAN)
    assert all_msgs[3].sender == "CBB"
    assert all_msgs[3].receiver.startswith("VAN")
    assert all_msgs[3].performative == Performative.DISPATCH
    assert "→ H1" in all_msgs[3].summary()

    # 5. VAN ACCEPT
    van_id = all_msgs[3].receiver
    assert all_msgs[4].sender == van_id
    assert all_msgs[4].receiver == "CBB"
    assert all_msgs[4].performative == Performative.ACCEPT

    # 6. CBB BACKUP_REQUEST(Reserve)
    assert all_msgs[5].sender == "CBB"
    assert all_msgs[5].receiver == "RBB"
    assert all_msgs[5].performative == Performative.BACKUP_REQUEST

    # 7. Reserve PROPOSE/REFUSE
    assert all_msgs[6].sender == "RBB"
    assert all_msgs[6].receiver == "CBB"
    assert all_msgs[6].performative in (Performative.REFUSE, Performative.PROPOSE)

    # Filter non-status updates to verify macro sequence
    macro_msgs = [m for m in all_msgs if m.performative != Performative.STATUS_UPDATE]

    # Verify DELIVERED and ACK at the end of the chain
    deliv_msg = macro_msgs[-2]
    ack_msg = macro_msgs[-1]

    assert deliv_msg.sender == van_id
    assert deliv_msg.receiver == "H1"
    assert deliv_msg.performative == Performative.DELIVERED

    assert ack_msg.sender == "H1"
    assert ack_msg.receiver == "CBB"
    assert ack_msg.performative == Performative.ACK

    # Verify every message carries conversation_id and human-readable summary
    for m in all_msgs:
        assert m.conversation_id, f"Message {m.message_id} missing conversation_id"
        summary = m.summary()
        assert not summary.startswith("{"), f"Summary contains raw dict string: {summary}"
        assert "object at 0x" not in summary, f"Summary contains raw repr: {summary}"

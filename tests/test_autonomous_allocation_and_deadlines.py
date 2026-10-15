"""Tests for autonomous blood bank allocation, contention batching, deadline tracking, and UI formatting."""

from pathlib import Path
import pytest
from src.simulation import SimulationEngine
from src.planning.allocation import AllocationOutcome, BloodRequirement
from src.messaging import Message, MessageBus, Performative
from src.ui.plot_theme import build_message_timeline_figure
from src.ui.components import render_message_log_table, render_allocation_table, render_kpi_strip

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "city.yaml"


def test_autonomous_allocation_on_step():
    """Verify Central Blood Bank allocates pending requests automatically on engine.step() without button press."""
    engine = SimulationEngine(CONFIG_PATH, random_seed=42)
    req = engine.submit_hospital_request(
        hospital_id="H1",
        blood_type="A+",
        units=2,
        urgency_level="Routine",
        time_to_need_minutes=90.0,
        reason="Elective Surgery",
    )

    # Prior to step, request queues in pending_requests
    assert len(engine.central_bank.pending_requests) == 1
    assert len(engine.allocation_history) == 0

    # Advance simulation by 1 minute: bank allocates automatically on first tick
    engine.step(1.0)

    assert len(engine.central_bank.pending_requests) == 0
    assert len(engine.allocation_history) == 1
    decision = engine.allocation_history[0]
    assert decision.request_id == req.request_id
    assert decision.outcome == AllocationOutcome.FULFILLED
    assert decision.units_allocated == 2


def test_paused_contention_allocated_together_on_first_tick():
    """Verify requests queued during the same paused moment are allocated together on the first tick."""
    engine = SimulationEngine(CONFIG_PATH, random_seed=42)
    engine.load_preset_scenario("2. Two Hospitals Competing for Scarce O-")

    # Both H1 and H3 are queued in pending_requests while clock is paused at T=0
    assert len(engine.central_bank.pending_requests) == 2
    assert len(engine.allocation_history) == 0

    # Step once: both requests are allocated together in that same tick
    engine.step(1.0)

    assert len(engine.central_bank.pending_requests) == 0
    assert len(engine.allocation_history) == 2

    # Ranking and contention must show
    d_rank1 = engine.allocation_history[0]
    d_rank2 = engine.allocation_history[1]

    assert d_rank1.rank == 1
    assert d_rank1.hospital_id == "H1"
    assert d_rank1.outcome == AllocationOutcome.FULFILLED
    assert d_rank1.units_allocated == 2

    assert d_rank2.rank == 2
    assert d_rank2.hospital_id == "H3"
    assert d_rank2.outcome == AllocationOutcome.REFUSED
    assert d_rank2.units_allocated == 0


def test_deadline_tracking_on_time():
    """Verify delivery arrival <= deadline is marked 'On time' in DELIVERED message, allocation table, and KPIs."""
    engine = SimulationEngine(CONFIG_PATH, random_seed=42)
    req = engine.submit_hospital_request(
        hospital_id="H1",
        blood_type="A+",
        units=2,
        urgency_level="Routine",
        time_to_need_minutes=90.0,
        reason="Orthopedic",
    )

    expected_deadline = 0.0 + 90.0
    assert req.deadline == expected_deadline
    assert engine.request_tracking[req.request_id]["deadline"] == expected_deadline

    # Run until delivery arrives
    engine.run_until_idle(max_steps=30)

    # 1. Check DELIVERED message
    delivered_msgs = [m for m in engine.bus.history if m.performative == Performative.DELIVERED]
    assert len(delivered_msgs) >= 1
    deliv = delivered_msgs[0]
    assert deliv.payload.get("deadline_status") == "On time"
    assert "On time" in deliv.summary()

    # 2. Check allocation table decision
    decision = engine.allocation_history[0]
    assert decision.deadline_status == "On time"

    # 3. Check KPIs
    metrics = engine.get_summary_metrics()
    assert metrics["on_time_count"] >= 1
    assert metrics["late_count"] == 0
    assert metrics["deadline_kpi_text"] == "On time"


def test_deadline_tracking_late_by_x_min():
    """Verify delivery arrival > deadline is marked 'Late by X min' in DELIVERED message, allocation table, and KPIs."""
    engine = SimulationEngine(CONFIG_PATH, random_seed=42)
    # Travel time to H1 is ~9 min, so a time_to_need of 4.0 min guarantees a late delivery
    req = engine.submit_hospital_request(
        hospital_id="H1",
        blood_type="A+",
        units=2,
        urgency_level="Emergency",
        time_to_need_minutes=4.0,
        reason="Acute Trauma",
    )

    expected_deadline = 0.0 + 4.0
    assert req.deadline == expected_deadline

    engine.run_until_idle(max_steps=30)

    delivered_msgs = [m for m in engine.bus.history if m.performative == Performative.DELIVERED]
    assert len(delivered_msgs) >= 1
    deliv = delivered_msgs[0]

    arrival_time = deliv.payload["delivered_at"]
    assert arrival_time > expected_deadline
    late_diff = round(arrival_time - expected_deadline, 1)
    late_str = f"{int(late_diff)}" if late_diff == int(late_diff) else f"{late_diff}"
    expected_status = f"Late by {late_str} min"

    assert deliv.payload.get("deadline_status") == expected_status
    assert expected_status in deliv.summary()

    # Allocation table decision
    decision = engine.allocation_history[0]
    assert decision.deadline_status == expected_status

    # KPIs
    metrics = engine.get_summary_metrics()
    assert metrics["late_count"] >= 1
    assert metrics["deadline_kpi_text"] == expected_status


def test_timeline_xaxis_starts_at_first_message():
    """Verify sequence timeline figure x-axis range starts at first message timestamp, not at 0."""
    bus = MessageBus()
    msg1 = Message(
        sender="H1",
        receiver="CBB",
        performative=Performative.REQUEST,
        timestamp=7.5,
        payload={"blood_type": "O-", "units": 1},
        conversation_id="C1",
    )
    msg2 = Message(
        sender="CBB",
        receiver="H1",
        performative=Performative.INFORM,
        timestamp=8.0,
        payload={"status": "APPROVED"},
        conversation_id="C1",
    )

    fig = build_message_timeline_figure([msg1, msg2])
    x_range = fig.layout.xaxis.range
    assert x_range[0] == 7.5


def test_log_table_time_column_format(monkeypatch):
    """Verify log table displays 'T+0 min' style short format without leading zeros."""
    rendered_chunks = []
    import src.ui.components as comps
    monkeypatch.setattr(comps, "render_html", lambda h: rendered_chunks.append(h))

    records = [
        {"timestamp": 0.0, "sender": "H1", "receiver": "CBB", "performative": "REQUEST", "summary": "Test 0", "conversation_id": "C1"},
        {"timestamp": 1.0, "sender": "CBB", "receiver": "H1", "performative": "INFORM", "summary": "Test 1", "conversation_id": "C1"},
        {"timestamp": 15.0, "sender": "VAN-01", "receiver": "H1", "performative": "DELIVERED", "summary": "Test 15", "conversation_id": "C1"},
    ]

    render_message_log_table(records)
    html_output = "".join(rendered_chunks)

    assert "T+0 min" in html_output
    assert "T+1 min" in html_output
    assert "T+15 min" in html_output
    # Must not contain old 2-digit zero-padded style like T+00 or T+01
    assert "T+00" not in html_output
    assert "T+01" not in html_output

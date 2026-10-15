"""Unit tests verifying map path visualization, hospital indicators, and delivery status cards."""

import pytest
from src.city import CityNetwork
from src.simulation import SimulationEngine
from src.ui.plot_theme import build_city_map_figure
from src.ui.components import render_delivery_route_status_card


def test_map_visualizes_planned_route_for_pending_request():
    """Verify that when a request is queued at T+0, the map shows the planned path and highlights the hospital."""
    engine = SimulationEngine("config/city.yaml")
    engine.load_preset_scenario("1. Single Routine Request")

    banks_stock = {
        "CBB": engine.central_bank.get_stock_counts(),
        "RBB": engine.reserve_bank.get_stock_counts(),
    }
    pending_list = engine.central_bank.pending_requests

    assert len(pending_list) == 1
    target_hid = pending_list[0].hospital_id

    fig = build_city_map_figure(
        city_net=engine.city_network,
        hospitals=engine.hospitals,
        banks=banks_stock,
        delivery_agents=engine.delivery_agents,
        pending_requests=pending_list,
        allocation_history=engine.allocation_history,
        request_tracking=engine.request_tracking,
    )

    # Verify figure contains planned route trace
    trace_names = [t.name for t in fig.data if hasattr(t, "name") and t.name]
    assert "Planned Route" in trace_names

    # Verify hospital label includes the pending request indicator
    hospital_traces = [t for t in fig.data if getattr(t, "name", None) == "Hospitals"]
    assert len(hospital_traces) == 1
    labels = hospital_traces[0].text
    h1_label = [l for l in labels if target_hid in l][0]
    assert "Need:" in h1_label or "⏳" in h1_label


def test_map_visualizes_active_delivery_route_and_vehicle_destination():
    """Verify that when a vehicle is en route, the map highlights the active route and vehicle destination."""
    engine = SimulationEngine("config/city.yaml")
    engine.load_preset_scenario("1. Single Routine Request")

    # Step 1: Autonomous allocation and dispatch
    engine.step()

    banks_stock = {
        "CBB": engine.central_bank.get_stock_counts(),
        "RBB": engine.reserve_bank.get_stock_counts(),
    }
    pending_list = engine.central_bank.pending_requests

    active_devs = [d for d in engine.delivery_agents.values() if d.is_accepted and not d.is_completed]
    assert len(active_devs) == 1
    dev = active_devs[0]

    fig = build_city_map_figure(
        city_net=engine.city_network,
        hospitals=engine.hospitals,
        banks=banks_stock,
        delivery_agents=engine.delivery_agents,
        pending_requests=pending_list,
        allocation_history=engine.allocation_history,
        request_tracking=engine.request_tracking,
    )

    trace_names = [t.name for t in fig.data if hasattr(t, "name") and t.name]
    assert "Active Route" in trace_names
    assert "Vehicles" in trace_names

    # Check vehicle marker text
    vehicle_trace = [t for t in fig.data if getattr(t, "name", None) == "Vehicles"][0]
    assert any("VAN-01" in lbl and "➔" in lbl for lbl in vehicle_trace.text)

    # Check destination hospital label
    hospital_trace = [t for t in fig.data if getattr(t, "name", None) == "Hospitals"][0]
    dest_label = [l for l in hospital_trace.text if dev.destination_node in l][0]
    assert "Delivering:" in dest_label or "📦" in dest_label


def test_map_visualizes_completed_delivery_trace():
    """Verify that when delivery arrives, a completed delivery trace and delivered indicator are rendered."""
    engine = SimulationEngine("config/city.yaml")
    engine.load_preset_scenario("1. Single Routine Request")

    # Run until delivery completes
    for _ in range(25):
        engine.step()
        if any(d.is_completed for d in engine.delivery_agents.values()):
            break

    banks_stock = {
        "CBB": engine.central_bank.get_stock_counts(),
        "RBB": engine.reserve_bank.get_stock_counts(),
    }

    fig = build_city_map_figure(
        city_net=engine.city_network,
        hospitals=engine.hospitals,
        banks=banks_stock,
        delivery_agents=engine.delivery_agents,
        pending_requests=[],
        allocation_history=engine.allocation_history,
        request_tracking=engine.request_tracking,
    )

    trace_names = [t.name for t in fig.data if hasattr(t, "name") and t.name]
    assert "Completed Route" in trace_names

    hospital_trace = [t for t in fig.data if getattr(t, "name", None) == "Hospitals"][0]
    h1_label = [l for l in hospital_trace.text if "H1" in l][0]
    assert "Delivered" in h1_label or "✓" in h1_label

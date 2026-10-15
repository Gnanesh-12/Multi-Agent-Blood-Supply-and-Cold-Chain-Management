"""Streamlit Web Application: Multi-Agent Blood Supply and Cold-Chain Management.

Presentation layer for multi-agent blood supply and cold-chain operations.
Follows clinical, information-first operational console guidelines.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import streamlit as st

from src.blood import BloodType
from src.simulation import SimulationEngine
from src.ui.components import (
    format_agent_name,
    format_enum_label,
    render_topbar,
    render_kpi_strip,
    render_breach_banner,
    render_incoming_requests,
    render_central_stock_bars,
    render_deliveries_list,
    render_allocation_table,
    render_message_log_table,
    render_delivery_route_status_card,
    status_pill,
)
from src.ui.plot_theme import (
    build_city_map_figure,
    build_temperature_telemetry_figure,
    build_message_timeline_figure,
)

# Page configuration
st.set_page_config(
    page_title="Multi-Agent Blood Supply and Cold-Chain Management",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# Load design tokens and styles from assets/style.css
CSS_PATH = Path(__file__).resolve().parent / "assets" / "style.css"
if CSS_PATH.exists():
    with open(CSS_PATH, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Initialize SimulationEngine in session_state
CONFIG_PATH = Path(__file__).resolve().parent / "config" / "city.yaml"
if "engine" not in st.session_state:
    engine_inst = SimulationEngine(CONFIG_PATH, random_seed=42)
    engine_inst.load_preset_scenario("1. Single Routine Request")
    st.session_state["engine"] = engine_inst

engine: SimulationEngine = st.session_state["engine"]

if "active_modal_hospital" not in st.session_state:
    st.session_state["active_modal_hospital"] = None

if "current_scenario_name" not in st.session_state:
    st.session_state["current_scenario_name"] = "1. Single Routine Request"

if "dismissed_banners" not in st.session_state:
    st.session_state["dismissed_banners"] = set()

if "last_breach_alert" not in st.session_state:
    st.session_state["last_breach_alert"] = None


# Dialog definition for Hospital Blood Requirement Form
def open_requirement_dialog(hospital_id: str) -> None:
    h_agent = engine.hospitals.get(hospital_id)
    if not h_agent:
        return

    @st.dialog(f"New blood request · {h_agent.name}")
    def _render_dialog() -> None:
        st.caption(f"Bed capacity: {h_agent.bed_capacity} beds &middot; Station clock: T+{engine.current_time:.1f} min")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown('<div class="section-label">Blood type</div>', unsafe_allow_html=True)
            chosen_bt = st.pills(
                "Blood type",
                [bt.value.replace("-", "−") for bt in BloodType],
                default="O+",
                label_visibility="collapsed",
            )
            if not chosen_bt:
                chosen_bt = "O+"
            blood_type = chosen_bt.replace("−", "-")

            st.markdown('<div class="section-label">Units required</div>', unsafe_allow_html=True)
            units = st.number_input(
                "Units required",
                min_value=1,
                max_value=20,
                value=2,
                step=1,
                label_visibility="collapsed",
                help="Units of whole red blood cells needed",
            )

            st.markdown('<div class="section-label">Clinical urgency</div>', unsafe_allow_html=True)
            urgency = st.radio(
                "Clinical urgency",
                ["Emergency", "Urgent", "Routine"],
                captions=[
                    "Life-threatening, needed within 30 min",
                    "High risk, required within 60 min",
                    "Elective or scheduled transfusion",
                ],
                index=0,
                label_visibility="collapsed",
            )

        with col_b:
            st.markdown('<div class="section-label">Required within</div>', unsafe_allow_html=True)
            time_to_need = st.number_input(
                "Required within (minutes)",
                min_value=5,
                max_value=240,
                value=25,
                step=5,
                label_visibility="collapsed",
                help="Minutes remaining until surgical procedure begins",
            )

            st.markdown('<div class="section-label">Clinical indication</div>', unsafe_allow_html=True)
            reason = st.selectbox(
                "Clinical indication",
                [
                    "Emergency surgery",
                    "Trauma resuscitation",
                    "Elective surgical support",
                    "Obstetric hemorrhage",
                    "Transfusion medicine",
                    "Other clinical indication",
                ],
                index=0,
                label_visibility="collapsed",
            )

            # Local hospital inventory indication
            curr_stock = h_agent.get_stock(blood_type)
            target_stock = h_agent.get_target(blood_type)
            st.markdown(
                f"""
                <div style="background: var(--surface-2); border: 1px solid var(--line); border-radius: 6px; padding: 10px 12px; margin-top: 18px; font-size: 12px;">
                    <div style="color: var(--ink-2); margin-bottom: 2px;">Local inventory ({blood_type}):</div>
                    <div><b class="mono">{curr_stock}</b> units available &middot; Target: <span class="mono">{target_stock}</span> units</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Inline validation
        units_valid = 1 <= units <= 20
        if not units_valid:
            st.error("Units must be between 1 and 20.")

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        if st.button("Send to Central Bank", type="primary", use_container_width=True, disabled=not units_valid):
            req = engine.submit_hospital_request(
                hospital_id=hospital_id,
                blood_type=blood_type,
                units=int(units),
                urgency_level=urgency,
                time_to_need_minutes=float(time_to_need),
                reason=reason,
            )
            st.session_state["active_modal_hospital"] = None
            st.toast(f"Request {req.request_id} sent to Central Bank")
            st.rerun()

    _render_dialog()


# Check for active breach alerts to generate notifications
breached_vehicles = [
    d for d in engine.delivery_agents.values()
    if d.is_quarantined
    or (
        d.is_accepted
        and not d.is_completed
        and (d.current_temp < float(engine.rule_engine.t_min) or d.current_temp > float(engine.rule_engine.t_max))
    )
]
active_breach_banner_text: Optional[str] = None
if breached_vehicles:
    first_breached = breached_vehicles[0]
    unit_id = first_breached.cargo_units[0].unit_id if first_breached.cargo_units else "U-CBB-ON-01"
    active_breach_banner_text = (
        f"{first_breached.agent_id} temperature out of range ({first_breached.current_temp:.1f} °C) — "
        f"unit {unit_id} quarantined, backup requested from Reserve Bank."
    )
    if st.session_state["last_breach_alert"] != first_breached.agent_id:
        st.session_state["last_breach_alert"] = first_breached.agent_id
        st.toast(active_breach_banner_text)


# ==========================================
# SIDEBAR CONTROLS (Top to bottom, nothing else)
# ==========================================
with st.sidebar:
    # 1. Scenario (selectbox; loads on change) + Reset
    scenario_options = [
        "1. Single Routine Request",
        "2. Two Hospitals Competing for Scarce O-",
        "3. Mass-Casualty Incident (4 Hospitals)",
        "4. Temperature Breach Mid-Delivery -> Backup from Reserve",
        "5. Traffic Jam (A* Dynamic Re-routing)",
        "6. Stockout -> Compatible Substitution",
    ]

    def _on_scenario_change() -> None:
        selected = st.session_state["scenario_selector"]
        engine.load_preset_scenario(selected)
        st.session_state["current_scenario_name"] = selected
        st.session_state["active_modal_hospital"] = None
        st.session_state["dismissed_banners"].clear()
        st.session_state["last_breach_alert"] = None

    curr_idx = 0
    if st.session_state["current_scenario_name"] in scenario_options:
        curr_idx = scenario_options.index(st.session_state["current_scenario_name"])

    st.selectbox(
        "Scenario",
        scenario_options,
        index=curr_idx,
        key="scenario_selector",
        on_change=_on_scenario_change,
    )

    if st.button("Reset", use_container_width=True):
        engine.reset()
        st.session_state["active_modal_hospital"] = None
        st.session_state["dismissed_banners"].clear()
        st.session_state["last_breach_alert"] = None
        st.rerun()

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # 2. Step 1 min, Run to end (side by side; short labels must not truncate)
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if st.button("Step 1 min", type="primary", use_container_width=True, help="Advance simulation by 1 minute (auto-allocates pending requests)"):
            engine.step(1.0)
            st.rerun()
    with col_s2:
        if st.button("Run to end", use_container_width=True, help="Run simulation until all deliveries complete"):
            engine.run_until_idle(max_steps=80)
            st.rerun()

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # 4. Rush hour (toggle; needed for the A* traffic demo)
    def _on_rush_hour_change() -> None:
        if st.session_state["rush_hour_toggle"]:
            engine.city_network.set_all_traffic_delays(2.0)
        else:
            if st.session_state.get("current_scenario_name") == "5. Traffic Jam (A* Dynamic Re-routing)":
                engine.city_network.set_all_traffic_delays(1.0)
                engine.city_network.set_road_delay("CBB", "J4", 3.0)
            else:
                engine.city_network.set_all_traffic_delays(1.0)

    st.toggle("Rush hour", key="rush_hour_toggle", on_change=_on_rush_hour_change)

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # 5. Inject breach: vehicle selectbox + "Inject breach" button (disabled when no vehicle is moving)
    moving_devs = [k for k, d in engine.delivery_agents.items() if d.is_accepted and not d.is_completed]
    has_moving = len(moving_devs) > 0

    sel_breach_dev = st.selectbox(
        "Vehicle for breach",
        moving_devs if has_moving else ["No vehicle moving"],
        disabled=not has_moving,
        label_visibility="collapsed",
    )
    if st.button(
        "Inject breach",
        disabled=not has_moving,
        use_container_width=True,
        help="Inject cold-chain temperature failure into active vehicle",
    ):
        if has_moving and sel_breach_dev in moving_devs:
            engine.inject_delivery_breach(sel_breach_dev, "HOT")
            st.session_state["dismissed_banners"].discard(f"breach_{sel_breach_dev}")
            st.toast(f"Injected heating breach into {sel_breach_dev}")
            st.rerun()

    # 6. Simulation clock T+mm:ss
    mins = int(engine.current_time)
    secs = int((engine.current_time * 60) % 60)
    clock_str = f"T+{mins:02d}:{secs:02d}"
    st.markdown(
        f'<div style="font-size:12px; color:var(--ink-2); margin-top:14px;">'
        f'Simulation clock: <span class="mono" style="font-weight:600; color:var(--ink);">{clock_str}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ==========================================
# MAIN PAGE (Single page with no tabs)
# ==========================================

# 1. Top bar: "Multi-Agent Blood Supply and Cold-Chain Management" + "Coimbatore region" on the left, the clock on the right.
render_topbar(engine.current_time)

if active_breach_banner_text:
    render_breach_banner(active_breach_banner_text, banner_id=f"breach_{st.session_state.get('last_breach_alert', 'active')}")

# 2. Four KPIs only:
metrics = engine.get_summary_metrics()
pending_list = engine.central_bank.pending_requests if engine.central_bank else []
pending_count = len(pending_list)
in_transit_count = sum(1 for d in engine.delivery_agents.values() if d.is_accepted and not d.is_completed)
render_kpi_strip(metrics, pending_count=pending_count, in_transit_count=in_transit_count)

# 3. Map (left, ~60%) | right column: "Requests" list + "Central Bank stock" bars per blood type. Clicking a hospital opens the request form, as before.
col_map, col_right = st.columns([1.5, 1.0])

with col_map:
    st.markdown('<div class="section-title">Regional Network Map</div>', unsafe_allow_html=True)
    cbb_stock = engine.central_bank.get_stock_counts() if engine.central_bank else {}
    rbb_stock = engine.reserve_bank.get_stock_counts() if engine.reserve_bank else {}
    banks_stock = {
        "CBB": cbb_stock,
        "RBB": rbb_stock,
    }

    # Route and destination status callout card
    render_delivery_route_status_card(
        delivery_agents=engine.delivery_agents,
        pending_requests=pending_list,
        request_tracking=engine.request_tracking,
        city_network=engine.city_network,
    )

    fig_map = build_city_map_figure(
        city_net=engine.city_network,
        hospitals=engine.hospitals,
        banks=banks_stock,
        delivery_agents=engine.delivery_agents,
        pending_requests=pending_list,
        allocation_history=engine.allocation_history,
        request_tracking=engine.request_tracking,
    )

    selected_data = st.plotly_chart(
        fig_map,
        use_container_width=True,
        on_select="rerun",
        selection_mode="points",
        key="city_network_map",
    )

    if selected_data and "selection" in selected_data and selected_data["selection"].get("points"):
        for pt in selected_data["selection"]["points"]:
            cdata = pt.get("customdata")
            if cdata and cdata in engine.hospitals:
                st.session_state["active_modal_hospital"] = cdata
                break

    st.markdown(
        '<div class="hint-text">Click a hospital to raise a blood request.</div>',
        unsafe_allow_html=True,
    )

    # Fast hospital selection row
    h_cols = st.columns(len(engine.hospitals))
    for idx, (h_id, h_agent) in enumerate(engine.hospitals.items()):
        with h_cols[idx]:
            if st.button(h_agent.name, key=f"quick_btn_{h_id}", use_container_width=True):
                st.session_state["active_modal_hospital"] = h_id
                st.rerun()

with col_right:
    st.markdown('<div class="section-title">Requests</div>', unsafe_allow_html=True)
    render_incoming_requests(pending_list, engine.current_time)

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">Central Bank stock</div>', unsafe_allow_html=True)
    render_central_stock_bars(cbb_stock, min_level=5)

if st.session_state.get("active_modal_hospital"):
    open_requirement_dialog(st.session_state["active_modal_hospital"])

# 4. "Allocation result": the decision table (rank, hospital, type, requested, allocated, score, outcome, reason) + the one-line plain-English explanation. Hide it until allocation has run.
if engine.allocation_history:
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Allocation result</div>', unsafe_allow_html=True)
    render_allocation_table(engine.allocation_history, engine.request_tracking)

# 5. "Deliveries": one row per vehicle (route, progress, ETA, temperature, status) + the temperature chart. Hide it until a vehicle exists.
has_vehicles = any(d.is_accepted for d in engine.delivery_agents.values())
if has_vehicles:
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Deliveries</div>', unsafe_allow_html=True)
    render_deliveries_list(engine.delivery_agents, engine.city_network)

    fig_temp = build_temperature_telemetry_figure(
        delivery_agents=engine.delivery_agents,
        t_min=float(engine.rule_engine.t_min),
        t_max=float(engine.rule_engine.t_max),
        current_time=engine.current_time,
    )
    st.plotly_chart(fig_temp, use_container_width=True)

# 6. "Agent messages": the log table with the "Hide routine status updates" toggle on by default, inside an st.expander that is expanded once there are messages. Put the sequence timeline chart in the same expander, above the table.
msg_records = engine.bus.get_timeline_records()
all_messages = engine.bus.get_messages()
has_messages = len(msg_records) > 0

st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
with st.expander("Agent messages", expanded=has_messages):
    fig_timeline = build_message_timeline_figure(all_messages)
    st.plotly_chart(fig_timeline, use_container_width=True)

    hide_routine = st.toggle("Hide routine status updates", value=True, key="filter_hide_routine")

    filtered = msg_records
    if hide_routine:
        filtered = [r for r in filtered if r["performative"] != "STATUS_UPDATE"]
    filtered = sorted(filtered, key=lambda r: (r["timestamp"], r["sequence_number"]))
    render_message_log_table(filtered, hospitals_map=engine.hospitals)

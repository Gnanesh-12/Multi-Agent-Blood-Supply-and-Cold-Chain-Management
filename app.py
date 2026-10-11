"""Streamlit Web Application: Multi-Agent Blood Supply & Cold-Chain Management.

Foundations of AI Case Study Interactive Demo.
Adheres strictly to the architectural boundary: app.py contains UI layer only.
"""

from __future__ import annotations

import os
from pathlib import Path
import pandas as pd
import streamlit as st

from src.blood import BloodType
from src.simulation import SimulationEngine
from src.planning.astar import astar_search, dijkstra_search
from src.ui_helpers import (
    build_city_map_figure,
    build_inventory_figure,
    build_message_timeline_figure,
    build_temperature_telemetry_figure,
)

# Page configuration
st.set_page_config(
    page_title="Multi-Agent Blood Supply & Cold-Chain Management",
    page_icon="🩸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for dark glassmorphism styling
st.markdown(
    """
    <style>
    /* Completely eliminate top whitespace on main page and sidebar */
    header[data-testid="stHeader"] {
        display: none !important;
    }
    .main .block-container,
    div[data-testid="stMainBlockContainer"],
    .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 1.5rem !important;
        margin-top: 0rem !important;
    }
    [data-testid="stSidebarHeader"] {
        display: none !important;
        height: 0rem !important;
        padding: 0rem !important;
    }
    [data-testid="stSidebarContent"] {
        padding-top: 0.5rem !important;
    }
    [data-testid="stSidebarUserContent"],
    section[data-testid="stSidebar"] .block-container {
        padding-top: 0.5rem !important;
        margin-top: 0rem !important;
    }
    section[data-testid="stSidebar"] {
        padding-top: 0rem !important;
    }
    h1, h2, h3, h4 {
        margin-top: 0rem !important;
        padding-top: 0rem !important;
    }

    /* Metric Card Styling */
    .metric-card {
        background: linear-gradient(135deg, rgba(26, 34, 53, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 14px 18px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        border-color: rgba(255, 51, 102, 0.4);
    }
    .metric-val {
        font-size: 26px;
        font-weight: 700;
        color: #F8FAFC;
        margin-top: 2px;
    }
    .metric-title {
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #94A3B8;
    }
    /* Badges */
    .badge-emergency { background-color: #EF4444; color: #FFFFFF; padding: 2px 8px; border-radius: 6px; font-weight: 600; font-size: 11px; }
    .badge-urgent { background-color: #F59E0B; color: #FFFFFF; padding: 2px 8px; border-radius: 6px; font-weight: 600; font-size: 11px; }
    .badge-routine { background-color: #3B82F6; color: #FFFFFF; padding: 2px 8px; border-radius: 6px; font-weight: 600; font-size: 11px; }
    .badge-fulfilled { background-color: #10B981; color: #FFFFFF; padding: 2px 8px; border-radius: 6px; font-weight: 600; font-size: 11px; }
    .badge-partial { background-color: #F59E0B; color: #FFFFFF; padding: 2px 8px; border-radius: 6px; font-weight: 600; font-size: 11px; }
    .badge-refused { background-color: #DC2626; color: #FFFFFF; padding: 2px 8px; border-radius: 6px; font-weight: 600; font-size: 11px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Initialize SimulationEngine in session_state
CONFIG_PATH = Path(__file__).resolve().parent / "config" / "city.yaml"
if "engine" not in st.session_state:
    st.session_state["engine"] = SimulationEngine(CONFIG_PATH, random_seed=42)

engine: SimulationEngine = st.session_state["engine"]

if "active_modal_hospital" not in st.session_state:
    st.session_state["active_modal_hospital"] = None


# Dialog definition for Blood Requirement Form
@st.dialog("Blood Requirement Order")
def open_requirement_dialog(hospital_id: str):
    h_agent = engine.hospitals.get(hospital_id)
    if not h_agent:
        st.error(f"Hospital {hospital_id} not found.")
        return

    st.markdown(f"### 🏥 {h_agent.name} (`{hospital_id}`)")
    st.caption(f"Bed Capacity: {h_agent.bed_capacity} beds | Current Clock: {engine.current_time:.1f} min")

    col_a, col_b = st.columns(2)
    with col_a:
        blood_type = st.selectbox(
            "Blood Type Required",
            [bt.value for bt in BloodType],
            index=0,
            help="Select recipient blood type needed for transfusion",
        )
        units = st.slider("Units Required", min_value=1, max_value=10, value=2)
        urgency = st.selectbox(
            "Clinical Urgency Level",
            ["Emergency", "Urgent", "Routine"],
            index=0,
            help="Emergency (score 3.0), Urgent (2.0), Routine (1.0)",
        )

    with col_b:
        time_to_need = st.number_input(
            "Time to Need / Surgery (minutes)",
            min_value=5,
            max_value=240,
            value=25,
            step=5,
            help="Minutes remaining until surgical procedure begins",
        )
        reason = st.selectbox(
            "Clinical Indication",
            ["Surgery", "Trauma", "Transfusion", "Other"],
            index=0,
        )

    # Show current local stock for this blood type
    curr_stock = h_agent.get_stock(blood_type)
    target_stock = h_agent.get_target(blood_type)
    st.info(f"Hospital Inventory of **{blood_type}**: **{curr_stock}** units (Target: {target_stock} units)")

    if st.button("🚀 Submit Request to Central Blood Bank", type="primary", use_container_width=True):
        req = engine.submit_hospital_request(
            hospital_id=hospital_id,
            blood_type=blood_type,
            units=units,
            urgency_level=urgency,
            time_to_need_minutes=float(time_to_need),
            reason=reason,
        )
        st.session_state["active_modal_hospital"] = None
        st.toast(f"Requirement {req.request_id} submitted by {h_agent.name}!", icon="🩸")
        st.rerun()


# ==========================================
# SIDEBAR CONTROLS
# ==========================================
with st.sidebar:
    st.markdown("## ⚙️ Control Center")
    st.caption("Metropolis AI Health Logistics Coordinator")

    # 1. Preset Scenarios
    st.markdown("### 📋 Preset Scenarios")
    scenario_choice = st.selectbox(
        "Select Demo Scenario",
        [
            "1. Single Routine Request",
            "2. Two Hospitals Competing for Scarce O-",
            "3. Mass-Casualty Incident (4 Hospitals)",
            "4. Temperature Breach Mid-Delivery -> Backup from Reserve",
            "5. Traffic Jam (A* Dynamic Re-routing)",
            "6. Stockout -> Compatible Substitution",
        ],
        index=0,
    )
    if st.button("📂 Load Preset Scenario", use_container_width=True):
        engine.load_preset_scenario(scenario_choice)
        st.session_state["active_modal_hospital"] = None
        st.toast(f"Loaded scenario: {scenario_choice}", icon="✅")
        st.rerun()

    st.markdown("---")

    # 2. Simulation Execution Buttons
    st.markdown("### ⏯️ Simulation Controls")
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("🎯 Run Allocation", type="primary", use_container_width=True, help="Run greedy priority allocation on pending requests"):
            engine.run_allocation()
            st.rerun()
    with btn_col2:
        if st.button("⏱️ Step (+1 min)", use_container_width=True, help="Advance simulation by 1 minute"):
            engine.step(1.0)
            st.rerun()

    run_comp_col, reset_col = st.columns(2)
    with run_comp_col:
        if st.button("⏩ Complete", use_container_width=True, help="Run until all deliveries finish"):
            engine.run_until_idle(max_steps=80)
            st.rerun()
    with reset_col:
        if st.button("🔄 Reset", use_container_width=True, help="Reset simulation to initial state"):
            engine.reset()
            st.session_state["active_modal_hospital"] = None
            st.rerun()

    st.markdown(f"**Simulation Clock:** `{engine.current_time:.1f}` minutes elapsed")

    # 3. Urgency Scoring Weights
    with st.expander("⚖️ Urgency Scoring Weights", expanded=False):
        st.caption("Urgency Score = w1·Urgency + w2·(1/Time) + w3·Deficit + w4·Rarity + w5·Waiting")
        w1 = st.slider("w1: Urgency Level", 0.0, 1.0, float(engine.city_network.urgency_weights.get("w1_urgency_level", 0.35)), 0.05)
        w2 = st.slider("w2: Time-to-Need (1/t)", 0.0, 1.0, float(engine.city_network.urgency_weights.get("w2_time_to_need", 0.25)), 0.05)
        w3 = st.slider("w3: Deficit Ratio", 0.0, 1.0, float(engine.city_network.urgency_weights.get("w3_deficit_ratio", 0.15)), 0.05)
        w4 = st.slider("w4: Blood Rarity", 0.0, 1.0, float(engine.city_network.urgency_weights.get("w4_blood_type_rarity", 0.15)), 0.05)
        w5 = st.slider("w5: Waiting Time (Aging)", 0.0, 1.0, float(engine.city_network.urgency_weights.get("w5_waiting_time", 0.10)), 0.05)
        engine.city_network.urgency_weights.update({
            "w1_urgency_level": w1,
            "w2_time_to_need": w2,
            "w3_deficit_ratio": w3,
            "w4_blood_type_rarity": w4,
            "w5_waiting_time": w5,
        })

    # 4. Cold Chain Safety Rules & Thresholds
    with st.expander("🌡️ Cold Chain Thresholds", expanded=False):
        t_min = st.slider("T_MIN Lower Limit (°C)", -2.0, 4.0, float(engine.rule_engine.t_min), 0.5)
        t_max = st.slider("T_MAX Upper Limit (°C)", 6.0, 15.0, float(engine.rule_engine.t_max), 0.5)
        d_consec = st.slider("D Consecutive Breach Readings", 1, 5, int(engine.rule_engine.d_consecutive), 1)
        engine.rule_engine.update_thresholds(t_min, t_max, d_consec)

    # 5. Traffic Jam & Delay Injection
    with st.expander("🚦 Traffic Conditions", expanded=False):
        rush_hour = st.toggle("Rush Hour (All Roads 2.0x Delay)", value=False)
        if rush_hour:
            engine.city_network.set_all_traffic_delays(2.0)
        else:
            roads_list = [f"{u} <-> {v}" for u, v in engine.city_network.graph.edges()]
            chosen_road = st.selectbox("Select Road Edge", roads_list, index=2 if len(roads_list) > 2 else 0)
            u_sel, v_sel = chosen_road.split(" <-> ")
            road_delay = st.slider(f"Delay Factor on {chosen_road}", 1.0, 3.5, float(engine.city_network.graph[u_sel][v_sel]["delay_factor"]), 0.25)
            engine.city_network.set_road_delay(u_sel, v_sel, road_delay)

    # 6. Temperature Breach Injection
    with st.expander("⚠️ Temperature Breach Injection", expanded=False):
        active_devs = [k for k, d in engine.delivery_agents.items() if not d.is_completed]
        if active_devs:
            sel_dev = st.selectbox("Select Active Vehicle", active_devs)
            b_col1, b_col2 = st.columns(2)
            with b_col1:
                if st.button("🔥 Heat Spike (+Hot)", use_container_width=True):
                    engine.inject_delivery_breach(sel_dev, "HOT")
                    st.toast(f"Injected heating failure into {sel_dev}!", icon="🔥")
                    st.rerun()
            with b_col2:
                if st.button("❄️ Freeze Fail (-Cold)", use_container_width=True):
                    engine.inject_delivery_breach(sel_dev, "COLD")
                    st.toast(f"Injected freezing failure into {sel_dev}!", icon="❄️")
                    st.rerun()
        else:
            st.caption("No active delivery vehicles currently in transit.")

    # 7. Blood Bank Inventory Adjustments
    with st.expander("🩸 Central Bank Inventory", expanded=False):
        if engine.central_bank:
            cbb_counts = engine.central_bank.get_stock_counts()
            for bt in [BloodType.O_NEG.value, BloodType.O_POS.value, BloodType.A_POS.value, BloodType.B_POS.value]:
                st.write(f"**{bt}**: {cbb_counts.get(bt, 0)} units available")


# ==========================================
# MAIN PAGE LAYOUT
# ==========================================

# 1. Header & Title Banner
st.markdown("## 🩸 Multi-Agent Blood Supply & Cold-Chain Management")


# 2. Metric Cards Summary Row
metrics = engine.get_summary_metrics()
m1, m2, m3, m4, m5, m6, m7 = st.columns(7)

with m1:
    st.markdown(
        f"""<div class="metric-card"><div class="metric-title">Requests Raised</div><div class="metric-val">{metrics['requests_received']}</div></div>""",
        unsafe_allow_html=True,
    )
with m2:
    st.markdown(
        f"""<div class="metric-card"><div class="metric-title">Fulfilled</div><div class="metric-val" style="color: #10B981;">{metrics['fulfilled']}</div></div>""",
        unsafe_allow_html=True,
    )
with m3:
    st.markdown(
        f"""<div class="metric-card"><div class="metric-title">Partial / Refused</div><div class="metric-val" style="color: #F59E0B;">{metrics['partial_or_refused']}</div></div>""",
        unsafe_allow_html=True,
    )
with m4:
    st.markdown(
        f"""<div class="metric-card"><div class="metric-title">Units Delivered</div><div class="metric-val" style="color: #38BDF8;">{metrics['units_delivered']}</div></div>""",
        unsafe_allow_html=True,
    )
with m5:
    st.markdown(
        f"""<div class="metric-card"><div class="metric-title">Breached / Quarantined</div><div class="metric-val" style="color: #EF4444;">{metrics['breaches_quarantined']}</div></div>""",
        unsafe_allow_html=True,
    )
with m6:
    st.markdown(
        f"""<div class="metric-card"><div class="metric-title">Avg Fulfilment Time</div><div class="metric-val">{metrics['avg_fulfilment_time_mins']} <span style="font-size:14px;color:#94A3B8;">min</span></div></div>""",
        unsafe_allow_html=True,
    )
with m7:
    st.markdown(
        f"""<div class="metric-card"><div class="metric-title">Agent Messages</div><div class="metric-val" style="color: #A855F7;">{metrics['total_messages']}</div></div>""",
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# 3. Two Columns: City Map (Wide Left) & Pending Requests + Inventory (Right)
col_left, col_right = st.columns([1.75, 1.25])

with col_left:
    st.markdown("### 🗺️ City Network & Active Logistics")

    # Bank stock dictionaries for map tooltips
    cbb_stock = engine.central_bank.get_stock_counts() if engine.central_bank else {}
    rbb_stock = engine.reserve_bank.get_stock_counts() if engine.reserve_bank else {}
    banks_stock = {
        "CBB": cbb_stock,
        "RBB": rbb_stock,
    }

    fig_map = build_city_map_figure(
        city_net=engine.city_network,
        hospitals=engine.hospitals,
        banks=banks_stock,
        delivery_agents=engine.delivery_agents,
    )

    # Plotly interactive chart with point selection
    selected_data = st.plotly_chart(
        fig_map,
        use_container_width=True,
        on_select="rerun",
        selection_mode="points",
        key="city_network_map",
    )

    # Handle map point click to open modal dialog
    if selected_data and "selection" in selected_data and selected_data["selection"].get("points"):
        clicked_points = selected_data["selection"]["points"]
        for pt in clicked_points:
            cdata = pt.get("customdata")
            if cdata and cdata in engine.hospitals:
                st.session_state["active_modal_hospital"] = cdata
                break

    # Quick Select Buttons Row for effortless modal launch
    st.caption("💡 Click on any hospital above, or use quick access:")
    h_btns = st.columns(5)
    for idx, (h_id, h_agent) in enumerate(engine.hospitals.items()):
        with h_btns[idx]:
            if st.button(f"🏥 {h_agent.name}", key=f"quick_btn_{h_id}", use_container_width=True):
                st.session_state["active_modal_hospital"] = h_id
                st.rerun()

    # Trigger active modal if requested
    if st.session_state.get("active_modal_hospital"):
        open_requirement_dialog(st.session_state["active_modal_hospital"])

with col_right:
    st.markdown("### 📋 Pending Requests Queue")
    pending_list = engine.central_bank.pending_requests if engine.central_bank else []

    if pending_list:
        pending_rows = []
        for r in pending_list:
            pending_rows.append({
                "ID": r.request_id,
                "Hospital": r.hospital_name,
                "Blood": r.blood_type,
                "Units": r.units_requested,
                "Urgency": r.urgency_level,
                "Need In": f"{r.time_to_need_minutes:.0f} min",
            })
        st.dataframe(pd.DataFrame(pending_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No pending requests. Click a hospital to raise a blood requirement.")

    st.markdown("### 🏦 Blood Bank Inventories")
    fig_inv = build_inventory_figure(cbb_stock, rbb_stock)
    st.plotly_chart(fig_inv, use_container_width=True)

st.markdown("---")

# 4. Allocation Decision Table
st.markdown("### ⚖️ Multi-Criteria Allocation Decisions")
if engine.allocation_history:
    alloc_rows = []
    for d in engine.allocation_history:
        b = d.score_breakdown
        alloc_rows.append({
            "Rank": d.rank,
            "Request ID": d.request_id,
            "Hospital": d.hospital_name,
            "Type Requested": d.blood_type_requested,
            "Requested": d.units_requested,
            "Allocated": d.units_allocated,
            "Substitution": d.substituted_type if d.substituted_type else "None (Exact)",
            "Score Breakdown": f"U={b.urgency_term:.2f} | 1/T={b.time_to_need_term:.2f} | D={b.deficit_term:.2f} | R={b.rarity_term:.2f} | W={b.waiting_term:.2f}",
            "Total Score": b.total_score,
            "Outcome": d.outcome.value,
            "Clinical Decision Reason": d.reason,
        })
    df_alloc = pd.DataFrame(alloc_rows)
    st.dataframe(df_alloc, use_container_width=True, hide_index=True)
else:
    st.caption("No allocation decisions processed yet. Click **Run Allocation** in the sidebar.")

st.markdown("---")

# 5. Active Deliveries & Live Cold Chain Telemetry
st.markdown("### 🚚 Active Transport Deliveries & Cold Chain Telemetry")
dev_cols = st.columns([1.3, 1.7])

with dev_cols[0]:
    st.markdown("#### Vehicle Status Cards")
    active_vehicles = [d for d in engine.delivery_agents.values() if d.is_accepted and not d.is_completed and d.destination_node]
    if active_vehicles:
        for dev in active_vehicles:
            status_color = "#EF4444" if dev.is_quarantined else ("#F59E0B" if dev.is_backup else "#10B981")
            status_text = "QUARANTINED" if dev.is_quarantined else ("BACKUP EN ROUTE" if dev.is_backup else "EN ROUTE")
            units_txt = ", ".join([f"{u.blood_type}" for u in dev.cargo_units])
            route_str = " → ".join(dev.route)

            # Compare A* vs Dijkstra for this vehicle's route
            search_a = astar_search(engine.city_network, dev.source_node, dev.destination_node)
            search_d = dijkstra_search(engine.city_network, dev.source_node, dev.destination_node)

            st.markdown(
                f"""
                <div style="background: rgba(22, 27, 34, 0.8); border: 1px solid rgba(255,255,255,0.08); border-left: 4px solid {status_color}; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:700; color:#F8FAFC;">{dev.name}</span>
                        <span style="background:{status_color}; color:#FFF; font-size:10px; padding:2px 6px; border-radius:4px; font-weight:700;">{status_text}</span>
                    </div>
                    <div style="font-size:12px; color:#94A3B8; margin-top:4px;">
                        <b>Route:</b> {route_str}<br>
                        <b>Cargo:</b> {len(dev.cargo_units)} units ({units_txt}) | <b>Temp:</b> <span style="color:#FDE047; font-weight:700;">{dev.current_temp:.1f} °C</span> | <b>ETA:</b> {dev.calculate_remaining_eta():.1f} min<br>
                        <b>A* Algorithm:</b> Expanded <b>{search_a.nodes_expanded}</b> nodes vs Dijkstra <b>{search_d.nodes_expanded}</b> nodes (Cost: {search_a.cost_minutes:.1f} min)
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("No delivery vehicles currently in transit.")

with dev_cols[1]:
    st.markdown("#### Live Sensor Telemetry (Safe Band: 1°C – 10°C)")
    fig_temp = build_temperature_telemetry_figure(
        delivery_agents=engine.delivery_agents,
        t_min=float(engine.rule_engine.t_min),
        t_max=float(engine.rule_engine.t_max),
    )
    st.plotly_chart(fig_temp, use_container_width=True)

st.markdown("---")

# 6. Message Timeline Sequence Chart
st.markdown("### 💬 Inter-Agent Message Timeline")
fig_timeline = build_message_timeline_figure(engine.bus.get_messages())
st.plotly_chart(fig_timeline, use_container_width=True)

st.markdown("---")

# 7. Message Log Table & Rule Firings
tab_msgs, tab_rules, tab_explain = st.tabs(["📜 Message Log", "🛡️ Safety Rule Firings", "🧠 AI Architecture & 'How It Works'"])

with tab_msgs:
    msg_records = engine.bus.get_timeline_records()
    if msg_records:
        # Extract unique conversation IDs and performatives for filters
        all_conv_ids = sorted(list({r["conversation_id"] for r in msg_records if r["conversation_id"]}))
        all_perfs = sorted(list({r["performative"] for r in msg_records}))

        # Filter controls
        f_col1, f_col2, f_col3 = st.columns([2, 2, 2])
        with f_col1:
            selected_conv = st.selectbox(
                "Filter by Conversation ID",
                options=["All"] + all_conv_ids,
                key="filter_conv_id",
            )
        with f_col2:
            selected_perf = st.selectbox(
                "Filter by Performative",
                options=["All"] + all_perfs,
                key="filter_performative",
            )
        with f_col3:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            hide_routine = st.checkbox(
                "Hide routine status updates",
                value=False,
                key="toggle_hide_routine_status",
            )

        # Filter the records
        filtered_records = msg_records
        if hide_routine:
            filtered_records = [r for r in filtered_records if r["performative"] != "STATUS_UPDATE"]
        if selected_conv != "All":
            filtered_records = [r for r in filtered_records if r["conversation_id"] == selected_conv]
        if selected_perf != "All":
            filtered_records = [r for r in filtered_records if r["performative"] == selected_perf]

        # Ensure strict causal sorting by (timestamp, sequence_number)
        filtered_records = sorted(filtered_records, key=lambda r: (r["timestamp"], r["sequence_number"]))

        # Build table dataframe
        df_msgs = pd.DataFrame([
            {
                "Seq #": r["sequence_number"],
                "Time (min)": f"{r['timestamp']:.1f}",
                "Sender": r["sender"],
                "Receiver": r["receiver"],
                "Performative": r["performative"],
                "Content Summary": r["summary"],
                "Conversation ID": r["conversation_id"],
            }
            for r in filtered_records
        ])
        st.dataframe(df_msgs, use_container_width=True, hide_index=True)

        # Raw payload expander for debugging
        with st.expander("🔍 Inspect Raw Message Payloads (Debug View)", expanded=False):
            st.caption("Select a message to inspect its complete underlying JSON payload:")
            msg_options = {
                f"#{r['sequence_number']} [{r['performative']}] {r['sender']} → {r['receiver']} (t={r['timestamp']:.1f}m)": r
                for r in filtered_records
            }
            if msg_options:
                selected_msg_label = st.selectbox("Select message:", list(msg_options.keys()))
                st.json(msg_options[selected_msg_label]["payload"])
    else:
        st.caption("No messages recorded.")

with tab_rules:
    rule_firings = engine.rule_engine.firings_log
    if rule_firings:
        df_rules = pd.DataFrame([
            {
                "Time (min)": f"{f.sim_time:.1f}",
                "Rule ID": f.rule_id,
                "Target": f.target_id,
                "Evaluated Condition (Antecedent)": f.condition_description,
                "Action Taken (Consequent)": f.action_taken,
                "Severity": f.severity,
            }
            for f in reversed(rule_firings)
        ])
        st.dataframe(df_rules, use_container_width=True, hide_index=True)
    else:
        st.caption("No safety rule violations fired yet. Normal operation.")

with tab_explain:
    st.markdown(
        """
        ### Multi-Agent Foundations of AI System Breakdown

        #### 1. Multi-Criteria Priority Allocation & Greedy Decision Making
        - **Urgency Scoring Function**:
          $$\\text{Score} = w_1 \\cdot \\text{Urgency} + w_2 \\cdot \\left(\\frac{1}{\\text{Time to Need}}\\right) + w_3 \\cdot \\text{Deficit Ratio} + w_4 \\cdot \\text{Rarity} + w_5 \\cdot \\text{Waiting Time}$$
        - **Aging Term ($w_5 \\cdot \\text{Waiting Time}$)**: Prevents starvation of routine cases under continuous emergency contention by progressively boosting priority over time.
        - **Max-Heap Priority Queue**: Utilizes Python's `heapq` for $O(N \\log N)$ optimal greedy ranking.
        - **FEFO (First-Expiry-First-Out)**: Units closest to expiration are allocated first to minimize product wastage.
        - **Compatible Substitution**: If exact blood types are exhausted, strictly medically compatible alternatives (e.g., $O^-$ universal RBC for $A^-$) are substituted.

        #### 2. Hand-Crafted A* Pathfinding vs Dijkstra
        - **Edge Travel Time**: $\\text{Cost}(u, v) = \\frac{\\text{Distance}_{km}}{\\text{Effective Speed}_{km/h}} \\times 60 \\times \\text{Delay Factor}$.
        - **Admissible Heuristic**:
          $$h(n, \\text{Goal}) = \\frac{\\text{Euclidean Distance}(n, \\text{Goal})}{\\text{Max Speed}} \\times 60$$
          *Admissibility Guarantee*: Straight-line Euclidean distance $\\le$ road network distance, and speed $\\le \\text{Max Speed}$. Therefore $h(n) \\le \\text{True Cost}$, guaranteeing mathematical optimality while pruning search space compared to uninformed Dijkstra.

        #### 3. Horn-Clause Forward-Chaining Safety Rules
        - **Cold-Chain Rule**:
          $$\\text{Temp} < T_{min} \\lor \\text{Temp} > T_{max} \\;(\\text{for } \\ge D \\text{ consecutive readings}) \\implies \\text{Quarantine}(\\text{unit}) \\land \\text{BREACH\\_ALERT} \\land \\text{Trigger Backup}$$
        - **Dual-Bank Backup Sourcing**: Evaluates Central vs Reserve Bank travel times via $A^*$ and stock availability to instantly reroute replacement blood supplies upon cold-chain failure.

        #### 4. FIPA-ACL Agent Interaction Protocol
        - Agents communicate exclusively via asynchronous messages over a decoupled `MessageBus`.
        - Formal communicative performatives: `REQUEST`, `PROPOSE`, `ACCEPT`, `REFUSE`, `DISPATCH`, `STATUS_UPDATE`, `BREACH_ALERT`, `QUARANTINE`, `BACKUP_REQUEST`, `DELIVERED`, `ACK`.
        """
    )

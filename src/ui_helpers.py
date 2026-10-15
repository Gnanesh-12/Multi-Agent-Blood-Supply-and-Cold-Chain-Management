"""UI helper functions for Plotly visualizations: city map, inventory bars, temperature telemetry, and sequence timeline."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import plotly.graph_objects as go
from src.blood import BloodType, BloodUnitStatus
from src.city import CityNetwork
from src.messaging import Message, Performative


# Color Palette
PERFORMATIVE_COLORS = {
    Performative.REQUEST.value: "#3B82F6",       # Blue
    Performative.INFORM.value: "#38BDF8",        # Sky Blue
    Performative.PROPOSE.value: "#60A5FA",       # Light Blue
    Performative.ACCEPT.value: "#10B981",        # Emerald
    Performative.REFUSE.value: "#EF4444",        # Crimson
    Performative.REJECT.value: "#E11D48",        # Bright Red
    Performative.DISPATCH.value: "#8B5CF6",      # Purple
    Performative.STATUS_UPDATE.value: "#64748B",  # Slate
    Performative.BREACH_ALERT.value: "#F43F5E",  # Rose/Red
    Performative.QUARANTINE.value: "#F59E0B",    # Amber
    Performative.BACKUP_REQUEST.value: "#EC4899",# Magenta
    Performative.DELIVERED.value: "#059669",     # Green
    Performative.ACK.value: "#14B8A6",           # Teal
}


def build_city_map_figure(
    city_net: CityNetwork,
    hospitals: Dict[str, Any],
    banks: Dict[str, Any],
    delivery_agents: Dict[str, Any],
) -> go.Figure:
    """Generate high-resolution interactive Plotly city map with roads, active routes, and vehicles."""
    fig = go.Figure()

    # 1. Plot road edges
    # Highlight active delivery paths
    active_edges = set()
    for dev in delivery_agents.values():
        if dev.is_accepted and not dev.is_completed and dev.route:
            for i in range(len(dev.route) - 1):
                u = dev.route[i]
                v = dev.route[i + 1]
                active_edges.add((min(u, v), max(u, v)))

    for u, v, data in city_net.graph.edges(data=True):
        u_coords = city_net.get_coordinates(u)
        v_coords = city_net.get_coordinates(v)
        delay = data.get("delay_factor", 1.0)
        dist = data.get("distance_km", 0.0)
        road_name = data.get("name", f"{u}-{v}")

        edge_pair = (min(u, v), max(u, v))
        is_active_delivery = edge_pair in active_edges

        # Road traffic color
        if delay >= 2.0:
            edge_color = "rgba(239, 68, 68, 0.85)"   # Red jammed
        elif delay > 1.2:
            edge_color = "rgba(245, 158, 11, 0.85)"  # Orange moderate
        else:
            edge_color = "rgba(71, 85, 105, 0.65)"   # Slate clear

        line_width = 4 if is_active_delivery else 2
        line_dash = "dash" if is_active_delivery else "solid"
        if is_active_delivery:
            edge_color = "#38BDF8"  # Cyan highlight for active routes

        hover_info = f"<b>{road_name}</b><br>Distance: {dist:.1f} km<br>Traffic Delay: {delay:.1f}x"

        fig.add_trace(
            go.Scatter(
                x=[u_coords[0], v_coords[0], None],
                y=[u_coords[1], v_coords[1], None],
                mode="lines",
                line=dict(width=line_width, color=edge_color, dash=line_dash),
                hoverinfo="text",
                hovertext=hover_info,
                showlegend=False,
            )
        )

    # 2. Plot Junctions
    j_x, j_y, j_labels, j_hover = [], [], [], []
    for nid, node in city_net.nodes.items():
        if node.node_type == "junction":
            j_x.append(node.x)
            j_y.append(node.y)
            j_labels.append(node.node_id)
            j_hover.append(f"<b>{node.name}</b> ({nid})")

    if j_x:
        fig.add_trace(
            go.Scatter(
                x=j_x,
                y=j_y,
                mode="markers+text",
                text=j_labels,
                textposition="bottom center",
                textfont=dict(size=9, color="#94A3B8"),
                marker=dict(size=8, color="#475569", symbol="circle"),
                hoverinfo="text",
                hovertext=j_hover,
                name="Junctions",
            )
        )

    # 3. Plot Blood Banks
    # Central Bank
    cbb_node = city_net.get_central_bank()
    if cbb_node:
        cbb_stock = banks.get(cbb_node.node_id, {})
        stock_summary = "<br>".join([f"{bt}: {cnt}" for bt, cnt in cbb_stock.items()]) if cbb_stock else "Normal"
        fig.add_trace(
            go.Scatter(
                x=[cbb_node.x],
                y=[cbb_node.y],
                mode="markers+text",
                text=[cbb_node.name],
                textposition="top center",
                textfont=dict(size=12, color="#60A5FA", weight="bold"),
                marker=dict(size=22, color="#2563EB", symbol="diamond", line=dict(color="#93C5FD", width=2)),
                hoverinfo="text",
                hovertext=[f"<b>{cbb_node.name} (Primary Supplier)</b><br><br><b>Available Stock:</b><br>{stock_summary}"],
                name="Central Blood Bank",
            )
        )

    # Reserve Bank
    rbb_node = city_net.get_reserve_bank()
    if rbb_node:
        rbb_stock = banks.get(rbb_node.node_id, {})
        stock_summary = "<br>".join([f"{bt}: {cnt}" for bt, cnt in rbb_stock.items()]) if rbb_stock else "Normal"
        fig.add_trace(
            go.Scatter(
                x=[rbb_node.x],
                y=[rbb_node.y],
                mode="markers+text",
                text=[rbb_node.name],
                textposition="bottom center",
                textfont=dict(size=11, color="#C084FC", weight="bold"),
                marker=dict(size=18, color="#9333EA", symbol="diamond", line=dict(color="#E9D5FF", width=2)),
                hoverinfo="text",
                hovertext=[f"<b>{rbb_node.name} (Quarantine Backup)</b><br><br><b>Stock:</b><br>{stock_summary}"],
                name="Reserve Blood Bank",
            )
        )

    # 4. Plot Hospitals (clickable markers with customdata for modal trigger)
    h_x, h_y, h_labels, h_customdata, h_hover = [], [], [], [], []
    for h_id, h_agent in hospitals.items():
        node = city_net.get_node(h_id)
        if node:
            h_x.append(node.x)
            h_y.append(node.y)
            h_labels.append(node.name)
            h_customdata.append(h_id)
            stock_lines = "<br>".join([f"{bt}: {h_agent.get_stock(bt)} / {h_agent.get_target(bt)}" for bt in ["O-", "O+", "A-", "A+", "B-", "B+"]])
            h_hover.append(
                f"<b>🏥 {node.name} ({h_id})</b><br>"
                f"Beds: {h_agent.bed_capacity}<br>"
                f"<i>Click to raise Blood Requirement</i><br><br>"
                f"<b>Current Stock / Target:</b><br>{stock_lines}"
            )

    if h_x:
        fig.add_trace(
            go.Scatter(
                x=h_x,
                y=h_y,
                mode="markers+text",
                text=h_labels,
                textposition="top center",
                textfont=dict(size=11, color="#FCA5A5", weight="bold"),
                customdata=h_customdata,
                marker=dict(
                    size=20,
                    color="#DC2626",
                    symbol="square-cross",
                    line=dict(color="#FECACA", width=2),
                ),
                hoverinfo="text",
                hovertext=h_hover,
                name="Hospitals (Click to Request)",
            )
        )

    # 5. Plot Active Delivery Vehicles (Moving markers)
    v_x, v_y, v_labels, v_hover, v_colors = [], [], [], [], []
    for dev_id, dev in delivery_agents.items():
        if dev.is_accepted and not dev.is_completed and dev.destination_node:
            pos_x, pos_y = dev.current_position_coords
            v_x.append(pos_x)
            v_y.append(pos_y)
            v_labels.append(f"{dev_id}")
            units_summary = ", ".join([f"{u.blood_type}" for u in dev.cargo_units])
            v_color = "#EF4444" if dev.is_quarantined else ("#F59E0B" if dev.is_backup else "#06B6D4")
            v_colors.append(v_color)
            v_hover.append(
                f"<b>🚚 {dev.name}</b><br>"
                f"Status: {'QUARANTINED' if dev.is_quarantined else 'EN ROUTE'}<br>"
                f"Current Temp: <b>{dev.current_temp:.1f} °C</b><br>"
                f"ETA: {dev.calculate_remaining_eta():.1f} min<br>"
                f"Cargo: {len(dev.cargo_units)} units ({units_summary})<br>"
                f"Destination: {dev.destination_node}"
            )

    if v_x:
        fig.add_trace(
            go.Scatter(
                x=v_x,
                y=v_y,
                mode="markers+text",
                text=v_labels,
                textposition="bottom right",
                textfont=dict(size=10, color="#FDE047", weight="bold"),
                marker=dict(
                    size=16,
                    color=v_colors,
                    symbol="circle",
                    line=dict(color="#FFFFFF", width=2),
                ),
                hoverinfo="text",
                hovertext=v_hover,
                name="Delivery Vehicles",
            )
        )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(11, 15, 25, 1.0)",
        plot_bgcolor="rgba(19, 27, 46, 0.6)",
        margin=dict(l=10, r=10, t=20, b=10),
        xaxis=dict(showgrid=True, gridcolor="rgba(255, 255, 255, 0.05)", zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=True, gridcolor="rgba(255, 255, 255, 0.05)", zeroline=False, showticklabels=False),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            font=dict(size=10),
        ),
        height=520,
    )
    return fig


def build_inventory_figure(central_stock: Dict[str, int], reserve_stock: Dict[str, int]) -> go.Figure:
    """Generate side-by-side bar chart showing Central vs Reserve Bank inventory."""
    blood_types = [bt.value for bt in BloodType]
    c_counts = [central_stock.get(bt, 0) for bt in blood_types]
    r_counts = [reserve_stock.get(bt, 0) for bt in blood_types]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Central Bank",
            x=blood_types,
            y=c_counts,
            marker_color="#3B82F6",
            text=c_counts,
            textposition="auto",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Reserve Bank",
            x=blood_types,
            y=r_counts,
            marker_color="#A855F7",
            text=r_counts,
            textposition="auto",
        )
    )

    fig.update_layout(
        barmode="group",
        template="plotly_dark",
        paper_bgcolor="rgba(11, 15, 25, 0)",
        plot_bgcolor="rgba(19, 27, 46, 0.4)",
        margin=dict(l=10, r=10, t=30, b=10),
        height=240,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0, font=dict(size=10)),
        xaxis=dict(title="Blood Type"),
        yaxis=dict(title="Units Available"),
    )
    return fig


def build_temperature_telemetry_figure(
    delivery_agents: Dict[str, Any],
    t_min: float = 1.0,
    t_max: float = 10.0,
) -> go.Figure:
    """Generate multi-line temperature telemetry chart with threshold zones and breach highlights."""
    fig = go.Figure()

    # Safe zone band
    max_t = 10.0
    for dev in delivery_agents.values():
        if dev.temperature_history:
            max_t = max(max_t, dev.temperature_history[-1][0])
    max_t = max(max_t, 20.0)

    # Shaded safe zone rectangle
    fig.add_hrect(
        y0=t_min,
        y1=t_max,
        fillcolor="rgba(16, 185, 129, 0.12)",
        line_width=0,
        annotation_text="Cold Chain Safe Band (1°C - 10°C)",
        annotation_position="top left",
        annotation_font_size=10,
        annotation_font_color="#10B981",
    )

    # Upper and lower threshold lines
    fig.add_hline(y=t_max, line_dash="dash", line_color="#EF4444", annotation_text=f"T_MAX ({t_max}°C)", annotation_font_size=9)
    fig.add_hline(y=t_min, line_dash="dash", line_color="#3B82F6", annotation_text=f"T_MIN ({t_min}°C)", annotation_font_size=9)

    # Vehicle lines
    colors = ["#38BDF8", "#F59E0B", "#EC4899", "#8B5CF6", "#10B981"]
    for idx, (dev_id, dev) in enumerate(delivery_agents.items()):
        if not dev.is_accepted or not dev.temperature_history:
            continue
        times = [pt[0] for pt in dev.temperature_history]
        temps = [pt[1] for pt in dev.temperature_history]
        line_color = colors[idx % len(colors)]

        fig.add_trace(
            go.Scatter(
                x=times,
                y=temps,
                mode="lines+markers",
                name=f"{dev_id} ({'Quarantined' if dev.is_quarantined else 'Normal'})",
                line=dict(color=line_color, width=2.5),
                marker=dict(size=5),
            )
        )

        # Highlight out of bounds points in red
        breach_x = [pt[0] for pt in dev.temperature_history if pt[1] < t_min or pt[1] > t_max]
        breach_y = [pt[1] for pt in dev.temperature_history if pt[1] < t_min or pt[1] > t_max]
        if breach_x:
            fig.add_trace(
                go.Scatter(
                    x=breach_x,
                    y=breach_y,
                    mode="markers",
                    marker=dict(color="#EF4444", size=10, symbol="x", line=dict(width=2, color="#FFFFFF")),
                    name=f"{dev_id} Breaches",
                    showlegend=False,
                )
            )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(11, 15, 25, 0)",
        plot_bgcolor="rgba(19, 27, 46, 0.4)",
        margin=dict(l=10, r=10, t=30, b=10),
        height=260,
        xaxis=dict(title="Simulation Time (minutes)", showgrid=True, gridcolor="rgba(255, 255, 255, 0.05)"),
        yaxis=dict(title="Temperature (°C)", range=[-2, 22], showgrid=True, gridcolor="rgba(255, 255, 255, 0.05)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0, font=dict(size=10)),
    )
    return fig


def build_message_timeline_figure(messages: List[Message]) -> go.Figure:
    """Generate sequence-style Plotly timeline with agent lanes and performative arrows."""
    fig = go.Figure()

    if not messages:
        fig.add_annotation(
            text="No inter-agent messages recorded yet. Submit requests and advance simulation.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=13, color="#94A3B8"),
        )
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(11, 15, 25, 0)",
            plot_bgcolor="rgba(19, 27, 46, 0.4)",
            height=280,
        )
        return fig

    # Collect unique agent lanes
    all_agents = sorted(list({m.sender for m in messages} | {m.receiver for m in messages}))
    # Priority order: Hospitals top, Banks middle, Vehicles bottom
    hospitals = [a for a in all_agents if a.startswith("H")]
    banks = [a for a in all_agents if "CBB" in a or "RBB" in a or "Bank" in a]
    vehicles = [a for a in all_agents if a.startswith("VAN")]
    others = [a for a in all_agents if a not in hospitals and a not in banks and a not in vehicles]
    lanes = sorted(hospitals) + sorted(banks) + sorted(vehicles) + sorted(others)

    lane_to_y = {lane: idx for idx, lane in enumerate(lanes)}

    # Plot arrows / connected segments for each message
    for msg in messages:
        sender_y = lane_to_y.get(msg.sender)
        receiver_y = lane_to_y.get(msg.receiver)
        perf_val = msg.performative.value if isinstance(msg.performative, Performative) else str(msg.performative)
        color = PERFORMATIVE_COLORS.get(perf_val, "#94A3B8")

        if sender_y is not None and receiver_y is not None:
            # Vertical connector line at msg.timestamp
            fig.add_trace(
                go.Scatter(
                    x=[msg.timestamp, msg.timestamp],
                    y=[sender_y, receiver_y],
                    mode="lines+markers",
                    line=dict(color=color, width=2),
                    marker=dict(size=[6, 9], symbol=["circle", "triangle-down" if receiver_y < sender_y else "triangle-up"]),
                    hoverinfo="text",
                    hovertext=(
                        f"<b>{perf_val}</b> ({msg.timestamp:.1f} min)<br>"
                        f"<b>From:</b> {msg.sender} → <b>To:</b> {msg.receiver}<br>"
                        f"<b>Summary:</b> {msg.summary_text}"
                    ),
                    showlegend=False,
                )
            )

    # Performative legend traces (dummy scatter points)
    for perf, col in PERFORMATIVE_COLORS.items():
        if any((m.performative.value if isinstance(m.performative, Performative) else str(m.performative)) == perf for m in messages):
            fig.add_trace(
                go.Scatter(
                    x=[None],
                    y=[None],
                    mode="markers",
                    marker=dict(size=8, color=col),
                    name=perf,
                )
            )

    first_msg_time = min([m.timestamp for m in messages], default=0.0)
    max_msg_time = max([m.timestamp for m in messages], default=0.0)

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(11, 15, 25, 0)",
        plot_bgcolor="rgba(19, 27, 46, 0.4)",
        margin=dict(l=80, r=10, t=30, b=30),
        height=320,
        xaxis=dict(
            title="Simulation Time (minutes)",
            showgrid=True,
            gridcolor="rgba(255, 255, 255, 0.05)",
            range=[first_msg_time, max(first_msg_time + 15.0, max_msg_time + 2.0)],
        ),
        yaxis=dict(
            tickmode="array",
            tickvals=list(range(len(lanes))),
            ticktext=lanes,
            showgrid=True,
            gridcolor="rgba(255, 255, 255, 0.05)",
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=9)),
    )
    return fig

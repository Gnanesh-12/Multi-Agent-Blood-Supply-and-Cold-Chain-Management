"""Shared Plotly styling and theme for Regional Blood Logistics Console.

Adheres strictly to the light, warm-neutral clinical visual tokens.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import plotly.graph_objects as go
from src.blood import BloodType
from src.city import CityNetwork
from src.messaging import Message, Performative

# Clinical Theme Color Tokens
THEME_BG = "#F6F5F2"
THEME_SURFACE = "#FFFFFF"
THEME_SURFACE_2 = "#EFEDE8"
THEME_INK = "#1D1F23"
THEME_INK_2 = "#5B606A"
THEME_LINE = "#DEDBD4"
THEME_ACCENT = "#B3261E"

STATUS_OK = "#2E7D4F"
STATUS_WARN = "#B7791F"
STATUS_CRITICAL = "#B3261E"
STATUS_INFO = "#2F5D8A"
STATUS_NEUTRAL = "#7A7F87"

FONT_SANS = "IBM Plex Sans, sans-serif"
FONT_MONO = "IBM Plex Mono, monospace"

# Performative color mapping for message charts
PERFORMATIVE_COLORS = {
    Performative.REQUEST.value: STATUS_INFO,
    Performative.INFORM.value: STATUS_OK,
    Performative.PROPOSE.value: STATUS_INFO,
    Performative.ACCEPT.value: STATUS_OK,
    Performative.REFUSE.value: STATUS_CRITICAL,
    Performative.REJECT.value: STATUS_CRITICAL,
    Performative.DISPATCH.value: STATUS_INFO,
    Performative.STATUS_UPDATE.value: STATUS_NEUTRAL,
    Performative.BREACH_ALERT.value: STATUS_CRITICAL,
    Performative.QUARANTINE.value: STATUS_WARN,
    Performative.BACKUP_REQUEST.value: STATUS_INFO,
    Performative.DELIVERED.value: STATUS_OK,
    Performative.ACK.value: STATUS_OK,
}


def apply_clinical_template(fig: go.Figure, height: int = 400) -> go.Figure:
    """Apply consistent clinical styling to Plotly figures."""
    fig.update_layout(
        paper_bgcolor=THEME_SURFACE,
        plot_bgcolor=THEME_SURFACE,
        margin=dict(l=24, r=24, t=32, b=24),
        height=height,
        font=dict(family=FONT_SANS, size=12, color=THEME_INK),
        hoverlabel=dict(
            bgcolor=THEME_SURFACE,
            bordercolor=THEME_LINE,
            font=dict(family=FONT_SANS, size=12, color=THEME_INK),
        ),
    )
    return fig


def build_city_map_figure(
    city_net: CityNetwork,
    hospitals: Dict[str, Any],
    banks: Dict[str, Any],
    delivery_agents: Dict[str, Any],
    pending_requests: Optional[List[Any]] = None,
) -> go.Figure:
    """Generate clinical regional network map.

    - Background matches --surface (#FFFFFF)
    - No gridlines or axes
    - Thin grey roads; traffic delay highlighted only on jammed roads
    - Hospitals: white square with red cross outline
    - Central Bank: filled red circle with droplet
    - Reserve Bank: outlined circle
    - Junctions: tiny dots with no labels
    - Active route: 3px info-blue line
    - Breached vehicle: red with pulsing semi-transparent ring
    """
    fig = go.Figure()

    # Calculate open requests per hospital for hover card
    open_reqs_per_hospital: Dict[str, int] = {}
    if pending_requests:
        for r in pending_requests:
            hid = getattr(r, "hospital_id", None)
            if hid:
                open_reqs_per_hospital[hid] = open_reqs_per_hospital.get(hid, 0) + 1

    # 1. Active delivery routes
    active_edges = set()
    for dev in delivery_agents.values():
        if dev.is_accepted and not dev.is_completed and dev.route:
            for i in range(len(dev.route) - 1):
                u = dev.route[i]
                v = dev.route[i + 1]
                active_edges.add((min(u, v), max(u, v)))

    # 2. Roads (Thin lines, traffic colored only on jammed roads)
    for u, v, data in city_net.graph.edges(data=True):
        u_coords = city_net.get_coordinates(u)
        v_coords = city_net.get_coordinates(v)
        delay = data.get("delay_factor", 1.0)
        dist = data.get("distance_km", 0.0)
        road_name = data.get("name", f"{u}-{v}")

        edge_pair = (min(u, v), max(u, v))
        is_active = edge_pair in active_edges

        # Base road color: thin neutral grey; only jam gets color
        if is_active:
            line_color = STATUS_INFO
            line_width = 3.0
            line_dash = "solid"
        elif delay >= 2.0:
            line_color = STATUS_CRITICAL  # jammed
            line_width = 2.0
            line_dash = "solid"
        elif delay > 1.2:
            line_color = STATUS_WARN      # moderate delay
            line_width = 2.0
            line_dash = "solid"
        else:
            line_color = THEME_LINE       # clear road
            line_width = 1.2
            line_dash = "solid"

        traffic_status = f"{delay:.1f}x delay" if delay > 1.0 else "Normal flow"
        hover_info = f"<b>{road_name}</b><br>Distance: {dist:.1f} km<br>Traffic: {traffic_status}"

        fig.add_trace(
            go.Scatter(
                x=[u_coords[0], v_coords[0], None],
                y=[u_coords[1], v_coords[1], None],
                mode="lines",
                line=dict(width=line_width, color=line_color, dash=line_dash),
                hoverinfo="text",
                hovertext=hover_info,
                showlegend=False,
            )
        )

    # 3. Junctions (tiny dots with NO labels)
    j_x, j_y, j_hover = [], [], []
    for nid, node in city_net.nodes.items():
        if node.node_type == "junction":
            j_x.append(node.x)
            j_y.append(node.y)
            j_hover.append(f"<b>Junction {node.node_id}</b><br>{node.name}")

    if j_x:
        fig.add_trace(
            go.Scatter(
                x=j_x,
                y=j_y,
                mode="markers",
                marker=dict(size=4, color="#A8A49C", symbol="circle"),
                hoverinfo="text",
                hovertext=j_hover,
                name="Junctions",
                showlegend=False,
            )
        )

    # 4. Central Bank (Filled red circle with droplet and label)
    cbb_node = city_net.get_central_bank()
    if cbb_node:
        cbb_stock = banks.get(cbb_node.node_id, {})
        stock_summary = " · ".join([f"{bt} {cnt}" for bt, cnt in list(cbb_stock.items())[:4]])
        fig.add_trace(
            go.Scatter(
                x=[cbb_node.x],
                y=[cbb_node.y],
                mode="markers+text",
                text=["Central Bank"],
                textposition="top center",
                textfont=dict(family=FONT_SANS, size=11, color=THEME_ACCENT, weight="bold"),
                marker=dict(size=16, color=THEME_ACCENT, symbol="circle", line=dict(color="#7E1510", width=1.5)),
                hoverinfo="text",
                hovertext=[f"<b>Central Blood Bank (CBB)</b><br>Primary Regional Storage<br>Stock: {stock_summary}"],
                name="Central Bank",
                showlegend=False,
            )
        )

    # 5. Reserve Bank (Outlined circle)
    rbb_node = city_net.get_reserve_bank()
    if rbb_node:
        rbb_stock = banks.get(rbb_node.node_id, {})
        stock_summary = " · ".join([f"{bt} {cnt}" for bt, cnt in list(rbb_stock.items())[:4]])
        fig.add_trace(
            go.Scatter(
                x=[rbb_node.x],
                y=[rbb_node.y],
                mode="markers+text",
                text=["Reserve Bank"],
                textposition="bottom center",
                textfont=dict(family=FONT_SANS, size=10, color=THEME_INK_2, weight="bold"),
                marker=dict(size=14, color=THEME_SURFACE, symbol="circle", line=dict(color=THEME_INK_2, width=2)),
                hoverinfo="text",
                hovertext=[f"<b>Reserve Blood Bank (RBB)</b><br>Quarantine Backup Hub<br>Stock: {stock_summary}"],
                name="Reserve Bank",
                showlegend=False,
            )
        )

    # 6. Hospitals (White square with red cross outline)
    h_x, h_y, h_labels, h_customdata, h_hover, h_positions = [], [], [], [], [], []
    for h_id, h_agent in hospitals.items():
        node = city_net.get_node(h_id)
        if node:
            h_x.append(node.x)
            h_y.append(node.y)
            h_labels.append(f"{node.name} ({h_id})")
            h_customdata.append(h_id)

            # Leftmost nodes (like H4 at x=1.5 and H1 at x=2.0) position label to the top right so they never clip
            if node.x <= 2.5:
                h_positions.append("top right")
            elif node.x >= 8.5:
                h_positions.append("top left")
            else:
                h_positions.append("top center")

            # Format hover card: "City General (H1)" / "Stock: O− 0 · A+ 4 …" / "Open requests: 1"
            stock_items = [f"{bt.replace('-', '−')} {h_agent.get_stock(bt)}" for bt in ["O-", "O+", "A+", "B+"]]
            stock_line = " · ".join(stock_items)
            open_reqs = open_reqs_per_hospital.get(h_id, 0)

            h_hover.append(
                f"<b>{node.name} ({h_id})</b><br>"
                f"Stock: {stock_line}<br>"
                f"Open requests: {open_reqs}"
            )

    if h_x:
        # White square marker with red outline
        fig.add_trace(
            go.Scatter(
                x=h_x,
                y=h_y,
                mode="markers+text",
                text=h_labels,
                textposition=h_positions,
                textfont=dict(family=FONT_SANS, size=11, color=THEME_INK, weight="bold"),
                customdata=h_customdata,
                marker=dict(
                    size=16,
                    color=THEME_SURFACE,
                    symbol="square",
                    line=dict(color=THEME_ACCENT, width=2),
                ),
                hoverinfo="text",
                hovertext=h_hover,
                name="Hospitals",
                showlegend=False,
            )
        )
        # Inner red cross symbol for unmistakable medical identification
        fig.add_trace(
            go.Scatter(
                x=h_x,
                y=h_y,
                mode="markers",
                customdata=h_customdata,
                marker=dict(
                    size=8,
                    color=THEME_ACCENT,
                    symbol="cross",
                ),
                hoverinfo="text",
                hovertext=h_hover,
                showlegend=False,
            )
        )

    # 7. Active Vehicles & Breached Ring
    v_x, v_y, v_labels, v_hover, v_colors = [], [], [], [], []
    breach_x, breach_y, breach_labels, breach_hover = [], [], [], []

    for dev_id, dev in delivery_agents.items():
        if dev.is_accepted and not dev.is_completed and dev.destination_node:
            pos_x, pos_y = dev.current_position_coords
            v_x.append(pos_x)
            v_y.append(pos_y)
            v_labels.append(dev_id)

            units_str = ", ".join([u.blood_type.replace("-", "−") for u in dev.cargo_units])
            v_color = STATUS_CRITICAL if dev.is_quarantined else STATUS_INFO
            v_colors.append(v_color)

            dest_node = city_net.get_node(dev.destination_node)
            dest_name = dest_node.name if dest_node else dev.destination_node

            v_hover.append(
                f"<b>{dev_id}</b> ({'Quarantined' if dev.is_quarantined else 'En route'})<br>"
                f"Destination: {dest_name}<br>"
                f"Temperature: {dev.current_temp:.1f} °C<br>"
                f"ETA: {dev.calculate_remaining_eta():.1f} min<br>"
                f"Cargo: {len(dev.cargo_units)} units ({units_str})"
            )

            # If vehicle is breached/quarantined, add second larger semi-transparent ring
            if dev.is_quarantined:
                breach_x.append(pos_x)
                breach_y.append(pos_y)
                breach_labels.append(dev_id)
                breach_hover.append(f"<b>BREACH ALERT: {dev_id}</b><br>Temperature: {dev.current_temp:.1f} °C")

    # Pulsing ring outer marker for breached vehicles
    if breach_x:
        fig.add_trace(
            go.Scatter(
                x=breach_x,
                y=breach_y,
                mode="markers",
                marker=dict(
                    size=28,
                    color="rgba(179, 38, 30, 0.22)",
                    symbol="circle",
                    line=dict(color=THEME_ACCENT, width=1.5),
                ),
                hoverinfo="text",
                hovertext=breach_hover,
                showlegend=False,
            )
        )

    # Core vehicle marker
    if v_x:
        fig.add_trace(
            go.Scatter(
                x=v_x,
                y=v_y,
                mode="markers+text",
                text=v_labels,
                textposition="bottom right",
                textfont=dict(family=FONT_MONO, size=10, color=THEME_INK, weight="bold"),
                marker=dict(
                    size=13,
                    color=v_colors,
                    symbol="circle",
                    line=dict(color=THEME_SURFACE, width=2),
                ),
                hoverinfo="text",
                hovertext=v_hover,
                name="Vehicles",
                showlegend=False,
            )
        )

    # Clean layout with no gridlines or axes, and generous coordinate padding
    all_x = [n.x for n in city_net.nodes.values()]
    all_y = [n.y for n in city_net.nodes.values()]
    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)
    dx = max_x - min_x
    dy = max_y - min_y
    pad_x = max(dx * 0.16, 2.5)
    pad_y = max(dy * 0.16, 2.5)

    fig.update_layout(
        paper_bgcolor=THEME_SURFACE,
        plot_bgcolor=THEME_SURFACE,
        margin=dict(l=15, r=15, t=15, b=15),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            range=[min_x - pad_x, max_x + pad_x],
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            range=[min_y - pad_y, max_y + pad_y],
        ),
        height=520,
        hoverlabel=dict(
            bgcolor=THEME_SURFACE,
            bordercolor=THEME_LINE,
            font=dict(family=FONT_SANS, size=12, color=THEME_INK),
        ),
    )
    return fig


def build_temperature_telemetry_figure(
    delivery_agents: Dict[str, Any],
    t_min: float = 1.0,
    t_max: float = 10.0,
    current_time: float = 0.0,
) -> go.Figure:
    """Generate clinical temperature telemetry chart.

    - Safe band (1.0 - 10.0 °C) with light shaded area
    - Dash lines at thresholds
    - Red markers at breach points
    - X-axis simulation minutes (0 -> current)
    - If no data, show "No vehicles in transit." with no -1..1 axis
    """
    has_data = any(
        dev.is_accepted and len(dev.temperature_history) > 0
        for dev in delivery_agents.values()
    )

    if not has_data:
        fig = go.Figure()
        fig.add_annotation(
            text="No vehicles in transit.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(family=FONT_SANS, size=13, color=THEME_INK_2),
        )
        fig.update_layout(
            paper_bgcolor=THEME_SURFACE,
            plot_bgcolor=THEME_SURFACE,
            height=140,
            margin=dict(l=20, r=20, t=20, b=20),
            xaxis=dict(visible=False, showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(visible=False, showgrid=False, zeroline=False, showticklabels=False),
        )
        return fig

    fig = go.Figure()

    # Shaded safe band (1°C to 10°C)
    fig.add_hrect(
        y0=t_min,
        y1=t_max,
        fillcolor="rgba(46, 125, 79, 0.08)",
        line_width=0,
        annotation_text="Safe band (1.0–10.0 °C)",
        annotation_position="top left",
        annotation_font=dict(family=FONT_SANS, size=10, color=STATUS_OK),
    )

    # Threshold dashed lines
    fig.add_hline(
        y=t_max,
        line_dash="dot",
        line_color=THEME_ACCENT,
        line_width=1.2,
        annotation_text=f"Max {t_max:.1f}°C",
        annotation_font=dict(family=FONT_MONO, size=9, color=THEME_ACCENT),
    )
    fig.add_hline(
        y=t_min,
        line_dash="dot",
        line_color=STATUS_INFO,
        line_width=1.2,
        annotation_text=f"Min {t_min:.1f}°C",
        annotation_font=dict(family=FONT_MONO, size=9, color=STATUS_INFO),
    )

    # Clinical vehicle lines
    palette = [STATUS_INFO, "#6B46C1", STATUS_WARN, "#0D9488", "#475569"]
    all_times = []

    for idx, (dev_id, dev) in enumerate(delivery_agents.items()):
        if not dev.is_accepted or not dev.temperature_history:
            continue
        times = [pt[0] for pt in dev.temperature_history]
        temps = [pt[1] for pt in dev.temperature_history]
        all_times.extend(times)
        color = palette[idx % len(palette)]

        fig.add_trace(
            go.Scatter(
                x=times,
                y=temps,
                mode="lines+markers",
                marker=dict(size=4),
                name=f"{dev_id}",
                line=dict(color=color, width=1.8),
                hovertemplate=f"<b>{dev_id}</b>: %{{y:.1f}} °C at T+%{{x:.0f}}m<extra></extra>",
            )
        )

        # Breach points in red markers
        breach_x = [pt[0] for pt in dev.temperature_history if pt[1] < t_min or pt[1] > t_max]
        breach_y = [pt[1] for pt in dev.temperature_history if pt[1] < t_min or pt[1] > t_max]
        if breach_x:
            fig.add_trace(
                go.Scatter(
                    x=breach_x,
                    y=breach_y,
                    mode="markers",
                    marker=dict(color=THEME_ACCENT, size=8, symbol="circle", line=dict(width=1.5, color=THEME_SURFACE)),
                    name=f"{dev_id} Breach",
                    showlegend=False,
                    hovertemplate=f"<b>Breach:</b> %{{y:.1f}} °C<extra></extra>",
                )
            )

    x_limit = max(current_time, max(all_times) if all_times else 1.0, 1.0)

    fig.update_layout(
        paper_bgcolor=THEME_SURFACE,
        plot_bgcolor=THEME_SURFACE,
        margin=dict(l=35, r=20, t=25, b=25),
        height=260,
        xaxis=dict(
            title=dict(text="Simulation time (min)", font=dict(family=FONT_SANS, size=11, color=THEME_INK_2)),
            showgrid=True,
            gridcolor=THEME_SURFACE_2,
            zeroline=False,
            range=[0, x_limit],
            tickfont=dict(family=FONT_MONO, size=10, color=THEME_INK_2),
        ),
        yaxis=dict(
            title=dict(text="Temperature (°C)", font=dict(family=FONT_SANS, size=11, color=THEME_INK_2)),
            range=[-2, 20],
            showgrid=True,
            gridcolor=THEME_SURFACE_2,
            zeroline=False,
            tickfont=dict(family=FONT_MONO, size=10, color=THEME_INK_2),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(family=FONT_SANS, size=10, color=THEME_INK_2),
        ),
        hoverlabel=dict(
            bgcolor=THEME_SURFACE,
            bordercolor=THEME_LINE,
            font=dict(family=FONT_SANS, size=11, color=THEME_INK),
        ),
    )
    return fig


def build_message_timeline_figure(messages: List[Message]) -> go.Figure:
    """Generate sequence timeline with agent lanes and performative arrows."""
    fig = go.Figure()

    if not messages:
        fig.add_annotation(
            text="No inter-agent messages recorded yet.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(family=FONT_SANS, size=12, color=THEME_INK_2),
        )
        fig.update_layout(
            paper_bgcolor=THEME_SURFACE,
            plot_bgcolor=THEME_SURFACE,
            height=280,
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        )
        return fig

    # Collect unique agent lanes
    all_agents = sorted(list({m.sender for m in messages} | {m.receiver for m in messages}))
    hospitals = [a for a in all_agents if a.startswith("H")]
    banks = [a for a in all_agents if "CBB" in a or "RBB" in a or "Bank" in a]
    vehicles = [a for a in all_agents if a.startswith("VAN")]
    others = [a for a in all_agents if a not in hospitals and a not in banks and a not in vehicles]
    lanes = sorted(hospitals) + sorted(banks) + sorted(vehicles) + sorted(others)

    lane_to_y = {lane: idx for idx, lane in enumerate(lanes)}

    agent_display_map = {
        "H1": "City General (H1)",
        "H2": "St. Mary's (H2)",
        "H3": "Apollo (H3)",
        "H4": "Govt Medical College (H4)",
        "H5": "Children's Hospital (H5)",
        "CBB": "Central Blood Bank (CBB)",
        "RBB": "Reserve Blood Bank (RBB)",
    }
    lane_labels = [agent_display_map.get(lane, lane) for lane in lanes]

    max_msg_time = max([m.timestamp for m in messages], default=0.0)

    # Plot arrows / connected segments for each message
    for msg in messages:
        sender_y = lane_to_y.get(msg.sender)
        receiver_y = lane_to_y.get(msg.receiver)
        perf_val = msg.performative.value if isinstance(msg.performative, Performative) else str(msg.performative)
        color = PERFORMATIVE_COLORS.get(perf_val, THEME_INK_2)

        if sender_y is not None and receiver_y is not None:
            fig.add_trace(
                go.Scatter(
                    x=[msg.timestamp, msg.timestamp],
                    y=[sender_y, receiver_y],
                    mode="lines+markers",
                    line=dict(color=color, width=1.5),
                    marker=dict(
                        size=[5, 7],
                        symbol=["circle", "triangle-down" if receiver_y < sender_y else "triangle-up"],
                    ),
                    hoverinfo="text",
                    hovertext=(
                        f"<b>{perf_val}</b> (T+{msg.timestamp:.1f}m)<br>"
                        f"From: {agent_display_map.get(msg.sender, msg.sender)} &rarr; To: {agent_display_map.get(msg.receiver, msg.receiver)}<br>"
                        f"{msg.summary_text}"
                    ),
                    showlegend=False,
                )
            )

    fig.update_layout(
        paper_bgcolor=THEME_SURFACE,
        plot_bgcolor=THEME_SURFACE,
        margin=dict(l=170, r=20, t=20, b=30),
        height=320,
        xaxis=dict(
            title=dict(text="Time elapsed (min)", font=dict(family=FONT_SANS, size=11, color=THEME_INK_2)),
            showgrid=True,
            gridcolor=THEME_SURFACE_2,
            range=[0, max(15.0, max_msg_time + 2.0)],
            tickfont=dict(family=FONT_MONO, size=10, color=THEME_INK_2),
        ),
        yaxis=dict(
            tickmode="array",
            tickvals=list(range(len(lanes))),
            ticktext=lane_labels,
            showgrid=True,
            gridcolor=THEME_SURFACE_2,
            tickfont=dict(family=FONT_SANS, size=10, color=THEME_INK),
        ),
        hoverlabel=dict(
            bgcolor=THEME_SURFACE,
            bordercolor=THEME_LINE,
            font=dict(family=FONT_SANS, size=11, color=THEME_INK),
        ),
    )
    return fig

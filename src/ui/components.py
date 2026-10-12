"""UI Components for Regional Blood Logistics Console.

Calm, dense, information-first presentation components.
"""

from __future__ import annotations

import html
from typing import Any, Dict, List, Optional
import streamlit as st

from src.blood import BloodType
from src.planning.allocation import AllocationDecision, AllocationOutcome, BloodRequirement


def render_html(html_str: str) -> None:
    """Render HTML safely without markdown code block indentation artifacts."""
    if hasattr(st, "html"):
        st.html(html_str)
    else:
        st.markdown(html_str, unsafe_allow_html=True)


def lucide_icon(name: str, size: int = 16, stroke: float = 1.5, color: str = "currentColor") -> str:
    """Generate small Lucide-style inline SVGs without emojis."""
    icons = {
        "hospital": (
            f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M12 6v4"/><path d="M10 8h4"/><path d="M18 20V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16"/>'
            '<path d="M2 20h20"/><path d="M14 12v.01"/><path d="M10 12v.01"/><path d="M14 16v.01"/><path d="M10 16v.01"/>'
            '</svg>'
        ),
        "droplet": (
            f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z"/>'
            '</svg>'
        ),
        "truck": (
            f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
            '<rect width="14" height="10" x="1" y="5" rx="1"/><path d="M15 8h4.5a1.5 1.5 0 0 1 1.2.6L23 12v3h-8V8z"/>'
            '<circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>'
            '</svg>'
        ),
        "thermometer": (
            f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M14 4v10.54a4 4 0 1 1-4 0V4a2 2 0 0 1 4 0Z"/>'
            '</svg>'
        ),
        "alert": (
            f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
            '<circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/>'
            '</svg>'
        ),
        "check": (
            f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
            '<polyline points="20 6 9 17 4 12"/>'
            '</svg>'
        ),
        "clock": (
            f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
            '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>'
            '</svg>'
        ),
        "close": (
            f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
            '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>'
            '</svg>'
        ),
    }
    return icons.get(name, "")


AGENT_NAME_MAP = {
    "H1": "City General (H1)",
    "H2": "St. Mary's (H2)",
    "H3": "Apollo (H3)",
    "H4": "Govt Medical College (H4)",
    "H5": "Children's Hospital (H5)",
    "CBB": "Central Blood Bank (CBB)",
    "RBB": "Reserve Blood Bank (RBB)",
}


def format_agent_name(agent_id: str, hospitals_map: Optional[Dict[str, Any]] = None) -> str:
    """Format agent identifier into human-readable display name."""
    if agent_id in AGENT_NAME_MAP:
        return AGENT_NAME_MAP[agent_id]
    if hospitals_map and agent_id in hospitals_map:
        return f"{hospitals_map[agent_id].name} ({agent_id})"
    if agent_id.startswith("VAN-"):
        return agent_id
    return agent_id


def format_enum_label(val: Any) -> str:
    """Convert enum, snake_case or SCREAMING_SNAKE to readable sentence casing."""
    text = getattr(val, "value", str(val))
    text = text.replace("_", " ").strip()
    return text.capitalize()


def status_pill(status_text: str, kind: str = "neutral", icon: Optional[str] = None) -> str:
    """Render compact clinical status pill."""
    icon_svg = lucide_icon(icon, size=12, stroke=1.8) if icon else ""
    return f'<span class="pill pill-{kind}">{icon_svg}{html.escape(status_text)}</span>'


def blood_chip(blood_type: str, is_rare: Optional[bool] = None) -> str:
    """Render blood type chip with neutral styling and a rarity indicator dot."""
    formatted_type = blood_type.replace("-", "−")
    if is_rare is None:
        is_rare = blood_type in ["O-", "AB-", "B-", "A-", "O−", "AB−", "B−", "A−"]
    dot_class = "rarity-dot rare" if is_rare else "rarity-dot"
    return f'<span class="blood-chip"><span class="{dot_class}"></span>{html.escape(formatted_type)}</span>'


def render_topbar(
    sim_time_minutes: float,
    scenario_name: Optional[str] = None,
    is_running: Optional[bool] = None,
) -> None:
    """Render simplified clinical top bar with product name and simulation clock."""
    mins = int(sim_time_minutes)
    secs = int((sim_time_minutes * 60) % 60)
    clock_str = f"T+{mins:02d}:{secs:02d}"

    html_code = (
        f'<div class="topbar-container">'
        f'<div class="topbar-left">'
        f'<span class="topbar-title">Multi-Agent Blood Supply and Cold-Chain Management</span>'
        f'</div>'
        f'<div class="topbar-right">'
        f'<span class="topbar-clock mono">{clock_str}</span>'
        f'</div>'
        f'</div>'
    )
    render_html(html_code)


def render_kpi_strip(
    metrics: Dict[str, Any],
    pending_count: int = 0,
    partial_count: int = 0,
    refused_count: int = 0,
    in_transit_count: int = 0,
) -> None:
    """Render thin KPI strip with exactly four consolidated stats."""
    total_reqs = metrics.get("requests_received", 0)
    fulfilled = metrics.get("fulfilled", 0)
    delivered = metrics.get("units_delivered", 0)
    breaches = metrics.get("breaches_quarantined", 0)
    p_cnt = partial_count if partial_count else metrics.get("partial", 0)
    r_cnt = refused_count if refused_count else metrics.get("refused", 0)

    breach_class = "kpi-cell breach-alert" if breaches > 0 else "kpi-cell"
    breach_context = f"{breaches} quarantined" if breaches > 0 else "0 within safe band"

    html_code = (
        f'<div class="kpi-strip">'
        f'<div class="kpi-cell">'
        f'<div class="kpi-label">Requests</div>'
        f'<div class="kpi-value">{total_reqs}</div>'
        f'<div class="kpi-context">{pending_count} pending</div>'
        f'</div>'
        f'<div class="kpi-cell">'
        f'<div class="kpi-label">Fulfilled</div>'
        f'<div class="kpi-value">{fulfilled}</div>'
        f'<div class="kpi-context">{p_cnt} partial / {r_cnt} refused</div>'
        f'</div>'
        f'<div class="kpi-cell">'
        f'<div class="kpi-label">In Transit / Delivered</div>'
        f'<div class="kpi-value">{in_transit_count} <span style="font-size:16px;font-weight:400;color:var(--ink-2);">/ {delivered}</span></div>'
        f'<div class="kpi-context">{in_transit_count} in transit · {delivered} delivered</div>'
        f'</div>'
        f'<div class="{breach_class}">'
        f'<div class="kpi-label">Breaches</div>'
        f'<div class="kpi-value">{breaches}</div>'
        f'<div class="kpi-context">{breach_context}</div>'
        f'</div>'
        f'</div>'
    )
    render_html(html_code)


def render_breach_banner(message: str, banner_id: str = "active_breach") -> None:
    """Render slim red alert banner at top of Operations tab if breach occurred."""
    if "dismissed_banners" not in st.session_state:
        st.session_state["dismissed_banners"] = set()

    if banner_id in st.session_state["dismissed_banners"]:
        return

    col_banner, col_dismiss = st.columns([0.94, 0.06])
    with col_banner:
        alert_svg = lucide_icon("alert", size=16, stroke=1.8, color="#B3261E")
        render_html(
            f'<div class="alert-banner">'
            f'<div class="alert-banner-content">{alert_svg}<span>{html.escape(message)}</span></div>'
            f'</div>'
        )
    with col_dismiss:
        if st.button("Dismiss", key=f"btn_dismiss_{banner_id}", help="Dismiss alert"):
            st.session_state["dismissed_banners"].add(banner_id)
            st.rerun()


def render_incoming_requests(pending_requests: List[BloodRequirement], current_time: float) -> None:
    """Render compact list of incoming requests."""
    if not pending_requests:
        render_html(
            '<div style="padding: 24px 16px; border: 1px dashed var(--line); border-radius: 6px; text-align: center; color: var(--ink-2);">'
            'No requests yet. Click a hospital on the map to raise one.'
            '</div>'
        )
        return

    items_html = []
    for req in pending_requests:
        created_time = getattr(req, "created_at_sim_time", getattr(req, "created_at", 0.0))
        age_mins = max(0.0, current_time - created_time)
        age_str = f"{age_mins:.0f} min ago" if age_mins >= 1.0 else "Just now"

        urg_kind = {
            "Emergency": "critical",
            "Urgent": "warn",
            "Routine": "neutral",
        }.get(req.urgency_level, "neutral")

        chip = blood_chip(req.blood_type)
        urg_pill = status_pill(req.urgency_level, kind=urg_kind)

        items_html.append(
            f'<div class="request-item">'
            f'<div class="request-item-left">{chip}<span class="request-item-hospital">{html.escape(req.hospital_name)}</span>'
            f'<span style="font-family:var(--font-mono); font-size:12px; color:var(--ink-2);">{req.units_requested} units</span></div>'
            f'<div class="request-item-right">{urg_pill}<span class="request-item-age">{age_str}</span></div>'
            f'</div>'
        )

    render_html("".join(items_html))


def render_central_stock_bars(stock_counts: Dict[str, int], min_level: int = 5) -> None:
    """Render horizontal bar per blood type with a minimum-stock marker line."""
    blood_types = [bt.value for bt in BloodType]
    max_count = max(max(stock_counts.values(), default=1), 20)

    rows_html = []
    for bt in blood_types:
        count = stock_counts.get(bt, 0)
        pct = min(100.0, (count / max_count) * 100.0)
        marker_pct = min(100.0, (min_level / max_count) * 100.0)
        fill_class = "stock-bar-fill low" if count <= min_level else "stock-bar-fill"
        display_bt = bt.replace("-", "−")

        rows_html.append(
            f'<div class="stock-bar-row">'
            f'<span class="stock-bar-label">{html.escape(display_bt)}</span>'
            f'<div class="stock-bar-track">'
            f'<div class="{fill_class}" style="width: {pct:.1f}%;"></div>'
            f'<div class="stock-bar-marker" style="left: {marker_pct:.1f}%;" title="Min threshold: {min_level} units"></div>'
            f'</div>'
            f'<span class="stock-bar-value">{count} <span style="color:var(--ink-2);font-size:10px;">units</span></span>'
            f'</div>'
        )

    render_html("".join(rows_html))


def generate_sparkline_svg(temp_history: List[Any], width: int = 70, height: int = 18) -> str:
    """Generate tiny inline SVG sparkline for cold-chain temperature telemetry."""
    if not temp_history or len(temp_history) < 2:
        return ""
    temps = [pt[1] for pt in temp_history]
    min_t, max_t = min(temps), max(temps)
    if max_t == min_t:
        max_t += 1.0
        min_t -= 1.0

    points = []
    has_breach = False
    for i, t in enumerate(temps):
        x = (i / (len(temps) - 1)) * (width - 4) + 2
        y = height - 2 - ((t - min_t) / (max_t - min_t)) * (height - 4)
        points.append(f"{x:.1f},{y:.1f}")
        if t < 1.0 or t > 10.0:
            has_breach = True

    stroke_color = "#B3261E" if has_breach else "#2F5D8A"
    poly = " ".join(points)
    return (
        f'<svg width="{width}" height="{height}" style="vertical-align: middle; margin-left: 6px;">'
        f'<polyline fill="none" stroke="{stroke_color}" stroke-width="1.5" points="{poly}" />'
        f'</svg>'
    )


def render_deliveries_list(delivery_agents: Dict[str, Any], city_network: Any) -> None:
    """Render delivery vehicles as one row per vehicle (route, progress, ETA, temperature, status)."""
    vehicles = [
        d for d in delivery_agents.values()
        if d.is_accepted and d.destination_node
    ]

    if not vehicles:
        render_html(
            '<div style="padding: 18px 14px; border: 1px dashed var(--line); border-radius: 6px; text-align: center; color: var(--ink-2);">'
            'No vehicles currently dispatched.'
            '</div>'
        )
        return

    rows_html = []
    for dev in vehicles:
        num_edges = max(1, len(dev.route) - 1)
        completed_edges = dev.current_route_index + max(0.0, min(1.0, dev.edge_progress))

        if dev.is_completed:
            status_kind = "ok"
            status_label = "Delivered"
            eta = 0.0
            progress_pct = 100.0
        elif dev.is_quarantined:
            status_kind = "critical"
            status_label = "Quarantined"
            eta = dev.calculate_remaining_eta()
            progress_pct = min(100.0, max(0.0, (completed_edges / num_edges) * 100.0))
        elif dev.is_backup:
            status_kind = "warn"
            status_label = "Backup en route"
            eta = dev.calculate_remaining_eta()
            progress_pct = min(100.0, max(0.0, (completed_edges / num_edges) * 100.0))
        else:
            status_kind = "info"
            status_label = "En route"
            eta = dev.calculate_remaining_eta()
            progress_pct = min(100.0, max(0.0, (completed_edges / num_edges) * 100.0))

        pill = status_pill(status_label, kind=status_kind)

        # Route formatting: CBB → J1 → J3 → City General
        route_hops = []
        for node_id in dev.route:
            node = city_network.get_node(node_id)
            if node_id == "CBB":
                route_hops.append("CBB")
            elif node_id == "RBB":
                route_hops.append("RBB")
            elif node_id.startswith("H") and node:
                route_hops.append(node.name)
            else:
                route_hops.append(node_id)
        route_str = " &rarr; ".join(route_hops)

        temp = dev.current_temp
        progress_color = 'var(--status-ok)' if dev.is_completed else ('var(--accent)' if dev.is_quarantined else 'var(--status-info)')
        temp_color = 'var(--accent)' if (temp < 1.0 or temp > 10.0) else 'var(--ink)'
        sparkline = generate_sparkline_svg(dev.temperature_history, width=54, height=14)

        rows_html.append(
            f'<div class="delivery-row">'
            f'<div class="delivery-col-id">'
            f'<span class="mono" style="font-weight:600; font-size:13px; color:var(--ink);">{html.escape(dev.agent_id)}</span>'
            f'{pill}'
            f'</div>'
            f'<div class="delivery-col-route" title="{route_str}">'
            f'<span style="color:var(--ink-2); font-size:11px; text-transform:uppercase; font-weight:600; margin-right:4px;">Route</span>'
            f'<span>{route_str}</span>'
            f'</div>'
            f'<div class="delivery-col-progress">'
            f'<div class="progress-bar-wrap">'
            f'<div class="progress-bar-fill" style="width:{progress_pct:.1f}%; background-color:{progress_color};"></div>'
            f'</div>'
            f'<span class="mono" style="font-size:11px; color:var(--ink-2); width:32px; text-align:right;">{progress_pct:.0f}%</span>'
            f'</div>'
            f'<div class="delivery-col-eta">'
            f'<span style="color:var(--ink-2); font-size:11px; margin-right:4px;">ETA</span>'
            f'<b class="mono" style="font-size:12px;">{eta:.1f} min</b>'
            f'</div>'
            f'<div class="delivery-col-temp">'
            f'<span style="color:var(--ink-2); font-size:11px; margin-right:4px;">Temp</span>'
            f'<b class="mono" style="font-size:12px; color:{temp_color};">{temp:.1f} °C</b>'
            f'{sparkline}'
            f'</div>'
            f'</div>'
        )

    render_html(f'<div class="delivery-list">{"".join(rows_html)}</div>')


def generate_allocation_summary(decisions: List[AllocationDecision]) -> str:
    """Generate a one-sentence plain-English explanation under the allocation table."""
    if not decisions:
        return "No allocation decisions processed yet."

    served_first = next((d for d in decisions if d.outcome == AllocationOutcome.FULFILLED), None)
    refused_one = next((d for d in decisions if d.outcome == AllocationOutcome.REFUSED), None)

    parts = []
    if served_first:
        parts.append(
            f"{served_first.hospital_name} was served first: "
            f"{served_first.units_allocated} units {served_first.blood_type_requested.replace('-', '−')} allocated "
            f"({served_first.reason.lower()})"
        )
    if refused_one:
        parts.append(
            f"{refused_one.hospital_name} was refused: {refused_one.reason.lower()}"
        )

    if parts:
        return ". ".join(parts) + "."

    total = len(decisions)
    fulfilled = sum(1 for d in decisions if d.outcome == AllocationOutcome.FULFILLED)
    return f"Processed {total} requirements: {fulfilled} fulfilled under multi-criteria priority scoring."


def render_allocation_table(decisions: List[AllocationDecision]) -> None:
    """Render allocation decision table with score breakdown bars and plain explanation."""
    if not decisions:
        render_html(
            '<div style="padding: 24px 16px; border: 1px dashed var(--line); border-radius: 6px; text-align: center; color: var(--ink-2);">'
            'No allocation decisions processed yet. Run allocation from the sidebar.'
            '</div>'
        )
        return

    table_rows = []
    for d in decisions:
        b = d.score_breakdown
        outcome_kind = {
            AllocationOutcome.FULFILLED: "ok",
            AllocationOutcome.PARTIAL: "warn",
            AllocationOutcome.REFUSED: "critical",
        }.get(d.outcome, "neutral")

        outcome_text = {
            AllocationOutcome.FULFILLED: "Fulfilled",
            AllocationOutcome.PARTIAL: "Partial",
            AllocationOutcome.REFUSED: "Refused",
        }.get(d.outcome, str(d.outcome.value))

        pill = status_pill(outcome_text, kind=outcome_kind)

        tot = max(b.total_score, 0.001)
        p_urg = (b.urgency_term / tot) * 100.0
        p_tim = (b.time_to_need_term / tot) * 100.0
        p_def = (b.deficit_term / tot) * 100.0
        p_rar = (b.rarity_term / tot) * 100.0
        p_wai = (b.waiting_term / tot) * 100.0

        tooltip_text = (
            f"Urgency: {b.urgency_term:.2f} | Time: {b.time_to_need_term:.2f} | "
            f"Deficit: {b.deficit_term:.2f} | Rarity: {b.rarity_term:.2f} | Waiting: {b.waiting_term:.2f}"
        )

        stacked_bar = (
            f'<div style="display: flex; flex-direction: column; gap: 2px;">'
            f'<div style="display: flex; height: 8px; width: 130px; border-radius: 3px; overflow: hidden; background: var(--surface-2); border: 1px solid var(--line);" title="{tooltip_text}">'
            f'<div style="width: {p_urg:.1f}%; background-color: #B3261E;" title="Urgency: {b.urgency_term:.2f}"></div>'
            f'<div style="width: {p_tim:.1f}%; background-color: #2F5D8A;" title="Time: {b.time_to_need_term:.2f}"></div>'
            f'<div style="width: {p_def:.1f}%; background-color: #B7791F;" title="Deficit: {b.deficit_term:.2f}"></div>'
            f'<div style="width: {p_rar:.1f}%; background-color: #6B46C1;" title="Rarity: {b.rarity_term:.2f}"></div>'
            f'<div style="width: {p_wai:.1f}%; background-color: #2E7D4F;" title="Waiting: {b.waiting_term:.2f}"></div>'
            f'</div>'
            f'<span class="mono" style="font-size: 11px; color: var(--ink-2);">{b.total_score:.3f}</span>'
            f'</div>'
        )

        subst_text = d.substituted_type.replace("-", "−") if d.substituted_type else "None (Exact)"

        row_html = (
            f'<tr>'
            f'<td class="mono" style="font-weight:600; text-align:center;">#{d.rank}</td>'
            f'<td class="mono" style="color:var(--ink-2);">{html.escape(d.request_id)}</td>'
            f'<td style="font-weight:500;">{html.escape(d.hospital_name)}</td>'
            f'<td>{blood_chip(d.blood_type_requested)}</td>'
            f'<td class="mono" style="text-align:right;">{d.units_requested}</td>'
            f'<td class="mono" style="text-align:right;">{d.units_allocated}</td>'
            f'<td><span style="font-size:12px;color:var(--ink-2);">{html.escape(subst_text)}</span></td>'
            f'<td>{stacked_bar}</td>'
            f'<td>{pill}</td>'
            f'<td style="font-size:12px; color:var(--ink-2);">{html.escape(d.reason)}</td>'
            f'</tr>'
        )
        table_rows.append(row_html)

    legend_html = (
        '<div style="font-size: 11px; color: var(--ink-2); margin-top: 4px; margin-bottom: 8px;">'
        'Score breakdown: '
        '<span style="color:#B3261E; font-weight:600;">■</span> Urgency &middot; '
        '<span style="color:#2F5D8A; font-weight:600;">■</span> Time to need &middot; '
        '<span style="color:#B7791F; font-weight:600;">■</span> Deficit &middot; '
        '<span style="color:#6B46C1; font-weight:600;">■</span> Rarity &middot; '
        '<span style="color:#2E7D4F; font-weight:600;">■</span> Waiting'
        '</div>'
    )

    html_code = (
        f'{legend_html}'
        f'<div class="log-table-container">'
        f'<table class="log-table">'
        f'<thead><tr>'
        f'<th style="width: 45px; text-align:center;">Rank</th>'
        f'<th style="width: 95px;">Request ID</th>'
        f'<th>Hospital</th>'
        f'<th style="width: 70px;">Type</th>'
        f'<th style="width: 45px; text-align:right;">Req</th>'
        f'<th style="width: 45px; text-align:right;">Alloc</th>'
        f'<th style="width: 100px;">Substitution</th>'
        f'<th style="width: 140px;">Score Breakdown</th>'
        f'<th style="width: 85px;">Outcome</th>'
        f'<th>Clinical Reason</th>'
        f'</tr></thead>'
        f'<tbody>{"".join(table_rows)}</tbody>'
        f'</table>'
        f'</div>'
    )
    render_html(html_code)

    explanation = generate_allocation_summary(decisions)
    st.markdown(
        f'<div style="margin-top: 8px; font-size: 12px; color: var(--ink-2); font-style: italic;">{html.escape(explanation)}</div>',
        unsafe_allow_html=True,
    )


def render_message_log_table(filtered_records: List[Dict[str, Any]], hospitals_map: Optional[Dict[str, Any]] = None) -> None:
    """Render message log as a clean table with conversation left border and status pills."""
    if not filtered_records:
        render_html(
            '<div style="padding: 24px 16px; border: 1px dashed var(--line); border-radius: 6px; text-align: center; color: var(--ink-2);">'
            'No messages match the current filter criteria.'
            '</div>'
        )
        return

    conv_border_colors = [
        "#2F5D8A", "#2E7D4F", "#B7791F", "#6B46C1", "#B3261E",
        "#0D9488", "#475569", "#D97706", "#2563EB", "#9333EA",
    ]
    conv_color_map = {}
    curr_color_idx = 0

    table_rows = []
    for r in filtered_records:
        conv_id = r.get("conversation_id") or "SYSTEM"
        if conv_id not in conv_color_map:
            conv_color_map[conv_id] = conv_border_colors[curr_color_idx % len(conv_border_colors)]
            curr_color_idx += 1
        border_col = conv_color_map[conv_id]

        perf = r.get("performative", "UNKNOWN")
        perf_kind = {
            "REQUEST": "info",
            "INFORM": "ok",
            "ACCEPT": "ok",
            "REFUSE": "critical",
            "REJECT": "critical",
            "BREACH_ALERT": "critical",
            "STATUS_UPDATE": "neutral",
            "QUARANTINE": "warn",
            "BACKUP_REQUEST": "info",
            "DELIVERED": "ok",
            "ACK": "ok",
            "DISPATCH": "info",
        }.get(perf, "neutral")

        icon_name = "alert" if perf in ["BREACH_ALERT", "QUARANTINE"] else None
        pill = status_pill(perf, kind=perf_kind, icon=icon_name)

        time_str = f"T+{int(r.get('timestamp', 0)):02d}"
        from_name = format_agent_name(r.get("sender", ""), hospitals_map)
        to_name = format_agent_name(r.get("receiver", ""), hospitals_map)
        summary_text = r.get("summary", "")

        row_html = (
            f'<tr style="border-left: 3px solid {border_col};">'
            f'<td class="mono" style="width: 55px; color: var(--ink-2);">{time_str}</td>'
            f'<td style="white-space: nowrap; font-weight: 500;">{html.escape(from_name)} &rarr; {html.escape(to_name)}</td>'
            f'<td style="width: 125px;">{pill}</td>'
            f'<td style="color: var(--ink);">{html.escape(summary_text)}</td>'
            f'<td class="mono" style="width: 105px; color: var(--ink-2); font-size: 11px;">{html.escape(conv_id)}</td>'
            f'</tr>'
        )
        table_rows.append(row_html)

    html_code = (
        f'<div class="log-table-container">'
        f'<table class="log-table">'
        f'<thead><tr>'
        f'<th style="width: 55px;">Time</th>'
        f'<th>From &rarr; To</th>'
        f'<th style="width: 125px;">Type</th>'
        f'<th>Details</th>'
        f'<th style="width: 105px;">Conversation</th>'
        f'</tr></thead>'
        f'<tbody>{"".join(table_rows)}</tbody>'
        f'</table>'
        f'</div>'
    )
    render_html(html_code)

"""
Action distribution chart components for the evolution dashboard.
"""

from __future__ import annotations

from typing import Optional

try:
    import plotly.graph_objects as go
    _PLOTLY_AVAILABLE = True
except ImportError:
    _PLOTLY_AVAILABLE = False

_DARK_COLORS = [
    "#00d4ff", "#ff6b6b", "#ffd93d", "#6bcb77", "#c77dff",
    "#f77f00", "#4ecdc4", "#ff9ff3", "#a8dadc", "#e63946",
]


def render_action_distribution(actions_by_type: dict) -> Optional[object]:
    """
    Horizontal bar chart of action counts sorted descending.

    Args:
        actions_by_type: {"move": 120, "eat": 45, ...}
    """
    if not _PLOTLY_AVAILABLE or not actions_by_type:
        return None

    sorted_items = sorted(actions_by_type.items(), key=lambda kv: kv[1], reverse=True)
    labels = [k for k, _ in sorted_items]
    counts = [v for _, v in sorted_items]

    fig = go.Figure(go.Bar(
        x=counts,
        y=labels,
        orientation="h",
        marker_color=_DARK_COLORS[:len(labels)],
        text=counts,
        textposition="outside",
    ))
    fig.update_layout(
        title="Action Distribution",
        xaxis_title="Count",
        height=max(200, 60 + len(labels) * 30),
        margin={"l": 20, "r": 40, "t": 40, "b": 20},
        plot_bgcolor="#1a1a2e",
        paper_bgcolor="#16213e",
        font_color="white",
        yaxis={"autorange": "reversed"},
    )
    return fig


def render_per_agent_actions(by_agent: dict) -> Optional[object]:
    """
    Stacked bar chart: agents on x-axis, action types as colored segments.

    Args:
        by_agent: {"agent_0": {"move": 30, "eat": 10, ...}, ...}
    """
    if not _PLOTLY_AVAILABLE or not by_agent:
        return None

    # Collect all action types across agents
    all_types: set[str] = set()
    for actions in by_agent.values():
        all_types.update(actions.keys())
    all_types_sorted = sorted(all_types)

    agents = sorted(by_agent.keys())

    fig = go.Figure()
    for i, action_type in enumerate(all_types_sorted):
        values = [by_agent[a].get(action_type, 0) for a in agents]
        fig.add_trace(go.Bar(
            name=action_type,
            x=agents,
            y=values,
            marker_color=_DARK_COLORS[i % len(_DARK_COLORS)],
        ))

    fig.update_layout(
        barmode="stack",
        title="Actions per Agent",
        xaxis_title="Agent",
        yaxis_title="Count",
        height=350,
        margin={"l": 20, "r": 20, "t": 40, "b": 60},
        plot_bgcolor="#1a1a2e",
        paper_bgcolor="#16213e",
        font_color="white",
        legend={"bgcolor": "#1a1a2e", "bordercolor": "#444"},
    )
    return fig

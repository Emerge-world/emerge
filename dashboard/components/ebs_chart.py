"""
EBS chart components: radar chart for EBS sub-components and
generation timeline line chart.
"""

from __future__ import annotations

from typing import Optional

try:
    import plotly.graph_objects as go
    _PLOTLY_AVAILABLE = True
except ImportError:
    _PLOTLY_AVAILABLE = False


def render_ebs_radar(ebs_data: dict) -> Optional[object]:
    """
    Render a radar chart of EBS components for a single node/run.

    Args:
        ebs_data: dict like {"components": {"novelty": {"score": 70}, ...}, "ebs": 55.0}
    """
    if not _PLOTLY_AVAILABLE:
        return None

    components = ebs_data.get("components", {})
    if not components:
        return go.Figure().update_layout(title="No EBS component data")

    cats = list(components.keys())
    values = [components[c].get("score", 0) if isinstance(components[c], dict) else components[c]
              for c in cats]
    # Close the radar chart
    cats_closed = cats + [cats[0]]
    values_closed = values + [values[0]]

    fig = go.Figure(go.Scatterpolar(
        r=values_closed,
        theta=cats_closed,
        fill="toself",
        line_color="#00d4ff",
        fillcolor="rgba(0,212,255,0.2)",
        name="EBS Components",
    ))
    fig.update_layout(
        polar={
            "radialaxis": {"visible": True, "range": [0, 100]},
            "bgcolor": "#1a1a2e",
        },
        showlegend=False,
        title=f"EBS: {ebs_data.get('ebs', 0):.1f}",
        height=350,
        margin={"l": 30, "r": 30, "t": 50, "b": 30},
        paper_bgcolor="#16213e",
        font_color="white",
    )
    return fig


def render_generation_timeline(tree_data: dict) -> Optional[object]:
    """
    Line chart: mean EBS per generation (with std deviation bands).
    """
    if not _PLOTLY_AVAILABLE:
        return None

    nodes = tree_data.get("nodes", {})
    if not nodes:
        return go.Figure().update_layout(title="No data")

    # Aggregate by generation
    gen_ebs: dict[int, list[float]] = {}
    for node in nodes.values():
        gen = node.get("generation", 0)
        ebs = node.get("mean_ebs", 0)
        gen_ebs.setdefault(gen, []).append(ebs)

    generations = sorted(gen_ebs.keys())
    mean_vals, std_vals = [], []
    for g in generations:
        vals = gen_ebs[g]
        mean = sum(vals) / len(vals)
        std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5 if len(vals) > 1 else 0
        mean_vals.append(mean)
        std_vals.append(std)

    upper = [m + s for m, s in zip(mean_vals, std_vals)]
    lower = [m - s for m, s in zip(mean_vals, std_vals)]

    fig = go.Figure()

    # Std band
    fig.add_trace(go.Scatter(
        x=generations + generations[::-1],
        y=upper + lower[::-1],
        fill="toself",
        fillcolor="rgba(0,212,255,0.15)",
        line={"color": "rgba(255,255,255,0)"},
        hoverinfo="skip",
        name="±1 std",
    ))

    # Mean line
    fig.add_trace(go.Scatter(
        x=generations,
        y=mean_vals,
        mode="lines+markers",
        line={"color": "#00d4ff", "width": 2},
        marker={"size": 8},
        name="Mean EBS",
        hovertemplate="Gen %{x}: EBS %{y:.1f}<extra></extra>",
    ))

    fig.update_layout(
        title="Mean EBS Across Generations",
        xaxis_title="Generation",
        yaxis_title="EBS",
        yaxis={"range": [0, 100]},
        showlegend=True,
        height=300,
        margin={"l": 30, "r": 20, "t": 40, "b": 30},
        plot_bgcolor="#1a1a2e",
        paper_bgcolor="#16213e",
        font_color="white",
    )
    return fig

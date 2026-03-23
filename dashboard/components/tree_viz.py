"""
Evolution tree visualization component using Plotly.
Renders nodes colored by EBS score, with edges showing lineage.
"""

from __future__ import annotations

from typing import Optional

try:
    import plotly.graph_objects as go
    _PLOTLY_AVAILABLE = True
except ImportError:
    _PLOTLY_AVAILABLE = False


def render_tree(tree_data: dict) -> Optional[object]:
    """
    Render the evolution tree as an interactive Plotly figure.

    Args:
        tree_data: parsed tree.json dict

    Returns:
        plotly.graph_objects.Figure or None if plotly is unavailable
    """
    if not _PLOTLY_AVAILABLE:
        return None

    nodes = tree_data.get("nodes", {})
    if not nodes:
        return go.Figure().update_layout(title="No nodes to display")

    # Layout: nodes by generation on x-axis, spread on y-axis
    gen_counts: dict[int, list[str]] = {}
    for nid, node in nodes.items():
        gen = node.get("generation", 0)
        gen_counts.setdefault(gen, []).append(nid)

    positions = {}
    for gen, nids in gen_counts.items():
        n = len(nids)
        for i, nid in enumerate(nids):
            y = (i - (n - 1) / 2) * 2  # spread evenly
            positions[nid] = (gen, y)

    # Build edge traces
    edge_x, edge_y = [], []
    for nid, node in nodes.items():
        parent = node.get("parent")
        if parent and parent in positions:
            px, py = positions[parent]
            cx, cy = positions[nid]
            edge_x += [px, cx, None]
            edge_y += [py, cy, None]

    # Build node traces — colored by EBS (green=high, red=low)
    node_x, node_y, node_text, node_colors, node_sizes, node_ids = [], [], [], [], [], []
    max_ebs = max((n.get("mean_ebs", 0) for n in nodes.values()), default=1) or 1

    for nid, node in nodes.items():
        x, y = positions[nid]
        ebs = node.get("mean_ebs", 0)
        selected = node.get("selected", False)
        n_runs = len(node.get("runs", []))

        node_x.append(x)
        node_y.append(y)
        node_ids.append(nid)
        node_text.append(
            f"{nid}<br>EBS: {ebs:.1f}<br>std: {node.get('std_ebs', 0):.1f}<br>runs: {n_runs}"
            + ("<br>★ SELECTED" if selected else "")
        )
        # Color: green for high EBS, red for low
        ratio = ebs / max_ebs if max_ebs > 0 else 0
        r = int(255 * (1 - ratio))
        g = int(200 * ratio)
        node_colors.append(f"rgb({r},{g},80)")
        # Selected nodes are larger
        node_sizes.append(18 if selected else 12)

    fig = go.Figure()

    # Edges
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y,
        mode="lines",
        line={"color": "#aaa", "width": 1},
        hoverinfo="none",
        name="lineage",
    ))

    # Nodes
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        marker={
            "size": node_sizes,
            "color": node_colors,
            "line": {"color": "white", "width": 1},
        },
        text=[nid.split("_")[-1] for nid in nodes],
        textposition="top center",
        hovertext=node_text,
        hoverinfo="text",
        customdata=node_ids,
        name="variants",
    ))

    fig.update_layout(
        title="Evolution Tree — nodes colored by EBS (green=high, red=low)",
        xaxis_title="Generation",
        yaxis={"showticklabels": False},
        showlegend=False,
        height=500,
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
        plot_bgcolor="#1a1a2e",
        paper_bgcolor="#16213e",
        font_color="white",
    )

    return fig

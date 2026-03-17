"""
World preview component: renders a 2D tile map from a WorldSchema.
"""

from __future__ import annotations

from typing import Optional

try:
    import plotly.graph_objects as go
    _PLOTLY_AVAILABLE = True
except ImportError:
    _PLOTLY_AVAILABLE = False

# Tile type → RGB color
_TILE_COLORS: dict[str, str] = {
    "water":    "#1a6b9a",
    "river":    "#4aa3d8",
    "sand":     "#d4b483",
    "land":     "#5a8a3c",
    "tree":     "#2d6a1f",
    "forest":   "#1a4d12",
    "mountain": "#8a7a6a",
    "cave":     "#5a4a3a",
}
_DEFAULT_COLOR = "#9a7a5a"  # unknown tile types


def render_world(schema_data: dict) -> Optional[object]:
    """
    Render a schematic world tile map from a world schema YAML dict.
    Uses a grid of colored rectangles (one per tile type distribution).

    Note: this is a schematic preview based on tile types — it does not
    run the full Perlin-noise generation. It shows approximate frequency.
    """
    if not _PLOTLY_AVAILABLE:
        return None

    tiles = schema_data.get("tiles", {})
    if not tiles:
        return go.Figure().update_layout(title="No tile data")

    # Compute area fraction per tile type from height_max thresholds
    sorted_tiles = [
        (name, cfg)
        for name, cfg in tiles.items()
        if not name.startswith("_") and isinstance(cfg, dict) and cfg.get("height_max") is not None
    ]
    sorted_tiles.sort(key=lambda t: t[1]["height_max"])

    prev_h = 0.0
    fractions = []
    for name, cfg in sorted_tiles:
        h = cfg["height_max"]
        fractions.append((name, h - prev_h))
        prev_h = h
    if prev_h < 1.0:
        overflow = schema_data.get("tiles", {}).get("_overflow", "mountain")
        fractions.append((overflow, 1.0 - prev_h))

    # Build bar chart (tile type distribution)
    names = [f[0] for f in fractions]
    values = [f[1] * 100 for f in fractions]  # percentage
    colors = [_TILE_COLORS.get(n, _DEFAULT_COLOR) for n in names]

    fig = go.Figure(go.Bar(
        x=values,
        y=names,
        orientation="h",
        marker_color=colors,
        text=[f"{v:.1f}%" for v in values],
        textposition="auto",
        hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
    ))

    fig.update_layout(
        title="Tile Type Distribution (from height thresholds)",
        xaxis_title="% of world area",
        yaxis_title="",
        height=350,
        margin={"l": 10, "r": 10, "t": 40, "b": 30},
        plot_bgcolor="#1a1a2e",
        paper_bgcolor="#16213e",
        font_color="white",
    )

    return fig


def render_resource_summary(schema_data: dict) -> str:
    """Return a markdown summary of resources defined in the schema."""
    resources = schema_data.get("resources", {})
    if not resources:
        return "_No resources defined_"
    lines = ["| Resource | Edible | Hunger - | Life Δ | Inexhaustible |",
             "|----------|--------|----------|--------|---------------|"]
    for name, cfg in resources.items():
        if not isinstance(cfg, dict):
            continue
        edible = "✓" if cfg.get("edible") else "✗"
        hunger = cfg.get("hunger_reduction", 0)
        life = cfg.get("life_change", 0)
        inexh = "✓" if cfg.get("inexhaustible") else "✗"
        lines.append(f"| {name} | {edible} | {hunger} | {life:+d} | {inexh} |")
    return "\n".join(lines)

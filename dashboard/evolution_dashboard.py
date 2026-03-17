"""
Evolution Dashboard — Streamlit app for visualizing the Emerge evolution tree.

Launch:
    uv run streamlit run dashboard/evolution_dashboard.py -- --tree data/evolution/evo_.../tree.json
    uv run streamlit run dashboard/evolution_dashboard.py   # auto-detects latest tree
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

import streamlit as st
import yaml

# Add project root to path so we can import simulation modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.components.tree_viz import render_tree
from dashboard.components.world_preview import render_world, render_resource_summary
from dashboard.components.ebs_chart import render_ebs_radar, render_generation_timeline


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _find_latest_tree(base_dir: Path) -> Optional[Path]:
    """Return the most recently modified tree.json in base_dir."""
    candidates = sorted(base_dir.glob("*/tree.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


@st.cache_data(ttl=5)
def _load_tree(tree_json_path: str) -> Optional[dict]:
    path = Path(tree_json_path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


@st.cache_data(ttl=10)
def _load_schema(schema_path: str) -> Optional[dict]:
    path = Path(schema_path)
    if not path.exists():
        return None
    try:
        with path.open() as f:
            return yaml.safe_load(f)
    except Exception:
        return None


@st.cache_data(ttl=10)
def _load_ebs(run_dir_path: str, run_id: str) -> Optional[dict]:
    path = Path(run_dir_path) / run_id / "metrics" / "ebs.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _runs_data_dir(tree_json_path: str) -> Path:
    """Guess the runs data directory from tree.json location."""
    # data/evolution/<tree_id>/tree.json → data/runs/
    return Path(tree_json_path).parent.parent.parent / "runs"


# ---------------------------------------------------------------------------
# Page rendering helpers
# ---------------------------------------------------------------------------

def _render_node_detail(tree_json_path: str, node_id: str, node: dict, tree_dir: Path) -> None:
    """Render the detail panel for a selected node."""
    st.subheader(f"Node: {node_id}")
    gen = node.get("generation", "?")
    parent = node.get("parent", "none")
    runs = node.get("runs", [])
    mean_ebs = node.get("mean_ebs", 0)
    std_ebs = node.get("std_ebs", 0)
    selected = node.get("selected", False)

    col1, col2, col3 = st.columns(3)
    col1.metric("Generation", gen)
    col2.metric("Mean EBS", f"{mean_ebs:.1f}", f"±{std_ebs:.1f}")
    col3.metric("Runs", len(runs))
    if selected:
        st.success("★ Selected (survives to next generation)")

    st.write(f"**Parent:** `{parent}`")

    # Mutations
    schema_path = tree_dir / node.get("schema_path", "")
    schema_data = _load_schema(str(schema_path))
    if schema_data:
        mutations = schema_data.get("metadata", {}).get("mutations_applied", [])
        if mutations:
            st.markdown("**Mutations applied:**")
            for m in mutations:
                st.write(f"- {m}")

    # EBS radar
    runs_dir = _runs_data_dir(tree_json_path)
    ebs_data = None
    for run_id in runs:
        ebs_data = _load_ebs(str(runs_dir), run_id)
        if ebs_data:
            break
    if ebs_data:
        fig = render_ebs_radar(ebs_data)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

    # World preview
    if schema_data:
        st.markdown("---")
        st.markdown("**World tile distribution:**")
        fig = render_world(schema_data)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        st.markdown("**Resource definitions:**")
        st.markdown(render_resource_summary(schema_data))


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Emerge — Evolution Dashboard",
        page_icon="🧬",
        layout="wide",
    )

    # --- Parse CLI args (passed after -- in streamlit run command) ---
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--tree", default=None)
    cli_args, _ = parser.parse_known_args()

    # --- Sidebar: tree selection ---
    st.sidebar.title("🧬 Evolution Dashboard")

    evo_dir = Path("data/evolution")
    tree_json_path: Optional[str] = cli_args.tree

    if not tree_json_path:
        if evo_dir.exists():
            tree_files = sorted(evo_dir.glob("*/tree.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if tree_files:
                options = [str(p) for p in tree_files]
                tree_json_path = st.sidebar.selectbox("Select evolution tree", options)
            else:
                st.sidebar.warning(f"No tree.json found in {evo_dir}/")
        else:
            st.sidebar.info(f"No {evo_dir}/ directory found. Run an evolution first.")

    if not tree_json_path:
        st.title("🧬 Emerge — Evolution Dashboard")
        st.info("No evolution tree selected. Pass `--tree path/to/tree.json` or run an evolution first.")
        st.code("uv run run_evolution.py --generations 5 --branches 3 --runs 3 --ticks 200 --no-llm")
        return

    auto_refresh = st.sidebar.checkbox("Auto-refresh (5s)", value=False)
    if auto_refresh:
        time.sleep(5)
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.caption(f"Tree: `{Path(tree_json_path).name}`")

    # --- Load tree ---
    tree_data = _load_tree(tree_json_path)
    if not tree_data:
        st.error(f"Could not load tree: {tree_json_path}")
        return

    tree_dir = Path(tree_json_path).parent
    config = tree_data.get("config", {})
    nodes = tree_data.get("nodes", {})

    # --- Header ---
    st.title(f"🧬 Evolution Tree: `{tree_data.get('tree_id', '?')}`")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Nodes", len(nodes))
    max_gen = max((n.get("generation", 0) for n in nodes.values()), default=0)
    c2.metric("Generations", max_gen + 1)
    c3.metric("Branches/Gen", config.get("branches_per_gen", "?"))
    c4.metric("Runs/Variant", config.get("runs_per_variant", "?"))

    st.markdown("---")

    # --- Tab layout ---
    tab_tree, tab_detail, tab_timeline = st.tabs(["🌳 Tree View", "🔍 Node Detail", "📈 Timeline"])

    with tab_tree:
        fig = render_tree(tree_data)
        if fig:
            event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="tree_chart")
            # Node selection via sidebar
        else:
            st.warning("Install plotly for interactive tree: `uv add plotly`")
            # Fallback: simple table
            rows = []
            for nid, n in nodes.items():
                rows.append({
                    "Node": nid,
                    "Gen": n.get("generation"),
                    "Parent": n.get("parent", "—"),
                    "Mean EBS": f"{n.get('mean_ebs', 0):.1f}",
                    "Runs": len(n.get("runs", [])),
                    "Selected": "★" if n.get("selected") else "",
                })
            st.dataframe(rows, use_container_width=True)

    with tab_detail:
        node_ids = list(nodes.keys())
        if not node_ids:
            st.info("No nodes yet.")
        else:
            selected_node_id = st.selectbox("Select a node", node_ids)
            node = nodes[selected_node_id]
            _render_node_detail(tree_json_path, selected_node_id, node, tree_dir)

    with tab_timeline:
        if len(nodes) < 2:
            st.info("Run at least 2 generations to see the timeline.")
        else:
            fig = render_generation_timeline(tree_data)
            if fig:
                st.plotly_chart(fig, use_container_width=True)

            # Best node per generation table
            st.markdown("**Best variant per generation:**")
            rows = []
            for gen in range(max_gen + 1):
                gen_nodes = [n for n in nodes.values() if n.get("generation") == gen]
                if not gen_nodes:
                    continue
                best = max(gen_nodes, key=lambda n: n.get("mean_ebs", 0))
                nid = next(k for k, v in nodes.items() if v is best)
                rows.append({
                    "Generation": gen,
                    "Best Node": nid,
                    "Mean EBS": f"{best.get('mean_ebs', 0):.1f}",
                    "Std EBS": f"{best.get('std_ebs', 0):.1f}",
                    "Runs": len(best.get("runs", [])),
                    "Selected": "★" if best.get("selected") else "",
                })
            st.dataframe(rows, use_container_width=True)

    # --- Live status sidebar ---
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Live status:**")
    incomplete = [nid for nid, n in nodes.items() if not n.get("runs")]
    running = [nid for nid, n in nodes.items() if n.get("runs") and not n.get("mean_ebs")]
    if incomplete:
        st.sidebar.warning(f"{len(incomplete)} variant(s) pending runs")
    elif running:
        st.sidebar.info(f"{len(running)} variant(s) awaiting EBS finalization")
    else:
        st.sidebar.success("All variants complete")

    total_runs = sum(len(n.get("runs", [])) for n in nodes.values())
    st.sidebar.metric("Total sim runs", total_runs)
    best_ebs = max((n.get("mean_ebs", 0) for n in nodes.values()), default=0)
    st.sidebar.metric("Best EBS so far", f"{best_ebs:.1f}")


if __name__ == "__main__":
    main()

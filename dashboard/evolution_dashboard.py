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
from dashboard.components.action_chart import render_action_distribution, render_per_agent_actions


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


@st.cache_data(ttl=10)
def _load_summary(run_dir_path: str, run_id: str) -> Optional[dict]:
    path = Path(run_dir_path) / run_id / "metrics" / "summary.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


@st.cache_data(ttl=30)
def _load_action_events(run_dir_path: str, run_id: str) -> dict:
    """Stream events.jsonl and aggregate agent_decision events."""
    path = Path(run_dir_path) / run_id / "events.jsonl"
    by_agent: dict[str, dict[str, int]] = {}
    by_type: dict[str, int] = {}
    if not path.exists():
        return {"by_agent": by_agent, "by_type": by_type}
    try:
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if ev.get("event") != "agent_decision":
                    continue
                agent = ev.get("agent_id", "unknown")
                action = ev.get("action_type", "unknown")
                by_agent.setdefault(agent, {})
                by_agent[agent][action] = by_agent[agent].get(action, 0) + 1
                by_type[action] = by_type.get(action, 0) + 1
    except Exception:
        pass
    return {"by_agent": by_agent, "by_type": by_type}


def _runs_data_dir(tree_json_path: str) -> Path:
    """Guess the runs data directory from tree.json location."""
    # data/evolution/<tree_id>/tree.json → data/runs/
    return Path(tree_json_path).parent.parent.parent / "runs"


# ---------------------------------------------------------------------------
# Page rendering helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30)
def _load_prompt_config(json_path: str) -> Optional[dict]:
    path = Path(json_path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _render_prompt_editor(node_id: str, node: dict, tree_dir: Path) -> None:
    """Render a prompt viewer/editor for the selected node."""
    with st.expander("📝 Prompts", expanded=False):
        agent_path_rel = node.get("agent_prompts_path")
        oracle_path_rel = node.get("oracle_prompts_path")

        if not agent_path_rel and not oracle_path_rel:
            st.info("No prompt configs saved for this node (pre-prompt-evolution run).")
            return

        edit_mode = st.toggle("Enable editing", key=f"prompt_edit_{node_id}")
        tab_agent, tab_oracle = st.tabs(["Agent Prompts", "Oracle Prompts"])

        with tab_agent:
            if not agent_path_rel:
                st.info("No agent prompt config for this node.")
            else:
                agent_path = tree_dir / agent_path_rel
                cfg = _load_prompt_config(str(agent_path))
                agent_prompts = (cfg or {}).get("agent_prompts", {})
                if not agent_prompts:
                    st.info("Agent prompts config is empty.")
                else:
                    updated: dict[str, str] = {}
                    for name, text in agent_prompts.items():
                        new_text = st.text_area(
                            label=f"`{name}`",
                            value=text,
                            height=200,
                            key=f"agent_{node_id}_{name}",
                            disabled=not edit_mode,
                        )
                        updated[name] = new_text
                    if edit_mode and st.button("Save agent prompts", key=f"save_agent_{node_id}"):
                        new_cfg = dict(cfg or {})
                        new_cfg["agent_prompts"] = updated
                        agent_path.write_text(
                            json.dumps(new_cfg, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        _load_prompt_config.clear()
                        st.success(f"Saved to `{agent_path_rel}`")

        with tab_oracle:
            if not oracle_path_rel:
                st.info("No oracle prompt config for this node.")
            else:
                oracle_path = tree_dir / oracle_path_rel
                cfg = _load_prompt_config(str(oracle_path))
                oracle_prompts = (cfg or {}).get("oracle_prompts", {})
                if not oracle_prompts:
                    st.info("Oracle prompts config is empty.")
                else:
                    updated_oracle: dict[str, str] = {}
                    for name, text in oracle_prompts.items():
                        new_text = st.text_area(
                            label=f"`{name}`",
                            value=text,
                            height=200,
                            key=f"oracle_{node_id}_{name}",
                            disabled=not edit_mode,
                        )
                        updated_oracle[name] = new_text
                    if edit_mode and st.button("Save oracle prompts", key=f"save_oracle_{node_id}"):
                        new_cfg = dict(cfg or {})
                        new_cfg["oracle_prompts"] = updated_oracle
                        oracle_path.write_text(
                            json.dumps(new_cfg, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        _load_prompt_config.clear()
                        st.success(f"Saved to `{oracle_path_rel}`")


def _render_node_detail(tree_json_path: str, node_id: str, node: dict, tree_dir: Path) -> None:
    """Render the detail panel for a selected node."""
    st.subheader(f"Node: {node_id}")
    gen = node.get("generation", "?")
    parent = node.get("parent", "none")
    runs = node.get("runs", [])
    mean_ebs = node.get("mean_ebs", 0)
    std_ebs = node.get("std_ebs", 0)
    selected = node.get("selected", False)

    # --- Header ---
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

    runs_dir = _runs_data_dir(tree_json_path)

    # --- Run Overview ---
    with st.expander("📊 Run Overview", expanded=True):
        if not runs:
            st.info("No runs recorded for this node.")
        else:
            rows = []
            ebs_list = []
            for run_id in runs:
                summary = _load_summary(str(runs_dir), run_id)
                ebs_data = _load_ebs(str(runs_dir), run_id)
                ebs_val = ebs_data.get("ebs", 0) if ebs_data else 0
                ebs_list.append((ebs_data, ebs_val))

                row: dict = {"Run ID": run_id, "EBS": f"{ebs_val:.1f}"}
                if summary:
                    row["Survival Rate"] = f"{summary.get('survival_rate', 0):.0%}"
                    row["Ticks"] = summary.get("ticks", "?")
                    row["Total Actions"] = summary.get("total_actions", "?")
                    oracle = summary.get("oracle", {})
                    success = oracle.get("success_rate", None)
                    row["Oracle Success %"] = f"{success:.0%}" if success is not None else "?"
                    parse_fail = oracle.get("parse_fail_rate", None)
                    row["Parse Fail %"] = f"{parse_fail:.0%}" if parse_fail is not None else "?"
                    inno = summary.get("innovations", {})
                    row["Innovations Approved"] = inno.get("approved", "?")
                else:
                    row.update({"Survival Rate": "?", "Ticks": "?", "Total Actions": "?",
                                "Oracle Success %": "?", "Parse Fail %": "?", "Innovations Approved": "?"})
                rows.append(row)

            st.dataframe(rows, use_container_width=True)

            # EBS radar for first run that has data
            for ebs_data, _ in ebs_list:
                if ebs_data:
                    fig = render_ebs_radar(ebs_data)
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)
                    break

    # --- Innovations ---
    with st.expander("💡 Innovations", expanded=True):
        total_attempts = 0
        total_approved = 0
        total_rejected = 0
        total_realized = 0
        all_innovations: list[dict] = []

        for run_id in runs:
            summary = _load_summary(str(runs_dir), run_id)
            if summary:
                inno = summary.get("innovations", {})
                total_attempts += inno.get("attempts", 0)
                total_approved += inno.get("approved", 0)
                total_rejected += inno.get("rejected", 0)
                total_realized += inno.get("realized", 0)
            ebs_data = _load_ebs(str(runs_dir), run_id)
            if ebs_data:
                for inno_entry in ebs_data.get("innovations", []):
                    all_innovations.append(inno_entry)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Attempts", total_attempts)
        c2.metric("Approved", total_approved)
        c3.metric("Rejected", total_rejected)
        c4.metric("Realized", total_realized)
        if total_attempts > 0:
            approval_rate = total_approved / total_attempts
            st.write(f"Approval rate: **{approval_rate:.0%}**")

        if all_innovations:
            st.markdown("**Individual innovations:**")
            for entry in all_innovations:
                st.write(f"- {entry}")
        elif total_attempts == 0:
            st.info("No innovation data found for this node.")

    # --- Agent Actions ---
    with st.expander("🎯 Agent Actions", expanded=True):
        # Aggregate actions.by_type from all summary.json
        agg_by_type: dict[str, int] = {}
        for run_id in runs:
            summary = _load_summary(str(runs_dir), run_id)
            if summary:
                for action_type, count in summary.get("actions", {}).get("by_type", {}).items():
                    agg_by_type[action_type] = agg_by_type.get(action_type, 0) + count

        if agg_by_type:
            fig = render_action_distribution(agg_by_type)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No action data in summary.json for this node.")

        show_per_agent = st.checkbox("Show per-agent breakdown (loads events.jsonl)", key=f"per_agent_{node_id}")
        if show_per_agent:
            agg_by_agent: dict[str, dict[str, int]] = {}
            for run_id in runs:
                events = _load_action_events(str(runs_dir), run_id)
                for agent, actions in events.get("by_agent", {}).items():
                    agg_by_agent.setdefault(agent, {})
                    for action_type, count in actions.items():
                        agg_by_agent[agent][action_type] = agg_by_agent[agent].get(action_type, 0) + count
            if agg_by_agent:
                fig = render_per_agent_actions(agg_by_agent)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No per-agent event data found.")

    # --- World Schema ---
    with st.expander("🗺️ World Schema", expanded=True):
        if schema_data:
            st.markdown("**World tile distribution:**")
            fig = render_world(schema_data)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            st.markdown("**Resource definitions:**")
            st.markdown(render_resource_summary(schema_data))
        else:
            st.info("No schema data available for this node.")

    # --- Prompts ---
    _render_prompt_editor(node_id, node, tree_dir)


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

    # --- Sidebar: jump-to-node fallback ---
    node_ids_list = list(nodes.keys())
    st.sidebar.markdown("---")
    jump_node = st.sidebar.selectbox(
        "Jump to node",
        ["(click tree or select)"] + node_ids_list,
        key="jump_node",
    )
    if jump_node != "(click tree or select)":
        st.session_state.selected_node = jump_node

    # --- Tab layout ---
    tab_tree, tab_timeline = st.tabs(["🌳 Tree View", "📈 Timeline"])

    with tab_tree:
        fig = render_tree(tree_data)
        if fig:
            event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="tree_chart")

            # Extract selected node from click event
            if event and hasattr(event, "selection") and event.selection:
                points = event.selection.get("points", [])
                for pt in points:
                    # curve_number 1 = nodes trace (0 = edges)
                    if pt.get("curve_number") == 1:
                        node_id_clicked = pt.get("customdata")
                        if node_id_clicked and node_id_clicked in nodes:
                            st.session_state.selected_node = node_id_clicked
                        break
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

        # --- Detail panel below tree ---
        selected_node = st.session_state.get("selected_node")
        if selected_node and selected_node in nodes:
            st.markdown("---")
            _render_node_detail(tree_json_path, selected_node, nodes[selected_node], tree_dir)
        else:
            st.info("Click a node in the tree above (or use **Jump to node** in the sidebar) to see details.")

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

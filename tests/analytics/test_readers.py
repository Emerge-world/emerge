# tests/analytics/test_readers.py
import pathlib
import pytest
from dashboard.analytics.backend.readers import (
    list_runs, read_meta, read_summary, read_ebs, read_events, read_timeseries,
    list_trees, read_tree,
)


def test_list_runs_returns_run_ids(tmp_runs):
    data_root, run_id = tmp_runs
    runs = list_runs(data_root)
    assert any(r["run_id"] == run_id for r in runs)


def test_list_runs_graceful_without_metrics(tmp_path):
    """Runs missing metrics/ show up with ebs=None."""
    run_id = "2099-02-01_00-00-00_s0_a1_abcd1234"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    import json
    meta = {"run_id": run_id, "seed": 0, "width": 10, "height": 10,
            "max_ticks": 3, "agent_count": 1, "agent_names": ["X"],
            "agent_model_id": "none", "oracle_model_id": "none",
            "git_commit": "abc", "created_at": "2099-02-01T00:00:00",
            "prompt_hashes": {}, "precedents_file": None}
    (run_dir / "meta.json").write_text(json.dumps(meta))
    runs = list_runs(tmp_path)
    result = next(r for r in runs if r["run_id"] == run_id)
    assert result["ebs"] is None
    assert result["survival_rate"] is None


def test_read_meta(tmp_runs):
    data_root, run_id = tmp_runs
    meta = read_meta(data_root / "runs" / run_id)
    assert meta["run_id"] == run_id
    assert meta["agent_names"] == ["Alice", "Bob"]


def test_read_summary(tmp_runs):
    data_root, run_id = tmp_runs
    summary = read_summary(data_root / "runs" / run_id)
    assert summary is not None
    assert summary["agents"]["final_survivors"] == ["Bob"]


def test_read_summary_missing_metrics_returns_none(tmp_path):
    run_dir = tmp_path / "runs" / "orphan"
    run_dir.mkdir(parents=True)
    assert read_summary(run_dir) is None


def test_read_ebs(tmp_runs):
    data_root, run_id = tmp_runs
    ebs = read_ebs(data_root / "runs" / run_id)
    assert ebs is not None
    assert ebs["ebs"] == 62.5
    assert ebs["components"]["novelty"]["score"] == 75.0


def test_read_events_all(tmp_runs):
    data_root, run_id = tmp_runs
    events = read_events(data_root / "runs" / run_id)
    assert len(events) == 4
    types = {e["event_type"] for e in events}
    assert "agent_decision" in types
    assert "innovation_validated" in types


def test_read_events_filter_by_type(tmp_runs):
    data_root, run_id = tmp_runs
    events = read_events(data_root / "runs" / run_id, types=["innovation_validated"])
    assert all(e["event_type"] == "innovation_validated" for e in events)
    assert len(events) == 1


def test_read_events_filter_by_tick_range(tmp_runs):
    data_root, run_id = tmp_runs
    events = read_events(data_root / "runs" / run_id, tick_from=2, tick_to=2)
    assert all(e["tick"] == 2 for e in events)


def test_read_timeseries(tmp_runs):
    data_root, run_id = tmp_runs
    ts = read_timeseries(data_root / "runs" / run_id)
    assert len(ts) == 3
    assert ts[0]["tick"] == 1


def test_list_trees(tmp_path):
    import json
    tree_dir = tmp_path / "evolution" / "evo_test_tree"
    tree_dir.mkdir(parents=True)
    tree = {"tree_id": "evo_test_tree", "config": {}, "nodes": {"n1": {}, "n2": {}}}
    (tree_dir / "tree.json").write_text(json.dumps(tree))
    trees = list_trees(tmp_path)
    assert any(t["tree_id"] == "evo_test_tree" for t in trees)
    result = next(t for t in trees if t["tree_id"] == "evo_test_tree")
    assert result["node_count"] == 2


def test_read_tree(tmp_path):
    import json
    tree_dir = tmp_path / "evolution" / "evo_test_tree"
    tree_dir.mkdir(parents=True)
    tree = {"tree_id": "evo_test_tree", "config": {"branches_per_gen": 3},
            "nodes": {"gen0_base": {"node_id": "gen0_base", "generation": 0,
                                    "parent": None, "runs": [], "selected": False}}}
    (tree_dir / "tree.json").write_text(json.dumps(tree))
    result = read_tree(tmp_path, "evo_test_tree")
    assert result is not None
    assert result["tree_id"] == "evo_test_tree"


def test_read_tree_missing_returns_none(tmp_path):
    assert read_tree(tmp_path, "nonexistent") is None

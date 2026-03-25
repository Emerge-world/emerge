# dashboard/analytics/backend/readers.py
from __future__ import annotations
import json
import pathlib
from typing import Any


DATA_ROOT = pathlib.Path("data")


def _runs_root(data_root: pathlib.Path = DATA_ROOT) -> pathlib.Path:
    return data_root / "runs"


def list_runs(
    data_root: pathlib.Path = DATA_ROOT,
    tree_id: str | None = None,
    node_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    runs_dir = _runs_root(data_root)
    if not runs_dir.exists():
        return []
    results = []
    for run_dir in sorted(runs_dir.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        meta_path = run_dir / "meta.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        summary = read_summary(run_dir)
        ebs_data = read_ebs(run_dir)
        entry: dict[str, Any] = {
            "run_id": meta["run_id"],
            "created_at": meta.get("created_at", ""),
            "total_ticks": summary["total_ticks"] if summary else 0,
            "ebs": ebs_data["ebs"] if ebs_data else None,
            "survival_rate": summary["agents"]["survival_rate"] if summary else None,
            "innovations_approved": summary["innovations"]["approved"] if summary else None,
            "tree_id": meta.get("tree_id"),
            "node_id": meta.get("node_id"),
        }
        if tree_id and entry["tree_id"] != tree_id:
            continue
        if node_id and entry["node_id"] != node_id:
            continue
        results.append(entry)
    return results[offset: offset + limit]


def read_meta(run_dir: pathlib.Path) -> dict[str, Any]:
    return json.loads((run_dir / "meta.json").read_text())


def read_summary(run_dir: pathlib.Path) -> dict[str, Any] | None:
    path = run_dir / "metrics" / "summary.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def read_ebs(run_dir: pathlib.Path) -> dict[str, Any] | None:
    path = run_dir / "metrics" / "ebs.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def read_events(
    run_dir: pathlib.Path,
    tick_from: int | None = None,
    tick_to: int | None = None,
    types: list[str] | None = None,
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    path = run_dir / "events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        evt = json.loads(line)
        if tick_from is not None and evt["tick"] < tick_from:
            continue
        if tick_to is not None and evt["tick"] > tick_to:
            continue
        if types and evt["event_type"] not in types:
            continue
        if agent_id and evt.get("agent_id") != agent_id:
            continue
        events.append(evt)
    return events


def read_timeseries(run_dir: pathlib.Path) -> list[dict[str, Any]]:
    path = run_dir / "metrics" / "timeseries.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def list_trees(data_root: pathlib.Path = DATA_ROOT) -> list[dict[str, Any]]:
    evo_dir = data_root / "evolution"
    if not evo_dir.exists():
        return []
    results = []
    for tree_dir in sorted(evo_dir.iterdir()):
        if not tree_dir.is_dir():
            continue
        tree_path = tree_dir / "tree.json"
        if not tree_path.exists():
            continue
        tree = json.loads(tree_path.read_text())
        results.append({
            "tree_id": tree_dir.name,
            "node_count": len(tree.get("nodes", {})),
        })
    return results


def read_tree(data_root: pathlib.Path, tree_id: str) -> dict[str, Any] | None:
    path = data_root / "evolution" / tree_id / "tree.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())

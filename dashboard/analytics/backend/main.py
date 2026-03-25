import pathlib
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dashboard.analytics.backend import readers
from dashboard.analytics.backend.models import (
    RunSummary, RunDetail, RunMetadata, AgentsSummary, ActionsSummary,
    InnovationsSummary, EbsComponents,
    Event, TimeseriesPoint, TreeSummary, TreeDetail, TreeNodeSummary,
)

app = FastAPI(title="Emerge Analytics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

DATA_ROOT = pathlib.Path("data")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/runs", response_model=list[RunSummary])
def list_runs(
    tree_id: str | None = None,
    node_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return readers.list_runs(DATA_ROOT, tree_id=tree_id, node_id=node_id,
                             limit=limit, offset=offset)


@app.get("/api/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: str):
    run_dir = DATA_ROOT / "runs" / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

    meta = readers.read_meta(run_dir)
    summary = readers.read_summary(run_dir)
    ebs_data = readers.read_ebs(run_dir)

    agents = AgentsSummary(**summary["agents"]) if summary else None
    actions = ActionsSummary(**summary["actions"]) if summary else None
    innovations = InnovationsSummary(**summary["innovations"]) if summary else None
    ebs = ebs_data["ebs"] if ebs_data else None
    ebs_components = None
    if ebs_data:
        ebs_components = EbsComponents(**{
            k: v["score"] for k, v in ebs_data["components"].items()
        })

    return RunDetail(
        metadata=RunMetadata(**meta),
        agents=agents,
        actions=actions,
        innovations=innovations,
        ebs=ebs,
        ebs_components=ebs_components,
    )


@app.get("/api/runs/{run_id}/events", response_model=list[Event])
def get_events(
    run_id: str,
    tick_from: int | None = None,
    tick_to: int | None = None,
    types: str | None = None,   # comma-separated
    agent_id: str | None = None,
):
    run_dir = DATA_ROOT / "runs" / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    type_list = types.split(",") if types else None
    return readers.read_events(run_dir, tick_from=tick_from, tick_to=tick_to,
                               types=type_list, agent_id=agent_id)


@app.get("/api/runs/{run_id}/timeseries", response_model=list[TimeseriesPoint])
def get_timeseries(run_id: str):
    run_dir = DATA_ROOT / "runs" / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return readers.read_timeseries(run_dir)


@app.get("/api/trees", response_model=list[TreeSummary])
def list_trees():
    return readers.list_trees(DATA_ROOT)


@app.get("/api/trees/{tree_id}", response_model=TreeDetail)
def get_tree(tree_id: str):
    tree = readers.read_tree(DATA_ROOT, tree_id)
    if tree is None:
        raise HTTPException(status_code=404, detail=f"Tree {tree_id!r} not found")
    nodes = {
        k: TreeNodeSummary(
            node_id=v.get("node_id", k),
            generation=v.get("generation", 0),
            parent=v.get("parent"),
            runs=v.get("runs", []),
            mean_ebs=v.get("mean_ebs"),
            std_ebs=v.get("std_ebs"),
            selected=v.get("selected", False),
        )
        for k, v in tree.get("nodes", {}).items()
    }
    return TreeDetail(tree_id=tree["tree_id"], config=tree.get("config", {}), nodes=nodes)


if __name__ == "__main__":
    uvicorn.run("dashboard.analytics.backend.main:app", host="0.0.0.0", port=8001, reload=True)

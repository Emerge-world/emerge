import pathlib
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dashboard.analytics.backend import readers
from dashboard.analytics.backend.models import (
    RunSummary, RunDetail, RunMetadata, AgentsSummary, ActionsSummary,
    InnovationsSummary, EbsComponents,
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


if __name__ == "__main__":
    uvicorn.run("dashboard.analytics.backend.main:app", host="0.0.0.0", port=8001, reload=True)

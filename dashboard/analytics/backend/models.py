# dashboard/analytics/backend/models.py
from __future__ import annotations
from typing import Any
from pydantic import BaseModel


class RunSummary(BaseModel):
    run_id: str
    created_at: str
    total_ticks: int
    ebs: float | None
    survival_rate: float | None
    innovations_approved: int | None
    tree_id: str | None = None
    node_id: str | None = None


class AgentsSummary(BaseModel):
    initial_count: int
    final_survivors: list[str]
    deaths: int
    survival_rate: float


class ActionsSummary(BaseModel):
    total: int
    by_type: dict[str, int]
    oracle_success_rate: float
    parse_fail_rate: float


class InnovationsSummary(BaseModel):
    attempts: int
    approved: int
    rejected: int
    used: int
    approval_rate: float
    realization_rate: float


class EbsComponents(BaseModel):
    novelty: float
    utility: float
    realization: float
    stability: float
    autonomy: float
    longevity: float


class RunMetadata(BaseModel):
    run_id: str
    seed: int
    width: int
    height: int
    max_ticks: int
    agent_count: int
    agent_names: list[str]
    agent_model_id: str
    oracle_model_id: str
    git_commit: str
    created_at: str
    precedents_file: str | None = None


class RunDetail(BaseModel):
    metadata: RunMetadata
    agents: AgentsSummary | None = None
    actions: ActionsSummary | None = None
    innovations: InnovationsSummary | None = None
    ebs: float | None = None
    ebs_components: EbsComponents | None = None


class Event(BaseModel):
    run_id: str
    seed: int
    tick: int
    sim_time: dict[str, int]
    event_type: str
    agent_id: str | None = None
    payload: dict[str, Any]


class TimeseriesPoint(BaseModel):
    tick: int
    sim_time: dict[str, int]
    alive: int
    mean_life: float
    mean_hunger: float
    mean_energy: float
    deaths: int
    actions: int
    innovations_attempted: int
    innovations_approved: int


class TreeNodeSummary(BaseModel):
    node_id: str
    generation: int
    parent: str | None
    runs: list[str]
    mean_ebs: float | None = None
    std_ebs: float | None = None
    selected: bool = False


class TreeSummary(BaseModel):
    tree_id: str
    node_count: int


class TreeDetail(BaseModel):
    tree_id: str
    config: dict[str, Any]
    nodes: dict[str, TreeNodeSummary]

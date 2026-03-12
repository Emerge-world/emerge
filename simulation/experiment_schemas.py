from pydantic import BaseModel, Field


class CohortConfig(BaseModel):
    name: str
    config: dict


class SuiteMetrics(BaseModel):
    primary: list[str] = Field(default_factory=list)
    secondary: list[str] = Field(default_factory=list)
    stability: list[str] = Field(default_factory=list)


class PolicyConfig(BaseModel):
    max_invalid_run_rate: float = 0.25
    min_effect_size: float = 0.0


class BudgetConfig(BaseModel):
    max_runs: int


class ExperimentSuite(BaseModel):
    name: str
    purpose: str
    mode: str
    seed_set: list[int]
    baseline: CohortConfig
    candidates: list[CohortConfig]
    metrics: SuiteMetrics
    policy: PolicyConfig
    budget: BudgetConfig


class DecisionArtifact(BaseModel):
    suite_name: str
    decision: str
    reason: str
    rules_fired: list[str]
    cohort_results: list[dict]

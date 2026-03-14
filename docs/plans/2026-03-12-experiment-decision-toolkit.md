# Experiment Decision Toolkit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an automation-first experiment toolkit that compares baseline and candidate cohorts, emits policy-driven gating decisions, and ranks next experiments to run.

**Architecture:** Build on top of the existing artifact pipeline instead of the simulation loop. Keep `events.jsonl`, `metrics_builder`, and per-run metrics as the canonical layer, then add a separate suite/cohort/decision pipeline that expands experiment specs, aggregates run metrics across seeds, applies explicit policies, and writes machine-readable decision artifacts.

**Tech Stack:** Python 3, stdlib dataclasses and JSON, PyYAML, pytest, existing `run_batch.py`, existing metrics artifacts under `data/runs/<run_id>/metrics/`

---

## Preconditions

- Work from a feature branch or worktree before implementing the plan.
- Do not overwrite unrelated local changes, especially the existing uncommitted `experiments.yaml` changes.
- Keep the first rollout automation-first. Human-readable reporting is explicitly out of scope for this plan.

### Task 1: Define Suite Spec And Decision Artifact Schemas

**Files:**
- Create: `simulation/experiment_schemas.py`
- Test: `tests/test_experiment_schemas.py`

**Step 1: Write the failing test**

```python
from simulation.experiment_schemas import ExperimentSuite, DecisionArtifact


def test_experiment_suite_parses_baseline_and_candidates():
    suite = ExperimentSuite.model_validate(
        {
            "name": "gate_inventory_change",
            "purpose": "Check whether inventory change improves survival",
            "mode": "both",
            "seed_set": [1, 2, 3],
            "baseline": {"name": "baseline", "config": {"agents": 3, "ticks": 50}},
            "candidates": [
                {"name": "candidate", "config": {"agents": 3, "ticks": 50}}
            ],
            "metrics": {"primary": ["survival_rate"], "secondary": ["innovation_realization_rate"]},
            "policy": {"max_invalid_run_rate": 0.25},
            "budget": {"max_runs": 6},
        }
    )
    assert suite.baseline.name == "baseline"
    assert suite.candidates[0].name == "candidate"


def test_decision_artifact_requires_final_decision():
    artifact = DecisionArtifact.model_validate(
        {
            "suite_name": "gate_inventory_change",
            "decision": "promote",
            "reason": "candidate improved survival without violating gates",
            "rules_fired": ["survival_gain", "no_primary_regression"],
            "cohort_results": [],
        }
    )
    assert artifact.decision == "promote"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_experiment_schemas.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'simulation.experiment_schemas'`

**Step 3: Write minimal implementation**

```python
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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_experiment_schemas.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_experiment_schemas.py simulation/experiment_schemas.py
git commit -m "feat: add experiment suite schemas"
```

### Task 2: Add Run Metric Loader And Rebuild Fallback

**Files:**
- Create: `simulation/experiment_loader.py`
- Modify: `simulation/metrics_builder.py`
- Test: `tests/test_experiment_loader.py`

**Step 1: Write the failing test**

```python
import json
from pathlib import Path

from simulation.experiment_loader import load_run_metrics


def test_load_run_metrics_reads_summary_when_present(tmp_path: Path):
    run_dir = tmp_path / "run_a"
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True)
    (metrics_dir / "summary.json").write_text(
        json.dumps({"agents": {"survival_rate": 0.5}, "actions": {"oracle_success_rate": 0.8}}),
        encoding="utf-8",
    )
    result = load_run_metrics(run_dir)
    assert result.summary["agents"]["survival_rate"] == 0.5
    assert result.rebuilt is False


def test_load_run_metrics_rebuilds_when_summary_missing(tmp_path: Path):
    run_dir = tmp_path / "run_b"
    run_dir.mkdir()
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")
    result = load_run_metrics(run_dir)
    assert result.invalid is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_experiment_loader.py -v`

Expected: FAIL because `load_run_metrics` does not exist.

**Step 3: Write minimal implementation**

```python
from dataclasses import dataclass, field
import json
from pathlib import Path

from simulation.metrics_builder import MetricsBuilder


@dataclass
class RunMetricsResult:
    run_dir: Path
    summary: dict = field(default_factory=dict)
    rebuilt: bool = False
    invalid: bool = False


def load_run_metrics(run_dir: Path) -> RunMetricsResult:
    metrics_path = Path(run_dir) / "metrics" / "summary.json"
    if not metrics_path.exists() and (Path(run_dir) / "events.jsonl").exists():
        MetricsBuilder(run_dir).build()
        rebuilt = True
    else:
        rebuilt = False

    if not metrics_path.exists():
        return RunMetricsResult(run_dir=Path(run_dir), rebuilt=rebuilt, invalid=True)

    summary = json.loads(metrics_path.read_text(encoding="utf-8"))
    return RunMetricsResult(run_dir=Path(run_dir), summary=summary, rebuilt=rebuilt, invalid=False)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_experiment_loader.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_experiment_loader.py simulation/experiment_loader.py
git commit -m "feat: add run metric loader with rebuild fallback"
```

### Task 3: Add Cohort Aggregation

**Files:**
- Create: `simulation/cohort_analyzer.py`
- Test: `tests/test_cohort_analyzer.py`

**Step 1: Write the failing test**

```python
from simulation.cohort_analyzer import summarize_cohort
from simulation.experiment_loader import RunMetricsResult


def test_summarize_cohort_computes_mean_and_invalid_rate(tmp_path):
    runs = [
        RunMetricsResult(
            run_dir=tmp_path / "run1",
            summary={"agents": {"survival_rate": 1.0}, "actions": {"oracle_success_rate": 0.9}},
            invalid=False,
        ),
        RunMetricsResult(
            run_dir=tmp_path / "run2",
            summary={"agents": {"survival_rate": 0.5}, "actions": {"oracle_success_rate": 0.7}},
            invalid=False,
        ),
        RunMetricsResult(run_dir=tmp_path / "run3", invalid=True),
    ]
    cohort = summarize_cohort("candidate", runs)
    assert cohort.metrics["survival_rate"]["mean"] == 0.75
    assert cohort.invalid_run_rate == 0.3333
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cohort_analyzer.py -v`

Expected: FAIL because `summarize_cohort` does not exist.

**Step 3: Write minimal implementation**

```python
from dataclasses import dataclass, field


@dataclass
class CohortSummary:
    name: str
    run_count: int
    invalid_run_rate: float
    metrics: dict = field(default_factory=dict)


def summarize_cohort(name: str, runs: list) -> CohortSummary:
    valid = [r for r in runs if not r.invalid]
    total = len(runs)
    survival = [r.summary["agents"]["survival_rate"] for r in valid]
    oracle = [r.summary["actions"]["oracle_success_rate"] for r in valid]
    metrics = {
        "survival_rate": {"mean": round(sum(survival) / len(survival), 4) if survival else 0.0},
        "oracle_success_rate": {"mean": round(sum(oracle) / len(oracle), 4) if oracle else 0.0},
    }
    return CohortSummary(
        name=name,
        run_count=total,
        invalid_run_rate=round((total - len(valid)) / total, 4) if total else 0.0,
        metrics=metrics,
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cohort_analyzer.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_cohort_analyzer.py simulation/cohort_analyzer.py
git commit -m "feat: add cohort metric aggregation"
```

### Task 4: Add Baseline Vs Candidate Comparison

**Files:**
- Create: `simulation/experiment_compare.py`
- Test: `tests/test_experiment_compare.py`

**Step 1: Write the failing test**

```python
from simulation.cohort_analyzer import CohortSummary
from simulation.experiment_compare import compare_to_baseline


def test_compare_to_baseline_computes_metric_deltas():
    baseline = CohortSummary(
        name="baseline",
        run_count=3,
        invalid_run_rate=0.0,
        metrics={"survival_rate": {"mean": 0.6}, "oracle_success_rate": {"mean": 0.8}},
    )
    candidate = CohortSummary(
        name="candidate",
        run_count=3,
        invalid_run_rate=0.0,
        metrics={"survival_rate": {"mean": 0.7}, "oracle_success_rate": {"mean": 0.82}},
    )
    diff = compare_to_baseline(baseline, candidate)
    assert diff["survival_rate"]["delta"] == 0.1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_experiment_compare.py -v`

Expected: FAIL because `compare_to_baseline` does not exist.

**Step 3: Write minimal implementation**

```python
def compare_to_baseline(baseline, candidate) -> dict:
    compared = {}
    for metric_name, baseline_value in baseline.metrics.items():
        candidate_value = candidate.metrics.get(metric_name, {"mean": 0.0})
        compared[metric_name] = {
            "baseline": baseline_value["mean"],
            "candidate": candidate_value["mean"],
            "delta": round(candidate_value["mean"] - baseline_value["mean"], 4),
        }
    return compared
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_experiment_compare.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_experiment_compare.py simulation/experiment_compare.py
git commit -m "feat: add cohort comparison against baseline"
```

### Task 5: Add Policy Engine For Gating Decisions

**Files:**
- Create: `simulation/experiment_policy.py`
- Test: `tests/test_experiment_policy.py`

**Step 1: Write the failing test**

```python
from simulation.experiment_policy import evaluate_candidate


def test_policy_rejects_candidate_with_primary_regression():
    decision = evaluate_candidate(
        comparison={"survival_rate": {"delta": -0.15}, "oracle_success_rate": {"delta": 0.01}},
        candidate_invalid_run_rate=0.0,
        primary_metrics=["survival_rate"],
        tolerances={"survival_rate": -0.05},
        max_invalid_run_rate=0.25,
        min_effect_size=0.02,
    )
    assert decision.decision == "reject"


def test_policy_promotes_candidate_with_safe_gain():
    decision = evaluate_candidate(
        comparison={"survival_rate": {"delta": 0.08}, "oracle_success_rate": {"delta": 0.03}},
        candidate_invalid_run_rate=0.0,
        primary_metrics=["survival_rate"],
        tolerances={"survival_rate": -0.05},
        max_invalid_run_rate=0.25,
        min_effect_size=0.02,
    )
    assert decision.decision == "promote"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_experiment_policy.py -v`

Expected: FAIL because `evaluate_candidate` does not exist.

**Step 3: Write minimal implementation**

```python
from dataclasses import dataclass, field


@dataclass
class CandidateDecision:
    decision: str
    reason: str
    rules_fired: list[str] = field(default_factory=list)


def evaluate_candidate(
    comparison: dict,
    candidate_invalid_run_rate: float,
    primary_metrics: list[str],
    tolerances: dict,
    max_invalid_run_rate: float,
    min_effect_size: float,
) -> CandidateDecision:
    if candidate_invalid_run_rate > max_invalid_run_rate:
        return CandidateDecision("inconclusive", "too many invalid runs", ["invalid_runs"])

    for metric in primary_metrics:
        if comparison.get(metric, {}).get("delta", 0.0) < tolerances.get(metric, 0.0):
            return CandidateDecision("reject", f"{metric} regressed", ["primary_regression"])

    if any(item.get("delta", 0.0) >= min_effect_size for item in comparison.values()):
        return CandidateDecision("promote", "candidate improved without violating gates", ["value_gain"])

    return CandidateDecision("inconclusive", "effect too small", ["small_effect"])
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_experiment_policy.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_experiment_policy.py simulation/experiment_policy.py
git commit -m "feat: add experiment policy engine"
```

### Task 6: Add Experiment Prioritizer

**Files:**
- Create: `simulation/experiment_prioritizer.py`
- Test: `tests/test_experiment_prioritizer.py`

**Step 1: Write the failing test**

```python
from simulation.experiment_prioritizer import rank_candidates


def test_rank_candidates_prefers_high_uncertainty_and_high_upside():
    ranked = rank_candidates(
        [
            {"name": "safe_small_gain", "uncertainty": 0.1, "upside": 0.2, "strategic_value": 0.4},
            {"name": "uncertain_high_gain", "uncertainty": 0.7, "upside": 0.8, "strategic_value": 0.7},
        ]
    )
    assert ranked[0]["name"] == "uncertain_high_gain"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_experiment_prioritizer.py -v`

Expected: FAIL because `rank_candidates` does not exist.

**Step 3: Write minimal implementation**

```python
def rank_candidates(candidates: list[dict]) -> list[dict]:
    def score(candidate: dict) -> float:
        return round(
            candidate.get("uncertainty", 0.0)
            + candidate.get("upside", 0.0)
            + candidate.get("strategic_value", 0.0),
            4,
        )

    return sorted(
        [{**candidate, "priority_score": score(candidate)} for candidate in candidates],
        key=lambda item: item["priority_score"],
        reverse=True,
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_experiment_prioritizer.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_experiment_prioritizer.py simulation/experiment_prioritizer.py
git commit -m "feat: add experiment prioritizer"
```

### Task 7: Extend Batch Config Parsing For Cohort Suites

**Files:**
- Modify: `run_batch.py`
- Create: `tests/test_experiment_suite_runner.py`
- Modify: `tests/test_run_batch.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

from run_batch import expand_suite_runs


def test_expand_suite_runs_builds_baseline_and_candidate_runs(tmp_path: Path):
    suite = {
        "name": "gate_inventory",
        "seed_set": [11, 12],
        "baseline": {"name": "baseline", "config": {"agents": 3, "ticks": 20}},
        "candidates": [{"name": "candidate", "config": {"agents": 3, "ticks": 20}}],
    }
    runs = expand_suite_runs(suite)
    assert runs[0]["name"] == "gate_inventory_baseline_seed11"
    assert runs[-1]["name"] == "gate_inventory_candidate_seed12"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_run_batch.py tests/test_experiment_suite_runner.py -v`

Expected: FAIL because `expand_suite_runs` does not exist.

**Step 3: Write minimal implementation**

```python
def expand_suite_runs(suite: dict) -> list[dict]:
    runs = []
    seeds = suite.get("seed_set", [])
    groups = [suite["baseline"], *suite.get("candidates", [])]
    for group in groups:
        for seed in seeds:
            config = dict(group["config"])
            config["seed"] = seed
            config["name"] = f"{suite['name']}_{group['name']}_seed{seed}"
            runs.append(config)
    return runs
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_run_batch.py tests/test_experiment_suite_runner.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_run_batch.py tests/test_experiment_suite_runner.py run_batch.py
git commit -m "feat: expand batch config for experiment suites"
```

### Task 8: Add End-To-End Decision Builder

**Files:**
- Create: `simulation/decision_builder.py`
- Create: `tests/test_decision_builder.py`

**Step 1: Write the failing test**

```python
import json
from pathlib import Path

from simulation.decision_builder import build_decision_artifact


def test_build_decision_artifact_writes_output(tmp_path: Path):
    suite = {
        "name": "gate_inventory",
        "metrics": {"primary": ["survival_rate"], "secondary": ["oracle_success_rate"]},
        "policy": {"max_invalid_run_rate": 0.25, "min_effect_size": 0.02},
    }
    baseline = {
        "name": "baseline",
        "run_count": 2,
        "invalid_run_rate": 0.0,
        "metrics": {"survival_rate": {"mean": 0.5}, "oracle_success_rate": {"mean": 0.8}},
    }
    candidate = {
        "name": "candidate",
        "run_count": 2,
        "invalid_run_rate": 0.0,
        "metrics": {"survival_rate": {"mean": 0.65}, "oracle_success_rate": {"mean": 0.82}},
    }
    output_path = tmp_path / "decision.json"
    build_decision_artifact(suite, baseline, candidate, output_path)
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["decision"] == "promote"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_decision_builder.py -v`

Expected: FAIL because `build_decision_artifact` does not exist.

**Step 3: Write minimal implementation**

```python
import json
from pathlib import Path

from simulation.experiment_compare import compare_to_baseline
from simulation.experiment_policy import evaluate_candidate


def build_decision_artifact(suite: dict, baseline: dict, candidate: dict, output_path: Path) -> None:
    comparison = compare_to_baseline(baseline, candidate)
    decision = evaluate_candidate(
        comparison=comparison,
        candidate_invalid_run_rate=candidate["invalid_run_rate"],
        primary_metrics=suite["metrics"]["primary"],
        tolerances={metric: -0.05 for metric in suite["metrics"]["primary"]},
        max_invalid_run_rate=suite["policy"]["max_invalid_run_rate"],
        min_effect_size=suite["policy"]["min_effect_size"],
    )
    payload = {
        "suite_name": suite["name"],
        "decision": decision.decision,
        "reason": decision.reason,
        "rules_fired": decision.rules_fired,
        "comparison": comparison,
        "baseline": baseline,
        "candidate": candidate,
    }
    Path(output_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_decision_builder.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_decision_builder.py simulation/decision_builder.py
git commit -m "feat: add end-to-end decision artifact builder"
```

### Task 9: Add CLI Entry Point For Gating And Prioritization

**Files:**
- Create: `experiment_toolkit.py`
- Create: `tests/test_experiment_toolkit_cli.py`

**Step 1: Write the failing test**

```python
from experiment_toolkit import build_parser


def test_cli_accepts_suite_config_and_output_dir():
    parser = build_parser()
    args = parser.parse_args(["suite.yaml", "--output-dir", "artifacts"])
    assert args.config == "suite.yaml"
    assert args.output_dir == "artifacts"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_experiment_toolkit_cli.py -v`

Expected: FAIL because `experiment_toolkit.py` does not exist.

**Step 3: Write minimal implementation**

```python
import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run experiment gating and prioritization")
    parser.add_argument("config")
    parser.add_argument("--output-dir", default="data/experiments")
    return parser
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_experiment_toolkit_cli.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_experiment_toolkit_cli.py experiment_toolkit.py
git commit -m "feat: add experiment toolkit cli entry point"
```

### Task 10: Add Regression Fixtures And Full Fast-Suite Coverage

**Files:**
- Create: `tests/fixtures/experiments/gate_inventory_suite.yaml`
- Create: `tests/fixtures/experiments/golden_decision.json`
- Modify: `tests/test_decision_builder.py`
- Modify: `tests/test_experiment_toolkit_cli.py`

**Step 1: Write the failing test**

```python
import json
from pathlib import Path


def test_golden_decision_fixture_matches_expected_decision():
    expected = json.loads(Path("tests/fixtures/experiments/golden_decision.json").read_text(encoding="utf-8"))
    assert expected["decision"] == "promote"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_decision_builder.py tests/test_experiment_toolkit_cli.py -v`

Expected: FAIL because the fixture files do not exist yet.

**Step 3: Write minimal implementation**

```json
{
  "suite_name": "gate_inventory",
  "decision": "promote",
  "reason": "candidate improved without violating gates",
  "rules_fired": ["value_gain"]
}
```

```yaml
name: gate_inventory
purpose: Baseline vs candidate gate
mode: both
seed_set: [11, 12]
baseline:
  name: baseline
  config:
    agents: 3
    ticks: 20
candidates:
  - name: candidate
    config:
      agents: 3
      ticks: 20
metrics:
  primary: [survival_rate]
  secondary: [oracle_success_rate]
policy:
  max_invalid_run_rate: 0.25
  min_effect_size: 0.02
budget:
  max_runs: 4
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_decision_builder.py tests/test_experiment_toolkit_cli.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/fixtures/experiments/gate_inventory_suite.yaml tests/fixtures/experiments/golden_decision.json tests/test_decision_builder.py tests/test_experiment_toolkit_cli.py
git commit -m "test: add golden fixtures for experiment decisions"
```

### Task 11: Update Docs And Cornerstone Context

**Files:**
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Modify: `project-cornerstone/10-testing/testing_context.md`
- Modify: `project-cornerstone/11-devops/devops_context.md`
- Modify: `docs/plans/2026-03-12-experiment-decision-toolkit-design.md`

**Step 1: Write the failing docs checklist**

```text
- Decision log explains automation-first experiment decisions
- Testing context mentions cohort/policy regression coverage
- DevOps context mentions suite configs and experiment artifacts
```

**Step 2: Verify the checklist is not satisfied yet**

Run: `rg -n "experiment toolkit|cohort|decision artifact|prioritization" project-cornerstone docs/plans/2026-03-12-experiment-decision-toolkit-design.md`

Expected: Missing references in one or more cornerstone files.

**Step 3: Write minimal documentation updates**

```markdown
### DEC-034: Automation-first experiment decision toolkit
- **Date**: 2026-03-12
- **Context**: The repo can run batches and compute metrics, but cannot yet decide whether a candidate change is better than baseline or which experiment to run next.
- **Decision**: Add a suite/cohort/policy decision layer above the canonical run artifacts. Keep per-run metrics canonical and produce machine-readable gating and prioritization artifacts first; human-readable plugins come later.
- **Rejected alternatives**: Replace metrics_builder with a new analytics stack; depend on W&B as the source of truth; lead with an LLM recommender.
- **Consequences**: Experiment configs expand from flat runs to cohort suites. Testing now includes policy and golden-decision regressions. DevOps now treats experiment artifacts as first-class outputs.
```

**Step 4: Verify the docs are updated**

Run: `rg -n "Automation-first experiment decision toolkit|golden-decision|cohort suites|decision artifacts" project-cornerstone docs/plans/2026-03-12-experiment-decision-toolkit-design.md`

Expected: Matching lines found in the updated files.

**Step 5: Commit**

```bash
git add project-cornerstone/00-master-plan/DECISION_LOG.md project-cornerstone/10-testing/testing_context.md project-cornerstone/11-devops/devops_context.md docs/plans/2026-03-12-experiment-decision-toolkit-design.md
git commit -m "docs: add experiment toolkit architecture context"
```

### Task 12: Final Verification

**Files:**
- Verify: `tests/test_experiment_schemas.py`
- Verify: `tests/test_experiment_loader.py`
- Verify: `tests/test_cohort_analyzer.py`
- Verify: `tests/test_experiment_compare.py`
- Verify: `tests/test_experiment_policy.py`
- Verify: `tests/test_experiment_prioritizer.py`
- Verify: `tests/test_experiment_suite_runner.py`
- Verify: `tests/test_decision_builder.py`
- Verify: `tests/test_experiment_toolkit_cli.py`
- Verify: `tests/test_run_batch.py`

**Step 1: Run focused experiment-toolkit tests**

Run: `uv run pytest tests/test_experiment_schemas.py tests/test_experiment_loader.py tests/test_cohort_analyzer.py tests/test_experiment_compare.py tests/test_experiment_policy.py tests/test_experiment_prioritizer.py tests/test_experiment_suite_runner.py tests/test_decision_builder.py tests/test_experiment_toolkit_cli.py tests/test_run_batch.py -v`

Expected: PASS

**Step 2: Run the required fast suite**

Run: `uv run pytest -m "not slow"`

Expected: PASS

**Step 3: Run a dry-run experiment suite**

Run: `uv run experiment_toolkit.py tests/fixtures/experiments/gate_inventory_suite.yaml --output-dir /tmp/emerge-experiments`

Expected: Decision and prioritization artifacts written without changing simulation behavior.

**Step 4: Review git status**

Run: `git status --short`

Expected: Only intended implementation files are modified or new.

**Step 5: Commit final integration**

```bash
git add simulation run_batch.py experiment_toolkit.py tests project-cornerstone docs/plans/2026-03-12-experiment-decision-toolkit.md
git commit -m "feat: add experiment decision toolkit"
```

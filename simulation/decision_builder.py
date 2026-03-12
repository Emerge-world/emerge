import json
from pathlib import Path

from simulation.cohort_analyzer import CohortSummary
from simulation.experiment_compare import compare_to_baseline
from simulation.experiment_policy import evaluate_candidate


def _cohort_from_mapping(data: dict) -> CohortSummary:
    return CohortSummary(
        name=data["name"],
        run_count=data["run_count"],
        invalid_run_rate=data["invalid_run_rate"],
        metrics=data["metrics"],
    )


def build_decision_artifact(suite: dict, baseline: dict, candidate: dict, output_path: Path) -> None:
    baseline_summary = _cohort_from_mapping(baseline)
    candidate_summary = _cohort_from_mapping(candidate)
    comparison = compare_to_baseline(baseline_summary, candidate_summary)
    decision = evaluate_candidate(
        comparison=comparison,
        candidate_invalid_run_rate=candidate_summary.invalid_run_rate,
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
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

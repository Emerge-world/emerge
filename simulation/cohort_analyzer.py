from dataclasses import dataclass, field

from simulation.experiment_loader import RunMetricsResult


METRIC_PATHS = {
    "survival_rate": ("agents", "survival_rate"),
    "oracle_success_rate": ("actions", "oracle_success_rate"),
    "parse_fail_rate": ("actions", "parse_fail_rate"),
    "innovation_approval_rate": ("innovations", "approval_rate"),
    "innovation_realization_rate": ("innovations", "realization_rate"),
}


@dataclass
class CohortSummary:
    name: str
    run_count: int
    invalid_run_rate: float
    metrics: dict = field(default_factory=dict)


def _extract_metric(summary: dict, path: tuple[str, ...]) -> float | None:
    current = summary
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    if not isinstance(current, int | float):
        return None
    return float(current)


def summarize_cohort(name: str, runs: list[RunMetricsResult]) -> CohortSummary:
    valid_runs = [run for run in runs if not run.invalid]
    metrics = {}

    for metric_name, path in METRIC_PATHS.items():
        values = [
            value
            for run in valid_runs
            if (value := _extract_metric(run.summary, path)) is not None
        ]
        if values:
            metrics[metric_name] = {
                "mean": round(sum(values) / len(values), 4),
                "count": len(values),
            }

    total_runs = len(runs)
    invalid_run_rate = round((total_runs - len(valid_runs)) / total_runs, 4) if total_runs else 0.0
    return CohortSummary(
        name=name,
        run_count=total_runs,
        invalid_run_rate=invalid_run_rate,
        metrics=metrics,
    )

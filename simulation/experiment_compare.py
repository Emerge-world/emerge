from simulation.cohort_analyzer import CohortSummary


def compare_to_baseline(baseline: CohortSummary, candidate: CohortSummary) -> dict:
    compared = {}
    metric_names = set(baseline.metrics) | set(candidate.metrics)

    for metric_name in sorted(metric_names):
        baseline_mean = baseline.metrics.get(metric_name, {}).get("mean", 0.0)
        candidate_mean = candidate.metrics.get(metric_name, {}).get("mean", 0.0)
        compared[metric_name] = {
            "baseline": baseline_mean,
            "candidate": candidate_mean,
            "delta": round(candidate_mean - baseline_mean, 4),
        }

    return compared

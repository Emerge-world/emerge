from simulation.cohort_analyzer import CohortSummary
from simulation.experiment_compare import compare_to_baseline


def test_compare_to_baseline_computes_metric_deltas():
    baseline = CohortSummary(
        name="baseline",
        run_count=3,
        invalid_run_rate=0.0,
        metrics={
            "survival_rate": {"mean": 0.6},
            "oracle_success_rate": {"mean": 0.8},
        },
    )
    candidate = CohortSummary(
        name="candidate",
        run_count=3,
        invalid_run_rate=0.0,
        metrics={
            "survival_rate": {"mean": 0.7},
            "oracle_success_rate": {"mean": 0.82},
        },
    )

    diff = compare_to_baseline(baseline, candidate)

    assert diff["survival_rate"]["delta"] == 0.1

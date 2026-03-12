from simulation.cohort_analyzer import summarize_cohort
from simulation.experiment_loader import RunMetricsResult


def test_summarize_cohort_computes_mean_and_invalid_rate(tmp_path):
    runs = [
        RunMetricsResult(
            run_dir=tmp_path / "run1",
            summary={
                "agents": {"survival_rate": 1.0},
                "actions": {"oracle_success_rate": 0.9},
            },
            invalid=False,
        ),
        RunMetricsResult(
            run_dir=tmp_path / "run2",
            summary={
                "agents": {"survival_rate": 0.5},
                "actions": {"oracle_success_rate": 0.7},
            },
            invalid=False,
        ),
        RunMetricsResult(run_dir=tmp_path / "run3", invalid=True),
    ]

    cohort = summarize_cohort("candidate", runs)

    assert cohort.metrics["survival_rate"]["mean"] == 0.75
    assert cohort.invalid_run_rate == 0.3333

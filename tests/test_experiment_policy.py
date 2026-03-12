from simulation.experiment_policy import evaluate_candidate


def test_policy_rejects_candidate_with_primary_regression():
    decision = evaluate_candidate(
        comparison={
            "survival_rate": {"delta": -0.15},
            "oracle_success_rate": {"delta": 0.01},
        },
        candidate_invalid_run_rate=0.0,
        primary_metrics=["survival_rate"],
        tolerances={"survival_rate": -0.05},
        max_invalid_run_rate=0.25,
        min_effect_size=0.02,
    )

    assert decision.decision == "reject"


def test_policy_promotes_candidate_with_safe_gain():
    decision = evaluate_candidate(
        comparison={
            "survival_rate": {"delta": 0.08},
            "oracle_success_rate": {"delta": 0.03},
        },
        candidate_invalid_run_rate=0.0,
        primary_metrics=["survival_rate"],
        tolerances={"survival_rate": -0.05},
        max_invalid_run_rate=0.25,
        min_effect_size=0.02,
    )

    assert decision.decision == "promote"

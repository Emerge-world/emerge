from simulation.experiment_schemas import DecisionArtifact, ExperimentSuite


def test_experiment_suite_parses_baseline_and_candidates():
    suite = ExperimentSuite.model_validate(
        {
            "name": "gate_inventory_change",
            "purpose": "Check whether inventory change improves survival",
            "mode": "both",
            "seed_set": [1, 2, 3],
            "baseline": {"name": "baseline", "config": {"agents": 3, "ticks": 50}},
            "candidates": [
                {"name": "candidate", "config": {"agents": 3, "ticks": 50}},
            ],
            "metrics": {
                "primary": ["survival_rate"],
                "secondary": ["innovation_realization_rate"],
            },
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

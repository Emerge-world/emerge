from simulation.experiment_prioritizer import rank_candidates


def test_rank_candidates_prefers_high_uncertainty_and_high_upside():
    ranked = rank_candidates(
        [
            {
                "name": "safe_small_gain",
                "uncertainty": 0.1,
                "upside": 0.2,
                "strategic_value": 0.4,
            },
            {
                "name": "uncertain_high_gain",
                "uncertainty": 0.7,
                "upside": 0.8,
                "strategic_value": 0.7,
            },
        ]
    )

    assert ranked[0]["name"] == "uncertain_high_gain"

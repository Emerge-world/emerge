from run_batch import expand_suite_runs


def test_expand_suite_runs_builds_baseline_and_candidate_runs():
    suite = {
        "name": "gate_inventory",
        "seed_set": [11, 12],
        "baseline": {"name": "baseline", "config": {"agents": 3, "ticks": 20}},
        "candidates": [{"name": "candidate", "config": {"agents": 3, "ticks": 20}}],
    }

    runs = expand_suite_runs(suite)

    assert runs[0]["name"] == "gate_inventory_baseline_seed11"
    assert runs[-1]["name"] == "gate_inventory_candidate_seed12"

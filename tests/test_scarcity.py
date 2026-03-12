"""Tests for simulation/scarcity.py."""

import pytest

from simulation.scarcity import BenchmarkMetadata, ScarcityConfig


def test_scarcity_config_rejects_negative_values():
    with pytest.raises(ValueError, match="initial_resource_scale"):
        ScarcityConfig(initial_resource_scale=-0.1)


def test_scale_initial_quantity_only_changes_food_resources():
    scarcity = ScarcityConfig(initial_resource_scale=0.5)

    assert scarcity.scale_initial_quantity("fruit", 4) == 2
    assert scarcity.scale_initial_quantity("mushroom", 3) == 1
    assert scarcity.scale_initial_quantity("stone", 4) == 4
    assert scarcity.scale_initial_quantity("water", 99) == 99


def test_scale_regen_probability_is_clamped():
    scarcity = ScarcityConfig(regen_chance_scale=10.0)

    assert scarcity.scale_regen_probability(0.3) == 1.0


def test_benchmark_metadata_as_dict():
    metadata = BenchmarkMetadata(
        benchmark_id="scarcity_v1_demo",
        benchmark_version="scarcity_v1",
        scenario_id="mild",
        candidate_label="candidate",
        baseline_label="baseline",
    )

    assert metadata.as_dict() == {
        "benchmark_id": "scarcity_v1_demo",
        "benchmark_version": "scarcity_v1",
        "scenario_id": "mild",
        "candidate_label": "candidate",
        "baseline_label": "baseline",
    }

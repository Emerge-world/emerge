"""Tests for simulation/benchmark_suite.py."""

from pathlib import Path

import pytest

from simulation.benchmark_suite import (
    BenchmarkDefaults,
    BenchmarkScenario,
    BenchmarkSuite,
    load_benchmark_suite,
)


def test_load_benchmark_suite_reads_scenarios(tmp_path: Path):
    path = tmp_path / "suite.yaml"
    path.write_text(
        """
benchmark_version: scarcity_v1
defaults:
  agents: 3
  ticks: 40
  width: 15
  height: 15
  no_llm: true
  seeds: [11, 22]
scenarios:
  - id: mild
    label: Mild Scarcity
    scarcity:
      initial_resource_scale: 0.6
      regen_chance_scale: 0.8
      regen_amount_scale: 0.8
""",
        encoding="utf-8",
    )

    suite = load_benchmark_suite(path)

    assert suite.benchmark_version == "scarcity_v1"
    assert suite.defaults == BenchmarkDefaults(
        agents=3,
        ticks=40,
        width=15,
        height=15,
        no_llm=True,
        seeds=[11, 22],
        model=None,
    )
    assert suite.scenarios == [
        BenchmarkScenario(
            id="mild",
            label="Mild Scarcity",
            scarcity={
                "initial_resource_scale": 0.6,
                "regen_chance_scale": 0.8,
                "regen_amount_scale": 0.8,
            },
        )
    ]


def test_load_benchmark_suite_defaults_label_to_id(tmp_path: Path):
    path = tmp_path / "suite.yaml"
    path.write_text(
        """
benchmark_version: scarcity_v1
defaults:
  agents: 2
  ticks: 20
  width: 10
  height: 10
  no_llm: false
  seeds: [7]
scenarios:
  - id: severe
    scarcity:
      initial_resource_scale: 0.25
      regen_chance_scale: 0.25
      regen_amount_scale: 0.5
""",
        encoding="utf-8",
    )

    suite = load_benchmark_suite(path)

    assert suite.scenarios[0].label == "severe"


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        (
            """
defaults:
  agents: 2
  ticks: 20
  width: 10
  height: 10
  no_llm: true
  seeds: [1]
scenarios: []
""",
            "benchmark_version",
        ),
        (
            """
benchmark_version: scarcity_v1
defaults:
  agents: 2
  ticks: 20
  width: 10
  height: 10
  no_llm: true
  seeds: [1]
scenarios:
  - id: broken
    scarcity:
      initial_resource_scale: 0.5
      unexpected_key: 1.0
""",
            "unexpected_key",
        ),
    ],
)
def test_load_benchmark_suite_rejects_invalid_input(tmp_path: Path, contents: str, message: str):
    path = tmp_path / "suite.yaml"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_benchmark_suite(path)


def test_load_benchmark_suite_returns_path(tmp_path: Path):
    path = tmp_path / "suite.yaml"
    path.write_text(
        """
benchmark_version: scarcity_v1
defaults:
  agents: 1
  ticks: 5
  width: 5
  height: 5
  no_llm: true
  seeds: [1]
scenarios:
  - id: smoke
    scarcity:
      initial_resource_scale: 1.0
      regen_chance_scale: 1.0
      regen_amount_scale: 1.0
""",
        encoding="utf-8",
    )

    suite = load_benchmark_suite(path)

    assert suite.path == path
    assert isinstance(suite, BenchmarkSuite)

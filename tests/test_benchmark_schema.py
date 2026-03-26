from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from simulation.benchmark.loader import load_manifest
from simulation.benchmark.schema import CriterionConfig, ManifestValidationError, WandbConfig

_EXAMPLE_MANIFEST_DIR = Path(__file__).resolve().parents[1] / "benchmarks" / "manifests"


def _write_manifest(tmp_path, content: str):
    path = tmp_path / "manifest.yaml"
    path.write_text(dedent(content).lstrip(), encoding="utf-8")
    return path


def _example_manifest_path(name: str) -> Path:
    return _EXAMPLE_MANIFEST_DIR / name


def test_load_manifest_accepts_minimal_valid_manifest():
    path = _example_manifest_path("example_minimal.yaml")

    manifest = load_manifest(path)

    assert manifest.benchmark.id == "survival_v1"
    assert manifest.benchmark.version == "1"
    assert manifest.metrics.primary == ["summary.agents.survival_rate"]


def test_load_manifest_wraps_yaml_syntax_error_with_source_path(tmp_path):
    path = _write_manifest(
        tmp_path,
        """
        version: 1
        benchmark:
          id: survival_v1
          version: "1"
        defaults: {}
        seed_sets:
          smoke: [11]
        scenarios:
          default_day: {}
        arms:
          full: {}
        matrix:
          seed_sets: [smoke]
          scenarios: [default_day]
          arms: [full]
        metrics:
          primary: [summary.agents.survival_rate]
        criteria: []
        wandb:
          enabled: false
          project: [broken
        """,
    )

    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(path)

    message = str(excinfo.value)
    assert str(path) in message
    assert "YAML" in message


def test_load_manifest_returns_typed_criteria_and_wandb_sections(tmp_path):
    path = _write_manifest(
        tmp_path,
        """
        version: 1

        benchmark:
          id: survival_v1
          version: "1"

        defaults: {}
        seed_sets:
          smoke: [11]
        scenarios:
          default_day: {}
        arms:
          full: {}
        matrix:
          seed_sets: [smoke]
          scenarios: [default_day]
          arms: [full]
        metrics:
          primary: [summary.agents.survival_rate]
        criteria:
          - id: full_survival_gate
            metric: summary.agents.survival_rate
            threshold: 0.8
            description: gate
        wandb:
          enabled: true
          project: emerge
          group_by: [benchmark_id, scenario_id]
        """,
    )

    manifest = load_manifest(path)

    assert manifest.criteria
    assert isinstance(manifest.criteria[0], CriterionConfig)
    assert manifest.criteria[0].id == "full_survival_gate"
    assert manifest.criteria[0].threshold == 0.8
    assert isinstance(manifest.wandb, WandbConfig)
    assert manifest.wandb.enabled is True
    assert manifest.wandb.project == "emerge"
    assert manifest.wandb.group_by == ["benchmark_id", "scenario_id"]


def test_load_manifest_rejects_unknown_top_level_key(tmp_path):
    path = _write_manifest(
        tmp_path,
        """
        version: 1

        benchmark:
          id: survival_v1
          version: "1"

        defaults: {}
        seed_sets:
          smoke: [11]
        scenarios:
          default_day: {}
        arms:
          full: {}
        matrix:
          seed_sets: [smoke]
          scenarios: [default_day]
          arms: [full]
        metrics:
          primary: [summary.agents.survival_rate]
        criteria: []
        wandb:
          enabled: false
        unexpected: true
        """,
    )

    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(path)

    assert "unexpected" in str(excinfo.value)
    assert "top-level" in str(excinfo.value)


def test_load_manifest_rejects_unknown_nested_key(tmp_path):
    path = _write_manifest(
        tmp_path,
        """
        version: 1

        benchmark:
          id: survival_v1
          version: "1"

        defaults:
          runtime:
            agents: 3
            ticks: 300
            width: 15
            height: 15
            start_hour: 8
            use_llm: true
            extra_runtime_field: 99
        seed_sets:
          smoke: [11]
        scenarios:
          default_day: {}
        arms:
          full: {}
        matrix:
          seed_sets: [smoke]
          scenarios: [default_day]
          arms: [full]
        metrics:
          primary: [summary.agents.survival_rate]
        criteria: []
        wandb:
          enabled: false
        """,
    )

    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(path)

    assert "defaults.runtime.extra_runtime_field" in str(excinfo.value)
    assert "is not allowed" in str(excinfo.value)


def test_load_manifest_rejects_unknown_matrix_reference(tmp_path):
    path = _write_manifest(
        tmp_path,
        """
        version: 1

        benchmark:
          id: survival_v1
          version: "1"

        defaults: {}
        seed_sets:
          smoke: [11]
        scenarios:
          default_day: {}
        arms:
          full: {}
        matrix:
          seed_sets: [smoke]
          scenarios: [night_start]
          arms: [full]
        metrics:
          primary: [summary.agents.survival_rate]
        criteria: []
        wandb:
          enabled: false
        """,
    )

    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(path)

    assert "matrix.scenarios[0]" in str(excinfo.value)
    assert "night_start" in str(excinfo.value)


def test_load_manifest_rejects_unknown_criteria_key(tmp_path):
    path = _write_manifest(
        tmp_path,
        """
        version: 1

        benchmark:
          id: survival_v1
          version: "1"

        defaults: {}
        seed_sets:
          smoke: [11]
        scenarios:
          default_day: {}
        arms:
          full: {}
        matrix:
          seed_sets: [smoke]
          scenarios: [default_day]
          arms: [full]
        metrics:
          primary: [summary.agents.survival_rate]
        criteria:
          - id: full_survival_gate
            metric: summary.agents.survival_rate
            threshold: 0.8
            stray: true
        wandb:
          enabled: false
        """,
    )

    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(path)

    message = str(excinfo.value)
    assert "criteria[0].stray" in message
    assert "is not allowed" in message


def test_load_manifest_reports_multiple_errors_together(tmp_path):
    path = _write_manifest(
        tmp_path,
        """
        version: 2

        benchmark:
          id: ""
          version: 1
          extra: true

        defaults:
          runtime:
            agents: "three"
            unknown_flag: true
        seed_sets:
          smoke: []
        scenarios:
          default_day:
            runtime:
              start_hour: 8
              stray: value
        arms:
          full: {}
        matrix:
          seed_sets: [smoke, eval]
          scenarios: [missing]
          arms: [full, full]
        metrics:
          secondary:
            - summary.actions.oracle_success_rate
        criteria: []
        wandb:
          enabled: false
        rogue: yes
        """,
    )

    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(path)

    message = str(excinfo.value)
    assert "version" in message
    assert "benchmark.id" in message
    assert "benchmark.version" in message
    assert "benchmark.extra" in message
    assert "defaults.runtime.agents" in message
    assert "defaults.runtime.unknown_flag" in message
    assert "seed_sets.smoke" in message
    assert "scenarios.default_day.runtime.stray" in message
    assert "matrix.seed_sets[1]" in message
    assert "matrix.scenarios[0]" in message
    assert "matrix.arms[1]" in message
    assert "metrics.primary" in message
    assert "rogue" in message

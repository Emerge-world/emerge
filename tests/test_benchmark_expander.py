from __future__ import annotations

import yaml
from pathlib import Path
from textwrap import dedent

import pytest

from simulation.benchmark.expander import build_run_id, expand_manifest
from simulation.benchmark.loader import load_manifest

_EXAMPLE_MANIFEST_DIR = Path(__file__).resolve().parents[1] / "benchmarks" / "manifests"


def _write_manifest(tmp_path, content: str):
    path = tmp_path / "manifest.yaml"
    path.write_text(dedent(content).lstrip(), encoding="utf-8")
    return path


def _load(tmp_path, content: str):
    return load_manifest(_write_manifest(tmp_path, content))


def _make_manifest(tmp_path, *, defaults: dict[str, object]):
    manifest = {
        "version": 1,
        "benchmark": {
            "id": "benchmark_v1",
            "version": "1",
        },
        "defaults": defaults,
        "seed_sets": {
            "smoke": [11],
        },
        "scenarios": {
            "alpha": {},
        },
        "arms": {
            "full": {},
        },
        "matrix": {
            "seed_sets": ["smoke"],
            "scenarios": ["alpha"],
            "arms": ["full"],
        },
        "metrics": {
            "primary": ["summary.agents.survival_rate"],
        },
        "criteria": [],
        "wandb": {
            "enabled": False,
        },
    }
    return load_manifest(
        _write_manifest(tmp_path, yaml.safe_dump(manifest, sort_keys=False))
    )


def _example_manifest_path(name: str) -> Path:
    return _EXAMPLE_MANIFEST_DIR / name


def test_expand_manifest_builds_cross_product_in_deterministic_matrix_order(tmp_path):
    manifest = _load(
        tmp_path,
        """
        version: 1

        benchmark:
          id: benchmark_v1
          version: "1"

        defaults:
          runtime:
            agents: 3
            ticks: 50
            width: 15
            height: 15
            start_hour: 8
            use_llm: true

        seed_sets:
          smoke: [11, 7]
          eval: [101]

        scenarios:
          alpha:
            runtime:
              start_hour: 9
          beta: {}

        arms:
          full: {}
          no_llm:
            runtime:
              use_llm: false

        matrix:
          seed_sets: [smoke, eval]
          scenarios: [alpha, beta]
          arms: [full, no_llm]

        metrics:
          primary: [summary.agents.survival_rate]
        criteria: []
        wandb:
          enabled: false
        """,
    )

    expanded = expand_manifest(manifest)

    assert [
        (item["matrix"]["seed_set"], item["matrix"]["seed"], item["matrix"]["scenario_id"], item["matrix"]["arm_id"])
        for item in expanded
    ] == [
        ("smoke", 11, "alpha", "full"),
        ("smoke", 11, "alpha", "no_llm"),
        ("smoke", 11, "beta", "full"),
        ("smoke", 11, "beta", "no_llm"),
        ("smoke", 7, "alpha", "full"),
        ("smoke", 7, "alpha", "no_llm"),
        ("smoke", 7, "beta", "full"),
        ("smoke", 7, "beta", "no_llm"),
        ("eval", 101, "alpha", "full"),
        ("eval", 101, "alpha", "no_llm"),
        ("eval", 101, "beta", "full"),
        ("eval", 101, "beta", "no_llm"),
    ]


def test_expand_manifest_rejects_unknown_selected_seed_set(tmp_path):
    manifest = _load(
        tmp_path,
        """
        version: 1

        benchmark:
          id: benchmark_v1
          version: "1"

        defaults: {}

        seed_sets:
          smoke: [11]
          eval: [22]

        scenarios:
          alpha: {}

        arms:
          full: {}

        matrix:
          seed_sets: [smoke, eval]
          scenarios: [alpha]
          arms: [full]

        metrics:
          primary: [summary.agents.survival_rate]
        criteria: []
        wandb:
          enabled: false
        """,
    )

    try:
        expand_manifest(manifest, selected_seed_sets=["dev"])
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ValueError for unknown selected seed set")

    assert "selected_seed_sets" in message
    assert "dev" in message


def test_expand_manifest_rejects_duplicate_selected_seed_set(tmp_path):
    manifest = _load(
        tmp_path,
        """
        version: 1

        benchmark:
          id: benchmark_v1
          version: "1"

        defaults: {}

        seed_sets:
          smoke: [11]
          eval: [22]

        scenarios:
          alpha: {}

        arms:
          full: {}

        matrix:
          seed_sets: [smoke, eval]
          scenarios: [alpha]
          arms: [full]

        metrics:
          primary: [summary.agents.survival_rate]
        criteria: []
        wandb:
          enabled: false
        """,
    )

    try:
        expand_manifest(manifest, selected_seed_sets=["smoke", "smoke"])
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ValueError for duplicate selected seed sets")

    assert "selected_seed_sets" in message
    assert "smoke" in message
    assert "duplicate" in message


def test_expand_manifest_selected_seed_sets_follow_manifest_order(tmp_path):
    manifest = _load(
        tmp_path,
        """
        version: 1

        benchmark:
          id: benchmark_v1
          version: "1"

        defaults: {}

        seed_sets:
          smoke: [11]
          eval: [22]

        scenarios:
          alpha: {}

        arms:
          full: {}

        matrix:
          seed_sets: [smoke, eval]
          scenarios: [alpha]
          arms: [full]

        metrics:
          primary: [summary.agents.survival_rate]
        criteria: []
        wandb:
          enabled: false
        """,
    )

    expanded = expand_manifest(manifest, selected_seed_sets=["eval", "smoke"])

    assert [item["matrix"]["seed_set"] for item in expanded] == ["smoke", "eval"]


def test_expand_manifest_rejects_frozen_profile_without_freeze_path(tmp_path):
    manifest = _make_manifest(
        tmp_path,
        defaults={"oracle": {"mode": "frozen"}},
    )

    with pytest.raises(ValueError, match="freeze_precedents_path"):
        expand_manifest(manifest)


def test_expand_manifest_accepts_symbolic_profile_with_freeze_path(tmp_path):
    manifest = _make_manifest(
        tmp_path,
        defaults={
            "oracle": {
                "mode": "symbolic",
                "freeze_precedents_path": "fixtures/symbolic.json",
            }
        },
    )

    runs = expand_manifest(manifest)

    assert runs[0]["profile"]["oracle"]["mode"] == "symbolic"
    assert runs[0]["profile"]["oracle"]["freeze_precedents_path"] == "fixtures/symbolic.json"


def test_expand_manifest_applies_defaults_then_scenario_then_arm_precedence(tmp_path):
    manifest = _load(
        tmp_path,
        """
        version: 1

        benchmark:
          id: benchmark_v1
          version: "1"

        defaults:
          runtime:
            agents: 3
            ticks: 50
            width: 15
            height: 15
            start_hour: 8
            use_llm: true
          capabilities:
            explicit_planning: true
          world_overrides:
            initial_resource_scale: 1.0
          tags: [base]

        seed_sets:
          smoke: [11]

        scenarios:
          alpha:
            runtime:
              width: 20
              start_hour: 10
            world_overrides:
              initial_resource_scale: 0.5
            tags: [scenario]

        arms:
          full:
            runtime:
              width: 25
            world_overrides:
              regen_amount_scale: 0.3
            tags: [arm]

        matrix:
          seed_sets: [smoke]
          scenarios: [alpha]
          arms: [full]

        metrics:
          primary: [summary.agents.survival_rate]
        criteria: []
        wandb:
          enabled: false
        """,
    )

    expanded = expand_manifest(manifest)
    assert len(expanded) == 1

    profile = expanded[0]["profile"]
    assert profile["runtime"]["agents"] == 3
    assert profile["runtime"]["ticks"] == 50
    assert profile["runtime"]["width"] == 25
    assert profile["runtime"]["height"] == 15
    assert profile["runtime"]["start_hour"] == 10
    assert profile["runtime"]["use_llm"] is True
    assert profile["runtime"]["seed"] == 11
    assert profile["capabilities"]["explicit_planning"] is True
    assert profile["world_overrides"]["initial_resource_scale"] == 0.5
    assert profile["world_overrides"]["regen_amount_scale"] == 0.3
    assert profile["benchmark"]["tags"] == ["base", "scenario", "arm"]


def test_build_run_id_uses_stable_format():
    assert build_run_id(
        benchmark_id="benchmark_v1",
        benchmark_version="1",
        seed_set="smoke",
        scenario_id="alpha",
        arm_id="full",
        seed=11,
    ) == "benchmark_v1__v1__ss-smoke__sc-alpha__arm-full__seed-11"


def test_expand_manifest_returns_expected_small_suite_payload():
    manifest = load_manifest(_example_manifest_path("example_small_suite.yaml"))

    expanded = expand_manifest(manifest)

    assert expanded == [
        {
            "run_id": "benchmark_v1__v1__ss-smoke__sc-alpha__arm-full__seed-11",
            "benchmark": {
                "id": "benchmark_v1",
                "version": "1",
            },
            "matrix": {
                "seed_set": "smoke",
                "scenario_id": "alpha",
                "arm_id": "full",
                "seed": 11,
            },
            "profile": {
                "runtime": {
                    "use_llm": True,
                    "model": None,
                    "agents": 2,
                    "ticks": 25,
                    "seed": 11,
                    "width": 12,
                    "height": 12,
                    "start_hour": 9,
                },
                "capabilities": {
                    "explicit_planning": True,
                    "semantic_memory": True,
                    "innovation": True,
                    "item_reflection": True,
                    "social": True,
                    "teach": True,
                    "reproduction": True,
                },
                "persistence": {
                    "mode": "none",
                    "clean_before_run": True,
                },
                "oracle": {
                    "mode": "live",
                    "freeze_precedents_path": None,
                },
                "benchmark": {
                    "benchmark_id": "benchmark_v1",
                    "benchmark_version": "1",
                    "scenario_id": "alpha",
                    "arm_id": "full",
                    "seed_set": "smoke",
                    "session_id": None,
                    "tags": ["suite"],
                },
                "world_overrides": {
                    "initial_resource_scale": None,
                    "regen_chance_scale": None,
                    "regen_amount_scale": None,
                    "world_fixture": None,
                },
            },
            "metrics": {
                "primary": ["summary.agents.survival_rate"],
                "secondary": ["summary.actions.oracle_success_rate"],
            },
            "criteria": [
                {
                    "id": "full_survival_gate",
                    "scenario": "alpha",
                    "compare": None,
                    "metric": "summary.agents.survival_rate",
                    "min_delta_abs": None,
                    "min_delta_rel": None,
                    "arm": "full",
                    "op": ">=",
                    "threshold": 0.8,
                    "description": "Gate",
                    "when_seed_set": None,
                    "group_by": [],
                }
            ],
            "wandb": {
                "enabled": True,
                "project": "emerge",
                "group_by": ["benchmark_id", "scenario_id", "arm_id"],
            },
        },
        {
            "run_id": "benchmark_v1__v1__ss-smoke__sc-alpha__arm-no_llm__seed-11",
            "benchmark": {
                "id": "benchmark_v1",
                "version": "1",
            },
            "matrix": {
                "seed_set": "smoke",
                "scenario_id": "alpha",
                "arm_id": "no_llm",
                "seed": 11,
            },
            "profile": {
                "runtime": {
                    "use_llm": False,
                    "model": None,
                    "agents": 2,
                    "ticks": 25,
                    "seed": 11,
                    "width": 12,
                    "height": 12,
                    "start_hour": 9,
                },
                "capabilities": {
                    "explicit_planning": True,
                    "semantic_memory": True,
                    "innovation": True,
                    "item_reflection": True,
                    "social": True,
                    "teach": True,
                    "reproduction": True,
                },
                "persistence": {
                    "mode": "none",
                    "clean_before_run": True,
                },
                "oracle": {
                    "mode": "live",
                    "freeze_precedents_path": None,
                },
                "benchmark": {
                    "benchmark_id": "benchmark_v1",
                    "benchmark_version": "1",
                    "scenario_id": "alpha",
                    "arm_id": "no_llm",
                    "seed_set": "smoke",
                    "session_id": None,
                    "tags": ["suite"],
                },
                "world_overrides": {
                    "initial_resource_scale": None,
                    "regen_chance_scale": None,
                    "regen_amount_scale": None,
                    "world_fixture": None,
                },
            },
            "metrics": {
                "primary": ["summary.agents.survival_rate"],
                "secondary": ["summary.actions.oracle_success_rate"],
            },
            "criteria": [
                {
                    "id": "full_survival_gate",
                    "scenario": "alpha",
                    "compare": None,
                    "metric": "summary.agents.survival_rate",
                    "min_delta_abs": None,
                    "min_delta_rel": None,
                    "arm": "full",
                    "op": ">=",
                    "threshold": 0.8,
                    "description": "Gate",
                    "when_seed_set": None,
                    "group_by": [],
                }
            ],
            "wandb": {
                "enabled": True,
                "project": "emerge",
                "group_by": ["benchmark_id", "scenario_id", "arm_id"],
            },
        },
        {
            "run_id": "benchmark_v1__v1__ss-smoke__sc-alpha__arm-full__seed-22",
            "benchmark": {
                "id": "benchmark_v1",
                "version": "1",
            },
            "matrix": {
                "seed_set": "smoke",
                "scenario_id": "alpha",
                "arm_id": "full",
                "seed": 22,
            },
            "profile": {
                "runtime": {
                    "use_llm": True,
                    "model": None,
                    "agents": 2,
                    "ticks": 25,
                    "seed": 22,
                    "width": 12,
                    "height": 12,
                    "start_hour": 9,
                },
                "capabilities": {
                    "explicit_planning": True,
                    "semantic_memory": True,
                    "innovation": True,
                    "item_reflection": True,
                    "social": True,
                    "teach": True,
                    "reproduction": True,
                },
                "persistence": {
                    "mode": "none",
                    "clean_before_run": True,
                },
                "oracle": {
                    "mode": "live",
                    "freeze_precedents_path": None,
                },
                "benchmark": {
                    "benchmark_id": "benchmark_v1",
                    "benchmark_version": "1",
                    "scenario_id": "alpha",
                    "arm_id": "full",
                    "seed_set": "smoke",
                    "session_id": None,
                    "tags": ["suite"],
                },
                "world_overrides": {
                    "initial_resource_scale": None,
                    "regen_chance_scale": None,
                    "regen_amount_scale": None,
                    "world_fixture": None,
                },
            },
            "metrics": {
                "primary": ["summary.agents.survival_rate"],
                "secondary": ["summary.actions.oracle_success_rate"],
            },
            "criteria": [
                {
                    "id": "full_survival_gate",
                    "scenario": "alpha",
                    "compare": None,
                    "metric": "summary.agents.survival_rate",
                    "min_delta_abs": None,
                    "min_delta_rel": None,
                    "arm": "full",
                    "op": ">=",
                    "threshold": 0.8,
                    "description": "Gate",
                    "when_seed_set": None,
                    "group_by": [],
                }
            ],
            "wandb": {
                "enabled": True,
                "project": "emerge",
                "group_by": ["benchmark_id", "scenario_id", "arm_id"],
            },
        },
        {
            "run_id": "benchmark_v1__v1__ss-smoke__sc-alpha__arm-no_llm__seed-22",
            "benchmark": {
                "id": "benchmark_v1",
                "version": "1",
            },
            "matrix": {
                "seed_set": "smoke",
                "scenario_id": "alpha",
                "arm_id": "no_llm",
                "seed": 22,
            },
            "profile": {
                "runtime": {
                    "use_llm": False,
                    "model": None,
                    "agents": 2,
                    "ticks": 25,
                    "seed": 22,
                    "width": 12,
                    "height": 12,
                    "start_hour": 9,
                },
                "capabilities": {
                    "explicit_planning": True,
                    "semantic_memory": True,
                    "innovation": True,
                    "item_reflection": True,
                    "social": True,
                    "teach": True,
                    "reproduction": True,
                },
                "persistence": {
                    "mode": "none",
                    "clean_before_run": True,
                },
                "oracle": {
                    "mode": "live",
                    "freeze_precedents_path": None,
                },
                "benchmark": {
                    "benchmark_id": "benchmark_v1",
                    "benchmark_version": "1",
                    "scenario_id": "alpha",
                    "arm_id": "no_llm",
                    "seed_set": "smoke",
                    "session_id": None,
                    "tags": ["suite"],
                },
                "world_overrides": {
                    "initial_resource_scale": None,
                    "regen_chance_scale": None,
                    "regen_amount_scale": None,
                    "world_fixture": None,
                },
            },
            "metrics": {
                "primary": ["summary.agents.survival_rate"],
                "secondary": ["summary.actions.oracle_success_rate"],
            },
            "criteria": [
                {
                    "id": "full_survival_gate",
                    "scenario": "alpha",
                    "compare": None,
                    "metric": "summary.agents.survival_rate",
                    "min_delta_abs": None,
                    "min_delta_rel": None,
                    "arm": "full",
                    "op": ">=",
                    "threshold": 0.8,
                    "description": "Gate",
                    "when_seed_set": None,
                    "group_by": [],
                }
            ],
            "wandb": {
                "enabled": True,
                "project": "emerge",
                "group_by": ["benchmark_id", "scenario_id", "arm_id"],
            },
        },
    ]

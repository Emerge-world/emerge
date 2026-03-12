"""Loading and validating benchmark suite definitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_SCARCITY_KEYS = frozenset({
    "initial_resource_scale",
    "regen_chance_scale",
    "regen_amount_scale",
})


@dataclass(frozen=True)
class BenchmarkDefaults:
    """Common run settings shared by all scenarios in a benchmark suite."""

    agents: int
    ticks: int
    width: int
    height: int
    no_llm: bool
    seeds: list[int]
    model: str | None = None


@dataclass(frozen=True)
class BenchmarkScenario:
    """One named scarcity scenario inside a benchmark suite."""

    id: str
    label: str
    scarcity: dict[str, float]


@dataclass(frozen=True)
class BenchmarkSuite:
    """Top-level suite definition loaded from YAML."""

    path: Path
    benchmark_version: str
    defaults: BenchmarkDefaults
    scenarios: list[BenchmarkScenario]


def _expect_mapping(value: Any, *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _expect_number(value: Any, *, name: str) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    return float(value)


def _load_defaults(raw_defaults: Any) -> BenchmarkDefaults:
    defaults = _expect_mapping(raw_defaults, name="defaults")

    required = ("agents", "ticks", "width", "height", "no_llm", "seeds")
    missing = [key for key in required if key not in defaults]
    if missing:
        raise ValueError(f"defaults missing required keys: {', '.join(missing)}")

    seeds = defaults["seeds"]
    if not isinstance(seeds, list) or not seeds or not all(isinstance(seed, int) for seed in seeds):
        raise ValueError("defaults.seeds must be a non-empty list of integers")

    model = defaults.get("model")
    if model is not None and not isinstance(model, str):
        raise ValueError("defaults.model must be a string when present")

    return BenchmarkDefaults(
        agents=int(defaults["agents"]),
        ticks=int(defaults["ticks"]),
        width=int(defaults["width"]),
        height=int(defaults["height"]),
        no_llm=bool(defaults["no_llm"]),
        seeds=list(seeds),
        model=model,
    )


def _load_scenario(raw_scenario: Any, index: int) -> BenchmarkScenario:
    scenario = _expect_mapping(raw_scenario, name=f"scenarios[{index}]")

    scenario_id = scenario.get("id")
    if not isinstance(scenario_id, str) or not scenario_id:
        raise ValueError(f"scenarios[{index}].id must be a non-empty string")

    label = scenario.get("label", scenario_id)
    if not isinstance(label, str) or not label:
        raise ValueError(f"scenarios[{index}].label must be a non-empty string")

    raw_scarcity = _expect_mapping(scenario.get("scarcity"), name=f"scenarios[{index}].scarcity")
    unknown_keys = set(raw_scarcity) - _SCARCITY_KEYS
    if unknown_keys:
        joined = ", ".join(sorted(unknown_keys))
        raise ValueError(f"scenarios[{index}].scarcity has unknown keys: {joined}")

    missing = [key for key in sorted(_SCARCITY_KEYS) if key not in raw_scarcity]
    if missing:
        raise ValueError(f"scenarios[{index}].scarcity missing required keys: {', '.join(missing)}")

    scarcity = {
        key: _expect_number(raw_scarcity[key], name=f"scenarios[{index}].scarcity.{key}")
        for key in sorted(_SCARCITY_KEYS)
    }

    return BenchmarkScenario(id=scenario_id, label=label, scarcity=scarcity)


def load_benchmark_suite(path: Path | str) -> BenchmarkSuite:
    """Load one benchmark suite YAML file."""

    suite_path = Path(path)
    raw = yaml.safe_load(suite_path.read_text(encoding="utf-8")) or {}
    data = _expect_mapping(raw, name="suite")

    version = data.get("benchmark_version")
    if not isinstance(version, str) or not version:
        raise ValueError("benchmark_version must be a non-empty string")

    defaults = _load_defaults(data.get("defaults"))

    raw_scenarios = data.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ValueError("scenarios must be a non-empty list")

    scenarios = [_load_scenario(raw_scenario, index) for index, raw_scenario in enumerate(raw_scenarios)]

    scenario_ids = [scenario.id for scenario in scenarios]
    duplicates = {scenario_id for scenario_id in scenario_ids if scenario_ids.count(scenario_id) > 1}
    if duplicates:
        raise ValueError(f"duplicate scenario ids: {', '.join(sorted(duplicates))}")

    return BenchmarkSuite(
        path=suite_path,
        benchmark_version=version,
        defaults=defaults,
        scenarios=scenarios,
    )

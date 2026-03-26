from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import asdict

from simulation.benchmark.schema import BenchmarkManifest, ProfileOverride
from simulation.runtime_profiles import build_default_profile, serialize_experiment_profile
from simulation.runtime_settings import ExperimentProfile


def build_run_id(
    *,
    benchmark_id: str,
    benchmark_version: str,
    seed_set: str,
    scenario_id: str,
    arm_id: str,
    seed: int,
) -> str:
    return (
        f"{benchmark_id}__v{benchmark_version}"
        f"__ss-{seed_set}__sc-{scenario_id}__arm-{arm_id}__seed-{seed}"
    )


def expand_manifest(
    manifest: BenchmarkManifest,
    *,
    selected_seed_sets: Iterable[str] | None = None,
) -> list[dict[str, object]]:
    matrix_seed_sets = _resolve_selected_seed_sets(manifest, selected_seed_sets)

    expanded: list[dict[str, object]] = []
    seen_run_ids: set[str] = set()

    for seed_set in matrix_seed_sets:
        for seed in manifest.seed_sets[seed_set]:
            for scenario_id in manifest.matrix.scenarios:
                scenario = manifest.scenarios[scenario_id]
                for arm_id in manifest.matrix.arms:
                    arm = manifest.arms[arm_id]
                    run_id = build_run_id(
                        benchmark_id=manifest.benchmark.id,
                        benchmark_version=manifest.benchmark.version,
                        seed_set=seed_set,
                        scenario_id=scenario_id,
                        arm_id=arm_id,
                        seed=seed,
                    )
                    if run_id in seen_run_ids:
                        raise ValueError(f"Duplicate expanded run_id {run_id!r}")
                    seen_run_ids.add(run_id)

                    profile = _build_profile(
                        manifest=manifest,
                        seed_set=seed_set,
                        seed=seed,
                        scenario_id=scenario_id,
                        scenario=scenario,
                        arm_id=arm_id,
                        arm=arm,
                    )

                    expanded.append(
                        {
                            "run_id": run_id,
                            "benchmark": {
                                "id": manifest.benchmark.id,
                                "version": manifest.benchmark.version,
                            },
                            "matrix": {
                                "seed_set": seed_set,
                                "scenario_id": scenario_id,
                                "arm_id": arm_id,
                                "seed": seed,
                            },
                            "profile": serialize_experiment_profile(profile),
                            "metrics": asdict(manifest.metrics),
                            "criteria": [asdict(criterion) for criterion in manifest.criteria],
                            "wandb": asdict(manifest.wandb),
                        }
                    )

    return expanded


def _resolve_selected_seed_sets(
    manifest: BenchmarkManifest,
    selected_seed_sets: Iterable[str] | None,
) -> list[str]:
    matrix_seed_sets = manifest.matrix.seed_sets
    if selected_seed_sets is None:
        return list(matrix_seed_sets)

    requested = list(selected_seed_sets)
    seen: set[str] = set()
    for seed_set in requested:
        if seed_set in seen:
            raise ValueError(f"selected_seed_sets contains duplicate entry {seed_set!r}")
        seen.add(seed_set)
        if seed_set not in matrix_seed_sets:
            raise ValueError(f"selected_seed_sets contains unknown seed set {seed_set!r}")

    return [seed_set for seed_set in matrix_seed_sets if seed_set in seen]


def _build_profile(
    *,
    manifest: BenchmarkManifest,
    seed_set: str,
    seed: int,
    scenario_id: str,
    scenario: ProfileOverride,
    arm_id: str,
    arm: ProfileOverride,
) -> ExperimentProfile:
    profile = deepcopy(build_default_profile())

    # Benchmark manifests only materialize the model when it is explicitly set.
    profile.runtime.model = None

    _apply_override(profile, manifest.defaults)
    _apply_override(profile, scenario)
    _apply_override(profile, arm)

    profile.runtime.seed = seed
    profile.benchmark.benchmark_id = manifest.benchmark.id
    profile.benchmark.benchmark_version = manifest.benchmark.version
    profile.benchmark.scenario_id = scenario_id
    profile.benchmark.arm_id = arm_id
    profile.benchmark.seed_set = seed_set
    profile.benchmark.session_id = None

    _validate_effective_profile(
        profile,
        scenario_id=scenario_id,
        arm_id=arm_id,
    )

    return profile


def _validate_effective_profile(
    profile: ExperimentProfile,
    *,
    scenario_id: str,
    arm_id: str,
) -> None:
    if (
        profile.oracle.mode in {"frozen", "symbolic"}
        and not profile.oracle.freeze_precedents_path
    ):
        raise ValueError(
            f"Expanded profile for scenario={scenario_id!r}, arm={arm_id!r} "
            "requires oracle.freeze_precedents_path when oracle.mode is frozen or symbolic"
        )


def _apply_override(profile: ExperimentProfile, override: ProfileOverride) -> None:
    for key, value in override.runtime.items():
        setattr(profile.runtime, key, value)
    for key, value in override.capabilities.items():
        setattr(profile.capabilities, key, value)
    for key, value in override.persistence.items():
        setattr(profile.persistence, key, value)
    for key, value in override.oracle.items():
        setattr(profile.oracle, key, value)
    for key, value in override.world_overrides.items():
        setattr(profile.world_overrides, key, value)
    if override.tags:
        profile.benchmark.tags = _merge_tags(profile.benchmark.tags, override.tags)


def _merge_tags(existing: list[str], new_tags: list[str]) -> list[str]:
    merged = list(existing)
    for tag in new_tags:
        if tag not in merged:
            merged.append(tag)
    return merged

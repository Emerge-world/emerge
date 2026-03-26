from __future__ import annotations

from dataclasses import asdict
from typing import Protocol, cast

from simulation import config as sim_config
from simulation.runtime_settings import (
    BenchmarkMetadata,
    CapabilitySettings,
    ExperimentProfile,
    OracleSettings,
    PersistenceSettings,
    PersistenceMode,
    RuntimeSettings,
    WorldOverrides,
)


class _ProfileCLIArgs(Protocol):
    agents: int
    ticks: int | None
    seed: int | None
    no_llm: bool
    model: str | None
    width: int
    height: int
    start_hour: int
    persistence: str


def _normalize_persistence_mode(persistence: PersistenceMode | str) -> PersistenceMode:
    if persistence not in ("none", "oracle", "lineage", "full"):
        raise ValueError(f"Invalid persistence mode: {persistence!r}")
    return cast(PersistenceMode, persistence)


def build_default_profile() -> ExperimentProfile:
    return ExperimentProfile(
        runtime=RuntimeSettings(
            use_llm=True,
            model=sim_config.VLLM_MODEL,
            agents=3,
            ticks=sim_config.MAX_TICKS,
            seed=None,
            width=sim_config.WORLD_WIDTH,
            height=sim_config.WORLD_HEIGHT,
            start_hour=sim_config.WORLD_START_HOUR,
        ),
        capabilities=CapabilitySettings(
            explicit_planning=sim_config.ENABLE_EXPLICIT_PLANNING,
            semantic_memory=True,
            innovation=True,
            item_reflection=True,
            social=True,
            teach=True,
            reproduction=True,
        ),
        persistence=PersistenceSettings(mode="none", clean_before_run=False),
        oracle=OracleSettings(mode="live", freeze_precedents_path=None),
        benchmark=BenchmarkMetadata(
            benchmark_id="adhoc",
            benchmark_version="adhoc",
            scenario_id="default",
            arm_id="default",
        ),
        world_overrides=WorldOverrides(),
    )


def build_profile_from_cli(args: _ProfileCLIArgs) -> ExperimentProfile:
    profile = build_default_profile()
    profile.runtime.agents = args.agents
    profile.runtime.ticks = args.ticks
    profile.runtime.seed = args.seed
    profile.runtime.use_llm = not args.no_llm
    profile.runtime.model = args.model or profile.runtime.model
    profile.runtime.width = args.width
    profile.runtime.height = args.height
    profile.runtime.start_hour = args.start_hour
    profile.persistence.mode = _normalize_persistence_mode(args.persistence)
    return profile


def build_profile_from_engine_kwargs(
    *,
    num_agents: int,
    world_seed: int | None,
    use_llm: bool,
    max_ticks: int | None,
    start_hour: int,
    world_width: int,
    world_height: int,
    ollama_model: str | None,
    persistence: PersistenceMode | str,
) -> ExperimentProfile:
    profile = build_default_profile()
    profile.runtime.agents = num_agents
    profile.runtime.seed = world_seed
    profile.runtime.use_llm = use_llm
    profile.runtime.ticks = max_ticks
    profile.runtime.start_hour = start_hour
    profile.runtime.width = world_width
    profile.runtime.height = world_height
    profile.runtime.model = ollama_model or profile.runtime.model
    profile.persistence.mode = _normalize_persistence_mode(persistence)
    return profile


def serialize_experiment_profile(profile: ExperimentProfile) -> dict:
    return asdict(profile)


def flatten_profile_for_wandb(profile: ExperimentProfile) -> dict[str, object]:
    flattened: dict[str, object] = {}

    def _visit(prefix: str, value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                _visit(f"{prefix}/{key}", child)
            return
        flattened[prefix] = value

    _visit("profile", serialize_experiment_profile(profile))
    return flattened

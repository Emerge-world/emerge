from dataclasses import replace

from main import build_parser
from simulation import config as sim_config
from simulation.runtime_profiles import (
    build_default_profile,
    build_profile_from_cli,
    build_profile_from_engine_kwargs,
    flatten_profile_for_wandb,
    serialize_experiment_profile,
)


def test_build_default_profile_matches_spec_defaults():
    profile = build_default_profile()

    assert profile.runtime.use_llm is True
    assert profile.runtime.model == sim_config.VLLM_MODEL
    assert profile.runtime.agents == 3
    assert profile.runtime.ticks == sim_config.MAX_TICKS
    assert profile.runtime.seed is None
    assert profile.runtime.width == sim_config.WORLD_WIDTH
    assert profile.runtime.height == sim_config.WORLD_HEIGHT
    assert profile.runtime.start_hour == sim_config.WORLD_START_HOUR

    assert profile.capabilities.explicit_planning == sim_config.ENABLE_EXPLICIT_PLANNING
    assert profile.capabilities.semantic_memory is True
    assert profile.capabilities.innovation is True
    assert profile.capabilities.item_reflection is True
    assert profile.capabilities.social is True
    assert profile.capabilities.teach is True
    assert profile.capabilities.reproduction is True

    assert profile.persistence.mode == "none"
    assert profile.persistence.clean_before_run is False

    assert profile.oracle.mode == "live"
    assert profile.oracle.freeze_precedents_path is None

    assert profile.benchmark.benchmark_id == "adhoc"
    assert profile.benchmark.benchmark_version == "adhoc"
    assert profile.benchmark.scenario_id == "default"
    assert profile.benchmark.arm_id == "default"
    assert profile.benchmark.seed_set is None
    assert profile.benchmark.session_id is None
    assert profile.benchmark.tags == []

    assert profile.world_overrides.initial_resource_scale is None
    assert profile.world_overrides.regen_chance_scale is None
    assert profile.world_overrides.regen_amount_scale is None
    assert profile.world_overrides.world_fixture is None


def test_default_list_fields_are_independent():
    first = build_default_profile()
    second = build_default_profile()

    first.benchmark.tags.append("typed")

    assert second.benchmark.tags == []


def test_build_profile_from_cli_applies_runtime_overrides_only():
    args = build_parser().parse_args(
        [
            "--agents",
            "5",
            "--ticks",
            "12",
            "--seed",
            "77",
            "--no-llm",
            "--model",
            "test-model",
            "--width",
            "21",
            "--height",
            "13",
            "--start-hour",
            "20",
            "--persistence",
            "oracle",
        ]
    )

    profile = build_profile_from_cli(args)

    assert profile.runtime.agents == 5
    assert profile.runtime.ticks == 12
    assert profile.runtime.seed == 77
    assert profile.runtime.use_llm is False
    assert profile.runtime.model == "test-model"
    assert profile.runtime.width == 21
    assert profile.runtime.height == 13
    assert profile.runtime.start_hour == 20
    assert profile.persistence.mode == "oracle"
    assert profile.benchmark.benchmark_id == "adhoc"
    assert profile.oracle.mode == "live"


def test_build_profile_from_engine_kwargs_preserves_legacy_persistence_default():
    profile = build_profile_from_engine_kwargs(
        num_agents=1,
        world_seed=5,
        use_llm=False,
        max_ticks=9,
        start_hour=8,
        world_width=11,
        world_height=7,
        ollama_model="engine-model",
        persistence="full",
    )

    assert profile.runtime.agents == 1
    assert profile.runtime.seed == 5
    assert profile.runtime.use_llm is False
    assert profile.runtime.ticks == 9
    assert profile.runtime.start_hour == 8
    assert profile.runtime.width == 11
    assert profile.runtime.height == 7
    assert profile.runtime.model == "engine-model"
    assert profile.persistence.mode == "full"


def test_build_profile_from_engine_kwargs_handles_none_inputs_like_legacy_constructor():
    profile = build_profile_from_engine_kwargs(
        num_agents=2,
        world_seed=None,
        use_llm=True,
        max_ticks=None,
        start_hour=10,
        world_width=12,
        world_height=14,
        ollama_model=None,
        persistence="full",
    )

    assert profile.runtime.seed is None
    assert profile.runtime.ticks is None
    assert profile.runtime.model == sim_config.VLLM_MODEL
    assert profile.persistence.mode == "full"


def test_profile_serialization_and_wandb_flattening_are_stable():
    profile = replace(
        build_default_profile(),
        benchmark=replace(
            build_default_profile().benchmark,
            benchmark_id="runtime-pr1",
            tags=["typed"],
        ),
    )

    serialized = serialize_experiment_profile(profile)
    flattened = flatten_profile_for_wandb(profile)

    assert serialized["benchmark"]["benchmark_id"] == "runtime-pr1"
    assert serialized["benchmark"]["tags"] == ["typed"]
    assert flattened["profile/runtime/agents"] == 3
    assert flattened["profile/runtime/use_llm"] is True
    assert flattened["profile/oracle/mode"] == "live"
    assert flattened["profile/benchmark/benchmark_id"] == "runtime-pr1"

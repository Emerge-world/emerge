import json
from dataclasses import replace

from simulation.config import MAX_AGENTS
from simulation.engine import SimulationEngine
from simulation.runtime_profiles import build_default_profile


def _patch_runtime_side_effects(monkeypatch):
    monkeypatch.setattr("simulation.engine.TICK_DELAY_SECONDS", 0)
    monkeypatch.setattr("simulation.engine.MetricsBuilder.build", lambda self: None)
    monkeypatch.setattr("simulation.engine.EBSBuilder.build", lambda self: None)


def test_profile_argument_has_precedence_over_legacy_kwargs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)
    profile = build_default_profile()
    profile = replace(
        profile,
        runtime=replace(
            profile.runtime,
            agents=2,
            ticks=1,
            seed=7,
            use_llm=False,
            width=18,
            height=12,
            start_hour=20,
        ),
        persistence=replace(profile.persistence, mode="none"),
    )

    engine = SimulationEngine(
        profile=profile,
        num_agents=99,
        world_seed=999,
        use_llm=True,
        max_ticks=123,
        start_hour=6,
        world_width=5,
        world_height=5,
        persistence="full",
        run_digest=False,
    )

    assert engine.profile.runtime.agents == 2
    assert engine.profile.runtime.seed == 7
    assert engine.profile.runtime.use_llm is False
    assert engine.profile.runtime.width == 18
    assert engine.profile.persistence.mode == "none"
    assert engine.max_ticks == 1
    assert engine._world_seed == 7
    assert engine._precedents_path.endswith("precedents_7.json")
    assert engine._lineage_path.endswith("lineage_7.json")


def test_legacy_engine_without_profile_keeps_full_persistence_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)

    engine = SimulationEngine(
        num_agents=1,
        use_llm=False,
        max_ticks=0,
        world_seed=3,
        run_digest=False,
    )

    assert engine.profile.persistence.mode == "full"


def test_agent_count_is_reflected_after_legacy_clamping(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)

    engine = SimulationEngine(
        num_agents=999,
        use_llm=False,
        max_ticks=0,
        world_seed=3,
        run_digest=False,
    )

    assert engine.profile.runtime.agents == len(engine.agents)


def test_profile_argument_is_not_mutated_in_place(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)

    profile = build_default_profile()
    profile = replace(
        profile,
        runtime=replace(
            profile.runtime,
            agents=MAX_AGENTS + 3,
            ticks=0,
            seed=11,
            use_llm=False,
        ),
        persistence=replace(profile.persistence, mode="none"),
    )

    engine = SimulationEngine(profile=profile, run_digest=False)

    assert profile.runtime.agents == MAX_AGENTS + 3
    assert engine.profile.runtime.agents == MAX_AGENTS


def test_normalized_profile_reaches_run_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)

    profile = build_default_profile()
    profile = replace(
        profile,
        runtime=replace(
            profile.runtime,
            agents=MAX_AGENTS + 3,
            ticks=0,
            seed=12,
            use_llm=False,
        ),
        persistence=replace(profile.persistence, mode="none"),
    )

    engine = SimulationEngine(profile=profile, run_digest=False)
    meta_path = engine.event_emitter.run_dir / "meta.json"
    meta = json.loads(meta_path.read_text())

    assert meta["experiment_profile"]["runtime"]["agents"] == MAX_AGENTS


def test_clean_before_run_removes_only_local_paths_allowed_by_persistence_mode(
    tmp_path, monkeypatch
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "precedents_12.json").write_text("{}", encoding="utf-8")
    (data_dir / "lineage_12.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)

    base_profile = build_default_profile()
    profile = replace(
        base_profile,
        runtime=replace(base_profile.runtime, ticks=0, seed=12, use_llm=False),
        persistence=replace(
            base_profile.persistence,
            mode="oracle",
            clean_before_run=True,
        ),
    )

    SimulationEngine(profile=profile, run_digest=False)

    assert not (data_dir / "precedents_12.json").exists()
    assert (data_dir / "lineage_12.json").exists()


def test_frozen_mode_loads_precedents_from_freeze_path_not_local_seed_file(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)
    freeze_path = tmp_path / "fixtures" / "frozen.json"
    freeze_path.parent.mkdir(parents=True)
    freeze_path.write_text(
        json.dumps(
            {
                "version": 1,
                "precedents": {
                    "physical:rest": {
                        "possible": True,
                        "reason": "frozen",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "precedents_7.json").write_text(
        json.dumps(
            {
                "version": 1,
                "precedents": {
                    "physical:rest": {
                        "possible": True,
                        "reason": "local",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    base_profile = build_default_profile()
    profile = replace(
        base_profile,
        runtime=replace(base_profile.runtime, ticks=0, seed=7, use_llm=False),
        persistence=replace(base_profile.persistence, mode="none"),
        oracle=replace(
            base_profile.oracle,
            mode="frozen",
            freeze_precedents_path=str(freeze_path),
        ),
    )

    engine = SimulationEngine(profile=profile, run_digest=False)
    meta = json.loads((engine.event_emitter.run_dir / "meta.json").read_text())

    assert engine.oracle.precedents["physical:rest"]["reason"] == "frozen"
    assert meta["precedents_file"] == str(freeze_path)
    assert meta["persistence_trace"]["mode"] == "none"
    assert meta["oracle_trace"]["mode"] == "frozen"
    assert meta["oracle_trace"]["precedents_loaded_from"] == str(freeze_path)


def test_symbolic_mode_loads_precedents_from_freeze_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)
    freeze_path = tmp_path / "fixtures" / "symbolic.json"
    freeze_path.parent.mkdir(parents=True)
    freeze_path.write_text(
        json.dumps(
            {
                "version": 1,
                "precedents": {
                    "physical:rest": {
                        "possible": True,
                        "reason": "symbolic",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    base_profile = build_default_profile()
    profile = replace(
        base_profile,
        runtime=replace(base_profile.runtime, ticks=0, seed=8, use_llm=False),
        persistence=replace(base_profile.persistence, mode="none"),
        oracle=replace(
            base_profile.oracle,
            mode="symbolic",
            freeze_precedents_path=str(freeze_path),
        ),
    )

    engine = SimulationEngine(profile=profile, run_digest=False)
    meta = json.loads((engine.event_emitter.run_dir / "meta.json").read_text())

    assert engine.oracle.precedents["physical:rest"]["reason"] == "symbolic"
    assert meta["precedents_file"] == str(freeze_path)
    assert meta["oracle_trace"]["mode"] == "symbolic"
    assert meta["oracle_trace"]["precedents_loaded_from"] == str(freeze_path)


def test_frozen_mode_missing_freeze_snapshot_fails_fast(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)
    missing_path = tmp_path / "fixtures" / "missing.json"

    base_profile = build_default_profile()
    profile = replace(
        base_profile,
        runtime=replace(base_profile.runtime, ticks=0, seed=9, use_llm=False),
        persistence=replace(base_profile.persistence, mode="none"),
        oracle=replace(
            base_profile.oracle,
            mode="frozen",
            freeze_precedents_path=str(missing_path),
        ),
    )

    try:
        SimulationEngine(profile=profile, run_digest=False)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ValueError for missing frozen snapshot")

    assert "freeze_precedents_path" in message
    assert "does not exist" in message


def test_symbolic_mode_malformed_freeze_snapshot_fails_fast(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)
    freeze_path = tmp_path / "fixtures" / "broken.json"
    freeze_path.parent.mkdir(parents=True)
    freeze_path.write_text("{not-json", encoding="utf-8")

    base_profile = build_default_profile()
    profile = replace(
        base_profile,
        runtime=replace(base_profile.runtime, ticks=0, seed=10, use_llm=False),
        persistence=replace(base_profile.persistence, mode="none"),
        oracle=replace(
            base_profile.oracle,
            mode="symbolic",
            freeze_precedents_path=str(freeze_path),
        ),
    )

    try:
        SimulationEngine(profile=profile, run_digest=False)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ValueError for malformed symbolic snapshot")

    assert "freeze_precedents_path" in message
    assert "valid JSON" in message


def test_corrupt_local_persistence_does_not_claim_successful_loads_in_trace(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "precedents_14.json").write_text("{broken", encoding="utf-8")
    (data_dir / "lineage_14.json").write_text("{broken", encoding="utf-8")

    base_profile = build_default_profile()
    profile = replace(
        base_profile,
        runtime=replace(base_profile.runtime, ticks=0, seed=14, use_llm=False),
        persistence=replace(base_profile.persistence, mode="full"),
    )

    engine = SimulationEngine(profile=profile, run_digest=False)
    meta = json.loads((engine.event_emitter.run_dir / "meta.json").read_text())

    assert meta["oracle_trace"]["precedents_loaded_from"] is None
    assert meta["persistence_trace"]["lineage_loaded_from"] is None


def test_unavailable_llm_updates_effective_profile(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)

    class FakeLLMClient:
        def __init__(self, *args, **kwargs):
            self.model = kwargs.get("model") or "fake-model"

        def is_available(self):
            return False

    monkeypatch.setattr("simulation.engine.LLMClient", FakeLLMClient)

    profile = build_default_profile()
    profile = replace(
        profile,
        runtime=replace(profile.runtime, use_llm=True, model="forced-model", ticks=0),
    )

    engine = SimulationEngine(profile=profile, run_digest=False)

    assert engine.use_llm is False
    assert engine.profile.runtime.use_llm is False
    assert engine.profile.runtime.model == "forced-model"


def test_runtime_policy_reaches_engine_subsystems(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)

    profile = build_default_profile()
    profile = replace(
        profile,
        runtime=replace(
            profile.runtime,
            agents=1,
            ticks=0,
            seed=21,
            use_llm=False,
        ),
        capabilities=replace(
            profile.capabilities,
            explicit_planning=False,
            semantic_memory=False,
            innovation=False,
        ),
        world_overrides=replace(
            profile.world_overrides,
            initial_resource_scale=0.5,
        ),
        persistence=replace(profile.persistence, mode="none"),
    )

    engine = SimulationEngine(profile=profile, run_digest=False)

    assert engine.runtime_policy.world.initial_resource_scale == 0.5
    assert engine.world.runtime_settings.initial_resource_scale == 0.5
    assert engine.oracle.runtime_settings.innovation is False
    assert engine.agents[0].runtime_settings.explicit_planning is False
    assert engine.agents[0].memory_system.runtime_settings.semantic_memory is False


def test_explicit_wandb_logger_stays_outside_profile(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)
    sentinel = object()

    engine = SimulationEngine(
        profile=build_default_profile(),
        wandb_logger=sentinel,
        run_digest=False,
    )

    assert engine.wandb_logger is sentinel


def test_run_digest_stays_outside_profile(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)

    engine = SimulationEngine(
        profile=build_default_profile(),
        run_digest=False,
    )

    assert engine.run_digest is False

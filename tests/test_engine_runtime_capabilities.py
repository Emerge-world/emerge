from dataclasses import replace

from simulation.engine import SimulationEngine
from simulation.runtime_profiles import build_default_profile


def _patch_runtime_side_effects(monkeypatch):
    monkeypatch.setattr("simulation.engine.TICK_DELAY_SECONDS", 0)
    monkeypatch.setattr("simulation.engine.MetricsBuilder.build", lambda self: None)
    monkeypatch.setattr("simulation.engine.EBSBuilder.build", lambda self: None)


def test_child_spawn_inherits_engine_runtime_policy(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)

    profile = build_default_profile()
    profile = replace(
        profile,
        runtime=replace(
            profile.runtime,
            agents=2,
            ticks=0,
            seed=33,
            use_llm=False,
        ),
        capabilities=replace(
            profile.capabilities,
            explicit_planning=False,
            semantic_memory=False,
            innovation=False,
            item_reflection=False,
            social=False,
            teach=False,
            reproduction=False,
        ),
        persistence=replace(profile.persistence, mode="none"),
    )

    engine = SimulationEngine(profile=profile, run_digest=False)
    parent_a, parent_b = engine.agents[:2]
    child = engine._spawn_child(parent_a.name, parent_b.name, pos=(0, 0), tick=1)

    assert child.runtime_settings is engine.runtime_policy.agent
    assert child.memory_system.runtime_settings is engine.runtime_policy.memory
    assert child.runtime_settings.reproduction is False
    assert "communicate" not in child.actions
    assert "innovate" not in child.actions

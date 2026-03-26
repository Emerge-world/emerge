from dataclasses import replace

from simulation.agent import Agent
from simulation.runtime_policy import AgentRuntimeSettings, MemoryRuntimeSettings


def _make_agent(runtime_settings: AgentRuntimeSettings) -> Agent:
    return Agent(
        name="Ada",
        x=0,
        y=0,
        runtime_settings=runtime_settings,
        memory_settings=MemoryRuntimeSettings(semantic_memory=True),
    )


def _default_runtime_settings() -> AgentRuntimeSettings:
    return AgentRuntimeSettings(
        explicit_planning=True,
        innovation=True,
        item_reflection=True,
        social=True,
        teach=True,
        reproduction=True,
    )


def test_innovation_disabled_omits_innovate():
    agent = _make_agent(replace(_default_runtime_settings(), innovation=False))

    assert "innovate" not in agent.actions
    assert "communicate" in agent.actions


def test_item_reflection_disabled_omits_reflect_item_uses():
    agent = _make_agent(replace(_default_runtime_settings(), item_reflection=False))

    assert "reflect_item_uses" not in agent.actions
    assert "innovate" in agent.actions


def test_social_disabled_omits_social_actions():
    agent = _make_agent(replace(_default_runtime_settings(), social=False))

    assert "communicate" not in agent.actions
    assert "give_item" not in agent.actions
    assert "teach" not in agent.actions


def test_teach_disabled_only_omits_teach():
    agent = _make_agent(replace(_default_runtime_settings(), teach=False))

    assert "communicate" in agent.actions
    assert "give_item" in agent.actions
    assert "teach" not in agent.actions

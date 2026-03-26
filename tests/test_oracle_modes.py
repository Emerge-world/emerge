from unittest.mock import MagicMock

from simulation.agent import Agent
from simulation.oracle import Oracle
from simulation.runtime_policy import OracleRuntimeSettings
from simulation.world import World


def _make_world() -> World:
    return World(width=5, height=5, seed=42)


def _make_agent(world: World, name: str = "Ada") -> Agent:
    agent = Agent(name=name, x=0, y=0)
    for y in range(world.height):
        for x in range(world.width):
            if world.get_tile(x, y) == "land":
                agent.x, agent.y = x, y
                return agent
    return agent


def _typed(payload: dict):
    typed = MagicMock()
    typed.model_dump.return_value = payload
    return typed


def _runtime_settings(*, mode: str, freeze_precedents_path: str | None = None) -> OracleRuntimeSettings:
    return OracleRuntimeSettings(
        innovation=True,
        item_reflection=True,
        social=True,
        teach=True,
        reproduction=True,
        mode=mode,
        freeze_precedents_path=freeze_precedents_path,
    )


def test_live_mode_learns_new_physical_precedent():
    world = _make_world()
    llm = MagicMock()
    llm.generate_structured.return_value = _typed(
        {"possible": True, "reason": "ok", "life_damage": 0}
    )
    llm.last_call = {}
    oracle = Oracle(
        world=world,
        llm=llm,
        runtime_settings=_runtime_settings(mode="live"),
    )

    result = oracle._oracle_reflect_physical("physical:traversal:tile:land", "prompt", tick=1)

    assert result["possible"] is True
    assert "physical:traversal:tile:land" in oracle.precedents


def test_frozen_mode_rejects_physical_novelty_without_writing():
    world = _make_world()
    llm = MagicMock()
    oracle = Oracle(
        world=world,
        llm=llm,
        runtime_settings=_runtime_settings(
            mode="frozen",
            freeze_precedents_path="fixtures/frozen.json",
        ),
    )

    result = oracle._oracle_reflect_physical("physical:traversal:tile:unknown", "prompt", tick=1)

    assert result["possible"] is False
    assert result["reason_code"] == "ORACLE_UNRESOLVED_NOVELTY"
    assert "physical:traversal:tile:unknown" not in oracle.precedents
    llm.generate_structured.assert_not_called()


def test_symbolic_mode_rejects_innovation_novelty_without_approving():
    world = _make_world()
    agent = _make_agent(world)
    llm = MagicMock()
    oracle = Oracle(
        world=world,
        llm=llm,
        runtime_settings=_runtime_settings(
            mode="symbolic",
            freeze_precedents_path="fixtures/symbolic.json",
        ),
    )

    result = oracle.resolve_action(
        agent,
        {"action": "innovate", "new_action_name": "fish_trap", "description": "trap fish"},
        tick=1,
    )

    assert result["success"] is False
    assert result["reason_code"] == "ORACLE_UNRESOLVED_NOVELTY"
    assert "fish_trap" not in agent.actions
    assert "innovation:fish_trap" not in oracle.precedents
    llm.generate_structured.assert_not_called()


def test_symbolic_mode_rejects_custom_action_novelty_without_writing():
    world = _make_world()
    agent = _make_agent(world)
    agent.actions.append("campfire_story")
    llm = MagicMock()
    oracle = Oracle(
        world=world,
        llm=llm,
        runtime_settings=_runtime_settings(
            mode="symbolic",
            freeze_precedents_path="fixtures/symbolic.json",
        ),
    )
    oracle.precedents["innovation:campfire_story"] = {
        "description": "tell a story around the fire",
        "category": "SOCIAL",
    }

    result = oracle._resolve_custom_action(agent, {"action": "campfire_story"}, tick=2)
    situation_key = oracle._custom_action_situation_key("campfire_story", world.get_tile(agent.x, agent.y), {})

    assert result["success"] is False
    assert result["reason_code"] == "ORACLE_UNRESOLVED_NOVELTY"
    assert situation_key not in oracle.precedents
    llm.generate_structured.assert_not_called()


def test_symbolic_mode_uses_curated_custom_action_precedent_hit():
    world = _make_world()
    agent = _make_agent(world)
    agent.actions.append("campfire_story")
    llm = MagicMock()
    oracle = Oracle(
        world=world,
        llm=llm,
        runtime_settings=_runtime_settings(
            mode="symbolic",
            freeze_precedents_path="fixtures/symbolic.json",
        ),
    )
    oracle.precedents["innovation:campfire_story"] = {
        "description": "tell a story around the fire",
        "category": "SOCIAL",
    }
    situation_key = oracle._custom_action_situation_key("campfire_story", world.get_tile(agent.x, agent.y), {})
    oracle.precedents[situation_key] = {
        "success": True,
        "message": "The group listens closely.",
        "effects": {"energy": -1, "hunger": 0, "life": 0},
    }

    result = oracle._resolve_custom_action(agent, {"action": "campfire_story"}, tick=3)

    assert result["success"] is True
    assert result["effects"]["energy"] == -1
    llm.generate_structured.assert_not_called()


def test_symbolic_mode_skips_item_affordance_discovery_on_novelty_miss():
    world = _make_world()
    agent = _make_agent(world)
    llm = MagicMock()
    oracle = Oracle(
        world=world,
        llm=llm,
        runtime_settings=_runtime_settings(
            mode="symbolic",
            freeze_precedents_path="fixtures/symbolic.json",
        ),
    )

    discovered = oracle._discover_item_affordances(
        agent,
        item_name="stone_knife",
        tick=4,
        discovery_mode="auto",
        trigger_action="make_knife",
    )

    assert discovered == []
    llm.generate_structured.assert_not_called()

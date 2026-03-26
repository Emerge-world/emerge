from unittest.mock import MagicMock

from simulation.agent import Agent
from simulation.oracle import Oracle
from simulation.runtime_policy import OracleRuntimeSettings
from simulation.world import World


def _make_runtime_settings(
    *,
    innovation: bool = True,
    item_reflection: bool = True,
    social: bool = True,
    teach: bool = True,
    reproduction: bool = True,
) -> OracleRuntimeSettings:
    return OracleRuntimeSettings(
        innovation=innovation,
        item_reflection=item_reflection,
        social=social,
        teach=teach,
        reproduction=reproduction,
    )


def _make_oracle(world: World, **capabilities) -> Oracle:
    return Oracle(world=world, llm=MagicMock(), runtime_settings=_make_runtime_settings(**capabilities))


def test_innovate_is_blocked_when_innovation_is_disabled():
    world = World(seed=7)
    oracle = _make_oracle(world, innovation=False)
    agent = Agent()

    result = oracle.resolve_action(
        agent,
        {"action": "innovate", "new_action_name": "fish", "description": "catch fish"},
        tick=1,
    )

    assert result["success"] is False
    assert "Unknown action" in result["message"]


def test_reflect_item_uses_is_blocked_when_item_reflection_is_disabled():
    world = World(seed=7)
    oracle = _make_oracle(world, item_reflection=False)
    agent = Agent()
    agent.inventory.add("fruit", 1)

    result = oracle.resolve_action(
        agent,
        {"action": "reflect_item_uses", "item": "fruit"},
        tick=1,
    )

    assert result["success"] is False
    assert "Unknown action" in result["message"]


def test_social_actions_are_blocked_when_social_is_disabled():
    world = World(seed=7)
    oracle = _make_oracle(world, social=False)
    sender = Agent(name="Ada", x=0, y=0)
    target = Agent(name="Bruno", x=1, y=0)
    oracle.current_tick_agents = [sender, target]
    sender.inventory.add("fruit", 1)

    communicate = oracle.resolve_action(
        sender,
        {"action": "communicate", "target": "Bruno", "message": "hello"},
        tick=1,
    )
    give_item = oracle.resolve_action(
        sender,
        {"action": "give_item", "target": "Bruno", "item": "fruit", "quantity": 1},
        tick=1,
    )

    assert communicate["success"] is False
    assert give_item["success"] is False
    assert "Unknown action" in communicate["message"]
    assert "Unknown action" in give_item["message"]


def test_teach_is_blocked_when_teach_is_disabled():
    world = World(seed=7)
    oracle = _make_oracle(world, teach=False)
    teacher = Agent(name="Ada", x=0, y=0)
    learner = Agent(name="Bruno", x=1, y=0)
    oracle.current_tick_agents = [teacher, learner]
    oracle.precedents["innovation:fire_making"] = {"description": "make fire"}

    result = oracle.resolve_action(
        teacher,
        {"action": "teach", "target": "Bruno", "skill": "fire_making"},
        tick=1,
    )

    assert result["success"] is False
    assert "Unknown action" in result["message"]


def test_reproduce_is_blocked_when_reproduction_is_disabled():
    world = World(seed=7)
    oracle = _make_oracle(world, reproduction=False)
    ada = Agent(name="Ada", x=0, y=0)
    bruno = Agent(name="Bruno", x=1, y=0)
    oracle.current_tick_agents = [ada, bruno]

    result = oracle.resolve_action(
        ada,
        {"action": "reproduce", "target": "Bruno"},
        tick=1,
    )

    assert result["success"] is False
    assert "Unknown action" in result["message"]


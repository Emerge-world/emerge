"""
Unit tests for the generic eat action (Issue #23).

Covers:
- Fruit tile → success, hunger reduced (backward compat)
- Mushroom tile → success, hunger reduced
- Stone tile → not edible, returns failure
- Second eat call reuses cached precedent (no extra LLM call)
- Old 'fruit_hunger_reduction' precedent is migrated to 'physical:eat:fruit'
- No resources nearby → failure with appropriate memory message
- Item with life_change != 0 modifies agent life
"""

from unittest.mock import MagicMock

import pytest

from simulation.agent import Agent
from simulation.oracle import Oracle
from simulation.world import World
from simulation.config import AGENT_START_HUNGER, AGENT_START_LIFE, AGENT_MAX_HUNGER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_world(seed: int = 42) -> World:
    return World(width=5, height=5, seed=seed)


def _make_agent(x: int = 0, y: int = 0) -> Agent:
    return Agent(name="Tester", x=x, y=y)


def _make_oracle(world: World, llm=None) -> Oracle:
    return Oracle(world=world, llm=llm)


def _mock_llm(response: dict):
    """Return a MagicMock LLM whose generate_json always returns response."""
    llm = MagicMock()
    llm.generate_json.return_value = response
    llm.last_call = None
    return llm


def _place_resource(world: World, x: int, y: int, resource_type: str, quantity: int = 3):
    """Directly place a resource on the world grid (bypasses generation)."""
    world.resources[(x, y)] = {"type": resource_type, "quantity": quantity}


# ---------------------------------------------------------------------------
# Tests: eating edible items
# ---------------------------------------------------------------------------

class TestEatEdibleItems:
    def test_eat_fruit_succeeds(self):
        """Fruit tile nearby → eat succeeds and reduces hunger."""
        world = _make_world()
        agent = _make_agent(x=2, y=2)
        agent.hunger = 60
        _place_resource(world, 2, 2, "fruit")
        oracle = _make_oracle(world)

        result = oracle.resolve_action(agent, {"action": "eat"}, tick=1)

        assert result["success"] is True
        assert agent.hunger < 60

    def test_eat_mushroom_succeeds(self):
        """Mushroom tile nearby → eat succeeds and reduces hunger."""
        world = _make_world()
        agent = _make_agent(x=2, y=2)
        agent.hunger = 60
        _place_resource(world, 2, 2, "mushroom")
        oracle = _make_oracle(world)

        result = oracle.resolve_action(agent, {"action": "eat"}, tick=1)

        assert result["success"] is True
        assert agent.hunger < 60

    def test_eat_consumes_resource(self):
        """Eating a mushroom removes it from the tile."""
        world = _make_world()
        agent = _make_agent(x=2, y=2)
        agent.hunger = 50
        _place_resource(world, 2, 2, "mushroom", quantity=1)
        oracle = _make_oracle(world)

        oracle.resolve_action(agent, {"action": "eat"}, tick=1)

        # Resource should be fully consumed
        assert world.get_resource(2, 2) is None

    def test_eat_records_item_type_in_memory(self):
        """Agent memory mentions the item type that was eaten."""
        world = _make_world()
        agent = _make_agent(x=2, y=2)
        agent.hunger = 50
        _place_resource(world, 2, 2, "mushroom")
        oracle = _make_oracle(world)

        oracle.resolve_action(agent, {"action": "eat"}, tick=1)

        assert any("mushroom" in m for m in agent.memory)

    def test_eat_adjacent_resource(self):
        """Eat works when resource is on an adjacent tile, not the agent's tile."""
        world = _make_world()
        agent = _make_agent(x=2, y=2)
        agent.hunger = 50
        # Place fruit one step east
        _place_resource(world, 3, 2, "fruit")
        oracle = _make_oracle(world)

        result = oracle.resolve_action(agent, {"action": "eat"}, tick=1)

        assert result["success"] is True


# ---------------------------------------------------------------------------
# Tests: non-edible items
# ---------------------------------------------------------------------------

class TestEatNonEdibleItems:
    def test_eat_stone_fails(self):
        """Stone is not edible → eat returns failure."""
        world = _make_world()
        agent = _make_agent(x=2, y=2)
        agent.hunger = 60
        _place_resource(world, 2, 2, "stone")
        oracle = _make_oracle(world)

        result = oracle.resolve_action(agent, {"action": "eat"}, tick=1)

        assert result["success"] is False
        assert agent.hunger == 60  # hunger unchanged

    def test_eat_stone_does_not_consume_resource(self):
        """Stone is not consumed when agent tries to eat it."""
        world = _make_world()
        agent = _make_agent(x=2, y=2)
        _place_resource(world, 2, 2, "stone", quantity=3)
        oracle = _make_oracle(world)

        oracle.resolve_action(agent, {"action": "eat"}, tick=1)

        assert world.get_resource(2, 2)["quantity"] == 3


# ---------------------------------------------------------------------------
# Tests: no resources nearby
# ---------------------------------------------------------------------------

class TestEatNoResources:
    def test_eat_fails_when_no_resources(self):
        """No resources nearby → eat returns failure."""
        world = _make_world()
        agent = _make_agent(x=2, y=2)
        # Clear any auto-generated resources near agent
        for pos in [(2,2),(3,2),(1,2),(2,3),(2,1)]:
            world.resources.pop(pos, None)
        oracle = _make_oracle(world)

        result = oracle.resolve_action(agent, {"action": "eat"}, tick=1)

        assert result["success"] is False

    def test_eat_hint_in_memory_when_inedible_resources_nearby(self):
        """When only non-edible items nearby, memory mentions them."""
        world = _make_world()
        agent = _make_agent(x=2, y=2)
        for pos in [(2,2),(3,2),(1,2),(2,3),(2,1)]:
            world.resources.pop(pos, None)
        _place_resource(world, 2, 2, "stone")
        oracle = _make_oracle(world)

        oracle.resolve_action(agent, {"action": "eat"}, tick=1)

        # Memory should mention something about non-edible / need to innovate
        combined_memory = " ".join(agent.memory)
        assert "stone" in combined_memory or "innovate" in combined_memory


# ---------------------------------------------------------------------------
# Tests: precedent caching
# ---------------------------------------------------------------------------

class TestEatPrecedentCaching:
    def test_eat_creates_precedent_for_item_type(self):
        """After eating mushroom, a precedent 'physical:eat:mushroom' is cached."""
        world = _make_world()
        agent = _make_agent(x=2, y=2)
        agent.hunger = 50
        _place_resource(world, 2, 2, "mushroom")
        oracle = _make_oracle(world)

        oracle.resolve_action(agent, {"action": "eat"}, tick=1)

        assert "physical:eat:mushroom" in oracle.precedents

    def test_eat_reuses_precedent_without_extra_llm_call(self):
        """Second eat of same item type reuses cached precedent, no LLM call."""
        world = _make_world()
        agent = _make_agent(x=2, y=2)
        llm = _mock_llm({"possible": True, "hunger_reduction": 15, "life_change": 0, "reason": "ok"})
        oracle = _make_oracle(world, llm=llm)
        # Pre-set the precedent as if already established
        oracle.precedents["physical:eat:mushroom"] = {
            "possible": True, "hunger_reduction": 15, "life_change": 0, "reason": "ok"
        }

        # Place resources for two consecutive eat attempts
        agent.hunger = 80
        _place_resource(world, 2, 2, "mushroom", quantity=5)
        oracle.resolve_action(agent, {"action": "eat"}, tick=1)
        agent.hunger = 80
        _place_resource(world, 2, 2, "mushroom", quantity=5)
        oracle.resolve_action(agent, {"action": "eat"}, tick=2)

        # LLM should NOT have been called because precedent was pre-set
        llm.generate_json.assert_not_called()

    def test_eat_stone_precedent_cached(self):
        """Stone precedent (possible=False) is stored after first attempt."""
        world = _make_world()
        agent = _make_agent(x=2, y=2)
        _place_resource(world, 2, 2, "stone")
        oracle = _make_oracle(world)

        oracle.resolve_action(agent, {"action": "eat"}, tick=1)

        assert "physical:eat:stone" in oracle.precedents
        assert oracle.precedents["physical:eat:stone"]["possible"] is False


# ---------------------------------------------------------------------------
# Tests: backward compatibility
# ---------------------------------------------------------------------------

class TestEatBackwardCompat:
    def test_old_fruit_hunger_reduction_precedent_respected(self):
        """If 'fruit_hunger_reduction' exists in precedents, fruit uses that value."""
        world = _make_world()
        agent = _make_agent(x=2, y=2)
        agent.hunger = 80
        _place_resource(world, 2, 2, "fruit")
        oracle = _make_oracle(world)
        # Simulate a precedent file from an old run
        oracle.precedents["fruit_hunger_reduction"] = {"value": 25}

        oracle.resolve_action(agent, {"action": "eat"}, tick=1)

        # Hunger should be reduced by 25 (the migrated value)
        assert agent.hunger == 80 - 25


# ---------------------------------------------------------------------------
# Tests: life_change applied
# ---------------------------------------------------------------------------

class TestEatLifeChange:
    def test_eat_harmful_item_reduces_life(self):
        """Item with life_change < 0 reduces agent life when eaten."""
        world = _make_world()
        agent = _make_agent(x=2, y=2)
        agent.hunger = 50
        # Invent a custom resource type 'poison_berry'
        _place_resource(world, 2, 2, "poison_berry")
        oracle = _make_oracle(world)
        # Pre-seed the precedent: poison_berry is edible but harmful
        oracle.precedents["physical:eat:poison_berry"] = {
            "possible": True,
            "hunger_reduction": 5,
            "life_change": -10,
            "reason": "Toxic but edible",
        }

        initial_life = agent.life
        oracle.resolve_action(agent, {"action": "eat"}, tick=1)

        assert agent.life == initial_life - 10

    def test_eat_safe_item_does_not_change_life(self):
        """Eating fruit (life_change=0) does not modify agent life."""
        world = _make_world()
        agent = _make_agent(x=2, y=2)
        agent.hunger = 50
        _place_resource(world, 2, 2, "fruit")
        oracle = _make_oracle(world)

        initial_life = agent.life
        oracle.resolve_action(agent, {"action": "eat"}, tick=1)

        assert agent.life == initial_life

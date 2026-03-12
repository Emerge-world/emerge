# tests/test_eat_inventory.py
"""
Unit tests for eating items from inventory (issue: agents picking up items
but never consuming them).

Covers:
- Eat from inventory: success, hunger reduced, item removed, energy cost
- Eat from inventory: memory entry added
- Eat from inventory: life_change applied for harmful items
- Eat from inventory: failure when item not in inventory
- Regression: eat without item field still consumes world resource, not inventory
"""

from unittest.mock import MagicMock

import pytest

from simulation.agent import Agent
from simulation.oracle import Oracle
from simulation.world import World
from simulation.config import AGENT_START_LIFE, ENERGY_COST_EAT


# ---------------------------------------------------------------------------
# Helpers (same patterns as test_eat.py)
# ---------------------------------------------------------------------------

def _make_world(seed: int = 42) -> World:
    return World(width=5, height=5, seed=seed)


def _make_agent(x: int = 2, y: int = 2) -> Agent:
    return Agent(name="Tester", x=x, y=y)


def _make_oracle(world: World) -> Oracle:
    return Oracle(world=world, llm=None)


def _place_resource(world: World, x: int, y: int, resource_type: str, quantity: int = 3):
    world.resources[(x, y)] = {"type": resource_type, "quantity": quantity}


def _clear_adjacent(world: World, x: int, y: int):
    """Remove all resources at agent position and 4 cardinal neighbours."""
    for pos in [(x, y), (x+1, y), (x-1, y), (x, y+1), (x, y-1)]:
        world.resources.pop(pos, None)


# ---------------------------------------------------------------------------
# Tests: eat from inventory
# ---------------------------------------------------------------------------

class TestEatFromInventory:
    def test_eat_from_inventory_success(self):
        """Eating fruit from inventory succeeds, removes item, reduces hunger."""
        world = _make_world()
        agent = _make_agent()
        agent.hunger = 60
        _clear_adjacent(world, agent.x, agent.y)
        agent.inventory.add("fruit", 1)
        oracle = _make_oracle(world)
        oracle.precedents["physical:eat:fruit"] = {
            "possible": True, "hunger_reduction": 20, "life_change": 0, "reason": "edible"
        }

        result = oracle.resolve_action(agent, {"action": "eat", "item": "fruit"}, tick=1)

        assert result["success"] is True
        assert not agent.inventory.has("fruit")
        assert agent.hunger == 40
        assert result["effects"]["life"] == 0

    def test_eat_from_inventory_energy_cost(self):
        """Eating from inventory deducts ENERGY_COST_EAT energy."""
        world = _make_world()
        agent = _make_agent()
        agent.hunger = 60
        agent.energy = 50
        _clear_adjacent(world, agent.x, agent.y)
        agent.inventory.add("fruit", 1)
        oracle = _make_oracle(world)
        oracle.precedents["physical:eat:fruit"] = {
            "possible": True, "hunger_reduction": 20, "life_change": 0, "reason": "edible"
        }

        oracle.resolve_action(agent, {"action": "eat", "item": "fruit"}, tick=1)

        assert agent.energy == 50 - ENERGY_COST_EAT

    def test_eat_from_inventory_memory_update(self):
        """Eating from inventory writes a memory entry mentioning 'inventory'."""
        world = _make_world()
        agent = _make_agent()
        agent.hunger = 60
        _clear_adjacent(world, agent.x, agent.y)
        agent.inventory.add("fruit", 1)
        oracle = _make_oracle(world)
        oracle.precedents["physical:eat:fruit"] = {
            "possible": True, "hunger_reduction": 20, "life_change": 0, "reason": "edible"
        }

        oracle.resolve_action(agent, {"action": "eat", "item": "fruit"}, tick=1)

        assert any("inventory" in m for m in agent.memory)

    def test_eat_from_inventory_no_item(self):
        """Eating an item not in inventory returns failure and leaves inventory unchanged."""
        world = _make_world()
        agent = _make_agent()
        _clear_adjacent(world, agent.x, agent.y)
        oracle = _make_oracle(world)

        result = oracle.resolve_action(agent, {"action": "eat", "item": "stone"}, tick=1)

        assert result["success"] is False
        assert agent.inventory.total() == 0
        assert "inventory" in result["message"].lower()

    def test_eat_from_inventory_life_change(self):
        """Eating a harmful item from inventory reduces life."""
        world = _make_world()
        agent = _make_agent()
        agent.hunger = 60
        _clear_adjacent(world, agent.x, agent.y)
        agent.inventory.add("mushroom", 1)
        oracle = _make_oracle(world)
        oracle.precedents["physical:eat:mushroom"] = {
            "possible": True, "hunger_reduction": 5, "life_change": -10, "reason": "toxic"
        }

        initial_life = agent.life
        oracle.resolve_action(agent, {"action": "eat", "item": "mushroom"}, tick=1)

        assert agent.life == initial_life - 10

    def test_eat_world_resource_when_inventory_nonempty(self):
        """eat without item field still consumes world resource, not inventory."""
        world = _make_world()
        agent = _make_agent()
        agent.hunger = 60
        _clear_adjacent(world, agent.x, agent.y)
        # Place a world resource adjacent to agent
        _place_resource(world, 3, 2, "fruit", quantity=1)
        # Also give agent fruit in inventory
        agent.inventory.add("fruit", 1)
        oracle = _make_oracle(world)

        result = oracle.resolve_action(agent, {"action": "eat"}, tick=1)

        # World resource consumed
        assert result["success"] is True
        assert world.get_resource(3, 2) is None
        # Inventory unchanged
        assert agent.inventory.items == {"fruit": 1}

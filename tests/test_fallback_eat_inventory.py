"""
Unit tests for Agent._fallback_decision — inventory-eat fix.

No LLM, World, or Oracle needed; _fallback_decision only reads
nearby_tiles, self.inventory, self.hunger, and self.energy.
"""
import pytest
from simulation.agent import Agent


def make_agent(hunger: int = 80, energy: int = 50) -> Agent:
    a = Agent(name="TestAgent", x=5, y=5, llm=None)
    a.hunger = hunger
    a.energy = energy
    return a


def fruit_tile_nearby() -> dict:
    return {"x": 5, "y": 4, "distance": 1, "resource": {"type": "fruit", "quantity": 1}}


def stone_tile_nearby() -> dict:
    return {"x": 5, "y": 4, "distance": 1, "resource": {"type": "stone", "quantity": 3}}


# --- 1. Eats from inventory when hungry, no ground food ---

def test_eats_from_inventory_when_no_ground_food():
    agent = make_agent(hunger=80)
    agent.inventory.add("fruit", 2)
    result = agent._fallback_decision([])
    assert result["action"] == "eat"
    assert result["item"] == "fruit"


# --- 2. Prefers ground food over inventory ---

def test_prefers_ground_food_over_inventory():
    agent = make_agent(hunger=80)
    agent.inventory.add("fruit", 2)
    result = agent._fallback_decision([fruit_tile_nearby()])
    assert result["action"] == "eat"
    assert "item" not in result


# --- 3. Skips non-edible inventory when hungry ---

def test_skips_non_edible_inventory():
    agent = make_agent(hunger=80)
    agent.inventory.add("stone", 3)
    result = agent._fallback_decision([])
    # Should NOT eat; no edible food anywhere
    assert result["action"] != "eat"


# --- 4. Picks edible item from mixed inventory ---

def test_picks_edible_from_mixed_inventory():
    agent = make_agent(hunger=80)
    agent.inventory.add("stone", 2)
    agent.inventory.add("mushroom", 1)
    result = agent._fallback_decision([])
    assert result["action"] == "eat"
    assert result["item"] == "mushroom"


# --- 5. No eat when not hungry ---

def test_no_eat_when_not_hungry():
    agent = make_agent(hunger=20)
    agent.inventory.add("fruit", 3)
    result = agent._fallback_decision([])
    assert result["action"] != "eat"


# --- 6. Ignores stone on the ground when hungry ---

def test_ignores_stone_on_ground():
    agent = make_agent(hunger=80)
    result = agent._fallback_decision([stone_tile_nearby()])
    # Should not eat stone; might move or rest but not eat
    assert result["action"] != "eat"


# --- 7. Moves toward edible tiles, not stone ---

def test_moves_toward_edible_not_stone():
    agent = make_agent(hunger=20, energy=50)  # not hungry enough to eat
    # stone close, fruit farther
    tiles = [
        stone_tile_nearby(),
        {"x": 3, "y": 5, "distance": 2, "resource": {"type": "fruit", "quantity": 1}},
    ]
    result = agent._fallback_decision(tiles)
    assert result["action"] == "move"
    # Should be heading west (toward x=3 from x=5), not toward stone
    assert result["direction"] == "west"

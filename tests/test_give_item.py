from unittest.mock import MagicMock

from simulation.agent import Agent
from simulation.config import GIVE_ITEM_ENERGY_COST, GIVE_ITEM_TRUST_DELTA
from simulation.oracle import Oracle


def make_two_agents():
    giver = Agent(name="Ada", x=5, y=5)
    giver.energy = 20
    giver.inventory.add("fruit", 3)
    target = Agent(name="Bruno", x=6, y=5)  # 1 tile away (adjacent)
    return giver, target


def make_oracle(giver, target):
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [giver, target]
    return oracle


# --- Happy path ---

def test_give_item_transfers_item():
    giver, target = make_two_agents()
    oracle = make_oracle(giver, target)
    action = {"action": "give_item", "target": "Bruno", "item": "fruit", "quantity": 2, "reason": "helping"}
    result = oracle.resolve_action(giver, action, tick=1)
    assert result["success"] is True
    assert giver.inventory.has("fruit", 1)
    assert not giver.inventory.has("fruit", 2)
    assert target.inventory.has("fruit", 2)


def test_give_item_costs_energy():
    giver, target = make_two_agents()
    oracle = make_oracle(giver, target)
    action = {"action": "give_item", "target": "Bruno", "item": "fruit", "quantity": 1, "reason": "test"}
    oracle.resolve_action(giver, action, tick=1)
    assert giver.energy == 20 - GIVE_ITEM_ENERGY_COST


def test_give_item_increases_target_trust():
    giver, target = make_two_agents()
    oracle = make_oracle(giver, target)
    action = {"action": "give_item", "target": "Bruno", "item": "fruit", "quantity": 1, "reason": "test"}
    oracle.resolve_action(giver, action, tick=1)
    # Target (Bruno) should trust giver (Ada) more
    assert "Ada" in target.relationships
    rel = target.relationships["Ada"]
    assert abs(rel.trust - GIVE_ITEM_TRUST_DELTA) < 0.001


def test_give_item_increments_cooperations():
    giver, target = make_two_agents()
    oracle = make_oracle(giver, target)
    action = {"action": "give_item", "target": "Bruno", "item": "fruit", "quantity": 1, "reason": "test"}
    oracle.resolve_action(giver, action, tick=1)
    assert target.relationships["Ada"].cooperations >= 1


def test_give_item_adds_episodic_memory_to_both():
    giver, target = make_two_agents()
    oracle = make_oracle(giver, target)
    action = {"action": "give_item", "target": "Bruno", "item": "fruit", "quantity": 1, "reason": "test"}
    oracle.resolve_action(giver, action, tick=1)
    giver_memories = " ".join(giver.memory)
    target_memories = " ".join(target.memory)
    assert "Bruno" in giver_memories or "fruit" in giver_memories
    assert "Ada" in target_memories or "fruit" in target_memories


# --- Failure cases ---

def test_give_item_target_not_found():
    giver, _ = make_two_agents()
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [giver]
    action = {"action": "give_item", "target": "Ghost", "item": "fruit", "quantity": 1, "reason": "test"}
    result = oracle.resolve_action(giver, action, tick=1)
    assert result["success"] is False


def test_give_item_target_dead():
    giver, target = make_two_agents()
    target.alive = False
    oracle = make_oracle(giver, target)
    action = {"action": "give_item", "target": "Bruno", "item": "fruit", "quantity": 1, "reason": "test"}
    result = oracle.resolve_action(giver, action, tick=1)
    assert result["success"] is False


def test_give_item_target_not_adjacent():
    giver = Agent(name="Ada", x=0, y=0)
    giver.energy = 20
    giver.inventory.add("fruit", 3)
    far_target = Agent(name="Bruno", x=5, y=5)  # 10 tiles away
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [giver, far_target]
    action = {"action": "give_item", "target": "Bruno", "item": "fruit", "quantity": 1, "reason": "test"}
    result = oracle.resolve_action(giver, action, tick=1)
    assert result["success"] is False


def test_give_item_insufficient_energy():
    giver, target = make_two_agents()
    giver.energy = GIVE_ITEM_ENERGY_COST - 1
    oracle = make_oracle(giver, target)
    action = {"action": "give_item", "target": "Bruno", "item": "fruit", "quantity": 1, "reason": "test"}
    result = oracle.resolve_action(giver, action, tick=1)
    assert result["success"] is False


def test_give_item_giver_lacks_item():
    giver, target = make_two_agents()
    oracle = make_oracle(giver, target)
    action = {"action": "give_item", "target": "Bruno", "item": "stone", "quantity": 1, "reason": "test"}
    result = oracle.resolve_action(giver, action, tick=1)
    assert result["success"] is False


def test_give_item_target_inventory_full():
    giver, target = make_two_agents()
    # Fill target's inventory completely
    target.inventory.add("stone", target.inventory.capacity)
    oracle = make_oracle(giver, target)
    action = {"action": "give_item", "target": "Bruno", "item": "fruit", "quantity": 1, "reason": "test"}
    result = oracle.resolve_action(giver, action, tick=1)
    assert result["success"] is False


def test_give_item_defaults_to_one_when_quantity_is_none():
    giver, target = make_two_agents()
    oracle = make_oracle(giver, target)
    action = {"action": "give_item", "target": "Bruno", "item": "fruit", "quantity": None, "reason": "test"}

    result = oracle.resolve_action(giver, action, tick=1)

    assert result["success"] is True
    assert giver.inventory.has("fruit", 2)
    assert not giver.inventory.has("fruit", 3)
    assert target.inventory.has("fruit", 1)


def test_give_item_rejects_non_positive_quantity():
    giver, target = make_two_agents()
    oracle = make_oracle(giver, target)
    action = {"action": "give_item", "target": "Bruno", "item": "fruit", "quantity": 0, "reason": "test"}

    result = oracle.resolve_action(giver, action, tick=1)

    assert result["success"] is False
    assert giver.inventory.has("fruit", 3)
    assert target.inventory.is_empty()

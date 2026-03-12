from simulation.agent import Agent
from simulation.oracle import Oracle
from simulation.world import World


def make_world():
    world = World(width=5, height=5, seed=42)
    world.resources.clear()
    return world


def make_agent():
    agent = Agent(name="Ada", x=2, y=2)
    agent.inventory.add("fruit", 3)
    agent.energy = 20
    return agent


def test_drop_item_creates_resource_on_empty_tile():
    world = make_world()
    agent = make_agent()
    oracle = Oracle(world=world, llm=None)

    result = oracle.resolve_action(
        agent,
        {"action": "drop_item", "item": "fruit", "quantity": 2, "reason": "free space"},
        tick=1,
    )

    assert result["success"] is True
    assert agent.inventory.items == {"fruit": 1}
    assert world.get_resource(2, 2) == {"type": "fruit", "quantity": 2}


def test_drop_item_merges_same_type_tile_resource():
    world = make_world()
    world.resources[(2, 2)] = {"type": "fruit", "quantity": 1}
    agent = make_agent()
    oracle = Oracle(world=world, llm=None)

    result = oracle.resolve_action(
        agent,
        {"action": "drop_item", "item": "fruit", "quantity": 2, "reason": "stack it"},
        tick=1,
    )

    assert result["success"] is True
    assert agent.inventory.items == {"fruit": 1}
    assert world.get_resource(2, 2) == {"type": "fruit", "quantity": 3}


def test_drop_item_rejects_non_positive_quantity():
    world = make_world()
    agent = make_agent()
    oracle = Oracle(world=world, llm=None)

    result = oracle.resolve_action(
        agent,
        {"action": "drop_item", "item": "fruit", "quantity": 0, "reason": "bad"},
        tick=1,
    )

    assert result["success"] is False
    assert agent.inventory.items == {"fruit": 3}
    assert world.get_resource(2, 2) is None


def test_drop_item_defaults_invalid_quantity_to_one():
    world = make_world()
    agent = make_agent()
    oracle = Oracle(world=world, llm=None)

    result = oracle.resolve_action(
        agent,
        {"action": "drop_item", "item": "fruit", "quantity": None, "reason": "default"},
        tick=1,
    )

    assert result["success"] is True
    assert agent.inventory.items == {"fruit": 2}
    assert world.get_resource(2, 2) == {"type": "fruit", "quantity": 1}


def test_drop_item_fails_when_inventory_lacks_item():
    world = make_world()
    agent = make_agent()
    oracle = Oracle(world=world, llm=None)

    result = oracle.resolve_action(
        agent,
        {"action": "drop_item", "item": "stone", "quantity": 1, "reason": "impossible"},
        tick=1,
    )

    assert result["success"] is False
    assert world.get_resource(2, 2) is None


def test_drop_item_fails_on_conflicting_tile_resource_without_mutation():
    world = make_world()
    world.resources[(2, 2)] = {"type": "stone", "quantity": 4}
    agent = make_agent()
    oracle = Oracle(world=world, llm=None)

    result = oracle.resolve_action(
        agent,
        {"action": "drop_item", "item": "fruit", "quantity": 2, "reason": "conflict"},
        tick=1,
    )

    assert result["success"] is False
    assert agent.inventory.items == {"fruit": 3}
    assert world.get_resource(2, 2) == {"type": "stone", "quantity": 4}


def test_drop_item_adds_memory_on_success():
    world = make_world()
    agent = make_agent()
    oracle = Oracle(world=world, llm=None)

    oracle.resolve_action(
        agent,
        {"action": "drop_item", "item": "fruit", "quantity": 1, "reason": "remember this"},
        tick=1,
    )

    assert any("dropped 1x fruit" in memory.lower() for memory in agent.memory)

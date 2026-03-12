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

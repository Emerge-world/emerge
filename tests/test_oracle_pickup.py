"""Tests for Oracle pickup action resolution."""
import pytest
from simulation.agent import Agent
from simulation.oracle import Oracle
from simulation.world import World
from simulation.config import AGENT_INVENTORY_CAPACITY


def _make_world(seed: int = 42, width: int = 20, height: int = 20) -> World:
    return World(width=width, height=height, seed=seed)


def _make_oracle(world: World) -> Oracle:
    return Oracle(world=world, llm=None)


def _find_tile_with_resource(world: World, resource_type: str = None):
    """Return (x, y) of first tile with a resource, optionally filtered by type."""
    for (x, y), res in world.resources.items():
        if resource_type is None or res["type"] == resource_type:
            if res.get("quantity", 0) > 0:
                return (x, y)
    return None


class TestOraclePickup:
    def test_pickup_success(self):
        """Agent picks up 1 item from tile with resource."""
        world = _make_world()
        pos = _find_tile_with_resource(world)
        if pos is None:
            pytest.skip("No tile with resource in generated world")
        x, y = pos
        resource_type = world.resources[(x, y)]["type"]
        qty_before = world.resources[(x, y)]["quantity"]

        oracle = _make_oracle(world)
        agent = Agent(x=x, y=y)

        result = oracle.resolve_action(agent, {"action": "pickup"}, tick=1)

        assert result["success"] is True
        assert agent.inventory.has(resource_type, 1)
        # World resource decremented by 1 (unless water which is infinite)
        if resource_type != "water":
            assert world.resources.get((x, y), {}).get("quantity", 0) == qty_before - 1

    def test_pickup_no_resource(self):
        """Agent picks up from empty tile → failure."""
        world = _make_world()
        oracle = _make_oracle(world)

        # Find a land tile without resources
        land_pos = None
        for y in range(world.height):
            for x in range(world.width):
                if world.get_tile(x, y) == "land" and world.get_resource(x, y) is None:
                    land_pos = (x, y)
                    break
            if land_pos:
                break

        if land_pos is None:
            pytest.skip("No resource-free land tile in this world")

        agent = Agent(x=land_pos[0], y=land_pos[1])
        result = oracle.resolve_action(agent, {"action": "pickup"}, tick=1)

        assert result["success"] is False
        assert agent.inventory.is_empty()

    def test_pickup_inventory_full(self):
        """Agent with full inventory cannot pick up."""
        world = _make_world()
        pos = _find_tile_with_resource(world)
        if pos is None:
            pytest.skip("No tile with resource in generated world")
        x, y = pos

        oracle = _make_oracle(world)
        agent = Agent(x=x, y=y)

        # Fill inventory to capacity with existing items
        agent.inventory.add("stone", AGENT_INVENTORY_CAPACITY)
        assert agent.inventory.free_space() == 0

        result = oracle.resolve_action(agent, {"action": "pickup"}, tick=1)

        assert result["success"] is False
        assert "full" in result["message"].lower()

    def test_pickup_world_resource_decremented(self):
        """Pickup removes exactly 1 from world resource (non-water)."""
        world = _make_world()
        pos = _find_tile_with_resource(world, resource_type="fruit")
        if pos is None:
            pytest.skip("No fruit in generated world")
        x, y = pos
        qty_before = world.resources[(x, y)]["quantity"]

        oracle = _make_oracle(world)
        agent = Agent(x=x, y=y)
        oracle.resolve_action(agent, {"action": "pickup"}, tick=1)

        remaining = world.resources.get((x, y), {}).get("quantity", 0)
        assert remaining == qty_before - 1

    def test_pickup_adds_to_inventory(self):
        """Pickup adds the resource type to agent inventory."""
        world = _make_world()
        pos = _find_tile_with_resource(world, resource_type="fruit")
        if pos is None:
            pytest.skip("No fruit in generated world")
        x, y = pos

        oracle = _make_oracle(world)
        agent = Agent(x=x, y=y)
        oracle.resolve_action(agent, {"action": "pickup"}, tick=1)

        assert agent.inventory.has("fruit", 1)
        assert agent.inventory.total() == 1

    def test_agent_status_includes_inventory(self):
        """get_status() returns inventory field."""
        agent = Agent(x=0, y=0)
        status = agent.get_status()
        assert "inventory" in status
        assert "items" in status["inventory"]
        assert "capacity" in status["inventory"]


class TestOracleInnovateRequiresItems:
    """Oracle checks requires.items before LLM call for innovations."""

    def test_innovate_fails_missing_required_item(self):
        """Innovation with item requirement fails if agent lacks the item."""
        world = _make_world()
        oracle = _make_oracle(world)

        # Find a land tile for the agent
        land_pos = None
        for y in range(world.height):
            for x in range(world.width):
                if world.get_tile(x, y) == "land":
                    land_pos = (x, y)
                    break
            if land_pos:
                break

        if land_pos is None:
            pytest.skip("No land tile in world")

        agent = Agent(x=land_pos[0], y=land_pos[1])
        # Agent has no items in inventory

        action = {
            "action": "innovate",
            "new_action_name": "build_shelter",
            "description": "build a shelter from wood",
            "requires": {"items": {"wood": 3}},
        }
        result = oracle.resolve_action(agent, action, tick=1)

        assert result["success"] is False
        assert "build_shelter" not in agent.actions
        assert "wood" in result["message"].lower() or "item" in result["message"].lower()

    def test_innovate_succeeds_with_required_items(self):
        """Innovation with item requirement succeeds if agent has the items (no LLM)."""
        world = _make_world()
        oracle = _make_oracle(world)  # no LLM → auto-approves

        # Place agent on land
        land_pos = None
        for y in range(world.height):
            for x in range(world.width):
                if world.get_tile(x, y) == "land":
                    land_pos = (x, y)
                    break
            if land_pos:
                break

        if land_pos is None:
            pytest.skip("No land tile in world")

        agent = Agent(x=land_pos[0], y=land_pos[1])
        agent.inventory.add("stone", 3)  # give agent required items

        action = {
            "action": "innovate",
            "new_action_name": "make_knife",
            "description": "carve stone into a knife",
            "requires": {"items": {"stone": 2}},
        }
        result = oracle.resolve_action(agent, action, tick=1)

        # Without LLM, oracle auto-approves innovations
        assert result["success"] is True
        assert "make_knife" in agent.actions
        # Items should NOT be consumed (crafting is next PR)
        assert agent.inventory.has("stone", 3)

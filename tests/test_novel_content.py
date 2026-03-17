"""
Tests for novel content handling: the simulation must gracefully process
LLM-invented tile types and resources without code changes.
"""

import pytest
import yaml
from pathlib import Path

from simulation.world_schema import WorldSchema
from simulation.world import World
from simulation.oracle import Oracle
from simulation.agent import Agent
from simulation.day_cycle import DayCycle


def _make_schema_with_swamp(tmp_path: Path) -> WorldSchema:
    """Build a minimal schema that adds a 'swamp' tile with 'herbs' resource."""
    src = Path(__file__).parent.parent / "data" / "schemas" / "base_world.yaml"
    with src.open() as f:
        data = yaml.safe_load(f)

    # Inject novel tile
    data["tiles"]["swamp"] = {
        "height_max": 0.74,  # between land (0.70) and tree (0.76)
        "walkable": True,
        "spawn_tiles": True,
        "resource": {
            "type": "herbs",
            "min": 1,
            "max": 3,
            "regenerates": True,
        },
        "risk": {"energy_cost_add": 1},
    }
    # Inject novel resource
    data["resources"]["herbs"] = {
        "edible": True,
        "hunger_reduction": 12,
        "life_change": 2,
    }
    return WorldSchema.from_dict(data)


@pytest.fixture
def swamp_schema(tmp_path) -> WorldSchema:
    return _make_schema_with_swamp(tmp_path)


class TestNovelTileInWorldGeneration:
    def test_schema_accepts_swamp_tile(self, swamp_schema):
        assert "swamp" in swamp_schema.tiles
        cfg = swamp_schema.tiles["swamp"]
        assert cfg["walkable"] is True
        assert cfg["resource"]["type"] == "herbs"

    def test_swamp_sorted_with_others(self, swamp_schema):
        sorted_tiles = swamp_schema.get_tiles_sorted_by_height()
        names = [n for n, _ in sorted_tiles]
        # swamp is between land (0.70) and tree (0.76)
        assert "swamp" in names
        land_idx = names.index("land")
        swamp_idx = names.index("swamp")
        tree_idx = names.index("tree")
        assert land_idx < swamp_idx < tree_idx

    def test_world_generates_with_swamp_schema(self, swamp_schema):
        world = World(seed=42, world_schema=swamp_schema)
        # World must generate without error
        assert world.width == swamp_schema.world["width"]
        assert world.height == swamp_schema.world["height"]
        all_tiles = {world.grid[y][x] for y in range(world.height) for x in range(world.width)}
        # Swamp and herbs are valid tiles (may or may not appear due to seed)
        for tile in all_tiles:
            assert isinstance(tile, str)

    def test_world_walkability_for_novel_tile(self, swamp_schema):
        world = World(seed=42, world_schema=swamp_schema)
        # Swamp should be walkable
        walkable = swamp_schema.get_walkable_tiles()
        assert "swamp" in walkable
        # Any swamp tile found in world should be walkable
        for y in range(world.height):
            for x in range(world.width):
                if world.grid[y][x] == "swamp":
                    assert world.is_walkable(x, y)
                    break

    def test_novel_tile_spawn_tiles(self, swamp_schema):
        spawn = swamp_schema.get_spawn_tiles()
        assert "swamp" in spawn

    def test_herbs_in_regenerating_map(self, swamp_schema):
        regen = swamp_schema.get_regenerating_tile_resource()
        assert "swamp" in regen
        assert regen["swamp"] == "herbs"


class TestNovelResourceHandling:
    def test_herbs_edible_in_schema(self, swamp_schema):
        edible = swamp_schema.get_edible_resources()
        assert "herbs" in edible

    def test_herbs_not_inexhaustible(self, swamp_schema):
        assert swamp_schema.is_resource_inexhaustible("herbs") is False

    def test_world_consumes_herbs(self, swamp_schema):
        world = World(seed=42, world_schema=swamp_schema)
        # Manually place herbs at (0,0) for test
        world.resources[(0, 0)] = {"type": "herbs", "quantity": 3}
        consumed = world.consume_resource(0, 0, 1)
        assert consumed == 1
        assert world.resources[(0, 0)]["quantity"] == 2

    def test_oracle_eat_defaults_include_herbs(self, swamp_schema):
        world = World(seed=42, world_schema=swamp_schema)
        oracle = Oracle(world, llm=None, world_schema=swamp_schema)
        # schema_eat_defaults should include herbs
        assert "herbs" in oracle._schema_eat_defaults
        herbs_default = oracle._schema_eat_defaults["herbs"]
        assert herbs_default["possible"] is True
        assert herbs_default["hunger_reduction"] == 12
        assert herbs_default["life_change"] == 2

    def test_oracle_eat_effect_uses_herbs_default(self, swamp_schema):
        world = World(seed=42, world_schema=swamp_schema)
        oracle = Oracle(world, llm=None, world_schema=swamp_schema)
        effect = oracle._get_item_eat_effect("herbs", tick=1)
        assert effect["possible"] is True
        assert effect["hunger_reduction"] == 12

    def test_agent_edible_items_include_herbs(self, swamp_schema):
        agent = Agent(x=0, y=0, world_schema=swamp_schema)
        assert "herbs" in agent._edible_items

    def test_agent_fallback_moves_toward_herbs(self, swamp_schema):
        agent = Agent(x=5, y=5, world_schema=swamp_schema)
        agent.hunger = 50  # hungry enough to seek food
        nearby = [
            {"x": 6, "y": 5, "tile": "swamp", "distance": 1, "resource": {"type": "herbs", "quantity": 2}},
        ]
        decision = agent._fallback_decision(nearby)
        # Agent should try to eat herbs (it's on distance 1 and agent is hungry)
        assert decision["action"] in ("eat", "move")


class TestNovelTileOracleTraversal:
    def test_oracle_resolves_move_to_swamp(self, swamp_schema):
        """Oracle should allow movement to swamp without crashing."""
        world = World(seed=42, world_schema=swamp_schema)
        # Force a swamp tile adjacent to agent
        world.grid[1][1] = "swamp"
        oracle = Oracle(world, llm=None, world_schema=swamp_schema)
        agent = Agent(x=1, y=0, world_schema=swamp_schema)
        agent.energy = 100
        result = oracle.resolve_action(agent, {"action": "move", "direction": "south"}, tick=1)
        # Should succeed (swamp is walkable)
        assert result["success"] is True
        assert agent.x == 1 and agent.y == 1

    def test_oracle_risk_applied_for_novel_tile(self, swamp_schema):
        """Swamp has energy_cost_add=1, so move should cost base + 1."""
        world = World(seed=42, world_schema=swamp_schema)
        world.grid[1][1] = "swamp"
        oracle = Oracle(world, llm=None, world_schema=swamp_schema)
        day_cycle = DayCycle(world_schema=swamp_schema)
        oracle.day_cycle = day_cycle
        agent = Agent(x=1, y=0, world_schema=swamp_schema)
        initial_energy = agent.energy
        oracle.resolve_action(agent, {"action": "move", "direction": "south"}, tick=1)
        energy_spent = initial_energy - agent.energy
        # base move cost (3) + swamp risk (1) = 4
        assert energy_spent == 4

    def test_simulation_runs_without_crash_with_novel_schema(self, swamp_schema):
        """End-to-end: engine creates world + runs 3 ticks with novel schema."""
        from simulation.engine import SimulationEngine
        engine = SimulationEngine(
            num_agents=1,
            world_seed=42,
            use_llm=False,
            max_ticks=3,
            world_schema=swamp_schema,
            run_digest=False,
        )
        # Should not raise
        engine.run()

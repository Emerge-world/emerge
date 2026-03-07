"""Tests for social perception: agents seeing other agents."""
import pytest
from simulation.agent import Agent
from simulation.world import World
from simulation.config import AGENT_VISION_RADIUS


class TestGetAgentsInRadius:
    def setup_method(self):
        Agent._id_counter = 0
        self.world = World(width=15, height=15, seed=42)

    def test_finds_agent_within_radius(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=7, y=5)  # Manhattan distance 2
        result = self.world.get_agents_in_radius(agent_a, [agent_a, agent_b], radius=3)
        assert len(result) == 1
        assert result[0][0].name == "Bruno"
        assert result[0][1] == 2

    def test_excludes_self(self):
        agent = Agent(name="Ada", x=5, y=5)
        result = self.world.get_agents_in_radius(agent, [agent], radius=3)
        assert result == []

    def test_excludes_dead_agents(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        agent_b.alive = False
        result = self.world.get_agents_in_radius(agent_a, [agent_a, agent_b], radius=3)
        assert result == []

    def test_excludes_agent_beyond_radius(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=9, y=5)  # distance 4, beyond radius 3
        result = self.world.get_agents_in_radius(agent_a, [agent_a, agent_b], radius=3)
        assert result == []

    def test_includes_agent_exactly_at_radius(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=8, y=5)  # distance exactly 3
        result = self.world.get_agents_in_radius(agent_a, [agent_a, agent_b], radius=3)
        assert len(result) == 1

    def test_returns_sorted_by_distance(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=7, y=5)  # distance 2
        agent_c = Agent(name="Clara", x=6, y=5)  # distance 1
        result = self.world.get_agents_in_radius(
            agent_a, [agent_a, agent_b, agent_c], radius=3
        )
        assert len(result) == 2
        assert result[0][0].name == "Clara"   # closer first
        assert result[0][1] == 1
        assert result[1][0].name == "Bruno"
        assert result[1][1] == 2

    def test_empty_agents_list(self):
        agent = Agent(name="Ada", x=5, y=5)
        result = self.world.get_agents_in_radius(agent, [], radius=3)
        assert result == []

    def test_night_vision_radius(self):
        """Radius 1 (night) should not see agents at distance 2."""
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=7, y=5)  # distance 2
        result = self.world.get_agents_in_radius(agent_a, [agent_a, agent_b], radius=1)
        assert result == []

    def test_uses_manhattan_distance(self):
        """Distance is |dx| + |dy|, not Euclidean."""
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=7, y=7)  # Manhattan=4, Euclidean≈2.8
        result = self.world.get_agents_in_radius(agent_a, [agent_a, agent_b], radius=3)
        assert result == []  # Manhattan distance 4 > radius 3


class TestNearbyAgentsPrompt:
    def setup_method(self):
        Agent._id_counter = 0

    def test_empty_list_returns_empty_string(self):
        agent = Agent(name="Ada", x=5, y=5)
        assert agent.nearby_agents_prompt([]) == ""

    def test_contains_nearby_agents_header(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=7, y=5)
        result = agent_a.nearby_agents_prompt([(agent_b, 2)])
        assert "NEARBY AGENTS:" in result

    def test_shows_agent_name_and_position(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=7, y=5)
        result = agent_a.nearby_agents_prompt([(agent_b, 2)])
        assert "Bruno" in result
        assert "(7,5)" in result
        assert "2 tiles" in result

    def test_singular_tile_at_distance_1(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        result = agent_a.nearby_agents_prompt([(agent_b, 1)])
        assert "1 tile away" in result

    def test_shows_hungry_status(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        agent_b.hunger = 75  # above 50 threshold
        result = agent_a.nearby_agents_prompt([(agent_b, 1)])
        assert "hungry" in result.lower()

    def test_not_hungry_when_below_threshold(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        agent_b.hunger = 30  # below 50 threshold
        result = agent_a.nearby_agents_prompt([(agent_b, 1)])
        assert "hungry" not in result.lower()

    def test_shows_tired_status(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        agent_b.energy = 20  # below 30 threshold
        result = agent_a.nearby_agents_prompt([(agent_b, 1)])
        assert "tired" in result.lower()

    def test_shows_hurt_status(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        agent_b.life = 40  # below 50 threshold
        result = agent_a.nearby_agents_prompt([(agent_b, 1)])
        assert "hurt" in result.lower()

    def test_shows_carrying_items_status(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        agent_b.inventory.add("fruit", 2)
        result = agent_a.nearby_agents_prompt([(agent_b, 1)])
        assert "carrying" in result.lower()

    def test_healthy_agent_shows_healthy(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        # Default stats: hunger=0, energy=100, life=100, empty inventory
        result = agent_a.nearby_agents_prompt([(agent_b, 1)])
        assert "healthy" in result.lower()

    def test_multiple_agents_in_prompt(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        agent_c = Agent(name="Clara", x=7, y=5)
        result = agent_a.nearby_agents_prompt([(agent_b, 1), (agent_c, 2)])
        assert "Bruno" in result
        assert "Clara" in result

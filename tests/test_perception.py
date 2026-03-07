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

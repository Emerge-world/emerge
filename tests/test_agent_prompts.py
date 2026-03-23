# tests/test_agent_prompts.py
import pytest
from simulation.agent import Agent
from simulation.config import REPRODUCE_MIN_TICKS_ALIVE
from simulation.personality import Personality
from simulation.planning_state import PlanningState, PlanningSubgoal

def _make_nearby(center_tile: str, *extra: dict) -> list[dict]:
    """Build a nearby_tiles list with the agent at (5,5) on center_tile."""
    tiles = [{"x": 5, "y": 5, "tile": center_tile, "distance": 0}]
    tiles.extend(extra)
    return tiles

class TestBuildAsciiGrid:
    def setup_method(self):
        Agent._id_counter = 0
        self.agent = Agent(name="Test", x=5, y=5)

    def test_agent_marker_renders_at(self):
        """The agent's position is rendered as @ in the grid."""
        nearby = _make_nearby("sand")
        grid = self.agent._build_ascii_grid(nearby)
        assert "@" in grid  # agent marker at center

    def test_out_of_bounds_renders_hash(self):
        """Cells outside nearby_tiles render as #."""
        # Agent at (0,0), only its own tile provided — all neighbors outside vision are #
        agent = Agent(name="Edge", x=0, y=0)
        nearby = [{"x": 0, "y": 0, "tile": "land", "distance": 0}]
        grid = agent._build_ascii_grid(nearby)
        assert "#" in grid

    def test_all_tile_chars(self):
        """Each tile type renders to the correct character in the grid."""
        expected = {
            "land":     ".",
            "sand":     "S",
            "water":    "W",
            "river":    "~",
            "forest":   "f",
            "mountain": "M",
            "cave":     "C",
            "tree":     "t",  # empty tree (no resource)
        }
        for tile_type, char in expected.items():
            nearby = [
                {"x": 5, "y": 5, "tile": "land", "distance": 0},  # agent tile
                {"x": 6, "y": 5, "tile": tile_type, "distance": 1},  # east tile
            ]
            grid = self.agent._build_ascii_grid(nearby)
            row_center = grid.split("\n")[3]  # middle row of 7x7 grid
            assert char in row_center, f"Expected '{char}' for tile '{tile_type}'"

    def test_fruit_tree_renders_F(self):
        nearby = [
            {"x": 5, "y": 5, "tile": "land", "distance": 0},
            {"x": 6, "y": 5, "tile": "tree", "distance": 1,
             "resource": {"type": "fruit", "quantity": 3}},
        ]
        grid = self.agent._build_ascii_grid(nearby)
        row_center = grid.split("\n")[3]
        assert "F" in row_center


class TestCurrentTileInfo:
    def setup_method(self):
        Agent._id_counter = 0
        self.agent = Agent(name="Test", x=5, y=5)

    def test_decision_prompt_contains_current_tile(self):
        """decision prompt shows [Tile: cave] when agent is on cave."""
        nearby = [
            {"x": 5, "y": 5, "tile": "cave", "distance": 0},
        ]
        prompt = self.agent._build_decision_prompt(nearby, tick=1)
        assert "[Tile: cave]" in prompt

    def test_decision_prompt_tile_changes_with_position(self):
        """different tile types appear correctly."""
        for tile_type in ["land", "sand", "forest", "mountain", "river"]:
            nearby = [{"x": 5, "y": 5, "tile": tile_type, "distance": 0}]
            prompt = self.agent._build_decision_prompt(nearby, tick=1)
            assert f"[Tile: {tile_type}]" in prompt


class TestResourceVisibilityPrompt:
    def setup_method(self):
        Agent._id_counter = 0
        self.agent = Agent(name="Test", x=5, y=5)

    def test_decision_prompt_splits_current_tile_and_nearby_resources(self):
        nearby = [
            {
                "x": 5,
                "y": 5,
                "tile": "tree",
                "distance": 0,
                "resource": {"type": "fruit", "quantity": 2},
            },
            {
                "x": 4,
                "y": 5,
                "tile": "tree",
                "distance": 1,
                "resource": {"type": "fruit", "quantity": 1},
            },
        ]

        prompt = self.agent._build_decision_prompt(nearby, tick=1)

        assert "RESOURCES ON YOUR TILE:" in prompt
        assert "- fruit HERE (qty: 2)" in prompt
        assert "NEARBY RESOURCES (MOVE FIRST):" in prompt
        assert "- fruit 1 tile WEST (qty: 1)" in prompt

    def test_observation_text_splits_current_tile_and_nearby_resources(self):
        nearby = [
            {
                "x": 5,
                "y": 5,
                "tile": "tree",
                "distance": 0,
                "resource": {"type": "fruit", "quantity": 2},
            },
            {
                "x": 6,
                "y": 5,
                "tile": "forest",
                "distance": 1,
                "resource": {"type": "mushroom", "quantity": 1},
            },
        ]

        observation = self.agent._build_observation_text(nearby, time_description="")

        assert "Resources on current tile: fruit" in observation
        assert "Nearby resources: mushroom" in observation


class TestPersonalityInAgent:
    def setup_method(self):
        Agent._id_counter = 0

    def test_agent_has_personality_by_default(self):
        agent = Agent(name="Ada", x=5, y=5)
        assert hasattr(agent, "personality")
        assert isinstance(agent.personality, Personality)

    def test_agent_personality_traits_in_range(self):
        agent = Agent(name="Ada", x=5, y=5)
        assert 0.0 <= agent.personality.courage <= 1.0
        assert 0.0 <= agent.personality.sociability <= 1.0

    def test_system_prompt_contains_personality(self):
        agent = Agent(name="Ada", x=5, y=5)
        agent.personality = Personality(courage=0.9, curiosity=0.1, patience=0.5, sociability=0.7)
        prompt = agent._build_system_prompt()
        assert "courage" in prompt.lower()
        assert "0.90" in prompt

    def test_system_prompt_personality_is_dynamic(self):
        """Different personalities produce different prompts."""
        agent = Agent(name="Ada", x=5, y=5)
        agent.personality = Personality(courage=0.1, curiosity=0.1, patience=0.1, sociability=0.1)
        prompt_low = agent._build_system_prompt()
        agent.personality = Personality(courage=0.9, curiosity=0.9, patience=0.9, sociability=0.9)
        prompt_high = agent._build_system_prompt()
        assert prompt_low != prompt_high

    def test_system_prompt_documents_drop_item(self):
        agent = Agent(name="Ada", x=5, y=5)

        prompt = agent._build_system_prompt()

        assert '{"action": "drop_item"' in prompt
        assert '"item": "<item_name>"' in prompt

    def test_system_prompt_requires_move_before_pickup_from_nearby_tile(self):
        agent = Agent(name="Ada", x=5, y=5)

        prompt = agent._build_system_prompt()

        assert "move first" in prompt.lower()

    def test_system_prompt_documents_reflect_item_uses(self):
        agent = Agent(name="Ada", x=5, y=5)
        prompt = agent._build_system_prompt()
        assert '{"action": "reflect_item_uses"' in prompt
        assert '"item": "<item_name>"' in prompt


class TestNearbyAgentsInDecisionPrompt:
    def setup_method(self):
        Agent._id_counter = 0

    def _make_nearby(self, center_tile="land"):
        return [{"x": 5, "y": 5, "tile": center_tile, "distance": 0}]

    def test_no_nearby_agents_omits_section(self):
        agent = Agent(name="Ada", x=5, y=5)
        nearby = self._make_nearby()
        prompt = agent._build_decision_prompt(nearby, tick=1, nearby_agents=[])
        assert "NEARBY AGENTS" not in prompt

    def test_nearby_agents_appears_in_prompt(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        nearby = self._make_nearby()
        prompt = agent_a._build_decision_prompt(
            nearby, tick=1, nearby_agents=[(agent_b, 1)]
        )
        assert "NEARBY AGENTS:" in prompt
        assert "Bruno" in prompt

    def test_decide_action_accepts_nearby_agents(self):
        """decide_action should not crash when nearby_agents is provided."""
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        nearby = self._make_nearby()
        # No LLM — uses fallback; should not raise
        result = agent_a.decide_action(nearby, tick=1, nearby_agents=[(agent_b, 1)])
        assert "action" in result


class TestReproductionPrompt:
    def setup_method(self):
        Agent._id_counter = 0

    def test_reproduce_hint_hidden_before_unlock(self):
        agent = Agent(name="Ada", x=5, y=5)
        nearby = [{"x": 5, "y": 5, "tile": "land", "distance": 0}]
        prompt = agent._build_decision_prompt(nearby, tick=REPRODUCE_MIN_TICKS_ALIVE - 1)
        assert 'To reproduce: {"action": "reproduce"' not in prompt

    def test_reproduce_hint_shown_after_unlock(self):
        agent = Agent(name="Ada", x=5, y=5)
        nearby = [{"x": 5, "y": 5, "tile": "land", "distance": 0}]
        prompt = agent._build_decision_prompt(nearby, tick=REPRODUCE_MIN_TICKS_ALIVE)
        assert 'To reproduce: {"action": "reproduce"' in prompt


class TestPlanningPrompt:
    def setup_method(self):
        Agent._id_counter = 0

    def test_executor_prompt_includes_active_subgoal(self):
        agent = Agent(name="Ada", x=5, y=5)
        agent.planning_state = PlanningState(
            goal="stabilize food",
            goal_type="survival",
            subgoals=[PlanningSubgoal(description="move toward fruit", kind="move")],
            active_subgoal_index=0,
            status="active",
            created_tick=1,
            last_plan_tick=1,
            last_progress_tick=1,
            confidence=0.8,
            horizon="short",
            success_signals=["eat fruit"],
            abort_conditions=[],
            blockers=[],
            rationale_summary="fruit visible",
        )

        prompt = agent._build_decision_prompt([{"x": 5, "y": 5, "tile": "land", "distance": 0}], tick=2)

        assert "ACTIVE SUBGOAL" in prompt
        assert "move toward fruit" in prompt

"""Tests for innovation result enrichment in Oracle._resolve_innovate."""

import pytest
from simulation.agent import Agent
from simulation.oracle import Oracle
from simulation.world import World


def _make_oracle(seed: int = 42) -> Oracle:
    world = World(width=20, height=20, seed=seed)
    return Oracle(world=world, llm=None)


def _make_agent(oracle: Oracle, name: str = "Ada") -> Agent:
    """Place agent on the first land tile found."""
    from simulation.config import TILE_LAND
    for y in range(oracle.world.height):
        for x in range(oracle.world.width):
            if oracle.world.get_tile(x, y) == TILE_LAND:
                return Agent(name=name, x=x, y=y, llm=None)
    raise RuntimeError("No land tile found in world")


class TestInnovateResultFields:
    def test_success_has_name(self):
        oracle = _make_oracle()
        agent = _make_agent(oracle)
        result = oracle.resolve_action(agent, {
            "action": "innovate",
            "new_action_name": "test_action",
            "description": "a test",
        }, tick=1)
        assert result["success"] is True
        assert result["name"] == "test_action"

    def test_success_has_reason_code(self):
        oracle = _make_oracle()
        agent = _make_agent(oracle)
        result = oracle.resolve_action(agent, {
            "action": "innovate",
            "new_action_name": "test_action",
            "description": "a test",
        }, tick=1)
        assert result["reason_code"] == "INNOVATION_APPROVED"

    def test_success_has_category(self):
        oracle = _make_oracle()
        agent = _make_agent(oracle)
        result = oracle.resolve_action(agent, {
            "action": "innovate",
            "new_action_name": "test_action",
            "description": "a test",
        }, tick=1)
        assert "category" in result
        assert result["category"] is not None

    def test_failure_duplicate_has_name(self):
        oracle = _make_oracle()
        agent = _make_agent(oracle)
        # First innovation succeeds
        oracle.resolve_action(agent, {
            "action": "innovate",
            "new_action_name": "test_action",
            "description": "a test",
        }, tick=1)
        # Second attempt is duplicate
        result = oracle.resolve_action(agent, {
            "action": "innovate",
            "new_action_name": "test_action",
            "description": "a test",
        }, tick=2)
        assert result["success"] is False
        assert result["name"] == "test_action"
        assert result["reason_code"] == "INNOVATION_DUPLICATE"

    def test_failure_no_name_has_reason_code(self):
        oracle = _make_oracle()
        agent = _make_agent(oracle)
        result = oracle.resolve_action(agent, {
            "action": "innovate",
            "new_action_name": "",
            "description": "",
        }, tick=1)
        assert result["success"] is False
        assert result["reason_code"] == "INNOVATION_NO_NAME"

    def test_failure_wrong_tile_has_reason_code(self):
        oracle = _make_oracle()
        agent = _make_agent(oracle)  # on land tile
        result = oracle.resolve_action(agent, {
            "action": "innovate",
            "new_action_name": "cave_action",
            "description": "needs cave",
            "requires": {"tile": "cave"},
        }, tick=1)
        assert result["success"] is False
        assert result["reason_code"] == "INNOVATION_WRONG_TILE"
        assert result["name"] == "cave_action"

    def test_failure_missing_items_has_reason_code(self):
        oracle = _make_oracle()
        agent = _make_agent(oracle)
        result = oracle.resolve_action(agent, {
            "action": "innovate",
            "new_action_name": "craft_something",
            "description": "needs stone",
            "requires": {"items": {"stone": 3}},
        }, tick=1)
        assert result["success"] is False
        assert result["reason_code"] == "INNOVATION_MISSING_ITEMS"

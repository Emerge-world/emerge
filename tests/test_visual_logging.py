"""
Tests for visual logging improvements — crafting events, inventory diffs, world state.

Covers:
- _apply_crafting_recipe returns {"consumed": {...}, "produced": {...}}
- _resolve_custom_action embeds crafting_event in result dict
- Fail-fast path (missing items) does NOT include crafting_event
- sim_logger.log_oracle_resolution writes inventory diff block
- sim_logger.log_oracle_resolution writes crafting block
- sim_logger.log_oracle_resolution omits crafting block when None
- sim_logger.log_tick_world_state writes harvested resource diff
- sim_logger.log_tick_world_state writes regenerated-at-dawn line
- sim_logger.log_tick_world_state writes "none" when no resources changed
"""

import os
from unittest.mock import MagicMock

import pytest

from simulation.agent import Agent
from simulation.oracle import Oracle
from simulation.world import World
from simulation.sim_logger import SimLogger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_world(seed: int = 42, width: int = 10, height: int = 10) -> World:
    return World(width=width, height=height, seed=seed)


def _make_agent(world: World, name: str = "Ada") -> Agent:
    agent = Agent(name=name, x=0, y=0)
    for y in range(world.height):
        for x in range(world.width):
            if world.get_tile(x, y) == "land":
                agent.x, agent.y = x, y
                return agent
    return agent


def _make_oracle(world: World, llm=None) -> Oracle:
    return Oracle(world=world, llm=llm)


@pytest.fixture
def logger(tmp_path, monkeypatch):
    """SimLogger that writes to tmp_path instead of the real logs/ dir."""
    monkeypatch.setattr("simulation.sim_logger.LOG_DIR", str(tmp_path))
    return SimLogger()


def _read_tick(logger: SimLogger, tick: int) -> str:
    path = os.path.join(logger.run_dir, f"tick_{tick:04d}.md")
    with open(path, encoding="utf-8") as f:
        return f.read()


def _mock_agent(inv_items: dict | None = None) -> MagicMock:
    """Create a minimal agent mock for SimLogger tests."""
    agent = MagicMock()
    agent.name = "Ada"
    agent.life = 80
    agent.hunger = 40
    agent.energy = 70
    agent.x = 3
    agent.y = 4
    agent.inventory = MagicMock()
    agent.inventory.items = inv_items or {}
    return agent


# ---------------------------------------------------------------------------
# Oracle: _apply_crafting_recipe return value
# ---------------------------------------------------------------------------

class TestApplyCraftingRecipeReturn:
    def test_returns_consumed_and_produced(self):
        """_apply_crafting_recipe should return what was consumed and produced."""
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        agent.inventory.add("stone", 3)
        result = oracle._apply_crafting_recipe(
            agent,
            action_type="make_knife",
            required_items={"stone": 2},
            produces={"knife": 1},
            tick=1,
        )

        assert result == {"consumed": {"stone": 2}, "produced": {"knife": 1}}
        assert agent.inventory.has("stone", 1)
        assert agent.inventory.has("knife", 1)

    def test_returns_empty_dicts_when_no_recipe(self):
        """With no required items and no produces, both dicts should be empty."""
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        result = oracle._apply_crafting_recipe(
            agent,
            action_type="wave",
            required_items={},
            produces={},
            tick=1,
        )

        assert result == {"consumed": {}, "produced": {}}

    def test_consumed_empty_when_no_required_items(self):
        """No required items → consumed dict is empty."""
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        result = oracle._apply_crafting_recipe(
            agent,
            action_type="mark_territory",
            required_items={},
            produces={"flag": 1},
            tick=1,
        )

        assert result["consumed"] == {}
        assert result["produced"] == {"flag": 1}

    def test_produced_empty_when_no_produces(self):
        """No produces → produced dict is empty."""
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        agent.inventory.add("wood", 2)
        result = oracle._apply_crafting_recipe(
            agent,
            action_type="burn_wood",
            required_items={"wood": 2},
            produces={},
            tick=1,
        )

        assert result["consumed"] == {"wood": 2}
        assert result["produced"] == {}


# ---------------------------------------------------------------------------
# Oracle: _resolve_custom_action embeds crafting_event
# ---------------------------------------------------------------------------

class TestResolveCustomActionCraftingEvent:
    def _setup_crafting_innovation(self, oracle: Oracle, action_name: str,
                                   required: dict, produces: dict):
        """Register a crafting innovation in oracle precedents (no LLM needed)."""
        oracle.precedents[f"innovation:{action_name}"] = {
            "description": f"crafts {action_name}",
            "category": "crafting",
            "requires": {"items": required},
            "produces": produces,
        }

    def test_crafting_event_in_result_on_success(self):
        """resolve_action embeds crafting_event when custom action succeeds."""
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)  # no LLM → no-LLM fallback path

        agent.actions.append("make_knife")
        self._setup_crafting_innovation(oracle, "make_knife", {"stone": 2}, {"knife": 1})
        agent.inventory.add("stone", 3)

        result = oracle.resolve_action(agent, {"action": "make_knife"}, tick=1)

        assert result["success"] is True
        crafting = result.get("crafting_event")
        assert crafting is not None
        assert crafting["consumed"] == {"stone": 2}
        assert crafting["produced"] == {"knife": 1}

    def test_no_crafting_event_on_fail_fast(self):
        """resolve_action does NOT include crafting_event when items are missing."""
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        agent.actions.append("make_knife")
        self._setup_crafting_innovation(oracle, "make_knife", {"stone": 2}, {"knife": 1})
        # Agent has no stone

        result = oracle.resolve_action(agent, {"action": "make_knife"}, tick=1)

        assert result["success"] is False
        assert "crafting_event" not in result

    def test_crafting_event_with_no_recipe_items(self):
        """Custom action with no required/produces still provides crafting_event."""
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        agent.actions.append("stomp")
        oracle.precedents["innovation:stomp"] = {
            "description": "stomp the ground",
            "category": "social",
        }

        result = oracle.resolve_action(agent, {"action": "stomp"}, tick=1)

        assert result["success"] is True
        crafting = result.get("crafting_event")
        assert crafting is not None
        assert crafting["consumed"] == {}
        assert crafting["produced"] == {}


# ---------------------------------------------------------------------------
# SimLogger: log_oracle_resolution inventory diff
# ---------------------------------------------------------------------------

class TestSimLoggerInventoryDiff:
    def _write_resolution(self, logger: SimLogger, agent, inventory_before: dict | None,
                          crafting_event=None, tick: int = 1):
        """Write an oracle resolution with given inventory state."""
        action = {"action": "make_knife", "reason": "I have stones"}
        result = {"success": True, "message": "Ada made a knife.", "effects": {"energy": -5}}
        logger.log_oracle_resolution(
            tick, agent, action, result,
            inventory_before=inventory_before,
            crafting_event=crafting_event,
        )

    def test_inventory_before_and_after_appear_in_markdown(self, logger):
        """log_oracle_resolution writes inventory before/after when data is provided."""
        agent = _mock_agent(inv_items={"stone": 1, "knife": 1})

        self._write_resolution(logger, agent, inventory_before={"stone": 3})

        content = _read_tick(logger, tick=1)
        assert "**Inventory before:**" in content
        assert "**Inventory after:**" in content

    def test_inventory_diff_shows_net_change(self, logger):
        """Inventory section shows what changed (e.g., -2 stone, +1 knife)."""
        agent = _mock_agent(inv_items={"stone": 1, "knife": 1})

        self._write_resolution(logger, agent, inventory_before={"stone": 3})

        content = _read_tick(logger, tick=1)
        # Should show loss of 2 stone and gain of 1 knife
        assert "-2 stone" in content
        assert "+1 knife" in content

    def test_no_inventory_section_when_none(self, logger):
        """When inventory_before is None, no inventory block is written."""
        agent = _mock_agent()

        self._write_resolution(logger, agent, inventory_before=None)

        content = _read_tick(logger, tick=1)
        assert "**Inventory before:**" not in content

    def test_inventory_shows_empty_before(self, logger):
        """Empty inventory_before shows 'empty'."""
        agent = _mock_agent(inv_items={"knife": 1})

        self._write_resolution(logger, agent, inventory_before={})

        content = _read_tick(logger, tick=1)
        assert "empty" in content


# ---------------------------------------------------------------------------
# SimLogger: log_oracle_resolution crafting block
# ---------------------------------------------------------------------------

class TestSimLoggerCraftingBlock:
    def _write_with_crafting(self, logger: SimLogger, crafting_event: dict | None,
                              tick: int = 1):
        agent = _mock_agent(inv_items={"knife": 1})
        action = {"action": "make_knife", "reason": "test"}
        result = {"success": True, "message": "Done.", "effects": {}}
        logger.log_oracle_resolution(
            tick, agent, action, result,
            inventory_before={"stone": 2},
            crafting_event=crafting_event,
        )

    def test_crafting_block_appears_when_event_present(self, logger):
        """Crafting block is written when crafting_event has consumed/produced items."""
        self._write_with_crafting(logger, {"consumed": {"stone": 2}, "produced": {"knife": 1}})

        content = _read_tick(logger, tick=1)
        assert "**Crafting:**" in content
        assert "2x stone" in content
        assert "1x knife" in content

    def test_crafting_block_absent_when_none(self, logger):
        """No crafting block when crafting_event is None."""
        self._write_with_crafting(logger, crafting_event=None)

        content = _read_tick(logger, tick=1)
        assert "**Crafting:**" not in content

    def test_crafting_block_absent_when_both_empty(self, logger):
        """No crafting block when both consumed and produced are empty."""
        self._write_with_crafting(logger, {"consumed": {}, "produced": {}})

        content = _read_tick(logger, tick=1)
        assert "**Crafting:**" not in content

    def test_crafting_block_shows_consumed_only(self, logger):
        """Crafting block works for consume-only actions."""
        self._write_with_crafting(logger, {"consumed": {"wood": 3}, "produced": {}})

        content = _read_tick(logger, tick=1)
        assert "**Crafting:**" in content
        assert "3x wood" in content


# ---------------------------------------------------------------------------
# SimLogger: log_tick_world_state
# ---------------------------------------------------------------------------

class TestSimLoggerWorldState:
    def _build_resources(self, tiles: list[tuple]) -> dict:
        """Build a resource snapshot dict from list of (x, y, type, qty) tuples."""
        return {(x, y): {"type": t, "quantity": q} for x, y, t, q in tiles}

    def test_world_state_appears_in_tick_file(self, logger):
        """log_tick_world_state writes a world state section to tick file."""
        before = self._build_resources([(5, 3, "fruit", 5)])
        after = self._build_resources([(5, 3, "fruit", 4)])

        logger.log_tick_world_state(
            tick=1, period="day", hour=9, day=1,
            resources_before=before, resources_after=after,
            regenerated=[],
        )

        content = _read_tick(logger, tick=1)
        assert "World State" in content

    def test_harvested_resource_shows_tile_and_delta(self, logger):
        """A tile that decreased in quantity appears with coordinates and delta."""
        before = self._build_resources([(5, 3, "fruit", 5)])
        after = self._build_resources([(5, 3, "fruit", 3)])

        logger.log_tick_world_state(
            tick=1, period="day", hour=9, day=1,
            resources_before=before, resources_after=after,
            regenerated=[],
        )

        content = _read_tick(logger, tick=1)
        assert "(5,3)" in content
        assert "fruit" in content
        assert "-2" in content

    def test_no_changes_shows_none(self, logger):
        """When no resources changed, 'none' is written for consumed."""
        snapshot = self._build_resources([(5, 3, "fruit", 5)])

        logger.log_tick_world_state(
            tick=1, period="night", hour=21, day=1,
            resources_before=snapshot, resources_after=snapshot,
            regenerated=[],
        )

        content = _read_tick(logger, tick=1)
        assert "none" in content

    def test_regenerated_at_dawn_appears(self, logger):
        """Regenerated positions appear when regenerated list is non-empty."""
        snapshot = self._build_resources([(5, 3, "fruit", 0)])
        after = self._build_resources([(5, 3, "fruit", 5)])

        logger.log_tick_world_state(
            tick=1, period="day", hour=6, day=2,
            resources_before=snapshot, resources_after=after,
            regenerated=[(5, 3), (12, 7)],
        )

        content = _read_tick(logger, tick=1)
        assert "Regenerated" in content
        assert "(5,3)" in content
        assert "(12,7)" in content

    def test_no_regenerated_section_when_empty(self, logger):
        """Regenerated section is absent when no tiles regenerated."""
        snapshot = self._build_resources([(5, 3, "fruit", 5)])

        logger.log_tick_world_state(
            tick=1, period="day", hour=9, day=1,
            resources_before=snapshot, resources_after=snapshot,
            regenerated=[],
        )

        content = _read_tick(logger, tick=1)
        assert "Regenerated" not in content

    def test_day_night_period_in_world_state(self, logger):
        """The time period (day/night/sunset) and day number appear in world state."""
        snapshot = self._build_resources([])

        logger.log_tick_world_state(
            tick=1, period="night", hour=21, day=3,
            resources_before=snapshot, resources_after=snapshot,
            regenerated=[],
        )

        content = _read_tick(logger, tick=1)
        assert "Night" in content or "night" in content.lower()
        assert "Day 3" in content

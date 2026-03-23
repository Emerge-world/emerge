"""
Unit tests for the innovation system in Oracle.

Covers:
- Prerequisites (tile, min_energy) rejected without LLM call
- Already-known action rejected without LLM call
- LLM approves → action added to agent.actions, precedent saved with category
- LLM rejects → action not added
- LLM fallback (no LLM) → innovation approved in no-llm mode
- Effect bounds clamping via _clamp_innovation_effects
- Out-of-bounds effects from LLM are clamped when resolving custom actions
"""

from unittest.mock import MagicMock

import pytest

from simulation.agent import Agent
from simulation.oracle import Oracle
from simulation.world import World
from simulation.config import (
    INNOVATION_EFFECT_BOUNDS,
    ENERGY_COST_INNOVATE,
    BASE_ACTIONS,
    ORACLE_RESPONSE_MAX_TOKENS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_world(seed: int = 42) -> World:
    return World(width=5, height=5, seed=seed)


def _make_agent(world: World, name: str = "Ada") -> Agent:
    """Place agent on a land tile (guaranteed by seed=42 at 0,0 or scan)."""
    agent = Agent(name=name, x=0, y=0)
    # Find the first land tile and put the agent there
    for y in range(world.height):
        for x in range(world.width):
            if world.get_tile(x, y) == "land":
                agent.x, agent.y = x, y
                return agent
    return agent  # fallback: stay at (0,0)


def _make_oracle(world: World, llm=None) -> Oracle:
    return Oracle(world=world, llm=llm)


def _typed(d: dict):
    """Wrap a dict as a typed-model-like MagicMock (simulate generate_structured result)."""
    m = MagicMock()
    m.model_dump.return_value = d
    return m


def _mock_llm(response: dict):
    """Return a MagicMock LLM whose generate_structured always returns response."""
    llm = MagicMock()
    llm.generate_structured.return_value = _typed(response)
    llm.last_call = {}
    return llm


# ---------------------------------------------------------------------------
# No-LLM fallback
# ---------------------------------------------------------------------------

class TestInnovationNoLLM:
    def test_innovation_approved_without_llm(self):
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)  # no LLM

        result = oracle.resolve_action(
            agent,
            {"action": "innovate", "new_action_name": "fish", "description": "catch fish"},
            tick=1,
        )
        assert result["success"] is True
        assert "fish" in agent.actions

    def test_innovation_costs_energy_without_llm(self):
        world = _make_world()
        agent = _make_agent(world)
        energy_before = agent.energy
        oracle = _make_oracle(world)

        oracle.resolve_action(
            agent,
            {"action": "innovate", "new_action_name": "craft_spear", "description": "make a spear"},
            tick=1,
        )
        assert agent.energy == energy_before - ENERGY_COST_INNOVATE

    def test_custom_action_fallback_without_llm(self):
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        # First innovate the action
        oracle.resolve_action(
            agent,
            {"action": "innovate", "new_action_name": "gather_wood", "description": "collect wood"},
            tick=1,
        )
        # Then use it
        result = oracle.resolve_action(agent, {"action": "gather_wood"}, tick=2)
        assert result["success"] is True
        assert result["effects"].get("energy") == -5  # generic fallback cost

    def test_innovation_validation_uses_oracle_token_budget(self):
        world = _make_world()
        agent = _make_agent(world)
        llm = _mock_llm({"approved": True, "reason": "ok", "category": "SURVIVAL"})
        oracle = _make_oracle(world, llm=llm)

        result = oracle.resolve_action(
            agent,
            {"action": "innovate", "new_action_name": "fish", "description": "catch fish"},
            tick=1,
        )

        assert result["success"] is True
        assert llm.generate_structured.call_args[1]["max_tokens"] == ORACLE_RESPONSE_MAX_TOKENS


# ---------------------------------------------------------------------------
# Already-known action
# ---------------------------------------------------------------------------

class TestInnovationAlreadyKnown:
    def test_base_action_rejected(self):
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        for base in BASE_ACTIONS:
            result = oracle.resolve_action(
                agent,
                {"action": "innovate", "new_action_name": base, "description": "..."},
                tick=1,
            )
            assert result["success"] is False, f"Should reject re-innovating base action '{base}'"

    def test_previously_innovated_action_rejected(self):
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        oracle.resolve_action(
            agent,
            {"action": "innovate", "new_action_name": "fish", "description": "catch fish"},
            tick=1,
        )
        # Try to innovate the same action again
        result = oracle.resolve_action(
            agent,
            {"action": "innovate", "new_action_name": "fish", "description": "catch fish again"},
            tick=2,
        )
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Prerequisites (requires field)
# ---------------------------------------------------------------------------

class TestInnovationRequires:
    def test_wrong_tile_rejected(self):
        world = _make_world()
        agent = _make_agent(world)
        # Agent is on land; innovation requires water
        assert world.get_tile(agent.x, agent.y) != "water", "Test setup: agent must not be on water"
        oracle = _make_oracle(world)

        result = oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "fish",
                "description": "catch fish in water",
                "requires": {"tile": "water"},
            },
            tick=1,
        )
        assert result["success"] is False
        assert "fish" not in agent.actions

    def test_correct_tile_passes(self):
        world = _make_world(seed=0)
        # Find a water tile and place agent there
        agent = Agent(name="Ada", x=0, y=0)
        placed = False
        for y in range(world.height):
            for x in range(world.width):
                if world.get_tile(x, y) == "water":
                    agent.x, agent.y = x, y
                    placed = True
                    break
            if placed:
                break

        if not placed:
            pytest.skip("No water tile found in this seed")

        oracle = _make_oracle(world)

        result = oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "fish",
                "description": "catch fish in water",
                "requires": {"tile": "water"},
            },
            tick=1,
        )
        assert result["success"] is True
        assert "fish" in agent.actions

    def test_insufficient_energy_rejected(self):
        world = _make_world()
        agent = _make_agent(world)
        agent.energy = 15  # below the requirement
        oracle = _make_oracle(world)

        result = oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "craft_shelter",
                "description": "build a basic shelter",
                "requires": {"min_energy": 30},
            },
            tick=1,
        )
        assert result["success"] is False
        assert "craft_shelter" not in agent.actions

    def test_sufficient_energy_passes(self):
        world = _make_world()
        agent = _make_agent(world)
        agent.energy = 50  # above the requirement
        oracle = _make_oracle(world)

        result = oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "craft_shelter",
                "description": "build a basic shelter",
                "requires": {"min_energy": 30},
            },
            tick=1,
        )
        assert result["success"] is True
        assert "craft_shelter" in agent.actions

    def test_missing_requires_field_is_ignored(self):
        """requires=None or absent must not cause errors."""
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        for req in [None, {}, "not_a_dict"]:
            agent2 = _make_agent(world, name="Bruno")
            result = oracle.resolve_action(
                agent2,
                {
                    "action": "innovate",
                    "new_action_name": f"gather_wood_{id(req)}",
                    "description": "collect wood",
                    "requires": req,
                },
                tick=1,
            )
            assert result["success"] is True


# ---------------------------------------------------------------------------
# LLM validation (approved / rejected)
# ---------------------------------------------------------------------------

class TestInnovationLLMValidation:
    def test_llm_approves_innovation(self):
        world = _make_world()
        agent = _make_agent(world)
        llm = _mock_llm({"approved": True, "reason": "Makes sense.", "category": "CRAFTING"})
        oracle = _make_oracle(world, llm=llm)

        result = oracle.resolve_action(
            agent,
            {"action": "innovate", "new_action_name": "craft_spear", "description": "sharpen a stick"},
            tick=1,
        )
        assert result["success"] is True
        assert "craft_spear" in agent.actions
        assert llm.generate_structured.called

    def test_llm_stores_category_in_precedent(self):
        world = _make_world()
        agent = _make_agent(world)
        llm = _mock_llm({"approved": True, "reason": "Good idea.", "category": "CRAFTING"})
        oracle = _make_oracle(world, llm=llm)

        oracle.resolve_action(
            agent,
            {"action": "innovate", "new_action_name": "craft_spear", "description": "sharpen a stick"},
            tick=1,
        )
        precedent = oracle.precedents.get("innovation:craft_spear", {})
        assert precedent.get("category") == "CRAFTING"

    def test_llm_rejects_innovation(self):
        world = _make_world()
        agent = _make_agent(world)
        llm = _mock_llm({"approved": False, "reason": "Too magical.", "category": "SURVIVAL"})
        oracle = _make_oracle(world, llm=llm)

        result = oracle.resolve_action(
            agent,
            {"action": "innovate", "new_action_name": "teleport", "description": "move instantly"},
            tick=1,
        )
        assert result["success"] is False
        assert "teleport" not in agent.actions

    def test_requires_checked_before_llm(self):
        """If prerequisites fail, the LLM must NOT be called."""
        world = _make_world()
        agent = _make_agent(world)
        agent.energy = 5  # too low
        llm = _mock_llm({"approved": True, "reason": "Sure.", "category": "SURVIVAL"})
        oracle = _make_oracle(world, llm=llm)

        oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "build_wall",
                "description": "heavy construction",
                "requires": {"min_energy": 50},
            },
            tick=1,
        )
        llm.generate_structured.assert_not_called()

    def test_llm_fallback_on_missing_approved_key(self):
        """If LLM returns unexpected JSON, default to approved."""
        world = _make_world()
        agent = _make_agent(world)
        llm = _mock_llm({"error": "confused"})  # missing "approved" key
        oracle = _make_oracle(world, llm=llm)

        result = oracle.resolve_action(
            agent,
            {"action": "innovate", "new_action_name": "craft_net", "description": "weave a net"},
            tick=1,
        )
        assert result["success"] is True
        assert "craft_net" in agent.actions


# ---------------------------------------------------------------------------
# Effect bounds clamping
# ---------------------------------------------------------------------------

class TestEffectBoundsClamping:
    def test_clamp_helper_within_bounds(self):
        oracle = _make_oracle(_make_world())
        effects = {"hunger": -10, "energy": -5, "life": 0}
        clamped = oracle._clamp_innovation_effects(effects)
        assert clamped == effects  # no change needed

    def test_clamp_helper_overflow(self):
        oracle = _make_oracle(_make_world())
        effects = {"hunger": -999, "energy": 999, "life": 999}
        clamped = oracle._clamp_innovation_effects(effects)
        h_lo, h_hi = INNOVATION_EFFECT_BOUNDS["hunger"]
        e_lo, e_hi = INNOVATION_EFFECT_BOUNDS["energy"]
        l_lo, l_hi = INNOVATION_EFFECT_BOUNDS["life"]
        assert clamped["hunger"] == h_lo
        assert clamped["energy"] == e_hi
        assert clamped["life"] == l_hi

    def test_clamp_helper_underflow(self):
        oracle = _make_oracle(_make_world())
        effects = {"hunger": 999, "energy": -999, "life": -999}
        clamped = oracle._clamp_innovation_effects(effects)
        h_lo, h_hi = INNOVATION_EFFECT_BOUNDS["hunger"]
        e_lo, e_hi = INNOVATION_EFFECT_BOUNDS["energy"]
        l_lo, l_hi = INNOVATION_EFFECT_BOUNDS["life"]
        assert clamped["hunger"] == h_hi
        assert clamped["energy"] == e_lo
        assert clamped["life"] == l_lo

    def test_clamp_helper_ignores_unknown_keys(self):
        oracle = _make_oracle(_make_world())
        effects = {"hunger": -5, "gold": 1000}
        clamped = oracle._clamp_innovation_effects(effects)
        assert clamped["gold"] == 1000  # untouched

    def test_custom_action_effects_are_clamped(self):
        """When the LLM returns extreme effects for a custom action, they should be clamped."""
        world = _make_world()
        agent = _make_agent(world)

        # LLM: first call approves innovation, second call judges the action effect
        llm = MagicMock()
        llm.last_call = None
        llm.generate_structured.side_effect = [
            _typed({"approved": True, "reason": "OK", "category": "SURVIVAL"}),
            _typed({"success": True, "message": "worked", "effects": {"energy": -500, "hunger": -500, "life": 0}}),
        ]
        oracle = _make_oracle(world, llm=llm)

        # Innovate first
        oracle.resolve_action(
            agent,
            {"action": "innovate", "new_action_name": "super_forage", "description": "forage intensely"},
            tick=1,
        )
        energy_before = agent.energy

        # Use the custom action
        oracle.resolve_action(agent, {"action": "super_forage"}, tick=2)

        # energy change must be within the clamped bound
        e_lo, _ = INNOVATION_EFFECT_BOUNDS["energy"]
        energy_spent = energy_before - agent.energy
        assert energy_spent <= -e_lo  # energy_spent should not exceed abs(lower bound)


# ---------------------------------------------------------------------------
# Crafting (DEC-018)
# ---------------------------------------------------------------------------

class TestCraftingPrecedentStorage:
    """_resolve_innovate must persist requires + produces in the innovation precedent."""

    def _innovate_make_knife(self, oracle, agent, tick=1):
        """Helper: agent innovates make_knife with requires+produces."""
        agent.inventory.add("stone", 3)  # agent must have the items to propose
        return oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "make_knife",
                "description": "carve two stones into a sharp blade",
                "requires": {"items": {"stone": 2}},
                "produces": {"knife": 1},
            },
            tick=tick,
        )

    def test_produces_stored_in_precedent(self):
        """After approval, precedent contains the produces dict."""
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        result = self._innovate_make_knife(oracle, agent)

        assert result["success"] is True
        precedent = oracle.precedents.get("innovation:make_knife", {})
        assert precedent.get("produces") == {"knife": 1}

    def test_requires_stored_in_precedent(self):
        """After approval, precedent contains the requires dict."""
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        self._innovate_make_knife(oracle, agent)

        precedent = oracle.precedents.get("innovation:make_knife", {})
        assert precedent.get("requires") == {"items": {"stone": 2}}

    def test_innovation_without_produces_stores_no_produces_key(self):
        """A normal (non-crafting) innovation must not get a produces key."""
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        oracle.resolve_action(
            agent,
            {"action": "innovate", "new_action_name": "fish", "description": "catch fish"},
            tick=1,
        )
        precedent = oracle.precedents.get("innovation:fish", {})
        assert "produces" not in precedent

    def test_produces_none_not_stored(self):
        """produces=None must not write a produces key."""
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "forage",
                "description": "gather mushrooms",
                "produces": None,
            },
            tick=1,
        )
        precedent = oracle.precedents.get("innovation:forage", {})
        assert "produces" not in precedent


class TestCraftingExecution:
    """_resolve_custom_action must check, consume, and produce items for crafting actions."""

    def _setup_crafting(self):
        """
        Return (oracle, agent) with 'make_knife' already innovated.
        make_knife: requires {items: {stone: 2}}, produces {knife: 1}.
        LLM mock: first call approves innovation, second judges the action execution.
        """
        world = _make_world()
        agent = _make_agent(world)
        agent.inventory.add("stone", 5)

        llm = MagicMock()
        llm.last_call = None
        llm.generate_structured.side_effect = [
            _typed({"approved": True, "reason": "Makes sense.", "category": "CRAFTING"}),
            _typed({"success": True, "message": "You shaped the stones into a blade.", "effects": {"energy": -8, "hunger": 0, "life": 0}}),
        ]

        oracle = _make_oracle(world, llm=llm)
        oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "make_knife",
                "description": "carve two stones into a blade",
                "requires": {"items": {"stone": 2}},
                "produces": {"knife": 1},
            },
            tick=1,
        )
        return oracle, agent

    def test_crafting_fails_without_required_items(self):
        """Crafting action fails when agent lacks required materials."""
        world = _make_world()
        agent = _make_agent(world)
        agent.inventory.add("stone", 5)

        llm = MagicMock()
        llm.last_call = None
        llm.generate_structured.return_value = _typed({"approved": True, "reason": "ok", "category": "CRAFTING"})
        oracle = _make_oracle(world, llm=llm)

        oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "make_knife",
                "description": "carve stones",
                "requires": {"items": {"stone": 2}},
                "produces": {"knife": 1},
            },
            tick=1,
        )
        agent.inventory.items.clear()

        result = oracle.resolve_action(agent, {"action": "make_knife"}, tick=2)
        assert result["success"] is False

    def test_crafting_failure_message_does_not_reveal_item_names(self):
        """The failure message must be generic — no specific item name like 'stone' revealed."""
        world = _make_world()
        agent = _make_agent(world)
        agent.inventory.add("stone", 5)

        llm = MagicMock()
        llm.last_call = None
        llm.generate_structured.return_value = _typed({"approved": True, "reason": "ok", "category": "CRAFTING"})
        oracle = _make_oracle(world, llm=llm)

        oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "make_knife",
                "description": "carve stones",
                "requires": {"items": {"stone": 2}},
                "produces": {"knife": 1},
            },
            tick=1,
        )
        agent.inventory.items.clear()

        result = oracle.resolve_action(agent, {"action": "make_knife"}, tick=2)
        assert "stone" not in result["message"].lower()

    def test_crafting_item_check_before_llm_on_execution(self):
        """When items are missing at execution time, no extra LLM call is made."""
        world = _make_world()
        agent = _make_agent(world)
        agent.inventory.add("stone", 5)

        llm = MagicMock()
        llm.last_call = None
        llm.generate_structured.return_value = _typed({"approved": True, "reason": "ok", "category": "CRAFTING"})
        oracle = _make_oracle(world, llm=llm)

        oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "make_knife",
                "description": "carve stones",
                "requires": {"items": {"stone": 2}},
                "produces": {"knife": 1},
            },
            tick=1,
        )
        calls_after_innovation = llm.generate_structured.call_count
        agent.inventory.items.clear()

        oracle.resolve_action(agent, {"action": "make_knife"}, tick=2)
        assert llm.generate_structured.call_count == calls_after_innovation

    def test_crafting_consumes_items_on_success(self):
        """After successful crafting, required items are removed from inventory."""
        oracle, agent = self._setup_crafting()
        stone_before = agent.inventory.items.get("stone", 0)

        oracle.resolve_action(agent, {"action": "make_knife"}, tick=2)

        assert agent.inventory.items.get("stone", 0) == stone_before - 2

    def test_crafting_produces_item_in_inventory(self):
        """After successful crafting, the produced item appears in inventory."""
        oracle, agent = self._setup_crafting()

        oracle.resolve_action(agent, {"action": "make_knife"}, tick=2)

        assert agent.inventory.items.get("knife", 0) == 1

    def test_crafting_no_llm_consumes_and_produces(self):
        """Without LLM, crafting still consumes and produces items (energy -5 fallback)."""
        world = _make_world()
        agent = _make_agent(world)
        agent.inventory.add("stone", 5)
        oracle = _make_oracle(world)  # no LLM

        oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "make_knife",
                "description": "carve stones",
                "requires": {"items": {"stone": 2}},
                "produces": {"knife": 1},
            },
            tick=1,
        )
        stone_before = agent.inventory.items.get("stone", 0)
        oracle.resolve_action(agent, {"action": "make_knife"}, tick=2)

        assert agent.inventory.items.get("stone", 0) == stone_before - 2
        assert agent.inventory.items.get("knife", 0) == 1

    def test_crafting_via_precedent_cache_also_consumes_produces(self):
        """The second execution (hits precedent cache) must also consume and produce."""
        oracle, agent = self._setup_crafting()

        # First execution: sets the situation precedent
        oracle.resolve_action(agent, {"action": "make_knife"}, tick=2)

        # Reload materials for second execution
        agent.inventory.add("stone", 5)
        knife_before = agent.inventory.items.get("knife", 0)
        stone_before = agent.inventory.items.get("stone", 0)

        # Second execution: hits precedent cache
        oracle.resolve_action(agent, {"action": "make_knife"}, tick=3)

        assert agent.inventory.items.get("stone", 0) == stone_before - 2
        assert agent.inventory.items.get("knife", 0) == knife_before + 1


# ---------------------------------------------------------------------------
# Affordance discovery
# ---------------------------------------------------------------------------

class TestAffordanceDiscovery:
    """Tests for Oracle._discover_item_affordances()."""

    def test_discover_item_affordances_adds_tool_requirement(self):
        """Discovered action must auto-attach requires.items = {<origin_item>: 1}."""
        llm = MagicMock()
        llm.generate_structured.side_effect = [
            _typed({
                "candidates": [
                    {"action_name": "cut_branches", "description": "cut branches from a tree", "tile": "tree"},
                ]
            }),
            _typed({"approved": True, "reason": "ok", "category": "CRAFTING"}),
        ]
        oracle = _make_oracle(_make_world(), llm=llm)
        agent = _make_agent(oracle.world)

        discovered = oracle._discover_item_affordances(
            agent, item_name="stone_knife", tick=2, discovery_mode="auto", trigger_action="make_knife"
        )

        assert len(discovered) == 1
        assert discovered[0]["attempt"]["requires"] == {
            "items": {"stone_knife": 1},
            "tile": "tree",
        }

    def test_discover_item_affordances_dedupes_known_actions(self):
        """Actions already known to the agent must be skipped."""
        llm = MagicMock()
        llm.generate_structured.side_effect = [
            _typed({
                "candidates": [
                    {"action_name": "stab", "description": "attack with the knife"},
                    {"action_name": "cut_branches", "description": "cut branches from a tree", "tile": "tree"},
                ]
            }),
            # Only one validation call expected (stab is skipped)
            _typed({"approved": True, "reason": "ok", "category": "CRAFTING"}),
        ]
        oracle = _make_oracle(_make_world(), llm=llm)
        agent = _make_agent(oracle.world)
        agent.actions.append("stab")  # pre-known

        discovered = oracle._discover_item_affordances(
            agent, item_name="stone_knife", tick=2, discovery_mode="auto", trigger_action="make_knife"
        )

        names = [entry["result"]["name"] for entry in discovered]
        assert "stab" not in names
        assert "cut_branches" in names

    def test_discover_item_affordances_no_llm_returns_empty(self):
        """When no LLM is attached, discovery returns an empty list."""
        oracle = _make_oracle(_make_world())  # no LLM
        agent = _make_agent(oracle.world)

        discovered = oracle._discover_item_affordances(
            agent, item_name="stone_knife", tick=1, discovery_mode="auto", trigger_action="make_knife"
        )

        assert discovered == []

    def test_discover_item_affordances_payload_shape(self):
        """Each returned entry has the expected engine-ready payload shape."""
        llm = MagicMock()
        llm.generate_structured.side_effect = [
            _typed({
                "candidates": [
                    {"action_name": "whittle_stake", "description": "whittle wood into a stake"},
                ]
            }),
            _typed({"approved": True, "reason": "ok", "category": "CRAFTING"}),
        ]
        oracle = _make_oracle(_make_world(), llm=llm)
        agent = _make_agent(oracle.world)

        discovered = oracle._discover_item_affordances(
            agent, item_name="stone_knife", tick=3, discovery_mode="auto", trigger_action="make_knife"
        )

        assert len(discovered) == 1
        entry = discovered[0]
        assert entry["origin_item"] == "stone_knife"
        assert entry["discovery_mode"] == "auto"
        assert entry["trigger_action"] == "make_knife"
        assert entry["attempt"]["action"] == "innovate"
        assert entry["attempt"]["new_action_name"] == "whittle_stake"
        assert "result" in entry

    def test_discover_item_affordances_no_tile_in_candidate(self):
        """When candidate has no tile, requires must not include a tile key."""
        llm = MagicMock()
        llm.generate_structured.side_effect = [
            _typed({
                "candidates": [
                    {"action_name": "sharpen_stick", "description": "sharpen a stick into a point"},
                ]
            }),
            _typed({"approved": True, "reason": "ok", "category": "CRAFTING"}),
        ]
        oracle = _make_oracle(_make_world(), llm=llm)
        agent = _make_agent(oracle.world)

        discovered = oracle._discover_item_affordances(
            agent, item_name="stone_knife", tick=1, discovery_mode="auto", trigger_action="make_knife"
        )

        assert len(discovered) == 1
        requires = discovered[0]["attempt"]["requires"]
        assert "tile" not in requires
        assert requires == {"items": {"stone_knife": 1}}

    def test_discover_item_affordances_dedupes_within_batch(self):
        """Duplicate names within a single response batch must be collapsed to one."""
        llm = MagicMock()
        llm.generate_structured.side_effect = [
            _typed({
                "candidates": [
                    {"action_name": "cut_rope", "description": "cut rope"},
                    {"action_name": "cut_rope", "description": "cut rope again"},
                ]
            }),
            _typed({"approved": True, "reason": "ok", "category": "CRAFTING"}),
        ]
        oracle = _make_oracle(_make_world(), llm=llm)
        agent = _make_agent(oracle.world)

        discovered = oracle._discover_item_affordances(
            agent, item_name="stone_knife", tick=1, discovery_mode="auto", trigger_action="make_knife"
        )

        names = [entry["result"]["name"] for entry in discovered]
        assert names.count("cut_rope") == 1

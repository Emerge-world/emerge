"""
Unit tests for Oracle tile effects:
- Mountain extra energy cost
- River life damage from Oracle judgment
- Cave rest bonus
- No-LLM safety (no damage in fallback mode)
"""

import pytest

from simulation.agent import Agent
from simulation.oracle import Oracle
from simulation.world import World
from simulation.config import (
    TILE_MOUNTAIN,
    TILE_CAVE,
    TILE_RIVER,
    TILE_LAND,
    TILE_RISKS,
    TILE_REST_BONUS,
    ENERGY_COST_MOVE,
    ENERGY_RECOVERY_REST,
    AGENT_START_LIFE,
    AGENT_START_ENERGY,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_world(seed: int = 42, width: int = 30, height: int = 30) -> World:
    return World(width=width, height=height, seed=seed)


def _make_oracle(world: World, llm=None) -> Oracle:
    return Oracle(world=world, llm=llm)


def _find_tile(world: World, tile_type: str):
    """Return the (x, y) of the first occurrence of tile_type, or None."""
    for y in range(world.height):
        for x in range(world.width):
            if world.get_tile(x, y) == tile_type:
                return (x, y)
    return None


def _find_adjacent_tile(world: World, tile_type: str):
    """
    Find an (agent_pos, target_pos, direction) triple where:
    - agent_pos is adjacent to a tile of tile_type
    - moving in direction from agent_pos reaches target_pos (the desired tile)
    Returns None if no such triple exists.
    """
    from simulation.oracle import DIRECTION_DELTAS
    for y in range(world.height):
        for x in range(world.width):
            if world.get_tile(x, y) == tile_type:
                # Check all cardinal + diagonal neighbours
                for direction, (dx, dy) in DIRECTION_DELTAS.items():
                    ax, ay = x - dx, y - dy  # agent position
                    if world.get_tile(ax, ay) is not None and world.get_tile(ax, ay) != "water":
                        return (ax, ay), (x, y), direction
    return None


# ---------------------------------------------------------------------------
# Mountain: extra energy cost on entry
# ---------------------------------------------------------------------------

class TestMountainExtraEnergy:
    def test_mountain_move_extra_energy(self):
        """Moving onto a mountain tile costs ENERGY_COST_MOVE + TILE_RISKS extra."""
        world = _make_world()
        result = _find_adjacent_tile(world, TILE_MOUNTAIN)
        if result is None:
            pytest.skip("No mountain tile with a walkable neighbour in this world")

        (ax, ay), (tx, ty), direction = result
        agent = Agent(name="Ada", x=ax, y=ay)
        agent.energy = AGENT_START_ENERGY

        oracle = _make_oracle(world)
        # Pre-populate the traversal precedent so no LLM call is made
        oracle.precedents[f"physical:traversal:tile:{TILE_MOUNTAIN}"] = {
            "possible": True,
            "reason": "Exhausting but traversable.",
            "life_damage": 0,
        }

        energy_before = agent.energy
        oracle.resolve_action(agent, {"action": "move", "direction": direction}, tick=1)

        expected_extra = TILE_RISKS[TILE_MOUNTAIN]["energy_cost_add"]
        energy_spent = energy_before - agent.energy
        assert energy_spent >= ENERGY_COST_MOVE + expected_extra, (
            f"Expected at least {ENERGY_COST_MOVE + expected_extra} energy spent, "
            f"but only {energy_spent} was spent"
        )


# ---------------------------------------------------------------------------
# Cave: rest bonus
# ---------------------------------------------------------------------------

class TestCaveRestBonus:
    def test_cave_rest_bonus(self):
        """Resting in a cave applies the extra shelter energy bonus."""
        world = _make_world()
        cave_pos = _find_tile(world, TILE_CAVE)
        if cave_pos is None:
            pytest.skip("No cave tile in this world")

        cx, cy = cave_pos
        agent = Agent(name="Bruno", x=cx, y=cy)
        agent.energy = 50  # not full so there is room to recover

        oracle = _make_oracle(world)
        oracle.resolve_action(agent, {"action": "rest"}, tick=1)

        bonus = TILE_REST_BONUS[TILE_CAVE]["energy_add"]
        # energy is clamped to max, so check against minimum expected gain
        expected_min_recovery = ENERGY_RECOVERY_REST + bonus
        # If we started at 50, new energy should be at least 50 + expected_min_recovery
        # (capped at AGENT_MAX_ENERGY)
        from simulation.config import AGENT_MAX_ENERGY
        expected_energy = min(AGENT_MAX_ENERGY, 50 + expected_min_recovery)
        assert agent.energy == expected_energy, (
            f"Expected energy {expected_energy} after cave rest, got {agent.energy}"
        )

    def test_rest_no_bonus_on_land(self):
        """Resting on a plain land tile yields exactly ENERGY_RECOVERY_REST (no bonus)."""
        world = _make_world()
        land_pos = _find_tile(world, TILE_LAND)
        if land_pos is None:
            pytest.skip("No land tile in this world")

        lx, ly = land_pos
        agent = Agent(name="Clara", x=lx, y=ly)
        # Set energy low enough so that resting won't hit the cap
        agent.energy = 10

        oracle = _make_oracle(world)
        oracle.resolve_action(agent, {"action": "rest"}, tick=1)

        from simulation.config import AGENT_MAX_ENERGY
        expected_energy = min(AGENT_MAX_ENERGY, 10 + ENERGY_RECOVERY_REST)
        assert agent.energy == expected_energy, (
            f"Expected energy {expected_energy} after land rest, got {agent.energy}"
        )


# ---------------------------------------------------------------------------
# River: life damage controlled by Oracle precedent
# ---------------------------------------------------------------------------

class TestRiverLifeDamage:
    def test_no_llm_river_no_life_damage(self):
        """Without an LLM, the default traversal precedent has life_damage=0, so no life is lost."""
        world = _make_world()
        result = _find_adjacent_tile(world, TILE_RIVER)
        if result is None:
            pytest.skip("No river tile with a walkable neighbour in this world")

        (ax, ay), (tx, ty), direction = result
        agent = Agent(name="Dante", x=ax, y=ay)
        agent.life = AGENT_START_LIFE

        oracle = _make_oracle(world)  # no LLM
        # Default precedent (set when no LLM present) must allow traversal with 0 damage
        oracle.resolve_action(agent, {"action": "move", "direction": direction}, tick=1)

        assert agent.life == AGENT_START_LIFE, (
            f"Agent should not lose life crossing river without LLM, but life is {agent.life}"
        )

    def test_river_life_damage_applied(self):
        """When a precedent specifies life_damage for river traversal, that damage is applied."""
        world = _make_world()
        result = _find_adjacent_tile(world, TILE_RIVER)
        if result is None:
            pytest.skip("No river tile with a walkable neighbour in this world")

        (ax, ay), (tx, ty), direction = result
        agent = Agent(name="Elena", x=ax, y=ay)
        agent.life = AGENT_START_LIFE

        oracle = _make_oracle(world)  # no LLM
        # Manually inject a precedent that assigns life_damage
        oracle.precedents[f"physical:traversal:tile:{TILE_RIVER}"] = {
            "possible": True,
            "reason": "The current is strong.",
            "life_damage": 8,
        }

        oracle.resolve_action(agent, {"action": "move", "direction": direction}, tick=1)

        assert agent.life == AGENT_START_LIFE - 8, (
            f"Expected life {AGENT_START_LIFE - 8} after river crossing with damage=8, got {agent.life}"
        )

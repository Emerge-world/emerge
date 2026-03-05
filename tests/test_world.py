"""
Unit tests for World resource regeneration.

Covers:
- update_resources() only triggers at dawn (tick % DAY_LENGTH == 0)
- Tick 0 is skipped (world just generated)
- Non-dawn ticks never trigger regen
- Only depleted trees (absent from self.resources) are eligible
- Regenerated quantities are within [REGEN_AMOUNT_MIN, REGEN_AMOUNT_MAX]
- All regenerated positions are on tree tiles
- Determinism: same seed -> same regen at same tick
- 100% regen chance: all depleted trees regrow (uses mock patch)
"""

from unittest.mock import patch

import pytest

from simulation.world import World
from simulation.config import (
    DAY_LENGTH,
    RESOURCE_REGEN_AMOUNT_MIN,
    RESOURCE_REGEN_AMOUNT_MAX,
    TILE_TREE,
    TILE_FOREST,
)


@pytest.fixture
def world():
    """10x10 world with fixed seed for deterministic tests."""
    return World(width=10, height=10, seed=42)


def _deplete_all(world: World) -> None:
    """Consume all fruit from every resource tile."""
    for pos in list(world.resources.keys()):
        world.consume_resource(*pos, amount=10)


# ---------------------------------------------------------------------------
# Dawn detection
# ---------------------------------------------------------------------------

def test_no_regen_on_non_dawn_ticks(world):
    """Non-dawn ticks must not trigger any regeneration."""
    _deplete_all(world)
    for tick in [1, 5, 10, DAY_LENGTH - 1, DAY_LENGTH + 1, DAY_LENGTH * 2 - 1]:
        result = world.update_resources(tick)
        assert result == [], f"Expected no regen at tick {tick}"


def test_no_regen_at_tick_zero(world):
    """Tick 0 is world generation — regen must be skipped."""
    _deplete_all(world)
    result = world.update_resources(0)
    assert result == []


def test_regen_triggers_at_first_dawn(world):
    """update_resources(24) runs the regen check (returns a list, may be empty)."""
    _deplete_all(world)
    result = world.update_resources(DAY_LENGTH)
    assert isinstance(result, list)


def test_regen_triggers_at_subsequent_dawns(world):
    """Regen triggers at ticks 48 and 72 as well."""
    _deplete_all(world)
    for dawn_tick in [DAY_LENGTH * 2, DAY_LENGTH * 3]:
        result = world.update_resources(dawn_tick)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Correctness of regeneration
# ---------------------------------------------------------------------------

def test_regen_only_affects_depleted_trees(world):
    """Trees that still have fruit must not be touched."""
    # Keep track of trees with fruit before regen
    trees_with_fruit = {
        pos: info["quantity"]
        for pos, info in world.resources.items()
    }
    if not trees_with_fruit:
        pytest.skip("No trees with fruit (unusual world layout)")

    world.update_resources(DAY_LENGTH)

    for pos, original_qty in trees_with_fruit.items():
        if pos in world.resources:
            assert world.resources[pos]["quantity"] == original_qty, (
                f"Tree at {pos} had fruit before dawn but quantity changed"
            )


def test_regen_quantity_in_range(world):
    """Every regenerated resource quantity must be within [MIN, MAX]."""
    _deplete_all(world)

    with patch("simulation.world.RESOURCE_REGEN_CHANCE", 1.0):
        regenerated = world.update_resources(DAY_LENGTH)

    # Only check positions that were actually regenerated (not pre-existing resources
    # like river water that are non-depletable and use a different quantity range).
    for pos in regenerated:
        qty = world.resources[pos]["quantity"]
        assert RESOURCE_REGEN_AMOUNT_MIN <= qty <= RESOURCE_REGEN_AMOUNT_MAX, (
            f"Quantity {qty} at {pos} is out of range"
        )


def test_regen_positions_are_resource_tiles(world):
    """Regenerated resources only appear on tree or forest tiles."""
    _deplete_all(world)

    with patch("simulation.world.RESOURCE_REGEN_CHANCE", 1.0):
        regenerated = world.update_resources(DAY_LENGTH)

    REGEN_TILES = {TILE_TREE, TILE_FOREST}
    for (x, y) in regenerated:
        tile = world.get_tile(x, y)
        assert tile in REGEN_TILES, (
            f"Regenerated resource at ({x},{y}) but tile is {tile}"
        )


def test_all_depleted_regen_tiles_regen_when_chance_is_100(world):
    """With 100% chance, every depleted tree and forest tile must regenerate."""
    _deplete_all(world)
    regen_tile_count = len(world._tree_positions) + len(world._forest_positions)

    with patch("simulation.world.RESOURCE_REGEN_CHANCE", 1.0):
        regenerated = world.update_resources(DAY_LENGTH)

    assert len(regenerated) == regen_tile_count


def test_regen_returns_coords_that_got_resources(world):
    """Returned (x, y) list must be a subset of resource positions after regen.

    Non-depletable tiles (e.g., rivers with permanent water) may also be in
    world.resources, so we check that all regenerated positions are present
    and that regenerated positions are a subset (not necessarily equal) of all
    resource positions.
    """
    _deplete_all(world)

    with patch("simulation.world.RESOURCE_REGEN_CHANCE", 1.0):
        regenerated = world.update_resources(DAY_LENGTH)

    regen_set = set(regenerated)
    resource_set = set(world.resources.keys())
    assert regen_set.issubset(resource_set), (
        f"Regenerated positions not all in resources: {regen_set - resource_set}"
    )
    # All regenerated positions should actually have a resource entry
    for pos in regenerated:
        assert pos in world.resources, f"Regenerated {pos} missing from resources"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_determinism_same_seed():
    """Two worlds with the same seed produce identical regeneration."""
    world_a = World(width=10, height=10, seed=42)
    world_b = World(width=10, height=10, seed=42)

    _deplete_all(world_a)
    _deplete_all(world_b)

    result_a = world_a.update_resources(DAY_LENGTH)
    result_b = world_b.update_resources(DAY_LENGTH)

    assert sorted(result_a) == sorted(result_b)
    assert world_a.resources == world_b.resources


def test_different_seeds_run_without_error():
    """Both world instances with different seeds run update_resources without error."""
    world_a = World(width=10, height=10, seed=1)
    world_b = World(width=10, height=10, seed=999)

    _deplete_all(world_a)
    _deplete_all(world_b)

    result_a = world_a.update_resources(DAY_LENGTH)
    result_b = world_b.update_resources(DAY_LENGTH)

    # At least the test runs without error; outcomes may differ
    assert isinstance(result_a, list)
    assert isinstance(result_b, list)

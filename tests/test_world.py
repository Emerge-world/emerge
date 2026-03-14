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


# ---------------------------------------------------------------------------
# Resource placement
# ---------------------------------------------------------------------------

def test_place_resource_creates_new_stack_on_empty_tile():
    world = World(width=5, height=5, seed=42)
    world.resources.pop((1, 1), None)

    placed = world.place_resource(1, 1, "fruit", 2)

    assert placed is True
    assert world.get_resource(1, 1) == {"type": "fruit", "quantity": 2}


def test_place_resource_merges_same_type_stack():
    world = World(width=5, height=5, seed=42)
    world.resources[(1, 1)] = {"type": "fruit", "quantity": 2}

    placed = world.place_resource(1, 1, "fruit", 3)

    assert placed is True
    assert world.get_resource(1, 1) == {"type": "fruit", "quantity": 5}


def test_place_resource_rejects_conflicting_stack():
    world = World(width=5, height=5, seed=42)
    world.resources[(1, 1)] = {"type": "stone", "quantity": 2}

    placed = world.place_resource(1, 1, "fruit", 1)

    assert placed is False
    assert world.get_resource(1, 1) == {"type": "stone", "quantity": 2}


# ---------------------------------------------------------------------------
# New tile types (Phase 2)
# ---------------------------------------------------------------------------

from simulation.config import (  # noqa: E402
    TILE_WATER, TILE_LAND,
    TILE_SAND, TILE_MOUNTAIN, TILE_CAVE, TILE_RIVER,
    TILE_RESOURCE_SPAWN,
)

RIVER_WATER_QTY = TILE_RESOURCE_SPAWN[TILE_RIVER]["min"]  # 99 = inexhaustible sentinel


def test_perlin_determinism():
    """Two worlds with the same seed produce identical tile grids."""
    world_a = World(width=20, height=20, seed=99)
    world_b = World(width=20, height=20, seed=99)

    for y in range(20):
        for x in range(20):
            assert world_a.get_tile(x, y) == world_b.get_tile(x, y), (
                f"Tile mismatch at ({x},{y}): {world_a.get_tile(x, y)} vs {world_b.get_tile(x, y)}"
            )


def test_new_tile_types_appear():
    """A 30x30 world (seed=42) should contain all expected tile types."""
    world = World(width=30, height=30, seed=42)
    all_tiles = {world.grid[y][x] for y in range(world.height) for x in range(world.width)}

    expected = {TILE_FOREST, TILE_MOUNTAIN, TILE_SAND, TILE_CAVE, TILE_RIVER}
    missing = expected - all_tiles

    # If seed=42 is missing some, try additional seeds before giving up
    for extra_seed in [1, 2, 3, 7]:
        if not missing:
            break
        extra_world = World(width=30, height=30, seed=extra_seed)
        extra_tiles = {extra_world.grid[y][x] for y in range(extra_world.height) for x in range(extra_world.width)}
        missing -= extra_tiles

    assert not missing, f"Tile types never appeared across tested seeds: {missing}"


def test_river_walkable():
    """River tiles must be walkable (agents can cross rivers)."""
    world = World(width=30, height=30, seed=42)
    for y in range(world.height):
        for x in range(world.width):
            if world.get_tile(x, y) == TILE_RIVER:
                assert world.is_walkable(x, y), f"River tile at ({x},{y}) should be walkable"
                return
    pytest.skip("No river tile found in this world — increase size or try another seed")


def test_water_not_walkable():
    """Deep water tiles must not be walkable."""
    world = World(width=30, height=30, seed=42)
    for y in range(world.height):
        for x in range(world.width):
            if world.get_tile(x, y) == TILE_WATER:
                assert not world.is_walkable(x, y), f"Water tile at ({x},{y}) should not be walkable"
                return
    pytest.skip("No water tile found in this world")


def test_forest_spawns_mushrooms():
    """Forest tiles must have a mushroom resource at world generation."""
    world = World(width=30, height=30, seed=42)
    for y in range(world.height):
        for x in range(world.width):
            if world.get_tile(x, y) == TILE_FOREST:
                res = world.get_resource(x, y)
                assert res is not None, f"Forest tile at ({x},{y}) has no resource"
                assert res["type"] == "mushroom", f"Forest tile at ({x},{y}) has wrong resource type: {res['type']}"
                return
    pytest.skip("No forest tile found in this world")


def test_mountain_spawns_stone():
    """Mountain tiles must have a stone resource at world generation."""
    world = World(width=30, height=30, seed=42)
    for y in range(world.height):
        for x in range(world.width):
            if world.get_tile(x, y) == TILE_MOUNTAIN:
                res = world.get_resource(x, y)
                assert res is not None, f"Mountain tile at ({x},{y}) has no resource"
                assert res["type"] == "stone", f"Mountain tile at ({x},{y}) has wrong resource type: {res['type']}"
                return
    pytest.skip("No mountain tile found in this world")


def test_cave_spawns_stone():
    """Cave tiles must have a stone resource at world generation."""
    world = World(width=30, height=30, seed=42)
    for y in range(world.height):
        for x in range(world.width):
            if world.get_tile(x, y) == TILE_CAVE:
                res = world.get_resource(x, y)
                assert res is not None, f"Cave tile at ({x},{y}) has no resource"
                assert res["type"] == "stone", f"Cave tile at ({x},{y}) has wrong resource type: {res['type']}"
                return
    pytest.skip("No cave tile found in this world")


def test_river_has_water_resource():
    """River tiles must have a water resource with quantity 99."""
    world = World(width=30, height=30, seed=42)
    for y in range(world.height):
        for x in range(world.width):
            if world.get_tile(x, y) == TILE_RIVER:
                res = world.get_resource(x, y)
                assert res is not None, f"River tile at ({x},{y}) has no resource"
                assert res["type"] == "water", f"River tile at ({x},{y}) has wrong resource type: {res['type']}"
                assert res["quantity"] == RIVER_WATER_QTY, f"River water at ({x},{y}) has unexpected quantity: {res['quantity']}"
                return
    pytest.skip("No river tile found in this world")


def test_river_water_inexhaustible():
    """Consuming from a river tile must not reduce its quantity."""
    world = World(width=30, height=30, seed=42)
    river_pos = None
    for y in range(world.height):
        for x in range(world.width):
            if world.get_tile(x, y) == TILE_RIVER:
                river_pos = (x, y)
                break
        if river_pos:
            break

    if river_pos is None:
        pytest.skip("No river tile found in this world")

    x, y = river_pos
    world.consume_resource(x, y, RIVER_WATER_QTY)
    res = world.get_resource(x, y)
    assert res is not None, "River resource disappeared after consuming — should be inexhaustible"
    assert res["quantity"] == RIVER_WATER_QTY, f"River quantity changed after consuming: {res['quantity']}"


def test_stone_does_not_regen():
    """Stone resources (mountain/cave) must NOT regenerate at dawn."""
    world = World(width=30, height=30, seed=42)
    _deplete_all(world)

    # Collect all mountain and cave positions before regen
    stone_tiles = {TILE_MOUNTAIN, TILE_CAVE}
    mountain_cave_positions = {
        (x, y)
        for y in range(world.height)
        for x in range(world.width)
        if world.get_tile(x, y) in stone_tiles
    }

    with patch("simulation.world.RESOURCE_REGEN_CHANCE", 1.0):
        regenerated = world.update_resources(DAY_LENGTH)

    regen_set = set(regenerated)
    stone_regen = regen_set & mountain_cave_positions
    assert stone_regen == set(), (
        f"Stone positions should never regenerate, but these did: {stone_regen}"
    )


def test_mushroom_regen_at_dawn():
    """Forest (mushroom) tiles must regenerate at dawn with 100% regen chance."""
    world = World(width=30, height=30, seed=42)
    forest_positions = [
        (x, y)
        for y in range(world.height)
        for x in range(world.width)
        if world.get_tile(x, y) == TILE_FOREST
    ]
    if not forest_positions:
        pytest.skip("No forest tiles in this world")

    _deplete_all(world)

    with patch("simulation.world.RESOURCE_REGEN_CHANCE", 1.0):
        regenerated = world.update_resources(DAY_LENGTH)

    regen_set = set(regenerated)
    forest_set = set(forest_positions)
    mushroom_regen = regen_set & forest_set
    assert len(mushroom_regen) > 0, "Expected at least some forest positions to regenerate mushrooms"


def test_world_size_configurable():
    """World dimensions must match the constructor arguments."""
    small = World(width=10, height=10)
    assert small.width == 10
    assert small.height == 10
    assert len(small.grid) == 10
    assert len(small.grid[0]) == 10

    rect = World(width=20, height=15)
    assert rect.width == 20
    assert rect.height == 15
    assert len(rect.grid) == 15
    assert len(rect.grid[0]) == 20

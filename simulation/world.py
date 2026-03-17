"""
2D world represented by a tile matrix.
Each tile can be: water, land, tree, sand, forest, mountain, cave, river.

If a WorldSchema is supplied, tile types, height thresholds, noise parameters,
resource spawn configs and regeneration parameters are all read from the schema.
Falls back to config.py constants when no schema is provided.
"""

import json
import random
import logging
from typing import Optional, TYPE_CHECKING

from opensimplex import OpenSimplex

from simulation.config import (
    WORLD_WIDTH, WORLD_HEIGHT,
    TILE_WATER, TILE_LAND, TILE_TREE,
    TILE_SAND, TILE_FOREST, TILE_MOUNTAIN, TILE_CAVE, TILE_RIVER,
    DAY_LENGTH,
    RESOURCE_REGEN_CHANCE, RESOURCE_REGEN_AMOUNT_MIN, RESOURCE_REGEN_AMOUNT_MAX,
    TILE_RESOURCE_SPAWN,
    WORLD_NOISE_SCALE, WORLD_RIVER_NOISE_SCALE, WORLD_RIVER_THRESHOLD,
    WORLD_HEIGHT_WATER, WORLD_HEIGHT_SAND, WORLD_HEIGHT_LAND,
    WORLD_HEIGHT_TREE, WORLD_HEIGHT_FOREST, WORLD_HEIGHT_MOUNTAIN, WORLD_HEIGHT_CAVE,
)

if TYPE_CHECKING:
    from simulation.world_schema import WorldSchema

logger = logging.getLogger(__name__)


class World:
    """2D world of NxM tiles."""

    def __init__(
        self,
        width: int = WORLD_WIDTH,
        height: int = WORLD_HEIGHT,
        seed: Optional[int] = None,
        world_schema: Optional["WorldSchema"] = None,
    ):
        self._schema = world_schema
        # Dimensions: schema overrides constructor args when provided
        if world_schema is not None:
            self.width = world_schema.world["width"]
            self.height = world_schema.world["height"]
        else:
            self.width = width
            self.height = height
        self.grid: list[list[str]] = []
        self.resources: dict[tuple[int, int], dict] = {}  # (x,y) -> resource info
        self._rng = random.Random(seed)       # dedicated RNG for regeneration (deterministic)
        self._tree_positions: list[tuple[int, int]] = []  # cached at generation time
        self._forest_positions: list[tuple[int, int]] = []  # cached at generation time
        self._resource_positions: dict[str, list[tuple[int, int]]] = {}
        # Build schema-driven lookup caches
        self._walkable_tiles: Optional[set[str]] = None
        self._spawn_tiles_set: Optional[set[str]] = None
        self._inexhaustible_resources: Optional[set[str]] = None
        if world_schema is not None:
            self._walkable_tiles = world_schema.get_walkable_tiles()
            self._spawn_tiles_set = world_schema.get_spawn_tiles()
            self._inexhaustible_resources = {
                r for r in world_schema.resources
                if world_schema.is_resource_inexhaustible(r)
            }
        self._generate(seed)

    def _generate(self, seed: Optional[int] = None):
        """Generate world using Perlin noise for geographic coherence."""
        schema = self._schema

        # Noise parameters
        if schema is not None:
            noise_cfg = schema.world["noise"]
            primary_scale = noise_cfg["primary_scale"]
            river_scale = noise_cfg["river_scale"]
            river_threshold = noise_cfg["river_threshold"]
        else:
            primary_scale = WORLD_NOISE_SCALE
            river_scale = WORLD_RIVER_NOISE_SCALE
            river_threshold = WORLD_RIVER_THRESHOLD

        gen_primary = OpenSimplex(seed if seed is not None else 0)
        gen_river   = OpenSimplex((seed if seed is not None else 0) + 1)  # + 1 ensures river noise field is uncorrelated with the height field

        self.grid = []
        self.resources = {}
        self._resource_positions: dict[str, list[tuple[int, int]]] = {}

        if schema is not None:
            # Schema-driven tile assignment: sorted tile list by height_max
            _sorted_tiles = schema.get_tiles_sorted_by_height()
            _overflow_tile = schema.get_overflow_tile()
            _river_overlay_tiles = schema.get_river_overlay_tiles()
            _tile_resources = {
                name: schema.get_tile_resource_spawn(name)
                for name, _ in _sorted_tiles
                if schema.get_tile_resource_spawn(name) is not None
            }
            # Also include river resource
            _river_res = schema.get_tile_resource_spawn("river")
        else:
            _sorted_tiles = None
            _overflow_tile = None
            _river_overlay_tiles = {TILE_SAND, TILE_LAND}
            _tile_resources = None
            _river_res = None

        for y in range(self.height):
            row = []
            for x in range(self.width):
                h = (gen_primary.noise2(x / primary_scale, y / primary_scale) + 1) / 2

                if schema is not None:
                    tile = _overflow_tile  # default: overflow tile
                    for tile_name, tile_cfg in _sorted_tiles:
                        if h < tile_cfg["height_max"]:
                            tile = tile_name
                            break
                    # River overlay: check secondary noise for river-eligible tiles
                    if tile in _river_overlay_tiles:
                        r = (gen_river.noise2(x / river_scale, y / river_scale) + 1) / 2
                        if r < river_threshold:
                            tile = "river"
                    # Spawn resources for this tile
                    spawn = None
                    if tile == "river":
                        spawn = _river_res
                    elif tile in _tile_resources:
                        spawn = _tile_resources[tile]
                else:
                    # Legacy hardcoded generation
                    if h < WORLD_HEIGHT_WATER:
                        tile = TILE_WATER
                    elif h < WORLD_HEIGHT_SAND:
                        r = (gen_river.noise2(x / river_scale, y / river_scale) + 1) / 2
                        tile = TILE_RIVER if r < river_threshold else TILE_SAND
                    elif h < WORLD_HEIGHT_LAND:
                        r = (gen_river.noise2(x / river_scale, y / river_scale) + 1) / 2
                        tile = TILE_RIVER if r < river_threshold else TILE_LAND
                    elif h < WORLD_HEIGHT_TREE:
                        tile = TILE_TREE
                    elif h < WORLD_HEIGHT_FOREST:
                        tile = TILE_FOREST
                    elif h < WORLD_HEIGHT_MOUNTAIN:
                        tile = TILE_MOUNTAIN
                    elif h < WORLD_HEIGHT_CAVE:
                        tile = TILE_CAVE
                    else:
                        tile = TILE_MOUNTAIN  # mountain peak, same type
                    spawn = TILE_RESOURCE_SPAWN.get(tile)

                row.append(tile)

                # Spawn resources for resource-bearing tiles
                if spawn:
                    qty = self._rng.randint(spawn["min"], spawn["max"])
                    self.resources[(x, y)] = {"type": spawn["type"], "quantity": qty}
                    self._resource_positions.setdefault(tile, []).append((x, y))

            self.grid.append(row)

        # Back-compat aliases used by existing regen logic
        self._tree_positions = self._resource_positions.get(TILE_TREE, [])
        self._forest_positions = self._resource_positions.get(TILE_FOREST, [])
        # Schema-driven: collect all tiles with regenerating resources
        if schema is not None:
            self._regen_tile_map = schema.get_regenerating_tile_resource()
        else:
            self._regen_tile_map = {"tree": "fruit", "forest": "mushroom"}

        logger.info(f"World generated: {self.width}x{self.height} (Perlin noise, seed={seed})")

    def get_tile(self, x: int, y: int) -> Optional[str]:
        """Return the tile type at (x, y) or None if out of bounds."""
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[y][x]
        return None

    def is_walkable(self, x: int, y: int) -> bool:
        """Check if an agent can move to this tile."""
        tile = self.get_tile(x, y)
        if tile is None:
            return False
        if self._walkable_tiles is not None:
            return tile in self._walkable_tiles
        return tile != TILE_WATER

    def get_resource(self, x: int, y: int) -> Optional[dict]:
        """Return resource information at (x, y), if any."""
        return self.resources.get((x, y))

    def place_resource(self, x: int, y: int, item: str, amount: int = 1) -> bool:
        """Place a resource stack on a tile if the tile is empty or same-typed."""
        if amount <= 0:
            return False

        existing = self.resources.get((x, y))
        if existing is None:
            self.resources[(x, y)] = {"type": item, "quantity": amount}
            return True

        if existing["type"] != item:
            return False

        existing["quantity"] += amount
        return True

    def consume_resource(self, x: int, y: int, amount: int = 1) -> int:
        """Consume a resource at a tile. Returns the amount actually consumed.
        Inexhaustible resources (e.g. water in rivers) are never decremented.
        """
        res = self.resources.get((x, y))
        if res and res["quantity"] > 0:
            res_type = res["type"]
            # Schema-aware inexhaustibility check
            is_inexhaustible = (
                res_type in self._inexhaustible_resources
                if self._inexhaustible_resources is not None
                else res_type == "water"
            )
            if is_inexhaustible:
                return amount
            consumed = min(amount, res["quantity"])
            res["quantity"] -= consumed
            if res["quantity"] <= 0:
                # The tile runs out of resource but the tile type remains
                del self.resources[(x, y)]
            return consumed
        return 0

    def update_resources(self, tick: int) -> list[tuple[int, int]]:
        """
        At each dawn (tick % DAY_LENGTH == 0, skipping tick 0), depleted resource
        tiles with regenerates=True have a chance to regrow their resource.
        Uses self._rng for determinism.

        Returns list of (x, y) positions where resources regenerated this tick.
        """
        if not (tick != 0 and tick % DAY_LENGTH == 0):
            return []

        schema = self._schema
        if schema is not None:
            regen_chance = schema.regeneration["chance"]
            regen_min = schema.regeneration["amount_min"]
            regen_max = schema.regeneration["amount_max"]
        else:
            regen_chance = RESOURCE_REGEN_CHANCE
            regen_min = RESOURCE_REGEN_AMOUNT_MIN
            regen_max = RESOURCE_REGEN_AMOUNT_MAX

        regenerated = []

        # Schema-driven: iterate all tile types that have regenerating resources
        for tile_name, resource_type in self._regen_tile_map.items():
            positions = self._resource_positions.get(tile_name, [])
            for (x, y) in positions:
                if (x, y) not in self.resources:  # depleted
                    if self._rng.random() < regen_chance:
                        qty = self._rng.randint(regen_min, regen_max)
                        self.resources[(x, y)] = {"type": resource_type, "quantity": qty}
                        regenerated.append((x, y))

        return regenerated

    def get_nearby_tiles(self, x: int, y: int, radius: int) -> list[dict]:
        """
        Return information about tiles around (x, y) within the given radius.
        Format: [{"x": int, "y": int, "tile": str, "resource": dict|None}, ...]
        """
        tiles = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = x + dx, y + dy
                tile_type = self.get_tile(nx, ny)
                if tile_type is not None:
                    tile_info = {
                        "x": nx,
                        "y": ny,
                        "tile": tile_type,
                        "distance": abs(dx) + abs(dy),
                    }
                    res = self.get_resource(nx, ny)
                    if res:
                        tile_info["resource"] = res
                    tiles.append(tile_info)
        return tiles

    def find_spawn_point(self) -> tuple[int, int]:
        """Find a random safe tile to spawn an agent."""
        spawn_tiles = (
            self._spawn_tiles_set
            if self._spawn_tiles_set is not None
            else {TILE_LAND, TILE_SAND, TILE_FOREST}
        )
        attempts = 0
        while attempts < 1000:
            x = self._rng.randint(0, self.width - 1)
            y = self._rng.randint(0, self.height - 1)
            if self.grid[y][x] in spawn_tiles:
                return (x, y)
            attempts += 1
        # Fallback: linear search
        for y in range(self.height):
            for x in range(self.width):
                if self.grid[y][x] in spawn_tiles:
                    return (x, y)
        raise RuntimeError("No safe spawn tile found")

    def to_json(self) -> str:
        """Export the complete world as JSON."""
        data = {
            "width": self.width,
            "height": self.height,
            "tiles": [],
        }
        for y in range(self.height):
            for x in range(self.width):
                tile_data = {"x": x, "y": y, "type": self.grid[y][x]}
                res = self.get_resource(x, y)
                if res:
                    tile_data["resource"] = res
                data["tiles"].append(tile_data)
        return json.dumps(data, indent=2)

    def get_summary(self) -> dict:
        """Statistical summary of the world."""
        counts: dict[str, int] = {}
        for row in self.grid:
            for tile in row:
                counts[tile] = counts.get(tile, 0) + 1

        resource_summary: dict[str, int] = {}
        for res in self.resources.values():
            rtype = res["type"]
            resource_summary[rtype] = resource_summary.get(rtype, 0) + res["quantity"]

        return {
            "dimensions": f"{self.width}x{self.height}",
            "tile_counts": counts,
            "resources_by_type": resource_summary,
            "resource_locations": len(self.resources),
        }

    def get_agents_in_radius(
        self,
        agent: object,
        agents_list: list,
        radius: int,
    ) -> list[tuple]:
        """
        Return alive agents within Manhattan distance `radius` of `agent`,
        excluding `agent` itself. Results sorted by distance (closest first).

        Returns list of (agent, distance) tuples.
        """
        result = []
        for other in agents_list:
            if other is agent:
                continue
            if not other.alive:
                continue
            distance = abs(other.x - agent.x) + abs(other.y - agent.y)
            if distance <= radius:
                result.append((other, distance))
        result.sort(key=lambda t: t[1])
        return result

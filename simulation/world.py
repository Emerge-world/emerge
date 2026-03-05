"""
2D world represented by a tile matrix.
Each tile can be: water, land, tree, sand, forest, mountain, cave, river.
"""

import json
import random
import logging
from typing import Optional

from opensimplex import OpenSimplex

from simulation.config import (
    WORLD_WIDTH, WORLD_HEIGHT,
    TILE_WATER, TILE_LAND, TILE_TREE,
    TILE_SAND, TILE_FOREST, TILE_MOUNTAIN, TILE_CAVE, TILE_RIVER,
    WORLD_WATER_PROB, WORLD_TREE_PROB,  # keep for backwards compat but won't use in generation
    DAY_LENGTH,
    RESOURCE_REGEN_CHANCE, RESOURCE_REGEN_AMOUNT_MIN, RESOURCE_REGEN_AMOUNT_MAX,
    TILE_RESOURCE_SPAWN,
    WORLD_NOISE_SCALE, WORLD_RIVER_NOISE_SCALE, WORLD_RIVER_THRESHOLD,
    WORLD_HEIGHT_WATER, WORLD_HEIGHT_SAND, WORLD_HEIGHT_LAND,
    WORLD_HEIGHT_TREE, WORLD_HEIGHT_FOREST, WORLD_HEIGHT_MOUNTAIN, WORLD_HEIGHT_CAVE,
)

logger = logging.getLogger(__name__)


class World:
    """2D world of NxM tiles."""

    def __init__(self, width: int = WORLD_WIDTH, height: int = WORLD_HEIGHT, seed: Optional[int] = None):
        self.width = width
        self.height = height
        self.grid: list[list[str]] = []
        self.resources: dict[tuple[int, int], dict] = {}  # (x,y) -> resource info
        self._rng = random.Random(seed)       # dedicated RNG for regeneration (deterministic)
        self._tree_positions: list[tuple[int, int]] = []  # cached at generation time
        self._forest_positions: list[tuple[int, int]] = []  # cached at generation time
        self._resource_positions: dict[str, list[tuple[int, int]]] = {}
        self._generate(seed)

    def _generate(self, seed=None):
        """Generate world using Perlin noise for geographic coherence."""
        gen_primary = OpenSimplex(seed if seed is not None else 0)
        gen_river   = OpenSimplex((seed if seed is not None else 0) + 1)

        self.grid = []
        self.resources = {}
        self._resource_positions: dict[str, list[tuple[int, int]]] = {}

        for y in range(self.height):
            row = []
            for x in range(self.width):
                h = (gen_primary.noise2(x / WORLD_NOISE_SCALE, y / WORLD_NOISE_SCALE) + 1) / 2

                if h < WORLD_HEIGHT_WATER:
                    tile = TILE_WATER
                elif h < WORLD_HEIGHT_SAND:
                    r = (gen_river.noise2(x / WORLD_RIVER_NOISE_SCALE, y / WORLD_RIVER_NOISE_SCALE) + 1) / 2
                    tile = TILE_RIVER if r < WORLD_RIVER_THRESHOLD else TILE_SAND
                elif h < WORLD_HEIGHT_LAND:
                    r = (gen_river.noise2(x / WORLD_RIVER_NOISE_SCALE, y / WORLD_RIVER_NOISE_SCALE) + 1) / 2
                    tile = TILE_RIVER if r < WORLD_RIVER_THRESHOLD else TILE_LAND
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

                row.append(tile)

                # Spawn resources for resource-bearing tiles
                spawn = TILE_RESOURCE_SPAWN.get(tile)
                if spawn:
                    qty = self._rng.randint(spawn["min"], spawn["max"])
                    self.resources[(x, y)] = {"type": spawn["type"], "quantity": qty}
                    self._resource_positions.setdefault(tile, []).append((x, y))

            self.grid.append(row)

        # Back-compat aliases used by existing regen logic
        self._tree_positions = self._resource_positions.get(TILE_TREE, [])
        self._forest_positions = self._resource_positions.get(TILE_FOREST, [])

        logger.info(f"World generated: {self.width}x{self.height} (Perlin noise, seed={seed})")

    def get_tile(self, x: int, y: int) -> Optional[str]:
        """Return the tile type at (x, y) or None if out of bounds."""
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[y][x]
        return None

    def is_walkable(self, x: int, y: int) -> bool:
        """Check if an agent can move to this tile."""
        tile = self.get_tile(x, y)
        return tile is not None and tile != TILE_WATER

    def get_resource(self, x: int, y: int) -> Optional[dict]:
        """Return resource information at (x, y), if any."""
        return self.resources.get((x, y))

    def consume_resource(self, x: int, y: int, amount: int = 1) -> int:
        """Consume a resource at a tile. Returns the amount actually consumed."""
        res = self.resources.get((x, y))
        if res and res["quantity"] > 0:
            consumed = min(amount, res["quantity"])
            res["quantity"] -= consumed
            if res["quantity"] <= 0:
                # The tile runs out of resource but the tile type remains
                del self.resources[(x, y)]
            return consumed
        return 0

    def update_resources(self, tick: int) -> list[tuple[int, int]]:
        """
        At each dawn (tick % DAY_LENGTH == 0, skipping tick 0), depleted trees
        have a chance to regrow fruit. Trees that still have fruit are skipped.
        Also regrows mushrooms on depleted forest tiles.
        Stone (mountain/cave) does NOT regenerate — finite resource.
        Uses self._rng for determinism.

        Returns list of (x, y) positions where resources regenerated this tick.
        """
        if not (tick != 0 and tick % DAY_LENGTH == 0):
            return []

        regenerated = []
        for (x, y) in self._tree_positions:
            if (x, y) not in self.resources:  # tree is depleted
                if self._rng.random() < RESOURCE_REGEN_CHANCE:
                    qty = self._rng.randint(RESOURCE_REGEN_AMOUNT_MIN, RESOURCE_REGEN_AMOUNT_MAX)
                    self.resources[(x, y)] = {"type": "fruit", "quantity": qty}
                    regenerated.append((x, y))

        # Mushroom regen for depleted forest tiles (same dawn trigger)
        for (x, y) in self._forest_positions:
            if (x, y) not in self.resources:
                if self._rng.random() < RESOURCE_REGEN_CHANCE:
                    qty = self._rng.randint(RESOURCE_REGEN_AMOUNT_MIN, RESOURCE_REGEN_AMOUNT_MAX)
                    self.resources[(x, y)] = {"type": "mushroom", "quantity": qty}
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
        """Find a random safe tile to spawn an agent (land, sand, or forest)."""
        SPAWN_TILES = {TILE_LAND, TILE_SAND, TILE_FOREST}
        attempts = 0
        while attempts < 1000:
            x = self._rng.randint(0, self.width - 1)
            y = self._rng.randint(0, self.height - 1)
            if self.grid[y][x] in SPAWN_TILES:
                return (x, y)
            attempts += 1
        # Fallback: linear search
        for y in range(self.height):
            for x in range(self.width):
                if self.grid[y][x] in SPAWN_TILES:
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

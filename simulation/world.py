"""
2D world represented by a tile matrix.
Each tile can be: water, land, tree.
"""

import json
import random
import logging
from typing import Optional

from simulation.config import (
    WORLD_WIDTH, WORLD_HEIGHT,
    TILE_WATER, TILE_LAND, TILE_TREE,
    WORLD_WATER_PROB, WORLD_TREE_PROB,
    DAY_LENGTH,
    RESOURCE_REGEN_CHANCE, RESOURCE_REGEN_AMOUNT_MIN, RESOURCE_REGEN_AMOUNT_MAX,
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
        self._generate(seed)

    def _generate(self, seed: Optional[int] = None):
        """Generate the world procedurally."""
        if seed is not None:
            random.seed(seed)

        self.grid = []
        self._tree_positions = []  # reset before populating
        for y in range(self.height):
            row = []
            for x in range(self.width):
                r = random.random()
                if r < WORLD_WATER_PROB:
                    tile = TILE_WATER
                elif r < WORLD_WATER_PROB + WORLD_TREE_PROB:
                    tile = TILE_TREE
                    # Trees have harvestable fruit
                    self.resources[(x, y)] = {"type": "fruit", "quantity": random.randint(1, 5)}
                    self._tree_positions.append((x, y))  # cache for fast regen iteration
                else:
                    tile = TILE_LAND
                row.append(tile)
            self.grid.append(row)

        logger.info(f"World generated: {self.width}x{self.height}")

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
                # The tree runs out of fruit but remains a tree
                del self.resources[(x, y)]
            return consumed
        return 0

    def update_resources(self, tick: int) -> list[tuple[int, int]]:
        """
        At each dawn (tick % DAY_LENGTH == 0, skipping tick 0), depleted trees
        have a chance to regrow fruit. Trees that still have fruit are skipped.
        Uses self._rng for determinism.

        Returns list of (x, y) positions where fruit regenerated this tick.
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
        """Find a random land tile to spawn an agent."""
        attempts = 0
        while attempts < 1000:
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            if self.grid[y][x] == TILE_LAND:
                return (x, y)
            attempts += 1
        # Fallback: linear search
        for y in range(self.height):
            for x in range(self.width):
                if self.grid[y][x] == TILE_LAND:
                    return (x, y)
        raise RuntimeError("No land tile found for spawning")

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
        counts = {TILE_WATER: 0, TILE_LAND: 0, TILE_TREE: 0}
        for row in self.grid:
            for tile in row:
                counts[tile] = counts.get(tile, 0) + 1
        total_fruit = sum(r["quantity"] for r in self.resources.values() if r["type"] == "fruit")
        return {
            "dimensions": f"{self.width}x{self.height}",
            "tile_counts": counts,
            "total_fruit_available": total_fruit,
            "fruit_locations": len(self.resources),
        }

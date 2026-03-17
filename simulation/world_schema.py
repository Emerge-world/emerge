"""
WorldSchema: data-driven world definition loaded from YAML.

All world/agent/simulation parameters that were previously hardcoded in
config.py are now expressed in a YAML file (data/schemas/base_world.yaml).
WorldSchema is the single source of truth for these values.

The schema is validated against data/schemas/world_schema.jsonschema on load.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

# Default schema path (relative to project root)
_DEFAULT_SCHEMA_PATH = Path(__file__).parent.parent / "data" / "schemas" / "base_world.yaml"
_JSONSCHEMA_PATH = Path(__file__).parent.parent / "data" / "schemas" / "world_schema.jsonschema"


class WorldSchema:
    """
    Parsed, validated world schema.

    Attributes are accessed as plain Python dicts/values mirroring the YAML
    structure. Use WorldSchema.load() or WorldSchema.load_default() to create
    an instance.
    """

    def __init__(self, data: dict[str, Any], source_path: Optional[Path] = None):
        self._data = data
        self.source_path = source_path

        # Top-level sections as direct attributes for convenience
        try:
            self.schema_version: str = data["schema_version"]
            self.metadata: dict = data["metadata"]
            self.world: dict = data["world"]
            self.tiles: dict[str, Any] = data["tiles"]
            self.resources: dict[str, Any] = data["resources"]
            self.agents: dict = data["agents"]
            self.day_night: dict = data["day_night"]
            self.regeneration: dict = data["regeneration"]
            self.innovation: dict = data["innovation"]
            self.reproduction: dict = data["reproduction"]
        except KeyError as exc:
            raise ValueError(f"WorldSchema validation failed: missing required field {exc}") from exc

        # Resolve the overflow tile name (for height > max tile)
        self._overflow_tile: str = self.tiles.get("_overflow", "mountain")

    # ------------------------------------------------------------------
    # Loader
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: Path | str) -> "WorldSchema":
        """Load and validate a schema YAML file."""
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        schema = cls(data, source_path=path)
        schema._validate()
        logger.debug("WorldSchema loaded from %s (generation %d)", path, schema.metadata.get("generation", 0))
        return schema

    @classmethod
    def load_default(cls) -> "WorldSchema":
        """Load the default base world schema."""
        return cls.load(_DEFAULT_SCHEMA_PATH)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorldSchema":
        """Create a WorldSchema directly from a dict (used by evolver)."""
        schema = cls(data, source_path=None)
        schema._validate()
        return schema

    def _validate(self):
        """Validate against JSON Schema if jsonschema package is available."""
        if not _JSONSCHEMA_PATH.exists():
            return
        try:
            import jsonschema  # type: ignore[import]
            with _JSONSCHEMA_PATH.open("r", encoding="utf-8") as f:
                jschema = json.load(f)
            jsonschema.validate(self._data, jschema)
        except ImportError:
            logger.debug("jsonschema not installed — skipping structural validation")
        except Exception as exc:
            raise ValueError(f"WorldSchema validation failed: {exc}") from exc

    def save(self, path: Path | str) -> None:
        """Save this schema to a YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            yaml.dump(self._data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        logger.debug("WorldSchema saved to %s", path)

    def to_yaml_str(self) -> str:
        """Serialize to YAML string (for LLM prompts)."""
        return yaml.dump(self._data, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def to_dict(self) -> dict[str, Any]:
        """Return raw dict copy."""
        import copy
        return copy.deepcopy(self._data)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def get_overflow_tile(self) -> str:
        """Tile type to use when height exceeds all defined height_max values."""
        return self._overflow_tile

    def get_walkable_tiles(self) -> set[str]:
        """Return set of tile type names that are walkable."""
        return {
            name for name, cfg in self.tiles.items()
            if not name.startswith("_") and isinstance(cfg, dict) and cfg.get("walkable", False)
        }

    def get_spawn_tiles(self) -> set[str]:
        """Return set of tile type names where agents can spawn."""
        return {
            name for name, cfg in self.tiles.items()
            if not name.startswith("_") and isinstance(cfg, dict) and cfg.get("spawn_tiles", False)
        }

    def get_tiles_sorted_by_height(self) -> list[tuple[str, dict]]:
        """
        Return tile (name, config) pairs sorted ascending by height_max,
        excluding special keys like _overflow and tiles with null height_max.
        Used by world generation.
        """
        result = []
        for name, cfg in self.tiles.items():
            if name.startswith("_") or not isinstance(cfg, dict):
                continue
            h = cfg.get("height_max")
            if h is not None:
                result.append((name, cfg))
        result.sort(key=lambda t: t[1]["height_max"])
        return result

    def get_tile_risk(self, tile_type: str) -> dict:
        """Return risk dict for a tile type, or empty dict if none."""
        cfg = self.tiles.get(tile_type, {})
        if isinstance(cfg, dict):
            return cfg.get("risk", {})
        return {}

    def get_tile_rest_bonus(self, tile_type: str) -> dict:
        """Return rest_bonus dict for a tile type, or empty dict if none."""
        cfg = self.tiles.get(tile_type, {})
        if isinstance(cfg, dict):
            return cfg.get("rest_bonus", {})
        return {}

    def get_tile_resource_spawn(self, tile_type: str) -> Optional[dict]:
        """Return resource spawn config for a tile type, or None."""
        cfg = self.tiles.get(tile_type, {})
        if isinstance(cfg, dict):
            return cfg.get("resource")
        return None

    def get_regenerating_tile_resource(self) -> dict[str, str]:
        """
        Return mapping of tile_type -> resource_type for tiles whose
        resource has regenerates=True.
        """
        result = {}
        for name, cfg in self.tiles.items():
            if name.startswith("_") or not isinstance(cfg, dict):
                continue
            res = cfg.get("resource")
            if res and res.get("regenerates", False):
                result[name] = res["type"]
        return result

    def is_resource_inexhaustible(self, resource_type: str) -> bool:
        """Return True if this resource type is inexhaustible (like water in rivers)."""
        res_cfg = self.resources.get(resource_type, {})
        return bool(res_cfg.get("inexhaustible", False))

    def get_edible_resources(self) -> set[str]:
        """Return set of resource type names that are edible."""
        return {
            name for name, cfg in self.resources.items()
            if isinstance(cfg, dict) and cfg.get("edible", False)
        }

    def get_river_overlay_tiles(self) -> set[str]:
        """Return tile names that can be overlaid with river."""
        return {
            name for name, cfg in self.tiles.items()
            if not name.startswith("_") and isinstance(cfg, dict) and cfg.get("river_overlay", False)
        }

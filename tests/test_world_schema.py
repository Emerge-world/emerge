"""
Tests for WorldSchema: loading, validation, and consistency with config.py constants.
"""

import pytest
from pathlib import Path
from simulation.world_schema import WorldSchema
import simulation.config as cfg


@pytest.fixture
def schema() -> WorldSchema:
    return WorldSchema.load_default()


class TestWorldSchemaLoad:
    def test_load_default_succeeds(self, schema):
        assert schema is not None
        assert schema.schema_version == "1.0"

    def test_metadata(self, schema):
        assert schema.metadata["name"] == "base"
        assert schema.metadata["generation"] == 0
        assert schema.metadata["parent"] is None
        assert isinstance(schema.metadata["mutations_applied"], list)

    def test_load_from_path(self, tmp_path):
        src = Path(__file__).parent.parent / "data" / "schemas" / "base_world.yaml"
        schema = WorldSchema.load(src)
        assert schema.source_path == src

    def test_from_dict_roundtrip(self, schema):
        data = schema.to_dict()
        schema2 = WorldSchema.from_dict(data)
        assert schema2.world["width"] == schema.world["width"]

    def test_to_yaml_str(self, schema):
        s = schema.to_yaml_str()
        assert "schema_version" in s
        assert "tiles" in s

    def test_save_and_reload(self, schema, tmp_path):
        out = tmp_path / "test_schema.yaml"
        schema.save(out)
        reloaded = WorldSchema.load(out)
        assert reloaded.world["width"] == schema.world["width"]
        assert reloaded.metadata["generation"] == 0


class TestWorldSchemaConsistency:
    """Assert that base_world.yaml values match config.py constants."""

    def test_world_dimensions(self, schema):
        assert schema.world["width"] == cfg.WORLD_WIDTH
        assert schema.world["height"] == cfg.WORLD_HEIGHT

    def test_noise_params(self, schema):
        noise = schema.world["noise"]
        assert noise["primary_scale"] == cfg.WORLD_NOISE_SCALE
        assert noise["river_scale"] == cfg.WORLD_RIVER_NOISE_SCALE
        assert noise["river_threshold"] == cfg.WORLD_RIVER_THRESHOLD

    def test_tile_height_thresholds(self, schema):
        assert schema.tiles["water"]["height_max"] == cfg.WORLD_HEIGHT_WATER
        assert schema.tiles["sand"]["height_max"] == cfg.WORLD_HEIGHT_SAND
        assert schema.tiles["land"]["height_max"] == cfg.WORLD_HEIGHT_LAND
        assert schema.tiles["tree"]["height_max"] == cfg.WORLD_HEIGHT_TREE
        assert schema.tiles["forest"]["height_max"] == cfg.WORLD_HEIGHT_FOREST
        assert schema.tiles["mountain"]["height_max"] == cfg.WORLD_HEIGHT_MOUNTAIN
        assert schema.tiles["cave"]["height_max"] == cfg.WORLD_HEIGHT_CAVE

    def test_tile_walkable(self, schema):
        assert schema.tiles["water"]["walkable"] is False
        for tile in ("sand", "land", "tree", "forest", "mountain", "cave", "river"):
            assert schema.tiles[tile]["walkable"] is True, f"{tile} should be walkable"

    def test_tile_risks(self, schema):
        mountain_risk = cfg.TILE_RISKS.get(cfg.TILE_MOUNTAIN, {})
        river_risk = cfg.TILE_RISKS.get(cfg.TILE_RIVER, {})
        assert schema.tiles["mountain"]["risk"]["energy_cost_add"] == mountain_risk.get("energy_cost_add", 0)
        assert schema.tiles["river"]["risk"]["energy_cost_add"] == river_risk.get("energy_cost_add", 0)

    def test_tile_rest_bonus(self, schema):
        cave_bonus = cfg.TILE_REST_BONUS.get(cfg.TILE_CAVE, {})
        assert schema.tiles["cave"]["rest_bonus"]["energy_add"] == cave_bonus.get("energy_add", 0)

    def test_agent_stats(self, schema):
        stats = schema.agents["stats"]
        assert stats["max_life"] == cfg.AGENT_MAX_LIFE
        assert stats["max_hunger"] == cfg.AGENT_MAX_HUNGER
        assert stats["max_energy"] == cfg.AGENT_MAX_ENERGY
        assert stats["start_life"] == cfg.AGENT_START_LIFE
        assert stats["start_hunger"] == cfg.AGENT_START_HUNGER
        assert stats["start_energy"] == cfg.AGENT_START_ENERGY

    def test_agent_costs(self, schema):
        costs = schema.agents["costs"]
        assert costs["move"] == cfg.ENERGY_COST_MOVE
        assert costs["eat"] == cfg.ENERGY_COST_EAT
        assert costs["innovate"] == cfg.ENERGY_COST_INNOVATE
        assert costs["communicate"] == cfg.COMMUNICATE_ENERGY_COST
        assert costs["give_item"] == cfg.GIVE_ITEM_ENERGY_COST
        assert costs["teach_teacher"] == cfg.TEACH_ENERGY_COST_TEACHER
        assert costs["teach_learner"] == cfg.TEACH_ENERGY_COST_LEARNER

    def test_agent_thresholds(self, schema):
        t = schema.agents["thresholds"]
        assert t["hunger_per_tick"] == cfg.HUNGER_PER_TICK
        assert t["hunger_damage_threshold"] == cfg.HUNGER_DAMAGE_THRESHOLD
        assert t["hunger_damage_per_tick"] == cfg.HUNGER_DAMAGE_PER_TICK
        assert t["energy_low_threshold"] == cfg.ENERGY_LOW_THRESHOLD
        assert t["energy_damage_per_tick"] == cfg.ENERGY_DAMAGE_PER_TICK
        assert t["heal_hunger_threshold"] == cfg.HEAL_HUNGER_THRESHOLD
        assert t["heal_energy_threshold"] == cfg.HEAL_ENERGY_THRESHOLD
        assert t["heal_per_tick"] == cfg.HEAL_PER_TICK

    def test_agent_vision_and_recovery(self, schema):
        assert schema.agents["vision_radius"] == cfg.AGENT_VISION_RADIUS
        assert schema.agents["rest_recovery"] == cfg.ENERGY_RECOVERY_REST
        assert schema.agents["inventory_capacity"] == cfg.AGENT_INVENTORY_CAPACITY
        assert schema.agents["max_count"] == cfg.MAX_AGENTS

    def test_day_night(self, schema):
        dn = schema.day_night
        assert dn["day_length"] == cfg.DAY_LENGTH
        assert dn["start_hour"] == cfg.WORLD_START_HOUR
        assert dn["sunset_start"] == cfg.SUNSET_START_HOUR
        assert dn["night_start"] == cfg.NIGHT_START_HOUR
        assert dn["night_vision_reduction"] == cfg.NIGHT_VISION_REDUCTION
        assert dn["sunset_vision_reduction"] == cfg.SUNSET_VISION_REDUCTION
        assert dn["night_energy_multiplier"] == cfg.NIGHT_ENERGY_MULTIPLIER

    def test_regeneration(self, schema):
        regen = schema.regeneration
        assert regen["chance"] == cfg.RESOURCE_REGEN_CHANCE
        assert regen["amount_min"] == cfg.RESOURCE_REGEN_AMOUNT_MIN
        assert regen["amount_max"] == cfg.RESOURCE_REGEN_AMOUNT_MAX

    def test_innovation_bounds(self, schema):
        bounds = schema.innovation["effect_bounds"]
        for stat, (lo, hi) in cfg.INNOVATION_EFFECT_BOUNDS.items():
            assert bounds[stat] == [lo, hi], f"{stat} bounds mismatch"

    def test_reproduction(self, schema):
        r = schema.reproduction
        assert r["min_life"] == cfg.REPRODUCE_MIN_LIFE
        assert r["max_hunger"] == cfg.REPRODUCE_MAX_HUNGER
        assert r["min_energy"] == cfg.REPRODUCE_MIN_ENERGY
        assert r["min_ticks_alive"] == cfg.REPRODUCE_MIN_TICKS_ALIVE
        assert r["cooldown"] == cfg.REPRODUCE_COOLDOWN
        assert r["life_cost"] == cfg.REPRODUCE_LIFE_COST
        assert r["hunger_cost"] == cfg.REPRODUCE_HUNGER_COST
        assert r["energy_cost"] == cfg.REPRODUCE_ENERGY_COST
        assert r["child_start_life"] == cfg.CHILD_START_LIFE
        assert r["child_start_hunger"] == cfg.CHILD_START_HUNGER
        assert r["child_start_energy"] == cfg.CHILD_START_ENERGY

    def test_resource_spawn_config(self, schema):
        for tile_name, spawn in cfg.TILE_RESOURCE_SPAWN.items():
            # river resource is in river tile cfg
            tile_cfg = schema.tiles.get(tile_name, {})
            assert isinstance(tile_cfg, dict), f"tile {tile_name} missing"
            res = tile_cfg.get("resource", {})
            assert res.get("type") == spawn["type"], f"{tile_name} resource type mismatch"
            assert res.get("min") == spawn["min"], f"{tile_name} resource min mismatch"
            assert res.get("max") == spawn["max"], f"{tile_name} resource max mismatch"

    def test_edible_resources(self, schema):
        edible = schema.get_edible_resources()
        assert edible == cfg.EDIBLE_ITEMS


class TestWorldSchemaAccessors:
    def test_walkable_tiles(self, schema):
        walkable = schema.get_walkable_tiles()
        assert "water" not in walkable
        assert "land" in walkable
        assert "cave" in walkable

    def test_spawn_tiles(self, schema):
        spawn = schema.get_spawn_tiles()
        assert "land" in spawn
        assert "sand" in spawn
        assert "water" not in spawn

    def test_tiles_sorted_by_height(self, schema):
        sorted_tiles = schema.get_tiles_sorted_by_height()
        heights = [cfg["height_max"] for _, cfg in sorted_tiles]
        assert heights == sorted(heights)
        # river has null height_max, should not appear
        names = [n for n, _ in sorted_tiles]
        assert "river" not in names
        assert "_overflow" not in names

    def test_get_tile_risk(self, schema):
        risk = schema.get_tile_risk("mountain")
        assert risk["energy_cost_add"] == 6
        risk_none = schema.get_tile_risk("land")
        assert risk_none == {}

    def test_get_tile_rest_bonus(self, schema):
        bonus = schema.get_tile_rest_bonus("cave")
        assert bonus["energy_add"] == 20
        bonus_none = schema.get_tile_rest_bonus("land")
        assert bonus_none == {}

    def test_regenerating_tiles(self, schema):
        regen = schema.get_regenerating_tile_resource()
        assert "tree" in regen
        assert regen["tree"] == "fruit"
        assert "forest" in regen
        assert regen["forest"] == "mushroom"
        assert "mountain" not in regen  # stone doesn't regenerate

    def test_inexhaustible_resource(self, schema):
        assert schema.is_resource_inexhaustible("water") is True
        assert schema.is_resource_inexhaustible("fruit") is False
        assert schema.is_resource_inexhaustible("stone") is False

    def test_river_overlay_tiles(self, schema):
        overlay = schema.get_river_overlay_tiles()
        assert "sand" in overlay
        assert "land" in overlay
        assert "water" not in overlay

    def test_overflow_tile(self, schema):
        assert schema.get_overflow_tile() == "mountain"


class TestWorldSchemaValidation:
    def test_missing_required_field_raises(self):
        import yaml
        src = Path(__file__).parent.parent / "data" / "schemas" / "base_world.yaml"
        with src.open() as f:
            data = yaml.safe_load(f)
        del data["tiles"]
        try:
            import jsonschema  # noqa: F401
            with pytest.raises(ValueError, match="validation failed"):
                WorldSchema.from_dict(data)
        except ImportError:
            pytest.skip("jsonschema not installed")

    def test_invalid_width_raises(self):
        import yaml
        src = Path(__file__).parent.parent / "data" / "schemas" / "base_world.yaml"
        with src.open() as f:
            data = yaml.safe_load(f)
        data["world"]["width"] = 0
        try:
            import jsonschema  # noqa: F401
            with pytest.raises(ValueError, match="validation failed"):
                WorldSchema.from_dict(data)
        except ImportError:
            pytest.skip("jsonschema not installed")

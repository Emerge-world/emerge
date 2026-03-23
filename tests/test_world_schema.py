"""
Tests for the base_world.yaml schema file.
Verifies that world-level constants remain consistent with simulation config.
"""

import pathlib

import pytest
import yaml

import simulation.config as cfg


@pytest.fixture
def schema():
    schema_path = pathlib.Path(__file__).parent.parent / "data" / "schemas" / "base_world.yaml"
    with schema_path.open() as f:
        raw = yaml.safe_load(f)

    class _Schema:
        def __init__(self, data):
            self._data = data
            self.agents = data["agents"]

    return _Schema(raw)


class TestWorldSchemaConsistency:
    def test_agent_costs_include_reflect_item_uses(self, schema):
        assert schema.agents["costs"]["reflect_item_uses"] == cfg.ENERGY_COST_REFLECT_ITEM_USES

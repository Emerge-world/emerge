"""
Tests for Oracle precedent persistence (save/load to JSON).
"""
import json
from unittest.mock import MagicMock

import pytest

from simulation.oracle import Oracle
from simulation.world import World


def _make_oracle() -> Oracle:
    world = World(width=5, height=5, seed=42)
    return Oracle(world, llm=None)


def _oracle_with_precedents() -> Oracle:
    oracle = _make_oracle()
    oracle.precedents = {
        "physical:rest": {"possible": True, "reason": "always"},
        "innovation:fish": {
            "creator": "Ada",
            "description": "catch fish",
            "tick_created": 3,
            "category": "SURVIVAL",
        },
    }
    return oracle


# ── load_precedents ──────────────────────────────────────────────────────────

def test_load_missing_file_is_noop(tmp_path):
    oracle = _make_oracle()
    oracle.load_precedents(str(tmp_path / "nonexistent.json"))
    assert oracle.precedents == {}


def test_load_corrupt_json_leaves_existing(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("THIS IS NOT JSON", encoding="utf-8")
    oracle = _make_oracle()
    oracle.precedents["existing"] = {"value": 1}
    oracle.load_precedents(str(p))
    assert oracle.precedents == {"existing": {"value": 1}}


def test_load_restores_precedents(tmp_path):
    oracle = _oracle_with_precedents()
    path = str(tmp_path / "p.json")
    oracle.save_precedents(path, tick=5, world_seed=42)

    fresh = _make_oracle()
    fresh.load_precedents(path)
    assert fresh.precedents == oracle.precedents


def test_load_merges_without_overwriting_existing(tmp_path):
    oracle = _oracle_with_precedents()
    path = str(tmp_path / "p.json")
    oracle.save_precedents(path, tick=5, world_seed=42)

    # Load into oracle that already has a different key
    receiver = _make_oracle()
    receiver.precedents["pre_existing"] = {"value": 99}
    receiver.load_precedents(path)

    assert receiver.precedents["pre_existing"] == {"value": 99}
    assert "physical:rest" in receiver.precedents

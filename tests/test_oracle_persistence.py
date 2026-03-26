"""
Tests for Oracle precedent persistence (save/load to JSON).
"""
import json

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


def test_load_explicit_frozen_snapshot_restores_precedents(tmp_path):
    path = tmp_path / "frozen.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "precedents": {
                    "physical:rest": {"possible": True, "reason": "frozen"},
                },
            }
        ),
        encoding="utf-8",
    )

    oracle = _make_oracle()
    oracle.load_precedents(str(path))

    assert oracle.precedents["physical:rest"]["reason"] == "frozen"


def test_load_merges_without_overwriting_existing(tmp_path):
    oracle = _oracle_with_precedents()
    path = str(tmp_path / "p.json")
    oracle.save_precedents(path, tick=5, world_seed=42)

    # Load into oracle that already has a different key
    receiver = _make_oracle()
    receiver.precedents["pre_existing"] = {"value": 99}
    receiver.load_precedents(path)

    assert receiver.precedents["pre_existing"] == {"value": 99}
    assert receiver.precedents["physical:rest"] == oracle.precedents["physical:rest"]


def test_load_file_wins_on_collision(tmp_path):
    """When a key exists in both file and memory, the file's value wins (update semantics)."""
    oracle = _make_oracle()
    oracle.precedents["physical:rest"] = {"possible": True, "reason": "original"}
    path = str(tmp_path / "p.json")
    oracle.save_precedents(path, tick=1, world_seed=42)

    receiver = _make_oracle()
    receiver.precedents["physical:rest"] = {"possible": True, "reason": "pre-loaded"}
    receiver.load_precedents(path)

    assert receiver.precedents["physical:rest"] == {"possible": True, "reason": "original"}


# ── save_precedents ──────────────────────────────────────────────────────────

def test_save_creates_file(tmp_path):
    oracle = _oracle_with_precedents()
    path = tmp_path / "out.json"
    oracle.save_precedents(str(path), tick=10, world_seed=42)
    assert path.exists()


def test_save_schema(tmp_path):
    oracle = _oracle_with_precedents()
    path = tmp_path / "out.json"
    oracle.save_precedents(str(path), tick=10, world_seed=42)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["world_seed"] == 42
    assert data["saved_at_tick"] == 10
    assert data["precedents"] == oracle.precedents


def test_save_creates_parent_dirs(tmp_path):
    oracle = _oracle_with_precedents()
    nested = tmp_path / "deeply" / "nested" / "prec.json"
    oracle.save_precedents(str(nested), tick=1, world_seed=0)
    assert nested.exists()


def test_save_round_trip(tmp_path):
    original = _oracle_with_precedents()
    path = str(tmp_path / "round.json")
    original.save_precedents(path, tick=7, world_seed=99)

    restored = _make_oracle()
    restored.load_precedents(path)
    assert restored.precedents == original.precedents


def test_save_failure_does_not_raise(tmp_path):
    """save_precedents must not raise even when the path is invalid (silent failure)."""
    oracle = _oracle_with_precedents()
    # Passing a directory path (not a file) causes IsADirectoryError on Linux
    oracle.save_precedents(str(tmp_path), tick=1, world_seed=0)
    # No exception — the directory itself is unchanged
    assert tmp_path.is_dir()

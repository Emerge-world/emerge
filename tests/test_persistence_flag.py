"""
Tests for the --persistence flag that replaces --save-state.

Covers:
- CLI parser accepts all four modes and rejects unknown values
- --save-state is no longer a valid flag
- engine respects persistence mode when deciding what to write
"""
import argparse
from dataclasses import replace
from pathlib import Path

import pytest

from main import build_parser
from simulation.engine import SimulationEngine
from simulation.runtime_profiles import build_default_profile


# ── CLI parser ────────────────────────────────────────────────────────────────

def test_persistence_defaults_to_none():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.persistence == "none"


def test_persistence_accepts_none():
    parser = build_parser()
    args = parser.parse_args(["--persistence", "none"])
    assert args.persistence == "none"


def test_persistence_accepts_oracle():
    parser = build_parser()
    args = parser.parse_args(["--persistence", "oracle"])
    assert args.persistence == "oracle"


def test_persistence_accepts_lineage():
    parser = build_parser()
    args = parser.parse_args(["--persistence", "lineage"])
    assert args.persistence == "lineage"


def test_persistence_accepts_full():
    parser = build_parser()
    args = parser.parse_args(["--persistence", "full"])
    assert args.persistence == "full"


def test_persistence_rejects_unknown_value():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--persistence", "everything"])


def test_save_state_flag_removed():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--save-state"])


# ── Engine persistence gating ─────────────────────────────────────────────────

def _monkeypatched_engine(tmp_path, monkeypatch, persistence: str) -> SimulationEngine:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("simulation.engine.TICK_DELAY_SECONDS", 0)
    monkeypatch.setattr("simulation.engine.MetricsBuilder.build", lambda self: None)
    monkeypatch.setattr("simulation.engine.EBSBuilder.build", lambda self: None)
    return SimulationEngine(
        num_agents=1,
        use_llm=False,
        max_ticks=1,
        world_seed=1,
        run_digest=False,
        persistence=persistence,
    )


def test_persistence_full_saves_both(tmp_path, monkeypatch):
    engine = _monkeypatched_engine(tmp_path, monkeypatch, "full")
    engine.run()
    assert (tmp_path / "data" / "precedents_1.json").exists()
    assert (tmp_path / "data" / "lineage_1.json").exists()


def test_persistence_none_saves_neither(tmp_path, monkeypatch):
    engine = _monkeypatched_engine(tmp_path, monkeypatch, "none")
    engine.run()
    assert not (tmp_path / "data" / "precedents_1.json").exists()
    assert not (tmp_path / "data" / "lineage_1.json").exists()


def test_persistence_oracle_saves_only_precedents(tmp_path, monkeypatch):
    engine = _monkeypatched_engine(tmp_path, monkeypatch, "oracle")
    engine.run()
    assert (tmp_path / "data" / "precedents_1.json").exists()
    assert not (tmp_path / "data" / "lineage_1.json").exists()


def test_persistence_lineage_saves_only_lineage(tmp_path, monkeypatch):
    engine = _monkeypatched_engine(tmp_path, monkeypatch, "lineage")
    engine.run()
    assert not (tmp_path / "data" / "precedents_1.json").exists()
    assert (tmp_path / "data" / "lineage_1.json").exists()


def test_frozen_oracle_never_saves_local_precedents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("simulation.engine.TICK_DELAY_SECONDS", 0)
    monkeypatch.setattr("simulation.engine.MetricsBuilder.build", lambda self: None)
    monkeypatch.setattr("simulation.engine.EBSBuilder.build", lambda self: None)

    freeze_path = tmp_path / "fixtures" / "frozen.json"
    freeze_path.parent.mkdir(parents=True)
    freeze_path.write_text(
        '{"version": 1, "precedents": {"physical:rest": {"possible": true}}}',
        encoding="utf-8",
    )

    base_profile = build_default_profile()
    profile = replace(
        base_profile,
        runtime=replace(base_profile.runtime, ticks=1, seed=1, use_llm=False, agents=1),
        persistence=replace(base_profile.persistence, mode="full"),
        oracle=replace(
            base_profile.oracle,
            mode="frozen",
            freeze_precedents_path=str(freeze_path),
        ),
    )

    engine = SimulationEngine(profile=profile, run_digest=False)
    engine.run()

    assert not (tmp_path / "data" / "precedents_1.json").exists()
    assert (tmp_path / "data" / "lineage_1.json").exists()


def test_symbolic_oracle_never_saves_local_precedents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("simulation.engine.TICK_DELAY_SECONDS", 0)
    monkeypatch.setattr("simulation.engine.MetricsBuilder.build", lambda self: None)
    monkeypatch.setattr("simulation.engine.EBSBuilder.build", lambda self: None)

    freeze_path = tmp_path / "fixtures" / "symbolic.json"
    freeze_path.parent.mkdir(parents=True)
    freeze_path.write_text(
        '{"version": 1, "precedents": {"physical:rest": {"possible": true}}}',
        encoding="utf-8",
    )

    base_profile = build_default_profile()
    profile = replace(
        base_profile,
        runtime=replace(base_profile.runtime, ticks=1, seed=2, use_llm=False, agents=1),
        persistence=replace(base_profile.persistence, mode="full"),
        oracle=replace(
            base_profile.oracle,
            mode="symbolic",
            freeze_precedents_path=str(freeze_path),
        ),
    )

    engine = SimulationEngine(profile=profile, run_digest=False)
    engine.run()

    assert not (tmp_path / "data" / "precedents_2.json").exists()
    assert (tmp_path / "data" / "lineage_2.json").exists()

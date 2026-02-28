"""
Tests for the behavioral audit system (recorder + comparison).
"""

import json
import os
import tempfile

import pytest

from simulation.audit_recorder import AuditRecorder
from simulation.audit_compare import (
    load_run,
    _bar,
    _sparkline,
    _delta_arrow,
    _compute_fingerprint,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def tmp_run_dir():
    """Create a temporary run directory."""
    with tempfile.TemporaryDirectory() as d:
        yield d


def _make_recorder(tmp_run_dir, config=None):
    """Create an AuditRecorder in the given directory."""
    config = config or {"max_ticks": 10, "num_agents": 1, "use_llm": False, "world_seed": 42}
    return AuditRecorder(tmp_run_dir, config)


def _make_nearby_tiles(food_adjacent=False, food_visible=False):
    """Build a minimal nearby_tiles list for testing."""
    tiles = [{"x": 5, "y": 5, "tile": "land", "distance": 0}]
    if food_adjacent:
        tiles.append({
            "x": 5, "y": 4, "tile": "tree", "distance": 1,
            "resource": {"type": "fruit", "quantity": 3},
        })
    elif food_visible:
        tiles.append({
            "x": 5, "y": 2, "tile": "tree", "distance": 3,
            "resource": {"type": "fruit", "quantity": 2},
        })
    return tiles


# ------------------------------------------------------------------
# AuditRecorder: meta.json
# ------------------------------------------------------------------

class TestAuditRecorderMeta:
    def test_meta_json_created(self, tmp_run_dir):
        _make_recorder(tmp_run_dir)
        meta_path = os.path.join(tmp_run_dir, "audit", "meta.json")
        assert os.path.exists(meta_path)

    def test_meta_contains_config(self, tmp_run_dir):
        config = {"max_ticks": 5, "num_agents": 2, "use_llm": False, "world_seed": 99}
        _make_recorder(tmp_run_dir, config)
        with open(os.path.join(tmp_run_dir, "audit", "meta.json")) as f:
            meta = json.load(f)
        assert meta["config"]["max_ticks"] == 5
        assert meta["config"]["world_seed"] == 99

    def test_meta_contains_prompts_with_hashes(self, tmp_run_dir):
        _make_recorder(tmp_run_dir)
        with open(os.path.join(tmp_run_dir, "audit", "meta.json")) as f:
            meta = json.load(f)
        prompts = meta["prompts"]
        # Should contain at least agent/system.txt and agent/decision.txt
        assert "agent/system.txt" in prompts
        assert "sha256" in prompts["agent/system.txt"]
        assert "text" in prompts["agent/system.txt"]
        assert len(prompts["agent/system.txt"]["sha256"]) == 64  # SHA-256 hex length


# ------------------------------------------------------------------
# AuditRecorder: event recording
# ------------------------------------------------------------------

class TestAuditRecorderEvents:
    def test_record_event_creates_jsonl(self, tmp_run_dir):
        rec = _make_recorder(tmp_run_dir)
        rec.record_event(
            tick=1, agent_name="Ada",
            stats_before={"life": 100, "hunger": 0, "energy": 100},
            position_before=(5, 5),
            action="move", action_source="fallback",
            oracle_success=True,
            effects={"energy": -3},
            stats_after={"life": 100, "hunger": 0, "energy": 97},
            position_after=(6, 5),
            nearby_tiles=_make_nearby_tiles(),
        )
        jsonl_path = os.path.join(tmp_run_dir, "audit", "events.jsonl")
        assert os.path.exists(jsonl_path)

        with open(jsonl_path) as f:
            line = f.readline()
        event = json.loads(line)
        assert event["tick"] == 1
        assert event["agent"] == "Ada"
        assert event["action"] == "move"
        assert event["oracle_success"] is True

    def test_context_flags_hungry(self, tmp_run_dir):
        rec = _make_recorder(tmp_run_dir)
        rec.record_event(
            tick=1, agent_name="Ada",
            stats_before={"life": 100, "hunger": 70, "energy": 50},
            position_before=(5, 5),
            action="eat", action_source="fallback",
            oracle_success=True,
            effects={"hunger": -20},
            stats_after={"life": 100, "hunger": 50, "energy": 48},
            position_after=(5, 5),
            nearby_tiles=_make_nearby_tiles(food_adjacent=True),
        )
        event = rec.events[0]
        assert event["context_flags"]["was_hungry"] is True
        assert event["context_flags"]["food_adjacent"] is True
        assert event["context_flags"]["food_visible"] is True

    def test_context_flags_exhausted(self, tmp_run_dir):
        rec = _make_recorder(tmp_run_dir)
        rec.record_event(
            tick=1, agent_name="Ada",
            stats_before={"life": 100, "hunger": 30, "energy": 15},
            position_before=(5, 5),
            action="rest", action_source="fallback",
            oracle_success=True,
            effects={"energy": 25},
            stats_after={"life": 100, "hunger": 30, "energy": 40},
            position_after=(5, 5),
            nearby_tiles=_make_nearby_tiles(),
        )
        event = rec.events[0]
        assert event["context_flags"]["was_exhausted"] is True
        assert event["context_flags"]["was_hungry"] is False

    def test_multiple_events_appended(self, tmp_run_dir):
        rec = _make_recorder(tmp_run_dir)
        for tick in range(1, 4):
            rec.record_event(
                tick=tick, agent_name="Ada",
                stats_before={"life": 100, "hunger": 0, "energy": 100},
                position_before=(5, 5),
                action="rest", action_source="fallback",
                oracle_success=True, effects={},
                stats_after={"life": 100, "hunger": 1, "energy": 100},
                position_after=(5, 5),
                nearby_tiles=_make_nearby_tiles(),
            )

        jsonl_path = os.path.join(tmp_run_dir, "audit", "events.jsonl")
        with open(jsonl_path) as f:
            lines = f.readlines()
        assert len(lines) == 3


# ------------------------------------------------------------------
# AuditRecorder: summary computation
# ------------------------------------------------------------------

class TestAuditRecorderSummary:
    def _record_scenario(self, tmp_run_dir, max_ticks=10):
        """Record a scenario with mixed actions and return the summary."""
        rec = _make_recorder(tmp_run_dir, {"max_ticks": max_ticks, "num_agents": 1, "use_llm": False, "world_seed": 42})

        # Tick 1: move
        rec.record_event(
            tick=1, agent_name="Ada",
            stats_before={"life": 100, "hunger": 10, "energy": 90},
            position_before=(5, 5), action="move", action_source="fallback",
            oracle_success=True, effects={"energy": -3},
            stats_after={"life": 100, "hunger": 11, "energy": 87},
            position_after=(6, 5),
            nearby_tiles=_make_nearby_tiles(food_visible=True),
        )
        # Tick 2: eat (hungry, food adjacent)
        rec.record_event(
            tick=2, agent_name="Ada",
            stats_before={"life": 100, "hunger": 65, "energy": 87},
            position_before=(6, 5), action="eat", action_source="llm",
            oracle_success=True, effects={"hunger": -20, "energy": -2},
            stats_after={"life": 100, "hunger": 46, "energy": 85},
            position_after=(6, 5),
            nearby_tiles=_make_nearby_tiles(food_adjacent=True),
        )
        # Tick 3: rest (exhausted)
        rec.record_event(
            tick=3, agent_name="Ada",
            stats_before={"life": 100, "hunger": 47, "energy": 15},
            position_before=(6, 5), action="rest", action_source="fallback",
            oracle_success=True, effects={"energy": 25},
            stats_after={"life": 100, "hunger": 48, "energy": 40},
            position_after=(6, 5),
            nearby_tiles=_make_nearby_tiles(),
        )
        # Tick 4: move (failed)
        rec.record_event(
            tick=4, agent_name="Ada",
            stats_before={"life": 100, "hunger": 49, "energy": 40},
            position_before=(6, 5), action="move", action_source="fallback",
            oracle_success=False, effects={},
            stats_after={"life": 100, "hunger": 50, "energy": 40},
            position_after=(6, 5),
            nearby_tiles=_make_nearby_tiles(),
        )

        rec.finalize(max_ticks)

        summary_path = os.path.join(tmp_run_dir, "audit", "summary.json")
        with open(summary_path) as f:
            return json.load(f)

    def test_summary_created(self, tmp_run_dir):
        summary = self._record_scenario(tmp_run_dir)
        assert "agents" in summary
        assert "aggregate" in summary
        assert "Ada" in summary["agents"]

    def test_survival_rate(self, tmp_run_dir):
        summary = self._record_scenario(tmp_run_dir, max_ticks=10)
        ada = summary["agents"]["Ada"]
        assert ada["survival_ticks"] == 4
        assert ada["survival_rate"] == 0.4

    def test_action_distribution(self, tmp_run_dir):
        summary = self._record_scenario(tmp_run_dir)
        ada = summary["agents"]["Ada"]
        assert ada["action_distribution"]["move"] == 0.5
        assert ada["action_distribution"]["eat"] == 0.25
        assert ada["action_distribution"]["rest"] == 0.25

    def test_oracle_success_rate(self, tmp_run_dir):
        summary = self._record_scenario(tmp_run_dir)
        ada = summary["agents"]["Ada"]
        assert ada["oracle_success_rate"] == 0.75

    def test_reactive_metrics(self, tmp_run_dir):
        summary = self._record_scenario(tmp_run_dir)
        ada = summary["agents"]["Ada"]
        # Hungry & food visible: tick 2 (ate) -> 1/1 = 1.0
        assert ada["ate_when_hungry"] == 1.0
        # Exhausted: tick 3 (rested) -> 1/1 = 1.0
        assert ada["rested_when_exhausted"] == 1.0

    def test_trajectories(self, tmp_run_dir):
        summary = self._record_scenario(tmp_run_dir)
        ada = summary["agents"]["Ada"]
        assert len(ada["trajectories"]["life"]) == 4
        assert ada["trajectories"]["life"][0] == 100
        assert ada["trajectories"]["energy"] == [87, 85, 40, 40]

    def test_exploration(self, tmp_run_dir):
        summary = self._record_scenario(tmp_run_dir)
        ada = summary["agents"]["Ada"]
        # Positions: (6,5), (6,5), (6,5), (6,5) -> 1 unique
        # But spawn was (5,5), max distance = 1
        assert ada["unique_tiles_visited"] >= 1
        assert ada["max_distance_from_spawn"] >= 1

    def test_empty_finalize(self, tmp_run_dir):
        rec = _make_recorder(tmp_run_dir)
        rec.finalize(10)
        summary_path = os.path.join(tmp_run_dir, "audit", "summary.json")
        with open(summary_path) as f:
            summary = json.load(f)
        assert summary["agents"] == {}
        assert summary["aggregate"] == {}


# ------------------------------------------------------------------
# Comparison helpers
# ------------------------------------------------------------------

class TestCompareHelpers:
    def test_bar_empty(self):
        assert _bar(0.0) == "\u2591" * 10

    def test_bar_full(self):
        assert _bar(1.0) == "\u2588" * 10

    def test_bar_half(self):
        result = _bar(0.5)
        assert result.count("\u2588") == 5
        assert result.count("\u2591") == 5

    def test_sparkline_flat(self):
        data = [50.0] * 10
        spark = _sparkline(data)
        # All same value -> all same char
        assert len(set(spark)) == 1

    def test_sparkline_ascending(self):
        data = [float(i) for i in range(10)]
        spark = _sparkline(data)
        assert len(spark) == 10
        # First char should be lowest, last should be highest
        assert spark[0] == " "
        assert spark[-1] == "\u2588"

    def test_delta_arrow_positive_large(self):
        assert _delta_arrow(0.15) == "^^"

    def test_delta_arrow_positive_small(self):
        assert _delta_arrow(0.05) == "^"

    def test_delta_arrow_negative(self):
        assert _delta_arrow(-0.2) == "vv"

    def test_delta_arrow_zero(self):
        assert _delta_arrow(0.005) == "="

    def test_compute_fingerprint(self):
        agg = {
            "survival_rate": 0.8,
            "oracle_success_rate": 0.7,
            "ate_when_hungry": 0.6,
            "rested_when_exhausted": 0.4,
            "unique_tiles_visited": 25,
            "action_distribution": {"innovate": 0.05},
        }
        fp = _compute_fingerprint(agg)
        labels = [item[0] for item in fp]
        assert "Survival" in labels
        assert "Reactivity" in labels
        assert "Success" in labels
        assert "Mobility" in labels
        assert "Innovation" in labels
        # Check survival value matches
        survival_item = next(item for item in fp if item[0] == "Survival")
        assert survival_item[1] == 0.8


# ------------------------------------------------------------------
# Full comparison (integration)
# ------------------------------------------------------------------

class TestFullComparison:
    def _create_run(self, tmp_dir, subdir, config, events_data, max_ticks=10):
        """Create a complete audit run in a subdirectory."""
        run_dir = os.path.join(tmp_dir, subdir)
        os.makedirs(run_dir, exist_ok=True)
        rec = AuditRecorder(run_dir, config)

        for ev in events_data:
            rec.record_event(**ev)

        rec.finalize(max_ticks)
        return run_dir

    def test_load_run(self, tmp_run_dir):
        """Test that load_run reads meta and summary correctly."""
        config = {"max_ticks": 5, "num_agents": 1, "use_llm": False, "world_seed": 42}
        rec = AuditRecorder(tmp_run_dir, config)
        rec.finalize(5)

        data = load_run(tmp_run_dir)
        assert "meta" in data
        assert "summary" in data
        assert data["meta"]["config"]["max_ticks"] == 5

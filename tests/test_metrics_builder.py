"""Unit tests for simulation/metrics_builder.py."""

import json
from pathlib import Path

import pytest

from simulation.metrics_builder import MetricsBuilder


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

def _write_events(run_dir: Path, events: list[dict]) -> None:
    """Write a synthetic events.jsonl to a run directory."""
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = "\n".join(json.dumps(e) for e in events) + "\n"
    (run_dir / "events.jsonl").write_text(lines, encoding="utf-8")


def _minimal_run(run_id: str = "test-run") -> list[dict]:
    """
    Synthetic run: 2 agents (Ada, Bruno), 3 ticks.
    Ada dies at tick 3. Bruno survives.
    1 innovation attempt (approved) at tick 2. Bruno uses it at tick 3.
    """
    return [
        # run_start
        {
            "run_id": run_id, "seed": 42, "tick": 0, "sim_time": None,
            "event_type": "run_start", "agent_id": None,
            "payload": {
                "config": {"width": 15, "height": 15, "max_ticks": 3,
                           "agent_count": 2, "agent_names": ["Ada", "Bruno"]},
                "model_id": "test-model", "world_seed": 42,
            },
        },
        # tick 1
        {"run_id": run_id, "tick": 1, "sim_time": {"day": 1, "hour": 6},
         "event_type": "agent_decision", "agent_id": "Ada",
         "payload": {"parsed_action": {"action": "move"}, "parse_ok": True, "action_origin": "base"}},
        {"run_id": run_id, "tick": 1, "sim_time": {"day": 1, "hour": 6},
         "event_type": "oracle_resolution", "agent_id": "Ada",
         "payload": {"success": True, "effects": {"energy": -3, "hunger": 0, "life": 0}}},
        {"run_id": run_id, "tick": 1, "sim_time": {"day": 1, "hour": 6},
         "event_type": "agent_state", "agent_id": "Ada",
         "payload": {"life": 100, "hunger": 2, "energy": 97, "pos": [1, 1], "alive": True, "inventory": {}}},
        {"run_id": run_id, "tick": 1, "sim_time": {"day": 1, "hour": 6},
         "event_type": "agent_decision", "agent_id": "Bruno",
         "payload": {"parsed_action": {"action": "eat"}, "parse_ok": True, "action_origin": "base"}},
        {"run_id": run_id, "tick": 1, "sim_time": {"day": 1, "hour": 6},
         "event_type": "oracle_resolution", "agent_id": "Bruno",
         "payload": {"success": False, "effects": {"energy": 0, "hunger": 0, "life": 0}}},
        {"run_id": run_id, "tick": 1, "sim_time": {"day": 1, "hour": 6},
         "event_type": "agent_state", "agent_id": "Bruno",
         "payload": {"life": 90, "hunger": 5, "energy": 80, "pos": [2, 2], "alive": True, "inventory": {}}},
        # tick 2 — Bruno innovates
        {"run_id": run_id, "tick": 2, "sim_time": {"day": 1, "hour": 7},
         "event_type": "agent_decision", "agent_id": "Bruno",
         "payload": {"parsed_action": {"action": "innovate"}, "parse_ok": True, "action_origin": "base"}},
        {"run_id": run_id, "tick": 2, "sim_time": {"day": 1, "hour": 7},
         "event_type": "innovation_attempt", "agent_id": "Bruno",
         "payload": {"name": "gather_wood", "description": "cut trees", "requires": None, "produces": None}},
        {"run_id": run_id, "tick": 2, "sim_time": {"day": 1, "hour": 7},
         "event_type": "oracle_resolution", "agent_id": "Bruno",
         "payload": {"success": True, "effects": {"energy": -10, "hunger": 0, "life": 0}}},
        {"run_id": run_id, "tick": 2, "sim_time": {"day": 1, "hour": 7},
         "event_type": "innovation_validated", "agent_id": "Bruno",
         "payload": {"name": "gather_wood", "approved": True, "category": "CRAFTING", "reason_code": "INNOVATION_APPROVED"}},
        {"run_id": run_id, "tick": 2, "sim_time": {"day": 1, "hour": 7},
         "event_type": "agent_state", "agent_id": "Bruno",
         "payload": {"life": 90, "hunger": 6, "energy": 70, "pos": [2, 2], "alive": True, "inventory": {}}},
        {"run_id": run_id, "tick": 2, "sim_time": {"day": 1, "hour": 7},
         "event_type": "agent_decision", "agent_id": "Ada",
         "payload": {"parsed_action": {"action": "rest"}, "parse_ok": False, "action_origin": "base"}},
        {"run_id": run_id, "tick": 2, "sim_time": {"day": 1, "hour": 7},
         "event_type": "oracle_resolution", "agent_id": "Ada",
         "payload": {"success": True, "effects": {"energy": 10, "hunger": 0, "life": 0}}},
        {"run_id": run_id, "tick": 2, "sim_time": {"day": 1, "hour": 7},
         "event_type": "agent_state", "agent_id": "Ada",
         "payload": {"life": 100, "hunger": 4, "energy": 100, "pos": [1, 1], "alive": True, "inventory": {}}},
        # tick 3 — Bruno uses custom action; Ada dies
        {"run_id": run_id, "tick": 3, "sim_time": {"day": 1, "hour": 8},
         "event_type": "agent_decision", "agent_id": "Bruno",
         "payload": {"parsed_action": {"action": "gather_wood"}, "parse_ok": True, "action_origin": "innovation"}},
        {"run_id": run_id, "tick": 3, "sim_time": {"day": 1, "hour": 8},
         "event_type": "custom_action_executed", "agent_id": "Bruno",
         "payload": {"name": "gather_wood", "success": True, "effects": {"energy": -5, "hunger": 0, "life": 0}}},
        {"run_id": run_id, "tick": 3, "sim_time": {"day": 1, "hour": 8},
         "event_type": "oracle_resolution", "agent_id": "Bruno",
         "payload": {"success": True, "effects": {"energy": -5, "hunger": 0, "life": 0}}},
        {"run_id": run_id, "tick": 3, "sim_time": {"day": 1, "hour": 8},
         "event_type": "agent_state", "agent_id": "Bruno",
         "payload": {"life": 90, "hunger": 7, "energy": 65, "pos": [2, 2], "alive": True, "inventory": {"wood": 1}}},
        {"run_id": run_id, "tick": 3, "sim_time": {"day": 1, "hour": 8},
         "event_type": "agent_decision", "agent_id": "Ada",
         "payload": {"parsed_action": {"action": "move"}, "parse_ok": True, "action_origin": "base"}},
        {"run_id": run_id, "tick": 3, "sim_time": {"day": 1, "hour": 8},
         "event_type": "oracle_resolution", "agent_id": "Ada",
         "payload": {"success": False, "effects": {"energy": 0, "hunger": 0, "life": 0}}},
        # Ada dies — alive transitions False
        {"run_id": run_id, "tick": 3, "sim_time": {"day": 1, "hour": 8},
         "event_type": "agent_state", "agent_id": "Ada",
         "payload": {"life": 0, "hunger": 100, "energy": 0, "pos": [1, 1], "alive": False, "inventory": {}}},
        # run_end
        {"run_id": run_id, "tick": 3, "sim_time": {"day": 1, "hour": 8},
         "event_type": "run_end", "agent_id": None,
         "payload": {"survivors": ["Bruno"], "total_ticks": 3}},
    ]


def _personality_survival_run(run_id: str = "trait-run") -> list[dict]:
    return [
        {
            "run_id": run_id,
            "seed": 42,
            "tick": 0,
            "sim_time": None,
            "event_type": "run_start",
            "agent_id": None,
            "payload": {
                "config": {
                    "width": 15,
                    "height": 15,
                    "max_ticks": 3,
                    "agent_count": 2,
                    "agent_names": ["Ada", "Bruno"],
                    "agent_profiles": [
                        {
                            "name": "Ada",
                            "personality": {
                                "courage": 0.1,
                                "curiosity": 0.9,
                                "patience": 0.2,
                                "sociability": 0.6,
                            },
                        },
                        {
                            "name": "Bruno",
                            "personality": {
                                "courage": 0.9,
                                "curiosity": 0.1,
                                "patience": 0.2,
                                "sociability": 0.2,
                            },
                        },
                    ],
                },
                "model_id": "test-model",
                "world_seed": 42,
            },
        },
        {
            "run_id": run_id,
            "tick": 1,
            "sim_time": {"day": 1, "hour": 6},
            "event_type": "agent_state",
            "agent_id": "Ada",
            "payload": {
                "life": 0,
                "hunger": 100,
                "energy": 0,
                "pos": [1, 1],
                "alive": False,
                "inventory": {},
            },
        },
        {
            "run_id": run_id,
            "tick": 1,
            "sim_time": {"day": 1, "hour": 6},
            "event_type": "agent_state",
            "agent_id": "Bruno",
            "payload": {
                "life": 90,
                "hunger": 5,
                "energy": 80,
                "pos": [2, 2],
                "alive": True,
                "inventory": {},
            },
        },
        {
            "run_id": run_id,
            "tick": 2,
            "sim_time": {"day": 1, "hour": 7},
            "event_type": "agent_birth",
            "agent_id": "Kira",
            "payload": {
                "child_name": "Kira",
                "generation": 1,
                "born_tick": 2,
                "parent_ids": ["Ada", "Bruno"],
                "pos": [3, 3],
                "personality": {
                    "courage": 0.5,
                    "curiosity": 0.5,
                    "patience": 0.2,
                    "sociability": 0.9,
                },
            },
        },
        {
            "run_id": run_id,
            "tick": 3,
            "sim_time": {"day": 1, "hour": 8},
            "event_type": "run_end",
            "agent_id": None,
            "payload": {
                "survivors": ["Bruno", "Kira"],
                "total_ticks": 3,
            },
        },
    ]


# ------------------------------------------------------------------ #
# Tests: summary.json
# ------------------------------------------------------------------ #

class TestSummaryJson:
    def test_summary_file_created(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        assert (run_dir / "metrics" / "summary.json").exists()

    def test_run_id(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run("my-run-id"))
        MetricsBuilder(run_dir).build()
        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        assert summary["run_id"] == "my-run-id"

    def test_total_ticks(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        assert summary["total_ticks"] == 3

    def test_agents_initial_count(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        assert summary["agents"]["initial_count"] == 2

    def test_agents_deaths(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        assert summary["agents"]["deaths"] == 1

    def test_agents_survivors(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        assert summary["agents"]["final_survivors"] == ["Bruno"]

    def test_agents_survival_rate(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        assert summary["agents"]["survival_rate"] == 0.5

    def test_actions_total(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        # 2 agents × 3 ticks = 6 agent_decision events
        assert summary["actions"]["total"] == 6

    def test_actions_by_type(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        by_type = summary["actions"]["by_type"]
        assert by_type["move"] == 2
        assert by_type["eat"] == 1
        assert by_type["rest"] == 1
        assert by_type["innovate"] == 1
        assert by_type["gather_wood"] == 1

    def test_actions_by_type_counts_drop_item(self, tmp_path):
        run_dir = tmp_path / "test-run"
        events = _minimal_run()
        events.append(
            {
                "run_id": "test-run",
                "tick": 3,
                "sim_time": {"day": 1, "hour": 8},
                "event_type": "agent_decision",
                "agent_id": "Ada",
                "payload": {
                    "parsed_action": {"action": "drop_item"},
                    "parse_ok": True,
                    "action_origin": "base",
                },
            }
        )
        _write_events(run_dir, events)

        MetricsBuilder(run_dir).build()
        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())

        assert summary["actions"]["by_type"]["drop_item"] == 1

    def test_parse_fail_rate(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        # 1 parse_ok=False out of 6 decisions
        assert round(summary["actions"]["parse_fail_rate"], 4) == round(1/6, 4)

    def test_oracle_success_rate(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        # 4 success out of 6 oracle_resolution events
        assert round(summary["actions"]["oracle_success_rate"], 4) == round(4/6, 4)

    def test_innovations_attempts(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        assert summary["innovations"]["attempts"] == 1

    def test_innovations_approved(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        assert summary["innovations"]["approved"] == 1

    def test_innovations_used(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        assert summary["innovations"]["used"] == 1

    def test_innovations_realization_rate(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        assert summary["innovations"]["realization_rate"] == 1.0

    def test_no_events_file_no_crash(self, tmp_path):
        """build() on a run dir with no events.jsonl should not raise."""
        run_dir = tmp_path / "empty-run"
        run_dir.mkdir()
        MetricsBuilder(run_dir).build()  # must not raise
        assert not (run_dir / "metrics" / "summary.json").exists()


class TestPersonalitySurvivalSummary:
    def test_summary_adds_personality_survival_block(self, tmp_path):
        run_dir = tmp_path / "trait-run"
        _write_events(run_dir, _personality_survival_run())
        MetricsBuilder(run_dir).build()

        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        ps = summary["personality_survival"]

        assert ps["method"] == "pearson_correlation"
        assert ps["lifespan_unit"] == "ticks_alive_since_entry"
        assert ps["sample_size"] == 3
        assert ps["trait_correlations"]["courage"] == 1.0
        assert ps["trait_correlations"]["curiosity"] == -1.0
        assert ps["trait_correlations"]["patience"] is None
        assert ps["best_trait"] == "courage"
        assert ps["best_correlation"] == 1.0

    def test_survivors_and_born_agents_use_run_end_when_no_death_tick(self, tmp_path):
        run_dir = tmp_path / "trait-run"
        _write_events(run_dir, _personality_survival_run())
        MetricsBuilder(run_dir).build()

        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        assert summary["personality_survival"]["sample_size"] == 3

    def test_old_runs_without_agent_profiles_return_null_personality_summary(self, tmp_path):
        run_dir = tmp_path / "legacy-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()

        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        ps = summary["personality_survival"]

        assert ps["sample_size"] == 0
        assert ps["trait_correlations"] == {
            "courage": None,
            "curiosity": None,
            "patience": None,
            "sociability": None,
        }
        assert ps["best_trait"] is None
        assert ps["best_correlation"] is None

    def test_one_usable_agent_returns_null_correlations(self, tmp_path):
        run_dir = tmp_path / "one-agent"
        one_agent_events = [
            {
                "run_id": "one-agent",
                "seed": 42,
                "tick": 0,
                "sim_time": None,
                "event_type": "run_start",
                "agent_id": None,
                "payload": {
                    "config": {
                        "width": 15,
                        "height": 15,
                        "max_ticks": 1,
                        "agent_count": 1,
                        "agent_names": ["Ada"],
                        "agent_profiles": [
                            {
                                "name": "Ada",
                                "personality": {
                                    "courage": 0.1,
                                    "curiosity": 0.9,
                                    "patience": 0.2,
                                    "sociability": 0.6,
                                },
                            }
                        ],
                    },
                    "model_id": "test-model",
                    "world_seed": 42,
                },
            },
            {
                "run_id": "one-agent",
                "tick": 1,
                "sim_time": {"day": 1, "hour": 6},
                "event_type": "run_end",
                "agent_id": None,
                "payload": {
                    "survivors": ["Ada"],
                    "total_ticks": 1,
                },
            },
        ]
        _write_events(run_dir, one_agent_events)
        MetricsBuilder(run_dir).build()

        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        assert summary["personality_survival"]["sample_size"] == 1
        assert summary["personality_survival"]["trait_correlations"]["courage"] is None
        assert summary["personality_survival"]["best_trait"] is None


# ------------------------------------------------------------------ #
# Tests: timeseries.jsonl
# ------------------------------------------------------------------ #

class TestTimeseriesJsonl:
    def _load_timeseries(self, run_dir: Path) -> list[dict]:
        path = run_dir / "metrics" / "timeseries.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines() if line]

    def test_timeseries_file_created(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        assert (run_dir / "metrics" / "timeseries.jsonl").exists()

    def test_timeseries_row_count(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        rows = self._load_timeseries(run_dir)
        assert len(rows) == 3  # ticks 1, 2, 3

    def test_timeseries_tick_order(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        rows = self._load_timeseries(run_dir)
        assert [r["tick"] for r in rows] == [1, 2, 3]

    def test_timeseries_alive_count(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        rows = self._load_timeseries(run_dir)
        assert rows[0]["alive"] == 2  # tick 1: both alive
        assert rows[1]["alive"] == 2  # tick 2: both alive
        assert rows[2]["alive"] == 1  # tick 3: Ada died

    def test_timeseries_deaths(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        rows = self._load_timeseries(run_dir)
        assert rows[0]["deaths"] == 0
        assert rows[1]["deaths"] == 0
        assert rows[2]["deaths"] == 1

    def test_timeseries_mean_life_tick1(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        rows = self._load_timeseries(run_dir)
        # tick 1: Ada life=100, Bruno life=90 → mean=95.0
        assert rows[0]["mean_life"] == 95.0

    def test_timeseries_innovations_tick2(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        rows = self._load_timeseries(run_dir)
        assert rows[1]["innovations_attempted"] == 1
        assert rows[1]["innovations_approved"] == 1

    def test_timeseries_sim_time_field(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        rows = self._load_timeseries(run_dir)
        assert rows[0]["sim_time"] == {"day": 1, "hour": 6}

    def test_timeseries_required_fields(self, tmp_path):
        run_dir = tmp_path / "test-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()
        rows = self._load_timeseries(run_dir)
        required = {"tick", "sim_time", "alive", "mean_life", "mean_hunger",
                    "mean_energy", "deaths", "actions", "oracle_success_rate",
                    "innovations_attempted", "innovations_approved"}
        for row in rows:
            assert required.issubset(row.keys()), f"Missing fields in tick {row['tick']}: {required - row.keys()}"


# ------------------------------------------------------------------ #
# Tests: item-derived innovation events
# ------------------------------------------------------------------ #

class TestMetricsBuilder:
    def test_metrics_builder_counts_item_derived_innovation_events(self, tmp_path):
        """innovation_validated events with extra origin_item field should be counted normally."""
        run_dir = tmp_path / "test-derived-run"
        events = [
            {
                "run_id": "test-derived-run", "seed": 1, "tick": 0, "sim_time": None,
                "event_type": "run_start", "agent_id": None,
                "payload": {
                    "config": {"width": 15, "height": 15, "max_ticks": 2,
                               "agent_count": 1, "agent_names": ["Ada"]},
                    "model_id": "test-model", "world_seed": 1,
                },
            },
            # innovation_attempt for derived innovation
            {
                "run_id": "test-derived-run", "tick": 1, "sim_time": {"day": 1, "hour": 6},
                "event_type": "innovation_attempt", "agent_id": "Ada",
                "payload": {
                    "name": "cut_branches",
                    "description": "cut branches from a tree",
                    "requires": {"items": {"stone_knife": 1}},
                    "produces": {"branches": 2},
                },
            },
            # innovation_validated with origin metadata
            {
                "run_id": "test-derived-run", "tick": 1, "sim_time": {"day": 1, "hour": 6},
                "event_type": "innovation_validated", "agent_id": "Ada",
                "payload": {
                    "name": "cut_branches",
                    "approved": True,
                    "category": "CRAFTING",
                    "reason_code": "INNOVATION_APPROVED",
                    "requires": {"items": {"stone_knife": 1}},
                    "produces": {"branches": 2},
                    "description": "cut branches from a tree",
                    "origin_item": "stone_knife",
                    "discovery_mode": "auto",
                    "trigger_action": "make_knife",
                },
            },
            {
                "run_id": "test-derived-run", "tick": 2, "sim_time": {"day": 1, "hour": 7},
                "event_type": "run_end", "agent_id": None,
                "payload": {"survivors": ["Ada"], "total_ticks": 2},
            },
        ]
        _write_events(run_dir, events)
        MetricsBuilder(run_dir).build()
        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        assert summary["innovations"]["approved"] == 1

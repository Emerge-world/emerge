"""Integration tests: verify engine wires innovation events into events.jsonl."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from simulation.engine import SimulationEngine


def _read_events(run_dir: Path) -> list[dict]:
    path = run_dir / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _make_engine(tmp_path, monkeypatch) -> SimulationEngine:
    monkeypatch.chdir(tmp_path)
    return SimulationEngine(num_agents=1, use_llm=False, max_ticks=2, world_seed=42)


class TestEngineInnovationEventWiring:
    def test_innovation_attempt_emitted(self, tmp_path, monkeypatch):
        """When an agent action is 'innovate', innovation_attempt must appear in events.jsonl."""
        engine = _make_engine(tmp_path, monkeypatch)
        innovate_action = {
            "action": "innovate",
            "new_action_name": "test_craft",
            "description": "A test innovation",
        }
        # Patch decide_action on the first agent to always return innovate
        with patch.object(engine.agents[0], "decide_action", return_value=innovate_action):
            engine.run()

        events = _read_events(engine.event_emitter.run_dir)
        types = [e["event_type"] for e in events]
        assert "innovation_attempt" in types

    def test_innovation_validated_emitted(self, tmp_path, monkeypatch):
        """When an agent innovates, innovation_validated must appear in events.jsonl."""
        engine = _make_engine(tmp_path, monkeypatch)
        innovate_action = {
            "action": "innovate",
            "new_action_name": "test_craft",
            "description": "A test innovation",
        }
        with patch.object(engine.agents[0], "decide_action", return_value=innovate_action):
            engine.run()

        events = _read_events(engine.event_emitter.run_dir)
        types = [e["event_type"] for e in events]
        assert "innovation_validated" in types

    def test_custom_action_executed_emitted(self, tmp_path, monkeypatch):
        """After innovation, using the custom action emits custom_action_executed."""
        engine = _make_engine(tmp_path, monkeypatch)
        call_count = {"n": 0}

        def decide(nearby, tick, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # Tick 1: innovate
                return {"action": "innovate", "new_action_name": "test_craft", "description": "test"}
            # Tick 2: use the innovation
            return {"action": "test_craft"}

        with patch.object(engine.agents[0], "decide_action", side_effect=decide):
            engine.run()

        events = _read_events(engine.event_emitter.run_dir)
        types = [e["event_type"] for e in events]
        assert "custom_action_executed" in types

    def test_innovation_attempt_payload(self, tmp_path, monkeypatch):
        """innovation_attempt event must carry name, description, requires, produces."""
        engine = _make_engine(tmp_path, monkeypatch)
        innovate_action = {
            "action": "innovate",
            "new_action_name": "test_craft",
            "description": "A test innovation",
            "requires": {"tile": "land"},
            "produces": {"item": 1},
        }
        with patch.object(engine.agents[0], "decide_action", return_value=innovate_action):
            engine.run()

        events = _read_events(engine.event_emitter.run_dir)
        attempt = next(e for e in events if e["event_type"] == "innovation_attempt")
        assert attempt["payload"]["name"] == "test_craft"
        assert attempt["payload"]["description"] == "A test innovation"

    def test_innovation_validated_payload(self, tmp_path, monkeypatch):
        """innovation_validated event must carry approved, name, category, reason_code."""
        engine = _make_engine(tmp_path, monkeypatch)
        innovate_action = {
            "action": "innovate",
            "new_action_name": "test_craft",
            "description": "A test innovation",
        }
        with patch.object(engine.agents[0], "decide_action", return_value=innovate_action):
            engine.run()

        events = _read_events(engine.event_emitter.run_dir)
        validated = next(e for e in events if e["event_type"] == "innovation_validated")
        p = validated["payload"]
        assert "approved" in p
        assert "name" in p
        assert "reason_code" in p

    def test_auto_discovered_innovations_emit_attempt_and_validated_events(
        self, tmp_path, monkeypatch
    ):
        """When oracle returns derived_innovations, attempt + validated events are emitted for each."""
        monkeypatch.chdir(tmp_path)
        engine = SimulationEngine(num_agents=1, use_llm=False, max_ticks=1, world_seed=42)

        # A crafting action that will return derived_innovations in the oracle result
        craft_action = {
            "action": "make_knife",
            "requires": {"items": {"stone": 1}},
        }

        derived_result = {
            "success": True,
            "message": "Crafted knife",
            "effects": {"energy": -5, "hunger": 0, "life": 0},
            "derived_innovations": [
                {
                    "attempt": {
                        "new_action_name": "cut_branches",
                        "description": "cut branches from a tree",
                        "requires": {"items": {"stone_knife": 1}},
                        "produces": {"branches": 2},
                    },
                    "result": {
                        "success": True,
                        "name": "cut_branches",
                        "category": "CRAFTING",
                        "reason_code": "INNOVATION_APPROVED",
                    },
                    "origin_item": "stone_knife",
                    "discovery_mode": "auto",
                    "trigger_action": "make_knife",
                }
            ],
        }

        with (
            patch.object(engine.agents[0], "decide_action", return_value=craft_action),
            patch.object(engine.oracle, "resolve_action", return_value=derived_result),
        ):
            engine.run()

        events = _read_events(engine.event_emitter.run_dir)
        attempts = [
            e for e in events
            if e["event_type"] == "innovation_attempt"
            and e["payload"].get("name") == "cut_branches"
        ]
        validated = [
            e for e in events
            if e["event_type"] == "innovation_validated"
            and e["payload"].get("name") == "cut_branches"
        ]
        assert len(attempts) == 1
        assert len(validated) == 1
        # Check origin metadata is present in validated event
        assert validated[0]["payload"]["origin_item"] == "stone_knife"
        assert validated[0]["payload"]["discovery_mode"] == "auto"
        assert validated[0]["payload"]["trigger_action"] == "make_knife"

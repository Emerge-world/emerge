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

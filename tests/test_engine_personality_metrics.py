"""Integration tests for personality metrics wiring in SimulationEngine."""

import json
from pathlib import Path

from simulation.engine import SimulationEngine


def _read_events(run_dir: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]


def _make_engine(tmp_path, monkeypatch, agents=2, ticks=2) -> SimulationEngine:
    monkeypatch.chdir(tmp_path)
    return SimulationEngine(num_agents=agents, use_llm=False, max_ticks=ticks, world_seed=42)


class TestEnginePersonalityEventWiring:
    def test_run_start_includes_initial_agent_profiles(self, tmp_path, monkeypatch):
        engine = _make_engine(tmp_path, monkeypatch, agents=2, ticks=1)
        engine.run()

        run_start = next(
            event
            for event in _read_events(engine.event_emitter.run_dir)
            if event["event_type"] == "run_start"
        )
        profiles = run_start["payload"]["config"]["agent_profiles"]

        assert len(profiles) == 2
        assert {profile["name"] for profile in profiles} == {agent.name for agent in engine.agents}
        assert set(profiles[0]["personality"].keys()) == {
            "courage",
            "curiosity",
            "patience",
            "sociability",
        }

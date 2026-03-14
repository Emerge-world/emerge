import json
from pathlib import Path
from unittest.mock import patch

from simulation.engine import SimulationEngine


def _read_events(run_dir: Path) -> list[dict]:
    path = run_dir / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _read_agent_log(engine: SimulationEngine, agent_name: str) -> str:
    path = Path(engine.sim_logger.run_dir) / "agents" / f"{agent_name}.md"
    return path.read_text()


def _make_engine(tmp_path, monkeypatch) -> SimulationEngine:
    monkeypatch.chdir(tmp_path)
    return SimulationEngine(num_agents=1, use_llm=False, max_ticks=2, world_seed=42)


def test_engine_emits_subgoal_completed(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    planning_trace = {"subgoal_completed": {"description": "move toward fruit"}}
    action = {
        "action": "move",
        "direction": "east",
        "reason": "following plan",
        "_planning_trace": planning_trace,
    }

    with patch.object(engine.agents[0], "decide_action", return_value=action):
        engine.run()

    events = _read_events(engine.event_emitter.run_dir)
    assert "subgoal_completed" in [event["event_type"] for event in events]


def test_engine_logs_planner_call_to_agent_file(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    action = {
        "action": "move",
        "direction": "east",
        "reason": "following plan",
        "_planning_trace": {
            "plan_created": {"goal": "stabilize food"},
            "planner_llm": {
                "system_prompt": "planner system",
                "user_prompt": "planner prompt",
                "raw_response": '{"goal":"stabilize food"}',
                "parsed_plan": {"goal": "stabilize food", "subgoals": []},
            },
        },
    }
    with patch.object(engine.agents[0], "decide_action", return_value=action):
        engine.run()

    content = _read_agent_log(engine, engine.agents[0].name)
    assert "### Planner" in content
    assert "planner prompt" in content


def test_engine_does_not_log_planner_call_without_trace(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    action = {"action": "move", "direction": "east", "reason": "following plan"}
    with patch.object(engine.agents[0], "decide_action", return_value=action):
        engine.run()

    content = _read_agent_log(engine, engine.agents[0].name)
    assert "### Planner" not in content

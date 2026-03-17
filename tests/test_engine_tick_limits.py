import json
import re

from simulation.engine import SimulationEngine


def _read_events(run_dir):
    path = run_dir / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_finite_engine_stops_at_requested_tick(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("simulation.engine.TICK_DELAY_SECONDS", 0)
    monkeypatch.setattr("simulation.engine.MetricsBuilder.build", lambda self: None)
    monkeypatch.setattr("simulation.engine.EBSBuilder.build", lambda self: None)

    engine = SimulationEngine(
        num_agents=1,
        use_llm=False,
        max_ticks=2,
        world_seed=42,
        run_digest=False,
    )

    engine.run()

    assert engine.current_tick == 2


def test_infinite_engine_runs_until_extinction_and_counts_exact_ticks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("simulation.engine.TICK_DELAY_SECONDS", 0)
    monkeypatch.setattr("simulation.engine.MetricsBuilder.build", lambda self: None)
    monkeypatch.setattr("simulation.engine.EBSBuilder.build", lambda self: None)

    engine = SimulationEngine(
        num_agents=1,
        use_llm=False,
        max_ticks=None,
        world_seed=42,
        run_digest=False,
    )
    seen_ticks = []

    def fake_run_tick(tick, alive_agents):
        seen_ticks.append(tick)
        if tick == 73:
            alive_agents[0].alive = False

    monkeypatch.setattr(engine, "_run_tick", fake_run_tick)

    engine.run()

    assert seen_ticks[:3] == [1, 2, 3]
    assert seen_ticks[-1] == 73
    assert engine.current_tick == 73

    run_end = next(
        ev for ev in _read_events(engine.event_emitter.run_dir)
        if ev["event_type"] == "run_end"
    )
    assert run_end["payload"]["total_ticks"] == 73


# ------------------------------------------------------------------ #
# Run ID format
# ------------------------------------------------------------------ #

_RUN_ID_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_(s\d+|unseeded)_a\d+_[0-9a-f]{8}$"
)


def test_run_id_format_seeded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = SimulationEngine(num_agents=2, use_llm=False, max_ticks=0, world_seed=42, run_digest=False)
    assert _RUN_ID_PATTERN.match(engine.run_id), f"Bad run_id format: {engine.run_id}"
    assert "_s42_" in engine.run_id
    assert "_a2_" in engine.run_id


def test_run_id_format_unseeded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = SimulationEngine(num_agents=1, use_llm=False, max_ticks=0, world_seed=None, run_digest=False)
    assert _RUN_ID_PATTERN.match(engine.run_id), f"Bad run_id format: {engine.run_id}"
    assert "_unseeded_" in engine.run_id


def test_run_id_matches_directory_and_meta(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("simulation.engine.TICK_DELAY_SECONDS", 0)
    monkeypatch.setattr("simulation.engine.MetricsBuilder.build", lambda self: None)
    monkeypatch.setattr("simulation.engine.EBSBuilder.build", lambda self: None)
    engine = SimulationEngine(num_agents=1, use_llm=False, max_ticks=1, world_seed=7, run_digest=False)
    engine.run()

    run_dir = engine.event_emitter.run_dir
    assert run_dir.name == engine.run_id

    meta = json.loads((run_dir / "meta.json").read_text())
    assert meta["run_id"] == engine.run_id

    for ev in _read_events(run_dir):
        assert ev["run_id"] == engine.run_id

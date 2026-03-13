import json

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

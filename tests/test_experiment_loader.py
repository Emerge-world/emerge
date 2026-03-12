import json
from pathlib import Path

from simulation.experiment_loader import load_run_metrics


def _write_events(run_dir: Path, events: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = "\n".join(json.dumps(event) for event in events) + "\n"
    (run_dir / "events.jsonl").write_text(lines, encoding="utf-8")


def _minimal_events() -> list[dict]:
    return [
        {
            "run_id": "test-run",
            "tick": 0,
            "sim_time": None,
            "event_type": "run_start",
            "agent_id": None,
            "payload": {"config": {"agent_names": ["Ada"]}},
        },
        {
            "run_id": "test-run",
            "tick": 1,
            "sim_time": {"day": 1, "hour": 6},
            "event_type": "agent_decision",
            "agent_id": "Ada",
            "payload": {"parsed_action": {"action": "move"}, "parse_ok": True},
        },
        {
            "run_id": "test-run",
            "tick": 1,
            "sim_time": {"day": 1, "hour": 6},
            "event_type": "oracle_resolution",
            "agent_id": "Ada",
            "payload": {"success": True},
        },
        {
            "run_id": "test-run",
            "tick": 1,
            "sim_time": {"day": 1, "hour": 6},
            "event_type": "agent_state",
            "agent_id": "Ada",
            "payload": {"life": 100, "hunger": 0, "energy": 100, "alive": True},
        },
        {
            "run_id": "test-run",
            "tick": 1,
            "sim_time": {"day": 1, "hour": 6},
            "event_type": "run_end",
            "agent_id": None,
            "payload": {"survivors": ["Ada"], "total_ticks": 1},
        },
    ]


def test_load_run_metrics_reads_summary_when_present(tmp_path: Path):
    run_dir = tmp_path / "run_a"
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True)
    (metrics_dir / "summary.json").write_text(
        json.dumps(
            {
                "agents": {"survival_rate": 0.5},
                "actions": {"oracle_success_rate": 0.8},
            }
        ),
        encoding="utf-8",
    )

    result = load_run_metrics(run_dir)

    assert result.summary["agents"]["survival_rate"] == 0.5
    assert result.rebuilt is False
    assert result.invalid is False


def test_load_run_metrics_rebuilds_when_summary_missing(tmp_path: Path):
    run_dir = tmp_path / "run_b"
    _write_events(run_dir, _minimal_events())

    result = load_run_metrics(run_dir)

    assert result.summary["agents"]["survival_rate"] == 1.0
    assert result.rebuilt is True
    assert result.invalid is False


def test_load_run_metrics_marks_run_invalid_without_artifacts(tmp_path: Path):
    run_dir = tmp_path / "run_c"
    run_dir.mkdir()

    result = load_run_metrics(run_dir)

    assert result.invalid is True
    assert result.summary == {}

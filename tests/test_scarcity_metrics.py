"""Tests for simulation/scarcity_metrics.py."""

import json
from pathlib import Path

from simulation.scarcity_metrics import ScarcityMetricsBuilder


def _write_events(run_dir: Path, events: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = "\n".join(json.dumps(event) for event in events) + "\n"
    (run_dir / "events.jsonl").write_text(lines, encoding="utf-8")


def test_build_writes_scarcity_json(tmp_path: Path):
    run_dir = tmp_path / "run"
    _write_events(
        run_dir,
        [
            {
                "run_id": "r1",
                "tick": 0,
                "event_type": "run_start",
                "agent_id": None,
                "payload": {
                    "config": {
                        "agent_names": ["Ada", "Bruno"],
                    }
                },
            },
            {
                "run_id": "r1",
                "tick": 1,
                "event_type": "agent_state",
                "agent_id": "Ada",
                "payload": {"alive": True, "hunger": 30, "life": 90, "energy": 70},
            },
            {
                "run_id": "r1",
                "tick": 1,
                "event_type": "agent_state",
                "agent_id": "Bruno",
                "payload": {"alive": True, "hunger": 50, "life": 80, "energy": 60},
            },
            {
                "run_id": "r1",
                "tick": 1,
                "event_type": "resource_consumed",
                "agent_id": "Ada",
                "payload": {"resource_type": "fruit", "position": [1, 2], "quantity": 1},
            },
            {
                "run_id": "r1",
                "tick": 2,
                "event_type": "agent_state",
                "agent_id": "Ada",
                "payload": {"alive": True, "hunger": 40, "life": 85, "energy": 65},
            },
            {
                "run_id": "r1",
                "tick": 2,
                "event_type": "agent_state",
                "agent_id": "Bruno",
                "payload": {"alive": False, "hunger": 100, "life": 0, "energy": 0},
            },
            {
                "run_id": "r1",
                "tick": 2,
                "event_type": "resource_regenerated",
                "agent_id": None,
                "payload": {"resource_type": "fruit", "position": [1, 2], "quantity": 2},
            },
            {
                "run_id": "r1",
                "tick": 2,
                "event_type": "run_end",
                "agent_id": None,
                "payload": {"survivors": ["Ada"], "total_ticks": 2},
            },
        ],
    )

    ScarcityMetricsBuilder(run_dir).build()

    data = json.loads((run_dir / "metrics" / "scarcity.json").read_text())
    assert data["run_id"] == "r1"
    assert data["survival_auc"] == 0.75
    assert data["starvation_pressure"] == 0.43
    assert data["food_conversion_efficiency"] == 3.0
    assert data["food_consumed"]["fruit"] == 1
    assert data["food_regenerated"]["fruit"] == 2
    assert data["first_food_tick"] == 1


def test_build_is_noop_without_events(tmp_path: Path):
    ScarcityMetricsBuilder(tmp_path / "missing-run").build()

    assert not (tmp_path / "missing-run" / "metrics" / "scarcity.json").exists()

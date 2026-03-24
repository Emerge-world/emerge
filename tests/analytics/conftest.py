import json
import pathlib
import pytest
from fastapi.testclient import TestClient
from dashboard.analytics.backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def tmp_runs(tmp_path):
    """Create a minimal run directory tree for testing."""
    run_id = "2099-01-01_00-00-00_s42_a2_test1234"
    run_dir = tmp_path / "runs" / run_id
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True)

    meta = {
        "run_id": run_id, "seed": 42, "width": 10, "height": 10,
        "max_ticks": 5, "agent_count": 2, "agent_names": ["Alice", "Bob"],
        "agent_model_id": "none", "oracle_model_id": "none",
        "git_commit": "abc123", "created_at": "2099-01-01T00:00:00",
        "prompt_hashes": {}, "precedents_file": None,
    }
    (run_dir / "meta.json").write_text(json.dumps(meta))

    events = [
        {"run_id": run_id, "seed": 42, "tick": 1, "sim_time": {"day": 1, "hour": 6},
         "event_type": "agent_decision", "agent_id": "Alice",
         "payload": {"parsed_action": {"action": "move", "direction": "north", "reason": "exploring"},
                     "parse_ok": True, "action_origin": "base"}},
        {"run_id": run_id, "seed": 42, "tick": 1, "sim_time": {"day": 1, "hour": 6},
         "event_type": "agent_state", "agent_id": "Alice",
         "payload": {"life": 90, "hunger": 20, "energy": 80, "pos": [3, 4], "alive": True,
                     "inventory": {}, "memory_semantic": 0}},
        {"run_id": run_id, "seed": 42, "tick": 2, "sim_time": {"day": 1, "hour": 12},
         "event_type": "innovation_validated", "agent_id": "Bob",
         "payload": {"name": "forage_deep", "approved": True, "category": "GATHERING",
                     "reason_code": "INNOVATION_APPROVED",
                     "requires": {"tile": "forest", "min_energy": 10, "items": {}},
                     "produces": {"berries": 3}}},
        {"run_id": run_id, "seed": 42, "tick": 3, "sim_time": {"day": 1, "hour": 18},
         "event_type": "agent_state", "agent_id": "Alice",
         "payload": {"life": 0, "hunger": 100, "energy": 0, "pos": [3, 4], "alive": False,
                     "inventory": {}, "memory_semantic": 0}},
    ]
    (run_dir / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))

    summary = {
        "run_id": run_id, "total_ticks": 5,
        "agents": {"initial_count": 2, "final_survivors": ["Bob"], "deaths": 1, "survival_rate": 0.5},
        "actions": {"total": 3, "by_type": {"move": 2, "eat": 1},
                    "oracle_success_rate": 1.0, "parse_fail_rate": 0.0},
        "innovations": {"attempts": 1, "approved": 1, "rejected": 0, "used": 0,
                        "approval_rate": 1.0, "realization_rate": 0.0},
        "personality_survival": {"method": "pearson_correlation", "lifespan_unit": "ticks",
                                  "sample_size": 2, "trait_correlations": {"courage": 0.5},
                                  "best_trait": "courage", "best_correlation": 0.5},
    }
    (metrics_dir / "summary.json").write_text(json.dumps(summary))

    ebs = {
        "run_id": run_id, "ebs": 62.5,
        "components": {
            "novelty":     {"score": 75.0, "weight": 0.25, "sub_scores": {}},
            "utility":     {"score": 50.0, "weight": 0.17, "sub_scores": {}},
            "realization": {"score": 40.0, "weight": 0.17, "sub_scores": {}},
            "stability":   {"score": 80.0, "weight": 0.13, "sub_scores": {}},
            "autonomy":    {"score": 60.0, "weight": 0.13, "sub_scores": {}},
            "longevity":   {"score": 55.0, "weight": 0.15, "sub_scores": {}},
        },
    }
    (metrics_dir / "ebs.json").write_text(json.dumps(ebs))

    timeseries = [
        {"tick": 1, "sim_time": {"day": 1, "hour": 6}, "alive": 2, "mean_life": 90.0,
         "mean_hunger": 20.0, "mean_energy": 80.0, "deaths": 0, "actions": 1,
         "innovations_attempted": 0, "innovations_approved": 0},
        {"tick": 2, "sim_time": {"day": 1, "hour": 12}, "alive": 2, "mean_life": 85.0,
         "mean_hunger": 25.0, "mean_energy": 75.0, "deaths": 0, "actions": 1,
         "innovations_attempted": 1, "innovations_approved": 1},
        {"tick": 3, "sim_time": {"day": 1, "hour": 18}, "alive": 1, "mean_life": 70.0,
         "mean_hunger": 40.0, "mean_energy": 60.0, "deaths": 1, "actions": 1,
         "innovations_attempted": 0, "innovations_approved": 0},
    ]
    (metrics_dir / "timeseries.jsonl").write_text("\n".join(json.dumps(t) for t in timeseries))

    return tmp_path, run_id

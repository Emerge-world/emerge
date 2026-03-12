import json
from pathlib import Path

from simulation.decision_builder import build_decision_artifact


def test_build_decision_artifact_writes_output(tmp_path: Path):
    suite = {
        "name": "gate_inventory",
        "metrics": {
            "primary": ["survival_rate"],
            "secondary": ["oracle_success_rate"],
        },
        "policy": {"max_invalid_run_rate": 0.25, "min_effect_size": 0.02},
    }
    baseline = {
        "name": "baseline",
        "run_count": 2,
        "invalid_run_rate": 0.0,
        "metrics": {
            "survival_rate": {"mean": 0.5},
            "oracle_success_rate": {"mean": 0.8},
        },
    }
    candidate = {
        "name": "candidate",
        "run_count": 2,
        "invalid_run_rate": 0.0,
        "metrics": {
            "survival_rate": {"mean": 0.65},
            "oracle_success_rate": {"mean": 0.82},
        },
    }
    output_path = tmp_path / "decision.json"

    build_decision_artifact(suite, baseline, candidate, output_path)

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["decision"] == "promote"

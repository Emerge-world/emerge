from pathlib import Path

import experiment_toolkit
from experiment_toolkit import _load_suites, build_parser, execute_suite
from simulation.experiment_loader import RunMetricsResult


def test_cli_accepts_suite_config_and_output_dir():
    parser = build_parser()
    args = parser.parse_args(["suite.yaml", "--output-dir", "artifacts"])

    assert args.config == "suite.yaml"
    assert args.output_dir == "artifacts"


def test_execute_suite_writes_decision_and_priorities(tmp_path, monkeypatch):
    suite = _load_suites(Path("tests/fixtures/experiments/gate_inventory_suite.yaml"))[0]

    def fake_run_cohort(_suite, cohort, _repo_root):
        survival_rate = 0.5 if cohort.name == "baseline" else 0.7
        return [
            RunMetricsResult(
                run_dir=tmp_path / cohort.name,
                summary={
                    "agents": {"survival_rate": survival_rate},
                    "actions": {"oracle_success_rate": 0.8},
                },
                invalid=False,
            )
        ]

    monkeypatch.setattr(experiment_toolkit, "_run_cohort", fake_run_cohort)

    execute_suite(suite, tmp_path / "artifacts", tmp_path)

    assert (tmp_path / "artifacts" / suite.name / "priorities.json").exists()
    assert (
        tmp_path / "artifacts" / suite.name / "decisions" / "candidate.json"
    ).exists()

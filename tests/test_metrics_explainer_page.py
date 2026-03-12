import json
from pathlib import Path


DOCS_DIR = Path("docs/metrics-explainer")
FIXTURES_DIR = DOCS_DIR / "fixtures"


class TestExplainerFixtures:
    def test_fixture_files_exist(self):
        for rel in (
            "sample_summary.json",
            "sample_timeseries.jsonl",
            "sample_ebs.json",
        ):
            assert (FIXTURES_DIR / rel).exists(), rel

    def test_summary_fixture_matches_metrics_shape(self):
        summary = json.loads((FIXTURES_DIR / "sample_summary.json").read_text())
        assert set(summary.keys()) == {"run_id", "total_ticks", "agents", "actions", "innovations"}
        assert set(summary["agents"].keys()) == {
            "initial_count",
            "final_survivors",
            "deaths",
            "survival_rate",
        }
        assert set(summary["actions"].keys()) == {
            "total",
            "by_type",
            "oracle_success_rate",
            "parse_fail_rate",
        }
        assert set(summary["innovations"].keys()) == {
            "attempts",
            "approved",
            "rejected",
            "used",
            "approval_rate",
            "realization_rate",
        }

    def test_timeseries_fixture_rows_match_metrics_shape(self):
        lines = (FIXTURES_DIR / "sample_timeseries.jsonl").read_text().splitlines()
        assert lines
        row = json.loads(lines[0])
        assert set(row.keys()) == {
            "tick",
            "sim_time",
            "alive",
            "mean_life",
            "mean_hunger",
            "mean_energy",
            "deaths",
            "actions",
            "oracle_success_rate",
            "innovations_attempted",
            "innovations_approved",
        }

    def test_ebs_fixture_matches_builder_shape(self):
        ebs = json.loads((FIXTURES_DIR / "sample_ebs.json").read_text())
        assert set(ebs.keys()) == {"run_id", "ebs", "components", "innovations"}
        assert set(ebs["components"].keys()) == {
            "novelty",
            "utility",
            "realization",
            "stability",
            "autonomy",
        }
        assert ebs["components"]["autonomy"]["sub_scores"]["self_generated_subgoals"] == 0.0

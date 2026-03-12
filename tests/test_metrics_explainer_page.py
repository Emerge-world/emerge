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


class TestExplainerScaffold:
    def test_entry_files_exist(self):
        for rel in ("index.html", "styles.css", "script.js"):
            assert (DOCS_DIR / rel).exists(), rel

    def test_core_sections_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        for section_id in (
            "hero",
            "flow",
            "population-metrics",
            "time-based-metrics",
            "ebs-score",
            "limits",
        ):
            assert f'id="{section_id}"' in html

    def test_run_explorer_controls_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert 'id="artifact-source-form"' in html
        assert 'name="artifact-mode"' in html
        assert 'id="artifact-path"' in html
        assert 'id="artifact-status"' in html


class TestExplainerContent:
    def test_primary_heading_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert "How Emerge Measures Population Behavior" in html

    def test_population_formulas_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert "Survival rate = final survivors / initial population" in html
        assert "Oracle success rate = successful oracle resolutions / total oracle resolutions" in html
        assert "Innovation approval rate = approved innovations / innovation attempts" in html
        assert "Innovation realization rate = approved innovations later used / approved innovations" in html

    def test_ebs_formula_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert "0.30 * Novelty" in html
        assert "0.20 * Utility" in html
        assert "0.20 * Realization" in html
        assert "0.15 * Stability" in html
        assert "0.15 * Autonomy" in html

    def test_detailed_ebs_component_formulas_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert (
            "Novelty = 100 * (0.40 * approval_rate + 0.30 * category_diversity + 0.30 * structural_originality)"
            in html
        )
        assert (
            "Utility = 100 * (0.50 * direct_state_improvement + 0.30 * future_option_value + 0.20 * execution_success_rate)"
            in html
        )
        assert "Realization = 100 * (0.60 * use_rate + 0.40 * execution_success_rate)" in html
        assert "Stability = clamp(100 - 40 * false_knowledge_rate - 30 * invalid_action_rate, 0, 100)" in html
        assert (
            "Autonomy = 100 * (0.40 * proactive_resource_acquisition + 0.30 * environment_contingent_innovation)"
            in html
        )

    def test_ebs_subscore_explanations_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert "category_diversity = distinct categories / 4" in html
        assert "welfare = life + energy - hunger" in html
        assert "5-tick window before and after first use" in html
        assert "invalid_action_rate = parse fails / total agent_decision events" in html
        assert "environment_contingent_innovation = innovation attempts with hunger > 60 / total innovation attempts" in html

    def test_limits_copy_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert "self_generated_subgoals" in html
        assert "0.0" in html
        assert "Weights & Biases" in html
        assert "optional observer" in html
        assert "not included in the current autonomy formula" in html


class TestLoaderHooks:
    def test_script_contains_loader_entrypoints(self):
        script = (DOCS_DIR / "script.js").read_text(encoding="utf-8")
        assert "async function loadArtifacts" in script
        assert "async function loadSummary" in script
        assert "async function loadTimeseries" in script
        assert "async function loadEbs" in script
        assert "function renderArtifactStatus" in script

    def test_script_handles_partial_failures(self):
        script = (DOCS_DIR / "script.js").read_text(encoding="utf-8")
        assert "Promise.allSettled" in script
        assert "summary:" in script
        assert "timeseries:" in script
        assert "ebs:" in script
        assert "unavailable" in script.lower()

    def test_index_contains_render_targets(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        for element_id in (
            "summary-cards",
            "timeseries-panel",
            "ebs-panels",
            "artifact-field-details",
        ):
            assert f'id="{element_id}"' in html


class TestPresentationHooks:
    def test_index_contains_interactive_view_toggles(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert 'data-view="meaning"' in html
        assert 'data-view="run"' in html
        assert "Show data source" in html

    def test_styles_define_visual_tokens(self):
        css = (DOCS_DIR / "styles.css").read_text(encoding="utf-8")
        for token in (
            "--page-bg",
            "--panel-bg",
            "--novelty",
            "--utility",
            "--realization",
            "--stability",
            "--autonomy",
        ):
            assert token in css

    def test_script_contains_renderers(self):
        script = (DOCS_DIR / "script.js").read_text(encoding="utf-8")
        assert "function renderSummaryCards" in script
        assert "function renderTimeseriesCharts" in script
        assert "function renderEbsPanels" in script
        assert "function renderMetricViewToggle" in script


class TestDocumentationConsistency:
    def test_cornerstone_mentions_docs_explainer(self):
        decision_log = Path(
            "project-cornerstone/00-master-plan/DECISION_LOG.md"
        ).read_text(encoding="utf-8")
        visualization = Path(
            "project-cornerstone/09-visualization/visualization_context.md"
        ).read_text(encoding="utf-8")
        assert "interactive metrics explainer" in decision_log.lower()
        assert "docs/metrics-explainer/" in visualization

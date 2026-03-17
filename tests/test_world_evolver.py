"""
Tests for WorldEvolver and RunAnalyzer.
"""

import json
import math
import pytest
import yaml
from pathlib import Path

from simulation.world_schema import WorldSchema
from simulation.evolution.run_analyzer import RunAnalyzer, RunSummary
from simulation.evolution.world_evolver import WorldEvolver, MockEvolver


@pytest.fixture
def base_schema() -> WorldSchema:
    return WorldSchema.load_default()


# ---------------------------------------------------------------------------
# RunAnalyzer tests
# ---------------------------------------------------------------------------

class TestRunAnalyzer:
    def _make_run_dir(self, tmp_path: Path, run_id: str, ebs: float, survival: float, ticks: int) -> Path:
        run_dir = tmp_path / run_id
        metrics = run_dir / "metrics"
        metrics.mkdir(parents=True)

        (metrics / "ebs.json").write_text(json.dumps({
            "run_id": run_id,
            "ebs": ebs,
            "components": {
                "novelty": {"score": ebs * 0.8, "weight": 0.25},
                "utility": {"score": ebs * 0.5, "weight": 0.17},
                "longevity": {"score": ebs * 1.2, "weight": 0.17},
            },
        }))
        (metrics / "summary.json").write_text(json.dumps({
            "run_id": run_id,
            "total_ticks": ticks,
            "agents": {"initial_count": 3, "final_survivors": [], "deaths": 3, "survival_rate": survival},
            "actions": {
                "total": 100,
                "by_type": {"move": 50, "eat": 30, "rest": 20},
                "oracle_success_rate": 0.8,
                "parse_fail_rate": 0.0,
            },
            "innovations": {"attempts": 2, "approved": 1, "rejected": 1, "approval_rate": 0.5},
        }))
        return run_dir

    def test_analyze_single_run(self, tmp_path):
        run_dir = self._make_run_dir(tmp_path, "run1", ebs=50.0, survival=0.33, ticks=200)
        analyzer = RunAnalyzer([run_dir])
        summary = analyzer.analyze()
        assert summary.mean_ebs == pytest.approx(50.0)
        assert summary.std_ebs == pytest.approx(0.0)
        assert summary.mean_survival_rate == pytest.approx(0.33)
        assert summary.mean_ticks == pytest.approx(200.0)

    def test_analyze_multiple_runs(self, tmp_path):
        d1 = self._make_run_dir(tmp_path, "run1", ebs=40.0, survival=0.3, ticks=150)
        d2 = self._make_run_dir(tmp_path, "run2", ebs=60.0, survival=0.7, ticks=250)
        analyzer = RunAnalyzer([d1, d2])
        summary = analyzer.analyze()
        assert summary.mean_ebs == pytest.approx(50.0)
        assert summary.std_ebs > 0
        assert summary.mean_survival_rate == pytest.approx(0.5)
        assert summary.mean_ticks == pytest.approx(200.0)

    def test_analyze_missing_dir(self, tmp_path):
        """Non-existent dir should be handled gracefully."""
        run_dir = self._make_run_dir(tmp_path, "run1", ebs=50.0, survival=0.5, ticks=200)
        missing = tmp_path / "nonexistent"
        analyzer = RunAnalyzer([run_dir, missing])
        summary = analyzer.analyze()
        # Should still return data from the valid run
        assert summary.mean_ebs == pytest.approx(50.0)

    def test_analyze_empty_list(self):
        analyzer = RunAnalyzer([])
        summary = analyzer.analyze()
        assert summary.mean_ebs == 0.0
        assert summary.run_ids == []

    def test_ebs_components_averaged(self, tmp_path):
        d1 = self._make_run_dir(tmp_path, "run1", ebs=40.0, survival=0.3, ticks=100)
        d2 = self._make_run_dir(tmp_path, "run2", ebs=60.0, survival=0.7, ticks=200)
        summary = RunAnalyzer([d1, d2]).analyze()
        assert "novelty" in summary.ebs_components
        novelty = summary.ebs_components["novelty"]["score"]
        # d1 novelty = 40*0.8=32, d2 novelty = 60*0.8=48 → avg 40
        assert novelty == pytest.approx(40.0)

    def test_prompt_text_format(self, tmp_path):
        run_dir = self._make_run_dir(tmp_path, "run1", ebs=55.0, survival=0.5, ticks=200)
        summary = RunAnalyzer([run_dir]).analyze()
        text = summary.to_prompt_text()
        assert "Mean EBS: 55.0" in text
        assert "move" in text
        assert "EBS COMPONENTS" in text

    def test_action_distribution_accumulated(self, tmp_path):
        d1 = self._make_run_dir(tmp_path, "run1", ebs=50.0, survival=0.5, ticks=100)
        d2 = self._make_run_dir(tmp_path, "run2", ebs=50.0, survival=0.5, ticks=100)
        summary = RunAnalyzer([d1, d2]).analyze()
        assert summary.action_distribution["move"] == 100  # 50 + 50


# ---------------------------------------------------------------------------
# WorldEvolver / MockEvolver tests
# ---------------------------------------------------------------------------

class TestMockEvolver:
    def test_mock_produces_n_variants(self, base_schema):
        evolver = MockEvolver()
        variants = evolver.mutate(base_schema, RunSummary(), n=3)
        assert len(variants) == 3

    def test_mock_increments_generation(self, base_schema):
        evolver = MockEvolver()
        variants = evolver.mutate(base_schema, RunSummary(), n=2)
        for v in variants:
            assert v.metadata["generation"] == base_schema.metadata["generation"] + 1

    def test_mock_sets_parent(self, base_schema):
        evolver = MockEvolver()
        variants = evolver.mutate(base_schema, RunSummary(), n=2)
        for v in variants:
            assert v.metadata["parent"] == base_schema.metadata["name"]

    def test_mock_records_mutations(self, base_schema):
        evolver = MockEvolver()
        variants = evolver.mutate(base_schema, RunSummary(), n=2)
        for v in variants:
            assert len(v.metadata["mutations_applied"]) > 0

    def test_mock_produces_valid_schemas(self, base_schema):
        evolver = MockEvolver()
        variants = evolver.mutate(base_schema, RunSummary(), n=3)
        for v in variants:
            # All required sections must be present
            assert v.tiles is not None
            assert v.resources is not None
            assert v.agents is not None

    def test_mock_zero_variants(self, base_schema):
        evolver = MockEvolver()
        variants = evolver.mutate(base_schema, RunSummary(), n=0)
        assert variants == []

    def test_mock_variants_are_distinct(self, base_schema):
        evolver = MockEvolver()
        variants = evolver.mutate(base_schema, RunSummary(), n=3)
        names = [v.metadata["name"] for v in variants]
        assert len(set(names)) == 3  # all distinct names


class TestWorldEvolverExtractYaml:
    def test_extracts_yaml_code_fence(self):
        text = "Here is the schema:\n```yaml\nschema_version: '1.0'\n```\nDone."
        result = WorldEvolver._extract_yaml(text)
        assert "schema_version" in result

    def test_extracts_plain_code_fence(self):
        text = "```\nschema_version: '1.0'\n```"
        result = WorldEvolver._extract_yaml(text)
        assert "schema_version" in result

    def test_extracts_bare_yaml(self):
        text = "schema_version: '1.0'\nmetadata:\n  name: test"
        result = WorldEvolver._extract_yaml(text)
        assert "schema_version" in result

    def test_empty_response(self):
        result = WorldEvolver._extract_yaml("")
        assert result == ""


class TestWorldEvolverParseAndValidate:
    def test_valid_schema_roundtrip(self, base_schema):
        evolver = WorldEvolver(llm=None)
        yaml_text = base_schema.to_yaml_str()
        variant = evolver._parse_and_validate(yaml_text, base_schema, attempt_index=0)
        assert variant is not None
        assert variant.metadata["generation"] == base_schema.metadata["generation"] + 1

    def test_invalid_yaml_returns_none(self, base_schema):
        evolver = WorldEvolver(llm=None)
        result = evolver._parse_and_validate("{{not yaml: [}", base_schema, 0)
        assert result is None

    def test_missing_required_field_returns_none(self, base_schema):
        try:
            import jsonschema  # noqa: F401
        except ImportError:
            pytest.skip("jsonschema not installed")
        evolver = WorldEvolver(llm=None)
        data = base_schema.to_dict()
        del data["tiles"]
        result = evolver._parse_and_validate(yaml.dump(data), base_schema, 0)
        assert result is None

    def test_metadata_defaults_applied(self, base_schema):
        evolver = WorldEvolver(llm=None)
        data = base_schema.to_dict()
        data["metadata"]["generation"] = 5
        raw = yaml.dump(data)
        variant = evolver._parse_and_validate(raw, base_schema, attempt_index=2)
        assert variant is not None
        # Generation should be parent+1
        assert variant.metadata["generation"] == base_schema.metadata["generation"] + 1

    def test_no_llm_returns_none_on_propose(self, base_schema):
        evolver = WorldEvolver(llm=None)
        result = evolver._call_llm("system", "user")
        assert result is None

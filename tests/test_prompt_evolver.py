"""Tests for PromptEvolver: mock evolver, variable safety rejection."""

import pytest

from simulation.evolution.prompt_config import PromptConfig
from simulation.evolution.prompt_evolver import MockPromptEvolver, PromptEvolver
from simulation.evolution.run_analyzer import RunSummary


@pytest.fixture
def baseline_config():
    return PromptConfig.from_disk()


@pytest.fixture
def run_summary():
    return RunSummary()


class TestMockPromptEvolver:
    def test_returns_n_variants_agent(self, baseline_config, run_summary):
        evolver = MockPromptEvolver()
        variants = evolver.mutate(baseline_config, run_summary, n=3, scope="agent")
        assert len(variants) == 3

    def test_returns_n_variants_oracle(self, baseline_config, run_summary):
        evolver = MockPromptEvolver()
        variants = evolver.mutate(baseline_config, run_summary, n=2, scope="oracle")
        assert len(variants) == 2

    def test_agent_mutation_modifies_agent_prompts(self, baseline_config, run_summary):
        evolver = MockPromptEvolver()
        variants = evolver.mutate(baseline_config, run_summary, n=1, scope="agent")
        v = variants[0]
        # Agent prompts should be modified (mock appends a comment)
        for name in baseline_config.agent_prompts:
            if name in v.agent_prompts:
                assert v.agent_prompts[name] != baseline_config.agent_prompts[name]
                break

    def test_oracle_mutation_modifies_oracle_prompts(self, baseline_config, run_summary):
        evolver = MockPromptEvolver()
        variants = evolver.mutate(baseline_config, run_summary, n=1, scope="oracle")
        v = variants[0]
        for name in baseline_config.oracle_prompts:
            if name in v.oracle_prompts:
                assert v.oracle_prompts[name] != baseline_config.oracle_prompts[name]
                break

    def test_agent_mutation_preserves_oracle_prompts(self, baseline_config, run_summary):
        evolver = MockPromptEvolver()
        variants = evolver.mutate(baseline_config, run_summary, n=1, scope="agent")
        v = variants[0]
        assert v.oracle_prompts == baseline_config.oracle_prompts

    def test_oracle_mutation_preserves_agent_prompts(self, baseline_config, run_summary):
        evolver = MockPromptEvolver()
        variants = evolver.mutate(baseline_config, run_summary, n=1, scope="oracle")
        v = variants[0]
        assert v.agent_prompts == baseline_config.agent_prompts

    def test_mock_variants_pass_validation(self, baseline_config, run_summary):
        """Mock mutations append a comment — $variables must still be present."""
        evolver = MockPromptEvolver()
        variants = evolver.mutate(baseline_config, run_summary, n=3, scope="agent")
        for v in variants:
            errors = v.validate_against(baseline_config)
            assert errors == [], f"Validation failed: {errors}"


class TestPromptEvolverVariableSafetyRejection:
    def test_broken_json_returns_empty(self, run_summary):
        """LLM returning garbage should produce no variants (None fallback path)."""
        evolver = PromptEvolver(llm=None)
        baseline = PromptConfig(
            agent_prompts={"system": "Hello $name"},
            oracle_prompts={},
        )
        # With llm=None, _call_llm returns None → all attempts fail
        result = evolver.mutate(baseline, run_summary, n=2, scope="agent")
        assert result == []

    def test_extract_json_valid(self):
        evolver = PromptEvolver(llm=None)
        text = '```json\n{"key": "value"}\n```'
        result = evolver._extract_json(text)
        assert result == {"key": "value"}

    def test_extract_json_bare(self):
        evolver = PromptEvolver(llm=None)
        text = '{"key": "value"}'
        result = evolver._extract_json(text)
        assert result == {"key": "value"}

    def test_extract_json_invalid_returns_none(self):
        evolver = PromptEvolver(llm=None)
        result = evolver._extract_json("this is not json at all")
        assert result is None

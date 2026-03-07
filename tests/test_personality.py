"""Tests for the Personality dataclass."""
import pytest
from simulation.personality import Personality


class TestPersonalityCreation:
    def test_direct_construction(self):
        p = Personality(courage=0.8, curiosity=0.3, patience=0.6, sociability=0.1)
        assert p.courage == 0.8
        assert p.curiosity == 0.3
        assert p.patience == 0.6
        assert p.sociability == 0.1

    def test_random_creates_personality(self):
        p = Personality.random()
        assert isinstance(p, Personality)

    def test_random_traits_in_range(self):
        for _ in range(20):
            p = Personality.random()
            assert 0.0 <= p.courage <= 1.0
            assert 0.0 <= p.curiosity <= 1.0
            assert 0.0 <= p.patience <= 1.0
            assert 0.0 <= p.sociability <= 1.0

    def test_random_produces_variety(self):
        """Different calls should produce different values."""
        values = {Personality.random().courage for _ in range(20)}
        assert len(values) > 1


class TestPersonalityToPrompt:
    def test_to_prompt_is_non_empty(self):
        p = Personality(courage=0.8, curiosity=0.3, patience=0.6, sociability=0.1)
        assert len(p.to_prompt()) > 0

    def test_to_prompt_contains_all_trait_names(self):
        p = Personality(courage=0.8, curiosity=0.3, patience=0.6, sociability=0.1)
        text = p.to_prompt()
        assert "courage" in text.lower()
        assert "curiosity" in text.lower()
        assert "patience" in text.lower()
        assert "sociability" in text.lower()

    def test_to_prompt_contains_numeric_values(self):
        p = Personality(courage=0.80, curiosity=0.30, patience=0.60, sociability=0.10)
        text = p.to_prompt()
        assert "0.80" in text
        assert "0.30" in text
        assert "0.60" in text
        assert "0.10" in text

    def test_to_prompt_high_label(self):
        p = Personality(courage=0.9, curiosity=0.5, patience=0.5, sociability=0.5)
        assert "high" in p.to_prompt().lower()

    def test_to_prompt_very_low_label(self):
        p = Personality(courage=0.1, curiosity=0.5, patience=0.5, sociability=0.5)
        assert "very low" in p.to_prompt().lower()

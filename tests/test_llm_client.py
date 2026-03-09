"""
Tests for LLMClient JSON parsing and repair.
"""

from unittest.mock import MagicMock, patch

import pytest

from simulation.llm_client import LLMClient


class TestGenerateJsonRepair:
    """generate_json recovers from common LLM malformations."""

    def _client_returning(self, raw: str) -> LLMClient:
        client = LLMClient()
        client.generate = MagicMock(return_value=raw)
        return client

    def test_valid_json_parsed_normally(self):
        client = self._client_returning('{"learnings": ["lesson A"]}')
        result = client.generate_json("prompt")
        assert result == {"learnings": ["lesson A"]}

    def test_repairs_split_arrays(self):
        """LLM emits {"learnings": ["A"], ["B"]} — must recover both lessons."""
        malformed = '{"learnings": ["lesson A"], ["lesson B"]}'
        client = self._client_returning(malformed)
        result = client.generate_json("prompt")
        assert result is not None
        assert result.get("learnings") == ["lesson A", "lesson B"]

    def test_repairs_three_split_arrays(self):
        malformed = '{"learnings": ["A"], ["B"], ["C"]}'
        client = self._client_returning(malformed)
        result = client.generate_json("prompt")
        assert result is not None
        assert result.get("learnings") == ["A", "B", "C"]

    def test_returns_none_on_unrecoverable_garbage(self):
        client = self._client_returning("not json at all, no strings")
        result = client.generate_json("prompt")
        assert result is None

    def test_returns_none_on_empty_response(self):
        client = self._client_returning("")
        result = client.generate_json("prompt")
        assert result is None

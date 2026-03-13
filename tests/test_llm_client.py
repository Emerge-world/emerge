"""
Tests for LLMClient structured output generation.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from simulation.llm_client import LLMClient
from simulation.schemas import AgentDecisionResponse, AgentPlanResponse, PhysicalReflectionResponse


class TestGenerateStructured:
    """generate_structured returns typed Pydantic models via vllm json_schema."""

    def _client_with_response(self, content: str) -> LLMClient:
        client = LLMClient()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = content
        client._client = MagicMock()
        client._client.chat.completions.create.return_value = mock_response
        return client

    def test_returns_typed_model_on_valid_json(self):
        payload = '{"action": "move", "reason": "need food", "direction": "north"}'
        client = self._client_with_response(payload)
        result = client.generate_structured("prompt", AgentDecisionResponse)
        assert isinstance(result, AgentDecisionResponse)
        assert result.action == "move"
        assert result.direction == "north"

    def test_optional_fields_default_to_none(self):
        payload = '{"action": "rest", "reason": "tired"}'
        client = self._client_with_response(payload)
        result = client.generate_structured("prompt", AgentDecisionResponse)
        assert result is not None
        assert result.direction is None
        assert result.target is None

    def test_physical_reflection_response(self):
        payload = '{"possible": true, "reason": "terrain is passable", "life_damage": 0}'
        client = self._client_with_response(payload)
        result = client.generate_structured("prompt", PhysicalReflectionResponse)
        assert isinstance(result, PhysicalReflectionResponse)
        assert result.possible is True
        assert result.life_damage == 0

    def test_returns_none_on_connection_error(self):
        client = LLMClient()
        client._client = MagicMock()
        client._client.chat.completions.create.side_effect = Exception("connection refused")
        result = client.generate_structured("prompt", AgentDecisionResponse)
        assert result is None

    def test_last_call_populated_on_success(self):
        payload = '{"action": "eat", "reason": "hungry"}'
        client = self._client_with_response(payload)
        client.generate_structured("my prompt", AgentDecisionResponse, system_prompt="sys")
        assert client.last_call["user_prompt"] == "my prompt"
        assert client.last_call["system_prompt"] == "sys"
        assert client.last_call["raw_response"] == payload

    def test_json_schema_passed_to_api(self):
        client = LLMClient()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"action": "rest", "reason": "ok"}'
        client._client = MagicMock()
        client._client.chat.completions.create.return_value = mock_response
        client.generate_structured("prompt", AgentDecisionResponse)
        call_kwargs = client._client.chat.completions.create.call_args[1]
        assert "response_format" in call_kwargs
        response_format = call_kwargs["response_format"]
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["name"] == "AgentDecisionResponse"
        assert response_format["json_schema"]["schema"] == AgentDecisionResponse.model_json_schema()

    def test_system_prompt_included_in_messages(self):
        client = LLMClient()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"action": "rest", "reason": "ok"}'
        client._client = MagicMock()
        client._client.chat.completions.create.return_value = mock_response
        client.generate_structured("user msg", AgentDecisionResponse, system_prompt="be helpful")
        messages = client._client.chat.completions.create.call_args[1]["messages"]
        assert messages[0] == {"role": "system", "content": "be helpful"}
        assert messages[1] == {"role": "user", "content": "user msg"}

    def test_explicit_max_tokens_overrides_default(self):
        client = LLMClient()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"action": "rest", "reason": "ok"}'
        client._client = MagicMock()
        client._client.chat.completions.create.return_value = mock_response

        client.generate_structured("prompt", AgentDecisionResponse, max_tokens=256)

        call_kwargs = client._client.chat.completions.create.call_args[1]
        assert call_kwargs["max_tokens"] == 256

    def test_decision_schema_caps_reason_length(self):
        schema = AgentDecisionResponse.model_json_schema()

        assert schema["properties"]["reason"]["maxLength"] == 160

    def test_plan_schema_caps_goal_and_rationale_length(self):
        schema = AgentPlanResponse.model_json_schema()

        assert schema["properties"]["goal"]["maxLength"] == 160
        assert schema["properties"]["rationale_summary"]["maxLength"] == 240

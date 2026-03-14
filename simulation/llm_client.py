"""
Client for communicating with vllm (OpenAI-compatible API).
Uses outlines structured_outputs for constrained token generation.
"""

import logging
from typing import TypeVar, Type

from openai import OpenAI
from pydantic import BaseModel

from simulation.config import (
    VLLM_BASE_URL,
    VLLM_MODEL,
    VLLM_API_KEY,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """Wrapper around the vllm OpenAI-compatible API with structured output support."""

    def __init__(self, base_url: str = VLLM_BASE_URL, model: str = VLLM_MODEL):
        self.model = model
        self._client = OpenAI(base_url=base_url, api_key=VLLM_API_KEY)
        # Stores the last call's prompts and raw response for logging
        self.last_call: dict = {}

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: str = "",
        temperature: float = LLM_TEMPERATURE,
        max_tokens: int = LLM_MAX_TOKENS,
    ) -> T | None:
        """Calls vllm with structured_outputs constraint. Returns typed model or None on error."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        self.last_call = {
            "system_prompt": system_prompt,
            "user_prompt": prompt,
            "raw_response": "",
        }

        try:
            logger.debug(f"LLM request to {self.model}: {prompt[:120]}...")
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_model.__name__,
                        "schema": response_model.model_json_schema(),
                    },
                },
                extra_body={
                    "chat_template_kwargs": {"enable_thinking": False},
                },
            )
            choice = response.choices[0]
            raw = choice.message.content or ""
            self.last_call["raw_response"] = raw
            if choice.finish_reason == "length":
                logger.warning(
                    f"LLM response truncated (max_tokens={max_tokens}) for {response_model.__name__}"
                )
                return None
            logger.debug(f"LLM response: {raw[:200]}...")
            # Strip control characters that vllm occasionally injects into string values
            sanitized = "".join(ch for ch in raw if ch >= " " or ch in "\n\r\t")
            # Extract just the JSON object — vllm sometimes appends trailing text
            start = sanitized.find("{")
            end = sanitized.rfind("}") + 1
            if start != -1 and end > start:
                sanitized = sanitized[start:end]
            return response_model.model_validate_json(sanitized)
        except Exception as e:
            logger.error(f"Error calling vllm: {e}")
            return None

    def is_available(self) -> bool:
        """Check if vllm is available."""
        try:
            self._client.models.list()
            return True
        except Exception:
            return False

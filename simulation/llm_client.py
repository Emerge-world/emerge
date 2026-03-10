"""
Client for communicating with vllm (OpenAI-compatible API).
Uses outlines guided_json for constrained token generation.
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
    ) -> T | None:
        """Calls vllm with guided_json constraint. Returns typed model or None on error."""
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
                max_tokens=LLM_MAX_TOKENS,
                extra_body={
                    "guided_json": response_model.model_json_schema(),
                    "chat_template_kwargs": {"enable_thinking": False},
                },
            )
            raw = response.choices[0].message.content or ""
            self.last_call["raw_response"] = raw
            logger.debug(f"LLM response: {raw[:200]}...")
            return response_model.model_validate_json(raw)
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

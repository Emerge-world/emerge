"""
Client for communicating with Ollama (Qwen 2.5-3B).
"""

import json
import re
import requests
import logging


def _repair_learnings_json(text: str) -> dict | None:
    """Recover from split-array malformation: {"learnings": ["A"], ["B"]} → {"learnings": ["A", "B"]}.

    Extracts all quoted string values from any array literals in the text,
    filtering out JSON key names, and reassembles a valid learnings dict.
    """
    strings = re.findall(r'"((?:[^"\\]|\\.)*)"', text)
    lessons = [s for s in strings if s != "learnings" and s.strip()]
    if not lessons:
        return None
    return {"learnings": lessons}

from simulation.config import OLLAMA_BASE_URL, OLLAMA_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS

logger = logging.getLogger(__name__)


class LLMClient:
    """Wrapper around the Ollama API."""

    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = OLLAMA_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model
        # Stores the last call's prompts and raw response for logging
        self.last_call: dict = {}

    def generate(self, prompt: str, system_prompt: str = "", temperature: float = LLM_TEMPERATURE) -> str:
        """
        Send a prompt to Ollama and return the response as text.
        """
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_predict": LLM_MAX_TOKENS,
            },
        }

        try:
            logger.debug(f"LLM request to {self.model}: {prompt[:120]}...")
            response = requests.post(url, json=payload, timeout=250)
            # write the request in a log for debugging
            logger.debug(f"LLM request payload: {payload}")
            response.raise_for_status()
            data = response.json()
            raw = data.get("response", "")
            # Qwen3 CoT: strip <think>...</think> blocks before returning
            result = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            logger.debug(f"LLM response: {result[:200]}...")
            self.last_call = {
                "system_prompt": system_prompt,
                "user_prompt": prompt,
                "raw_response": result,
            }
            return result
        except requests.exceptions.ConnectionError:
            logger.error(f"Cannot connect to Ollama at {self.base_url}. Is it running?")
            self.last_call = {"system_prompt": system_prompt, "user_prompt": prompt, "raw_response": ""}
            return ""
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            self.last_call = {"system_prompt": system_prompt, "user_prompt": prompt, "raw_response": ""}
            return ""

    def generate_json(self, prompt: str, system_prompt: str = "", temperature: float = LLM_TEMPERATURE) -> dict | None:
        """
        Send a prompt and expect a JSON response. Attempts to parse the result.
        """
        full_system = system_prompt + "\n\nIMPORTANT: Respond ONLY with valid JSON. No extra text, no markdown, no code fences."
        raw = self.generate(prompt, system_prompt=full_system, temperature=temperature)

        if not raw:
            return None

        # Try to clean up the response
        cleaned = raw.strip()
        # Remove possible code fences
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        # Find JSON within the response
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start != -1 and end > start:
            cleaned = cleaned[start:end]

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            repaired = _repair_learnings_json(cleaned)
            if repaired is not None:
                return repaired
            logger.warning(f"Could not parse JSON from LLM response: {raw[:300]}")
            return None

    def is_available(self) -> bool:
        """Check if Ollama is available."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

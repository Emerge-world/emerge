"""
PromptEvolver: LLM-driven agent/oracle prompt mutation engine.

Parallel structure to WorldEvolver. Given a PromptConfig and run statistics,
calls an LLM to propose mutated prompt variants and validates $variable safety.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from simulation.evolution.prompt_config import PromptConfig
from simulation.evolution.run_analyzer import RunSummary

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts" / "evolution"
_MAX_RETRIES = 2


class PromptEvolver:
    """
    Proposes PromptConfig mutations using an LLM.

    Usage:
        evolver = PromptEvolver(llm_client)
        variants = evolver.mutate(current_config, run_summary, n=3, scope="agent")
    """

    def __init__(self, llm, model: Optional[str] = None):
        self.llm = llm
        self.model = model

    def mutate(
        self,
        config: PromptConfig,
        run_summary: RunSummary,
        n: int = 3,
        scope: str = "agent",   # "agent" or "oracle"
    ) -> list[PromptConfig]:
        """
        Generate N mutated PromptConfig variants.

        Args:
            config: current baseline prompt config
            run_summary: statistics from recent runs
            n: number of variants to generate
            scope: "agent" mutates agent prompts; "oracle" mutates oracle prompts
        """
        variants: list[PromptConfig] = []
        for i in range(n):
            variant = self._propose_single(config, run_summary, scope=scope, attempt_index=i)
            if variant is not None:
                variants.append(variant)
        logger.info(
            "PromptEvolver (%s) produced %d/%d valid variants", scope, len(variants), n
        )
        return variants

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_prompt(self, name: str) -> str:
        path = _PROMPTS_DIR / f"{name}.txt"
        if path.exists():
            return path.read_text(encoding="utf-8")
        logger.warning("Prompt file not found: %s", path)
        return ""

    def _propose_single(
        self,
        config: PromptConfig,
        run_summary: RunSummary,
        scope: str,
        attempt_index: int = 0,
    ) -> Optional[PromptConfig]:
        """Propose one mutated config, retrying up to _MAX_RETRIES times."""
        current_prompts = (
            config.agent_prompts if scope == "agent" else config.oracle_prompts
        )

        system_prompt = self._load_prompt("prompt_mutation_system")
        user_template = self._load_prompt("prompt_mutation_user")

        prompts_json = json.dumps(current_prompts, indent=2, ensure_ascii=False)
        user_prompt = user_template.format(
            scope=scope,
            prompts_json=prompts_json,
            run_statistics=run_summary.to_prompt_text(),
        )

        for attempt in range(_MAX_RETRIES + 1):
            raw = self._call_llm(system_prompt, user_prompt)
            if raw is None:
                logger.warning("LLM returned None on attempt %d", attempt)
                continue

            variant = self._parse_and_validate(raw, config, scope, attempt_index)
            if variant is not None:
                return variant

            logger.warning(
                "Prompt mutation attempt %d/%d failed validation — %s",
                attempt + 1,
                _MAX_RETRIES + 1,
                "retrying" if attempt < _MAX_RETRIES else "discarding",
            )

        return None

    def _call_llm(self, system: str, user: str) -> Optional[str]:
        if self.llm is None:
            return None
        try:
            return self.llm.generate_text(user=user, system=system, max_tokens=8192)
        except Exception as exc:
            logger.warning("LLM call failed: %s", exc)
            return None

    def _parse_and_validate(
        self,
        raw: str,
        reference: PromptConfig,
        scope: str,
        attempt_index: int,
    ) -> Optional[PromptConfig]:
        """Extract JSON dict of prompts, validate, and return a PromptConfig."""
        prompts_dict = self._extract_json(raw)
        if prompts_dict is None:
            logger.warning("No JSON dict found in LLM response")
            return None

        if not isinstance(prompts_dict, dict):
            logger.warning("LLM response parsed to non-dict: %s", type(prompts_dict))
            return None

        # Build a candidate config with the mutated scope
        if scope == "agent":
            candidate = PromptConfig(
                agent_prompts=prompts_dict,
                oracle_prompts=dict(reference.oracle_prompts),
                metadata={"mutated_scope": scope, "attempt": attempt_index},
            )
        else:
            candidate = PromptConfig(
                agent_prompts=dict(reference.agent_prompts),
                oracle_prompts=prompts_dict,
                metadata={"mutated_scope": scope, "attempt": attempt_index},
            )

        errors = candidate.validate_against(reference)
        if errors:
            for err in errors:
                logger.warning("Prompt validation error: %s", err)
            return None

        return candidate

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        """Extract the first JSON object from the LLM response."""
        # Try ```json ... ``` blocks first
        match = re.search(r"```(?:json)?\s*\n([\s\S]*?)\n```", text)
        if match:
            candidate = match.group(1)
        else:
            # Find first { ... } span
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            candidate = text[start : end + 1]

        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None


class MockPromptEvolver(PromptEvolver):
    """
    Deterministic prompt evolver for testing — returns copies with a trivial
    comment appended to each prompt text (no LLM required).
    """

    def __init__(self):
        super().__init__(llm=None)

    def mutate(
        self,
        config: PromptConfig,
        run_summary: RunSummary,
        n: int = 3,
        scope: str = "agent",
    ) -> list[PromptConfig]:
        variants: list[PromptConfig] = []
        for i in range(n):
            if scope == "agent":
                mutated = {
                    k: v + f"\n# mock_mutation_{i}"
                    for k, v in config.agent_prompts.items()
                }
                variant = PromptConfig(
                    agent_prompts=mutated,
                    oracle_prompts=dict(config.oracle_prompts),
                    metadata={"mutated_scope": scope, "attempt": i, "mock": True},
                )
            else:
                mutated = {
                    k: v + f"\n# mock_mutation_{i}"
                    for k, v in config.oracle_prompts.items()
                }
                variant = PromptConfig(
                    agent_prompts=dict(config.agent_prompts),
                    oracle_prompts=mutated,
                    metadata={"mutated_scope": scope, "attempt": i, "mock": True},
                )
            variants.append(variant)
        return variants

"""
WorldEvolver: LLM-driven world schema mutation engine.

Given a WorldSchema and run statistics, calls an LLM to propose mutations
and returns validated WorldSchema variants.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import yaml

from simulation.world_schema import WorldSchema
from simulation.evolution.run_analyzer import RunSummary

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts" / "evolution"
_MAX_RETRIES = 2  # LLM retries on validation failure


class WorldEvolver:
    """
    Proposes WorldSchema mutations using an LLM.

    Usage:
        evolver = WorldEvolver(llm_client)
        variants = evolver.mutate(current_schema, run_summary, n=3)
    """

    def __init__(self, llm, model: Optional[str] = None):
        """
        Args:
            llm: LLMClient instance (or any object with a .complete(system, user) method)
            model: optional model override (e.g. "claude-3-5-sonnet" for cloud)
        """
        self.llm = llm
        self.model = model

    def mutate(
        self,
        schema: WorldSchema,
        run_summary: RunSummary,
        n: int = 3,
    ) -> list[WorldSchema]:
        """
        Generate N mutated schema variants from the current schema and run summary.

        Returns a list of validated WorldSchema instances. If a proposed mutation
        fails validation it is retried once; persistent failures are logged and
        excluded from the result.
        """
        variants: list[WorldSchema] = []
        for i in range(n):
            variant = self._propose_single(schema, run_summary, attempt_index=i)
            if variant is not None:
                variants.append(variant)
        logger.info("WorldEvolver produced %d/%d valid variants", len(variants), n)
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
        schema: WorldSchema,
        run_summary: RunSummary,
        attempt_index: int = 0,
    ) -> Optional[WorldSchema]:
        """Propose one mutated schema, retrying up to _MAX_RETRIES times."""
        current_gen = schema.metadata.get("generation", 0)
        system_prompt = self._load_prompt("world_mutation_system")
        user_template = self._load_prompt("world_mutation_user")

        user_prompt = user_template.format(
            generation=current_gen,
            parent_name=schema.metadata.get("name", "unknown"),
            current_schema_yaml=schema.to_yaml_str(),
            run_statistics=run_summary.to_prompt_text(),
            next_generation=current_gen + 1,
            current_schema_name=schema.metadata.get("name", "unknown"),
        )

        for attempt in range(_MAX_RETRIES + 1):
            raw = self._call_llm(system_prompt, user_prompt)
            if raw is None:
                logger.warning("LLM returned None on attempt %d", attempt)
                continue

            variant = self._parse_and_validate(raw, schema, attempt_index)
            if variant is not None:
                return variant

            logger.warning(
                "Mutation attempt %d/%d failed validation — %s",
                attempt + 1, _MAX_RETRIES + 1,
                "retrying" if attempt < _MAX_RETRIES else "discarding",
            )

        return None

    def _call_llm(self, system: str, user: str) -> Optional[str]:
        """Call the LLM and return the raw text response."""
        if self.llm is None:
            return None
        try:
            return self.llm.generate_text(user=user, system=system, max_tokens=4096)
        except Exception as exc:
            logger.warning("LLM call failed: %s", exc)
            return None

    def _parse_and_validate(
        self,
        raw: str,
        parent_schema: WorldSchema,
        attempt_index: int,
    ) -> Optional[WorldSchema]:
        """
        Extract YAML from the raw LLM response, parse it, and validate.
        Returns a WorldSchema if valid, None otherwise.
        """
        yaml_text = self._extract_yaml(raw)
        if not yaml_text:
            logger.warning("No YAML found in LLM response")
            return None

        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as exc:
            logger.warning("YAML parse error: %s", exc)
            return None

        if not isinstance(data, dict):
            logger.warning("LLM response parsed to non-dict: %s", type(data))
            return None

        # Ensure required metadata is set correctly
        parent_gen = parent_schema.metadata.get("generation", 0)
        data.setdefault("metadata", {})
        data["metadata"]["generation"] = parent_gen + 1
        if not data["metadata"].get("parent"):
            data["metadata"]["parent"] = parent_schema.metadata.get("name")
        if not data["metadata"].get("name"):
            data["metadata"]["name"] = f"gen{parent_gen + 1}_v{attempt_index}"
        if "mutations_applied" not in data["metadata"]:
            data["metadata"]["mutations_applied"] = []

        try:
            variant = WorldSchema.from_dict(data)
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("WorldSchema validation failed: %s", exc)
            return None

        return variant

    @staticmethod
    def _extract_yaml(text: str) -> str:
        """Extract YAML content from a text that may contain code fences."""
        # Try ```yaml ... ``` blocks first
        match = re.search(r"```(?:yaml)?\s*\n([\s\S]*?)\n```", text)
        if match:
            return match.group(1)
        # Try ``` ... ``` without language tag
        match = re.search(r"```\s*\n([\s\S]*?)\n```", text)
        if match:
            return match.group(1)
        # Assume the entire response is YAML (LLM followed instructions)
        stripped = text.strip()
        if stripped.startswith("schema_version") or stripped.startswith("metadata"):
            return stripped
        # Try to find first line that looks like YAML
        if ":" in text:
            return stripped
        return ""


class MockEvolver(WorldEvolver):
    """
    A deterministic evolver for testing — returns copies of the input schema
    with minimal mutations applied (no LLM required).
    """

    def __init__(self):
        super().__init__(llm=None)

    def mutate(
        self,
        schema: WorldSchema,
        run_summary: RunSummary,
        n: int = 3,
    ) -> list[WorldSchema]:
        """Generate N deterministic schema variants without calling an LLM."""
        variants = []
        for i in range(n):
            data = schema.to_dict()
            current_gen = data.get("metadata", {}).get("generation", 0)
            data["metadata"]["generation"] = current_gen + 1
            data["metadata"]["parent"] = data["metadata"].get("name", "base")
            data["metadata"]["name"] = f"gen{current_gen + 1}_mock_v{i}"
            data["metadata"]["mutations_applied"] = [
                f"mock_mutation_{i}: adjusted hunger_per_tick to {1 + i * 0.1:.1f}"
            ]
            # Minimal tweak: nudge hunger_per_tick slightly
            data["agents"]["thresholds"]["hunger_per_tick"] = 1 + i * 0.1
            try:
                variants.append(WorldSchema.from_dict(data))
            except Exception as exc:
                logger.warning("MockEvolver variant %d failed: %s", i, exc)
        return variants

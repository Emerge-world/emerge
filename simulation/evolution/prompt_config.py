"""
PromptConfig: serializable snapshot of agent and oracle prompts.

Mirrors the WorldSchema pattern — can be saved/loaded as JSON, and provides
a to_loader_dict() method for use with prompt_loader.set_override().
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"

# Prompt files that belong to each category
_AGENT_PROMPT_NAMES = [
    "system",
    "decision",
    "planner_system",
    "planner",
    "memory_compression",
    "energy_critical",
    "energy_low",
]
_ORACLE_PROMPT_NAMES = [
    "physical_system",
    "custom_action_system",
    "innovation_system",
    "fruit_effect",
    "item_eat_effect",
]

# Required $variables per prompt (empty set = no templating, loaded raw)
REQUIRED_VARIABLES: dict[str, set[str]] = {
    "agent/system": {
        "$name", "$actions", "$personality_description", "$custom_actions_section"
    },
    "agent/decision": {
        "$tick", "$life", "$max_life", "$hunger", "$max_hunger", "$hunger_threshold",
        "$energy", "$max_energy", "$status_effects", "$inventory_info", "$ascii_grid",
        "$pickup_ready_resources", "$nearby_resource_hints", "$nearby_agents",
        "$incoming_messages", "$relationships", "$current_goal", "$active_subgoal",
        "$plan_status", "$family_info", "$memory_text", "$reproduction_hint",
        "$time_info", "$current_tile_info",
    },
    "agent/planner_system": {"$agent_name"},
    "agent/planner": {"$tick", "$observation_text", "$current_plan", "$planner_context"},
    "agent/memory_compression": {"$agent_name", "$episodes", "$existing_knowledge"},
    "agent/energy_critical": set(),
    "agent/energy_low": set(),
}


@dataclass
class PromptConfig:
    """Snapshot of all agent and oracle prompt texts."""

    agent_prompts: dict[str, str] = field(default_factory=dict)
    # keys: bare name like "system", "decision", ...
    oracle_prompts: dict[str, str] = field(default_factory=dict)
    # keys: bare name like "physical_system", ...
    metadata: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Factory: read from disk
    # ------------------------------------------------------------------

    @classmethod
    def from_disk(
        cls,
        prompts_dir: Optional[Path] = None,
    ) -> "PromptConfig":
        """Read all agent and oracle prompts from the prompts/ directory."""
        root = prompts_dir or _PROMPTS_DIR
        agent: dict[str, str] = {}
        oracle: dict[str, str] = {}
        for name in _AGENT_PROMPT_NAMES:
            p = root / "agent" / f"{name}.txt"
            if p.exists():
                agent[name] = p.read_text(encoding="utf-8")
        for name in _ORACLE_PROMPT_NAMES:
            p = root / "oracle" / f"{name}.txt"
            if p.exists():
                oracle[name] = p.read_text(encoding="utf-8")
        return cls(agent_prompts=agent, oracle_prompts=oracle)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "agent_prompts": self.agent_prompts,
            "oracle_prompts": self.oracle_prompts,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PromptConfig":
        return cls(
            agent_prompts=d.get("agent_prompts", {}),
            oracle_prompts=d.get("oracle_prompts", {}),
            metadata=d.get("metadata", {}),
        )

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path | str) -> "PromptConfig":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    # ------------------------------------------------------------------
    # prompt_loader integration
    # ------------------------------------------------------------------

    def to_loader_dict(self) -> dict[str, str]:
        """
        Return a flat dict keyed by prompt_loader names.

        e.g. {"agent/system": "...", "oracle/physical_system": "..."}
        """
        result: dict[str, str] = {}
        for name, text in self.agent_prompts.items():
            result[f"agent/{name}"] = text
        for name, text in self.oracle_prompts.items():
            result[f"oracle/{name}"] = text
        return result

    # ------------------------------------------------------------------
    # Template variable helpers
    # ------------------------------------------------------------------

    @staticmethod
    def extract_variables(text: str) -> set[str]:
        """Return the set of $variable tokens in text."""
        # Match $name or ${name}
        return set(re.findall(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?", text))

    def validate_against(self, reference: "PromptConfig") -> list[str]:
        """
        Check that all required $variables still appear in each mutated prompt.

        Returns a list of error strings (empty if valid).
        """
        errors: list[str] = []
        for name, text in self.agent_prompts.items():
            key = f"agent/{name}"
            required = REQUIRED_VARIABLES.get(key, set())
            if not required:
                continue
            ref_text = reference.agent_prompts.get(name, "")
            # Only validate variables that exist in the reference
            expected = self.extract_variables(ref_text) & required
            present = self.extract_variables(text)
            missing = expected - present
            if missing:
                errors.append(
                    f"{key}: missing required variables {sorted(missing)}"
                )
        return errors

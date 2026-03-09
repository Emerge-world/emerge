"""
Lineage tracking: records births, deaths, innovations, and family trees.
Persisted to data/lineage_{seed}.json between runs.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LineageRecord:
    agent_name: str
    parent_names: list[str]       # [] for generation-0 agents
    generation: int
    born_tick: int
    died_tick: Optional[int] = None
    innovations_created: list[str] = field(default_factory=list)
    children_names: list[str] = field(default_factory=list)


class LineageTracker:
    """Tracks the full family tree across the simulation."""

    def __init__(self):
        self.records: dict[str, LineageRecord] = {}

    def record_birth(
        self,
        agent_name: str,
        parent_names: list[str],
        generation: int,
        tick: int,
    ) -> None:
        self.records[agent_name] = LineageRecord(
            agent_name=agent_name,
            parent_names=list(parent_names),
            generation=generation,
            born_tick=tick,
        )

    def record_death(self, agent_name: str, tick: int) -> None:
        if agent_name in self.records:
            self.records[agent_name].died_tick = tick

    def record_innovation(self, agent_name: str, innovation_name: str) -> None:
        if agent_name in self.records:
            self.records[agent_name].innovations_created.append(innovation_name)

    def record_child(self, parent_name: str, child_name: str) -> None:
        if parent_name in self.records:
            self.records[parent_name].children_names.append(child_name)

    def save(self, path: str) -> None:
        """Persist all records to a JSON file."""
        p = Path(path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            data = {
                name: {
                    "agent_name": r.agent_name,
                    "parent_names": r.parent_names,
                    "generation": r.generation,
                    "born_tick": r.born_tick,
                    "died_tick": r.died_tick,
                    "innovations_created": r.innovations_created,
                    "children_names": r.children_names,
                }
                for name, r in self.records.items()
            }
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info("Saved lineage for %d agents to %s", len(self.records), path)
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Could not save lineage to %s: %s", path, exc)

    def load(self, path: str) -> None:
        """Load records from a JSON file. Silently skips if file does not exist."""
        p = Path(path)
        if not p.exists():
            logger.debug("No lineage file at %s, starting fresh.", path)
            return
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            for name, d in data.items():
                self.records[name] = LineageRecord(
                    agent_name=d["agent_name"],
                    parent_names=d.get("parent_names", []),
                    generation=d.get("generation", 0),
                    born_tick=d.get("born_tick", 0),
                    died_tick=d.get("died_tick"),
                    innovations_created=d.get("innovations_created", []),
                    children_names=d.get("children_names", []),
                )
            logger.info("Loaded lineage for %d agents from %s", len(self.records), path)
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            logger.warning("Could not load lineage from %s: %s", path, exc)

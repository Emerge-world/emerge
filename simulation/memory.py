"""
Dual memory system: episodic (short-term events) + semantic (long-term knowledge).

Episodic memory stores raw events (max MEMORY_EPISODIC_MAX, FIFO).
Semantic memory stores compressed knowledge (max MEMORY_SEMANTIC_MAX, FIFO).
Every MEMORY_COMPRESSION_INTERVAL ticks, the LLM compresses recent episodes
into reusable lessons that persist in semantic memory.
"""

import json
import logging
from typing import Optional

from simulation.config import (
    MEMORY_EPISODIC_MAX,
    MEMORY_SEMANTIC_MAX,
    MEMORY_COMPRESSION_INTERVAL,
    MEMORY_EPISODIC_IN_PROMPT,
    MEMORY_SEMANTIC_IN_PROMPT,
    INHERIT_SEMANTIC_MAX,
)

logger = logging.getLogger(__name__)


class Memory:
    """Dual episodic + semantic memory for an agent."""

    def __init__(self):
        self.episodic: list[str] = []
        self.semantic: list[str] = []
        self._last_compression_tick: int = 0

    def add_episode(self, entry: str):
        """Add a raw event to episodic memory."""
        self.episodic.append(entry)
        if len(self.episodic) > MEMORY_EPISODIC_MAX:
            self.episodic = self.episodic[-MEMORY_EPISODIC_MAX:]

    def add_knowledge(self, entry: str):
        """Add a learned lesson to semantic memory."""
        self.semantic.append(entry)
        if len(self.semantic) > MEMORY_SEMANTIC_MAX:
            self.semantic = self.semantic[-MEMORY_SEMANTIC_MAX:]

    def should_compress(self, tick: int) -> bool:
        """Check if compression is due (every N ticks, and has episodes)."""
        if not self.episodic:
            return False
        if tick < MEMORY_COMPRESSION_INTERVAL:
            return False
        if tick % MEMORY_COMPRESSION_INTERVAL != 0:
            return False
        if tick == self._last_compression_tick:
            return False
        return True

    def compress(self, llm, tick: int, agent_name: str) -> list[str]:
        """Ask the LLM to extract learnings from recent episodes into semantic memory.

        Three-layer fallback: null LLM check, try/except, result validation.
        Never crashes. Returns the list of accepted learnings (empty on any failure).
        """
        if not llm:
            logger.debug(f"[{agent_name}] No LLM available, skipping memory compression")
            self._last_compression_tick = tick
            return []

        from simulation import prompt_loader

        episodes_text = "\n".join(f"- {ep}" for ep in self.episodic)
        existing_knowledge = "\n".join(f"- {k}" for k in self.semantic) if self.semantic else "None yet."

        accepted: list[str] = []
        try:
            prompt = prompt_loader.render(
                "agent/memory_compression",
                agent_name=agent_name,
                episodes=episodes_text,
                existing_knowledge=existing_knowledge,
            )

            from simulation.schemas import MemoryCompressionResponse
            typed = llm.generate_structured(prompt, MemoryCompressionResponse, temperature=0.3)

            if typed is not None:
                learnings = typed.learnings
                for lesson in learnings:
                    if isinstance(lesson, str) and lesson.strip():
                        self.add_knowledge(lesson.strip())
                        accepted.append(lesson.strip())
                logger.info(f"[{agent_name}] Compressed {len(self.episodic)} episodes into {len(accepted)} learnings")
            else:
                logger.warning(f"[{agent_name}] Memory compression returned invalid format, skipping")

        except Exception as e:
            logger.warning(f"[{agent_name}] Memory compression failed: {e}")

        self._last_compression_tick = tick
        return accepted

    def to_prompt(self) -> str:
        """Format both memory stores for the decision prompt."""
        sections = []

        # Semantic knowledge (most important, shown first)
        if self.semantic:
            knowledge = self.semantic[-MEMORY_SEMANTIC_IN_PROMPT:]
            lines = "\n".join(f"- [KNOW] {k}" for k in knowledge)
            sections.append(f"KNOWLEDGE (things I've learned):\n{lines}")

        # Recent episodes
        if self.episodic:
            recent = self.episodic[-MEMORY_EPISODIC_IN_PROMPT:]
            lines = "\n".join(f"- [RECENT] {ep}" for ep in recent)
            sections.append(f"RECENT EVENTS:\n{lines}")

        if not sections:
            return "I have no previous memories. I just arrived in the world."

        return "\n\n".join(sections)

    @property
    def total_entries(self) -> int:
        """Total number of memory entries across both stores."""
        return len(self.episodic) + len(self.semantic)

    def inherit_from(self, parent_a: "Memory", parent_b: "Memory") -> None:
        """Seed this memory with up to INHERIT_SEMANTIC_MAX semantic memories from each parent.

        Prefixes each entry with '[Inherited]' to distinguish from personal experience.
        No episodic memories are inherited (those are personal).
        """
        for parent in (parent_a, parent_b):
            for entry in parent.semantic[-INHERIT_SEMANTIC_MAX:]:
                self.add_knowledge(f"[Inherited] {entry}")

    def all_entries(self) -> list[str]:
        """All entries from both stores (semantic first, then episodic). For backward compat."""
        return list(self.semantic) + list(self.episodic)

"""
Personality traits for agents.
Injected into the LLM system prompt to shape emergent behavior.
"""

import random
from dataclasses import dataclass


@dataclass
class Personality:
    courage: float     # 0.0-1.0: boldness, willingness to take risks
    curiosity: float   # 0.0-1.0: tendency to explore and innovate
    patience: float    # 0.0-1.0: willingness to wait vs. act immediately
    sociability: float # 0.0-1.0: tendency to seek out and interact with others

    @classmethod
    def random(cls) -> "Personality":
        """Create a personality with randomized traits."""
        return cls(
            courage=round(random.random(), 2),
            curiosity=round(random.random(), 2),
            patience=round(random.random(), 2),
            sociability=round(random.random(), 2),
        )

    def to_prompt(self) -> str:
        """Return a description for injection into the LLM system prompt."""
        def label(v: float) -> str:
            if v >= 0.75:
                return "high"
            if v >= 0.50:
                return "moderate"
            if v >= 0.25:
                return "low"
            return "very low"

        return (
            f"Personality traits — "
            f"courage: {label(self.courage)} ({self.courage:.2f}), "
            f"curiosity: {label(self.curiosity)} ({self.curiosity:.2f}), "
            f"patience: {label(self.patience)} ({self.patience:.2f}), "
            f"sociability: {label(self.sociability)} ({self.sociability:.2f})."
        )

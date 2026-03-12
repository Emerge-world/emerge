"""Scarcity and benchmark metadata models."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

_FOOD_RESOURCE_TYPES = frozenset({"fruit", "mushroom"})


@dataclass(frozen=True)
class ScarcityConfig:
    """Per-run scarcity controls for benchmark scenarios."""

    initial_resource_scale: float = 1.0
    regen_chance_scale: float = 1.0
    regen_amount_scale: float = 1.0

    def __post_init__(self):
        for field_name, value in asdict(self).items():
            if value < 0:
                raise ValueError(f"{field_name} must be >= 0")

    def as_dict(self) -> dict[str, float]:
        return dict(asdict(self))

    def scales_food_resource(self, resource_type: str) -> bool:
        return resource_type in _FOOD_RESOURCE_TYPES

    def scale_initial_quantity(self, resource_type: str, quantity: int) -> int:
        if not self.scales_food_resource(resource_type):
            return quantity
        return _scale_quantity(quantity, self.initial_resource_scale)

    def scale_regen_probability(self, probability: float) -> float:
        return max(0.0, min(1.0, probability * self.regen_chance_scale))

    def scale_regen_quantity(self, quantity: int) -> int:
        return _scale_quantity(quantity, self.regen_amount_scale)


@dataclass(frozen=True)
class BenchmarkMetadata:
    """Metadata attached to benchmark-driven runs."""

    benchmark_id: str
    benchmark_version: str
    scenario_id: str
    candidate_label: str
    baseline_label: str | None = None

    def __post_init__(self):
        for field_name in ("benchmark_id", "benchmark_version", "scenario_id", "candidate_label"):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must be a non-empty string")

    def as_dict(self) -> dict[str, str | None]:
        return dict(asdict(self))


def _scale_quantity(quantity: int, scale: float) -> int:
    """Scale resource quantities deterministically.

    Scale < 1 uses floor to let scarcity remove resources entirely.
    Scale > 1 uses ceil so abundance increases are visible even at low counts.
    """

    if quantity <= 0 or scale <= 0:
        return 0
    scaled = quantity * scale
    if scale < 1.0:
        return math.floor(scaled)
    return math.ceil(scaled)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

OracleMode = Literal["live", "frozen", "symbolic"]
PersistenceMode = Literal["none", "oracle", "lineage", "full"]


@dataclass(slots=True)
class RuntimeSettings:
    use_llm: bool
    model: str | None
    agents: int
    ticks: int | None
    seed: int | None
    width: int
    height: int
    start_hour: int


@dataclass(slots=True)
class CapabilitySettings:
    explicit_planning: bool
    semantic_memory: bool
    innovation: bool
    item_reflection: bool
    social: bool
    teach: bool
    reproduction: bool


@dataclass(slots=True)
class PersistenceSettings:
    mode: PersistenceMode
    clean_before_run: bool


@dataclass(slots=True)
class OracleSettings:
    mode: OracleMode
    freeze_precedents_path: str | None


@dataclass(slots=True)
class BenchmarkMetadata:
    benchmark_id: str
    benchmark_version: str
    scenario_id: str
    arm_id: str
    seed_set: str | None = None
    session_id: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WorldOverrides:
    initial_resource_scale: float | None = None
    regen_chance_scale: float | None = None
    regen_amount_scale: float | None = None
    world_fixture: str | None = None


@dataclass(slots=True)
class ExperimentProfile:
    runtime: RuntimeSettings
    capabilities: CapabilitySettings
    persistence: PersistenceSettings
    oracle: OracleSettings
    benchmark: BenchmarkMetadata
    world_overrides: WorldOverrides

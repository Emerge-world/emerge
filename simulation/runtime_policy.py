from __future__ import annotations

from dataclasses import dataclass

from simulation.runtime_settings import ExperimentProfile


@dataclass(slots=True)
class AgentRuntimeSettings:
    explicit_planning: bool
    innovation: bool
    item_reflection: bool
    social: bool
    teach: bool
    reproduction: bool


@dataclass(slots=True)
class MemoryRuntimeSettings:
    semantic_memory: bool


@dataclass(slots=True)
class OracleRuntimeSettings:
    innovation: bool
    item_reflection: bool
    social: bool
    teach: bool
    reproduction: bool


@dataclass(slots=True)
class WorldRuntimeSettings:
    initial_resource_scale: float | None
    regen_chance_scale: float | None
    regen_amount_scale: float | None


@dataclass(slots=True)
class RuntimePolicy:
    agent: AgentRuntimeSettings
    memory: MemoryRuntimeSettings
    oracle: OracleRuntimeSettings
    world: WorldRuntimeSettings


def derive_runtime_policy(profile: ExperimentProfile) -> RuntimePolicy:
    caps = profile.capabilities
    return RuntimePolicy(
        agent=AgentRuntimeSettings(
            explicit_planning=caps.explicit_planning,
            innovation=caps.innovation,
            item_reflection=caps.item_reflection,
            social=caps.social,
            teach=caps.teach,
            reproduction=caps.reproduction,
        ),
        memory=MemoryRuntimeSettings(semantic_memory=caps.semantic_memory),
        oracle=OracleRuntimeSettings(
            innovation=caps.innovation,
            item_reflection=caps.item_reflection,
            social=caps.social,
            teach=caps.teach,
            reproduction=caps.reproduction,
        ),
        world=WorldRuntimeSettings(
            initial_resource_scale=profile.world_overrides.initial_resource_scale,
            regen_chance_scale=profile.world_overrides.regen_chance_scale,
            regen_amount_scale=profile.world_overrides.regen_amount_scale,
        ),
    )

# Typed Experimental Runtime Design

**Date:** 2026-03-26
**Status:** Approved

## Problem

The current simulation runtime is configured through a mix of CLI flags, direct reads from `simulation/config.py`, and ad hoc parameter passing into `SimulationEngine`.

That structure makes the base simulation runnable, but it does not provide a typed per-run contract that can support the benchmark refactor described in `BENCHMARK_REFACTOR_TRACKER.md`. In particular:

- `config.py` acts as both defaults store and effective runtime source
- runtime inputs are passed as loose kwargs instead of a coherent per-run object
- benchmark metadata has no stable home in the runtime contract
- future YAML-driven execution would need to translate into the old parameter soup

The first layer of the refactor needs to introduce a typed runtime model without coupling new code to `run_batch.py` or `experiments.yaml`, and without breaking the existing simulation entrypoint.

## Goal

Introduce the first runtime layer for the benchmark refactor:

- a typed `RuntimeSettings`
- a typed `ExperimentProfile`
- clear separation between global defaults and per-run overrides
- initial wiring so `main.py` can construct a profile and pass it into the runtime
- no dependency on `run_batch.py` or `experiments.yaml`

The repo must remain runnable and the base simulation behavior must remain equivalent to today when using default settings.

## Decision

Adopt a hybrid migration design:

- define the new runtime contract as pure dataclasses
- keep construction logic separate in a dedicated builder/factory module
- make `ExperimentProfile` the canonical new per-run object
- update `main.py` to build and pass an `ExperimentProfile`
- update `SimulationEngine` to accept `profile` as the new API while keeping legacy kwargs temporarily for compatibility

This is the best fit for PR 1 in `BENCHMARK_REFACTOR_TRACKER.md` because it establishes the correct boundary now, keeps the repo runnable, and avoids prematurely forcing the rest of the runtime to consume benchmark-specific logic.

## Design

### 1. Typed Runtime Model

Add a new module for typed runtime models, for example `simulation/runtime_settings.py`.

It should define the following dataclasses:

- `CapabilitySettings`
- `PersistenceSettings`
- `OracleSettings`
- `BenchmarkMetadata`
- `WorldOverrides`
- `RuntimeSettings`
- `ExperimentProfile`

Expected contents:

- `RuntimeSettings`
  - `use_llm: bool`
  - `model: str | None`
  - `agents: int`
  - `ticks: int | None`
  - `seed: int | None`
  - `width: int`
  - `height: int`
  - `start_hour: int`
- `CapabilitySettings`
  - `explicit_planning: bool`
  - `semantic_memory: bool`
  - `innovation: bool`
  - `item_reflection: bool`
  - `social: bool`
  - `teach: bool`
  - `reproduction: bool`
- `OracleSettings`
  - `mode: live | frozen | symbolic`
  - `freeze_precedents_path: str | None`
- `PersistenceSettings`
  - `mode: none | oracle | lineage | full`
  - `clean_before_run: bool`
- `BenchmarkMetadata`
  - `benchmark_id: str`
  - `benchmark_version: str`
  - `scenario_id: str`
  - `arm_id: str`
  - `seed_set: str | None`
  - `session_id: str | None`
  - `tags: list[str]`
- `WorldOverrides`
  - `initial_resource_scale: float | None`
  - `regen_chance_scale: float | None`
  - `regen_amount_scale: float | None`
  - `world_fixture: str | None`
- `ExperimentProfile`
  - `runtime: RuntimeSettings`
  - `capabilities: CapabilitySettings`
  - `persistence: PersistenceSettings`
  - `oracle: OracleSettings`
  - `benchmark: BenchmarkMetadata`
  - `world_overrides: WorldOverrides`

These dataclasses must stay pure. They should not import CLI code, read `config.py`, or know anything about manifests.

`OracleSettings.mode` semantics for the contract:

- `live`: current runtime behavior using the existing oracle path
- `frozen`: reserved for a future deterministic mode backed by a read-only precedents snapshot
- `symbolic`: reserved for a future deterministic non-LLM oracle path

`freeze_precedents_path` semantics:

- required for `frozen` once that mode is implemented
- ignored for `live`
- ignored for `symbolic` in the current design unless a later spec states otherwise

PR 1 does not implement `frozen` or `symbolic` behavior. It only introduces the typed field and keeps the current CLI/builder path on `live`.

### 2. Builder / Factory Separation

Add a separate construction module, for example `simulation/runtime_profiles.py`.

This module owns the composition logic for:

- reading global defaults from `simulation/config.py`
- building a default `ExperimentProfile`
- applying per-run overrides
- constructing a profile from the current CLI arguments in `main.py`

Recommended public helpers:

- `build_default_profile() -> ExperimentProfile`
- `build_profile_from_cli(args) -> ExperimentProfile`
- one or more typed override helpers if needed internally

This separation is required because the tracker explicitly says `config.py` must remain defaults, not the single source of truth. The builder may read `config.py`; the dataclasses must not.

This also keeps the future path clean:

- current CLI -> builder -> `ExperimentProfile`
- future YAML loader -> builder or typed override helpers -> `ExperimentProfile`

without introducing any dependency on `run_batch.py` or `experiments.yaml`.

### 2.1 Default Profile Contract

`build_default_profile()` must return a fully materialized profile with explicit defaults for every field.

Defaults that mirror the current base simulation:

| Field | Default |
|---|---|
| `runtime.use_llm` | `True` |
| `runtime.model` | `simulation.config.VLLM_MODEL` |
| `runtime.agents` | `3` |
| `runtime.ticks` | `simulation.config.MAX_TICKS` |
| `runtime.seed` | `None` |
| `runtime.width` | `simulation.config.WORLD_WIDTH` |
| `runtime.height` | `simulation.config.WORLD_HEIGHT` |
| `runtime.start_hour` | `simulation.config.WORLD_START_HOUR` |
| `capabilities.explicit_planning` | `simulation.config.ENABLE_EXPLICIT_PLANNING` |
| `capabilities.semantic_memory` | `True` |
| `capabilities.innovation` | `True` |
| `capabilities.item_reflection` | `True` |
| `capabilities.social` | `True` |
| `capabilities.teach` | `True` |
| `capabilities.reproduction` | `True` |
| `persistence.mode` | `"none"` |
| `persistence.clean_before_run` | `False` |
| `oracle.mode` | `"live"` |
| `oracle.freeze_precedents_path` | `None` |
| `benchmark.benchmark_id` | `"adhoc"` |
| `benchmark.benchmark_version` | `"adhoc"` |
| `benchmark.scenario_id` | `"default"` |
| `benchmark.arm_id` | `"default"` |
| `benchmark.seed_set` | `None` |
| `benchmark.session_id` | `None` |
| `benchmark.tags` | `[]` |
| `world_overrides.initial_resource_scale` | `None` |
| `world_overrides.regen_chance_scale` | `None` |
| `world_overrides.regen_amount_scale` | `None` |
| `world_overrides.world_fixture` | `None` |

Notes:

- `runtime.ticks = None` is a real runtime value meaning an unbounded run, matching current engine behavior for infinite/default runs.
- `runtime.seed = None` is a real runtime value meaning unseeded world generation, matching current engine behavior.
- `benchmark.*` defaults represent a direct ad hoc run outside the future benchmark-manifest flow.
- `benchmark.tags` must use a safe empty-list default via dataclass field factory.
- `persistence.clean_before_run = False` preserves current base behavior in this PR. Future benchmark manifests may override it to `True`.

### 3. Runtime Wiring

Update `main.py` so the current CLI builds an `ExperimentProfile` and passes it to `SimulationEngine`.

`SimulationEngine` should gain a new optional parameter:

- `profile: ExperimentProfile | None = None`

The compatibility policy should be explicit:

- if `profile` is passed, it is the canonical input
- if `profile` is not passed, the engine constructs an equivalent profile from legacy kwargs
- if both `profile` and legacy kwargs are passed, `profile` wins and legacy kwargs are not merged silently

This precedence rule applies only to fields represented in `ExperimentProfile`.

The following inputs remain outside the profile in PR 1 and keep their current explicit-engine semantics:

- `wandb_logger`
- `run_digest`

They are operational runtime wrappers, not part of the typed experimental settings contract yet. If `profile` is supplied, these arguments still behave exactly as explicitly passed by the caller.

This keeps the old call sites viable while making the new object the real boundary going forward.

Legacy constructor compatibility must preserve historical `SimulationEngine` semantics for omitted kwargs. In particular:

- `build_default_profile()` is the baseline for `main.py` and future benchmark entrypoints
- direct legacy `SimulationEngine(...)` construction without `profile` must preserve the constructor's current defaults
- therefore, if `profile` is omitted and `persistence` is also omitted, the effective profile built inside the engine must use legacy constructor default `"full"` rather than the CLI/profile-builder default `"none"`

This keeps old programmatic call sites stable while the migration is in progress. The mismatch is transitional and should disappear when the legacy kwargs are removed in a later refactor.

For this PR, engine consumption remains conservative:

- use `profile.runtime` for the fields already accepted as direct engine inputs
- use `profile.persistence.mode` in place of the current persistence string
- keep `profile.oracle`, `profile.capabilities`, `profile.benchmark`, and `profile.world_overrides` available on the engine even if only partially consumed for now

The engine should expose the effective profile as instance state so later refactor steps can push it down into `World`, `Oracle`, `Agent`, and `Memory` without inventing another configuration path.

### 3.1 Observability Contract

The effective per-run profile must be observable from the same artifacts and telemetry that describe the run.

PR 1 should require:

- `data/runs/<run_id>/meta.json` includes the effective `ExperimentProfile` in serialized form
- `run_start` event payload config includes the effective profile, or a clearly named serialized profile field alongside the existing run config fields
- existing W&B run-level config, when enabled, is derived from the effective profile for overlapping runtime fields rather than rebuilt independently from raw CLI args

This is run-level observability only. Session-level W&B grouping and session artifacts remain out of scope for PR 1.

### 4. Defaults and Override Precedence

The precedence must be stable and testable:

1. global defaults from `simulation/config.py`
2. per-run overrides from the current CLI
3. future typed overrides from manifests or expanded runs

For this PR, only steps 1 and 2 are implemented.

There should be no hidden fallback to globals after a profile has been built. Once the profile exists, it is the effective runtime contract for that run.

This means:

- `config.py` remains the defaults baseline
- `ExperimentProfile` becomes the per-run source of truth
- future benchmark tooling can construct profiles without changing runtime APIs again

### 5. Scope Boundaries for PR 1

This PR intentionally stops before capability-aware behavior and benchmark execution features.

Included:

- typed runtime models
- typed profile builder/factory
- `main.py` wiring to build and pass a profile
- `SimulationEngine` compatibility layer for `profile`
- basic unit tests for defaults, overrides, and compatibility

Explicitly not included:

- new benchmark CLI
- manifest schema, loader, or matrix expansion
- prompt-surface changes
- backend capability toggles in `Agent`, `Oracle`, `World`, or `Memory`
- session aggregation
- session-level W&B integration
- benchmark-specific logic for survival, scarcity, or any named suite

### 6. Error Handling and Safety

This change should not introduce new failure modes into the simulation startup path.

Requirements:

- invalid or missing optional benchmark metadata should not break the base simulation path when using defaults
- profile construction from the current CLI should produce a fully usable profile for the existing runtime
- legacy engine construction without `profile` must still work
- non-`live` oracle modes are reserved in PR 1 and must not be exposed through the current CLI path
- `runtime.ticks=None` and `runtime.seed=None` must be treated as valid runtime values, not builder-only sentinels
- `wandb_logger` and `run_digest` must preserve current behavior because they remain outside the profile boundary in this PR
- default behavior should remain equivalent to the current base simulation

No new benchmark-specific validation layer is needed in this PR. The goal is to establish the typed contract and wiring, not to enforce the full manifest schema yet.

### 7. Tests

Add basic unit coverage for the new profile layer.

Required tests:

- default profile values mirror the current baseline from `simulation/config.py`
- default profile values for non-`config.py` fields match the explicit contract in this spec
- CLI-derived overrides change only the expected runtime fields
- nested dataclass defaults are independent and safe
- benchmark metadata, oracle settings, persistence settings, and world overrides are present with stable defaults
- `SimulationEngine(profile=...)` uses the profile path successfully
- `SimulationEngine(...)` with legacy kwargs still works
- legacy `SimulationEngine(...)` construction preserves `persistence=\"full\"` when no `profile` is supplied and no persistence override is passed
- if both `profile` and legacy kwargs are supplied, the profile path has explicit precedence
- `wandb_logger` and `run_digest` remain explicit engine inputs when `profile` is supplied
- serialized run metadata and W&B run config reflect the effective profile

These tests should stay narrow. The purpose is to lock down the contract and transition behavior, not to validate future benchmark functionality.

## What Does Not Change

- the current CLI surface in `main.py`
- the base simulation execution model
- current W&B run logging behavior
- prompt composition
- capability-specific backend behavior
- any existing benchmark scripts, even if they become legacy after later PRs

## Touch Points

| File | Change |
|---|---|
| `simulation/runtime_settings.py` | Add typed dataclasses for the runtime contract |
| `simulation/runtime_profiles.py` | Add default/profile construction helpers |
| `main.py` | Build an `ExperimentProfile` from CLI args and pass it to the engine |
| `simulation/engine.py` | Accept `profile`, normalize compatibility, expose effective profile |
| `simulation/event_emitter.py` | Carry serialized effective profile into run metadata and run-start payload |
| `simulation/wandb_logger.py` or `main.py` W&B setup | Build run-level W&B config from the effective profile |
| `tests/...` | Add unit tests for profile defaults, overrides, and engine precedence |

## Documentation Updates During Implementation

The implementation should also update:

- `project-cornerstone/00-master-plan/DECISION_LOG.md` to record the new runtime profile boundary
- the relevant architecture and benchmark-tracker docs if implementation details require clarification

No benchmark-manifest documentation changes are required in this PR because manifest work starts in the next slice.

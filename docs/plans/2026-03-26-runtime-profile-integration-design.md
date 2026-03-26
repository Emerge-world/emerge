# Runtime Profile Integration Design

- **Date:** 2026-03-26
- **Status:** Approved for implementation
- **Audience:** Emerge maintainers working on the simulation runtime, benchmark runtime, and prompt surfaces
- **Primary goal:** Make the real runtime obey `ExperimentProfile` for backend behavior instead of depending implicitly on globals for experimental capabilities
- **Focus:** `SimulationEngine`, `Agent`, `Oracle`, `World`, and `Memory`

## 1. Problem Statement

The repository already has a typed `ExperimentProfile` and the CLI/runtime boundary now passes that profile into `SimulationEngine`.

That solves configuration transport, but not runtime authority.

Today the effective simulation behavior is still split across two sources:

- `ExperimentProfile` controls run metadata, persistence mode, and normalized runtime fields such as width, height, seed, and agent count
- `simulation.config` still implicitly controls several experimental behaviors such as explicit planning, semantic memory, built-in action availability, reproduction unlocks, and world resource regeneration behavior

This leaves the benchmark runtime in an inconsistent state:

1. capability flags exist in the profile, but several backend paths do not actually obey them
2. some capabilities can still leak through side paths even if an arm intends to disable them
3. prompt-surface fidelity cannot be implemented safely until backend gating is authoritative
4. future benchmark runs would compare arms that differ in YAML but not fully in actual runtime behavior

The immediate gap to close is backend fidelity, not prompt wording.

## 2. Design Goals

This change should:

1. make `ExperimentProfile` the single per-run source of truth for experimental runtime behavior
2. inject runtime settings explicitly into `SimulationEngine`, `Agent`, `Oracle`, `World`, and `Memory`
3. enforce backend capability toggles for:
   - `explicit_planning`
   - `semantic_memory`
   - `innovation`
   - `item_reflection`
   - `social`
   - `teach`
   - `reproduction`
4. preserve current behavior when all capabilities are enabled
5. keep the runtime safe if an action arrives that should have been hidden by prompts later
6. support real world-resource overrides from the profile for benchmark scenarios

This change should not:

- redesign prompt templates yet
- introduce the benchmark CLI yet
- introduce W&B session reporting yet
- implement `world_fixture`
- implement `oracle.mode` execution variants yet
- implement frozen-precedent loading from `freeze_precedents_path` yet

## 3. Required Behavioral Semantics

### 3.1 General rule for disabled capabilities

If a capability is disabled, the backend must block it for real.

The user-approved backend behavior is:

- the action is removed from the agent's effective repertoire
- if the action still arrives for any reason, it is treated like an action the agent does not know
- the runtime should not emit benchmark-specific error types for this case

This means the runtime should fail closed without introducing a new experimental error protocol.

### 3.2 Capability-by-capability semantics

#### `explicit_planning=false`

- the planner must not run
- planning lifecycle events must not be emitted
- `Agent.decide_action()` must skip the planning branch entirely
- fallback and executor behavior must continue to work

#### `semantic_memory=false`

- episodic memory remains active
- task memory remains active
- semantic compression must not run
- semantic inheritance must not run
- semantic knowledge must not appear in backend-produced memory text

#### `innovation=false`

- `innovate` must not be an available action
- `Oracle` must not accept direct innovation attempts
- item-derived action discovery must also stop, because it creates new actions through a side path

#### `item_reflection=false`

- `reflect_item_uses` must not be an available action
- `Oracle` must not accept manual reflection attempts
- automatic post-craft affordance discovery should remain controlled by `innovation`, not by `item_reflection`

This keeps the semantics narrow:

- `innovation` controls whether new actions can exist at all
- `item_reflection` controls only the dedicated manual reflection action

#### `social=false`

- `communicate`, `give_item`, and `teach` must not be available actions
- `Oracle` must not execute any social action path when forced

#### `teach=false`

- only `teach` must be removed and blocked
- `communicate` and `give_item` may remain active if `social=true`

#### `reproduction=false`

- `reproduce` must never unlock
- `Oracle` must not execute reproduction
- `SimulationEngine` must never reach child spawning from a disabled reproduction path

## 4. Approaches Considered

### Option A: Read `ExperimentProfile` directly everywhere

Pass the full profile into each subsystem and read capability flags inline.

**Pros**

- small amount of new scaffolding
- easy to start

**Cons**

- benchmark schema leaks into domain logic
- repeated inline checks spread through multiple modules
- hard to keep backend and future prompt-surface policy aligned

### Option B: Gate only inside `SimulationEngine`

Leave most subsystems unchanged and filter actions centrally.

**Pros**

- smallest diff
- minimal constructor churn

**Cons**

- does not protect direct `Oracle` or `Memory` paths
- leaves hidden global dependencies in place
- does not satisfy the requirement that the subsystems themselves use profile settings

### Option C: Derive internal runtime settings from `ExperimentProfile` and inject them into subsystems

Keep `ExperimentProfile` as the external run boundary, but translate it into subsystem-oriented runtime settings for the real engine.

**Pros**

- clean separation between benchmark schema and runtime policy
- explicit constructor-level dependency injection
- backend and future prompt surface can share one capability policy
- best fit for deterministic testing

**Cons**

- requires touching multiple constructors and tests
- introduces a small amount of runtime-policy scaffolding

## 5. Chosen Direction

Adopt **Option C**.

`ExperimentProfile` remains the canonical external run contract. `SimulationEngine` becomes the point where that contract is normalized and translated into explicit runtime settings for the actual subsystems.

This design keeps the profile as the source of truth while avoiding a runtime that is tightly coupled to benchmark-oriented dataclasses.

## 6. Architecture

### 6.1 Runtime boundary

`main.py -> ExperimentProfile -> SimulationEngine` remains the main runtime boundary.

Inside the engine, a small internal runtime-policy layer should derive subsystem-specific settings from the normalized profile. This layer should be independent of prompt-template concerns.

Recommended shape:

- `simulation/runtime_policy.py`
- subsystem-oriented dataclasses and helper functions

Example responsibilities:

- derive which actions are enabled by capabilities
- derive whether semantic memory is active
- derive whether the planner is active
- derive world resource scaling values

### 6.2 Subsystem settings

The implementation should define a minimal internal runtime policy model such as:

- `AgentRuntimeSettings`
- `MemoryRuntimeSettings`
- `OracleRuntimeSettings`
- `WorldRuntimeSettings`

These should be executable settings, not benchmark metadata mirrors.

### 6.3 Engine responsibilities

`SimulationEngine` should:

1. deep-copy and normalize the incoming profile as it already does
2. derive runtime policy objects from that profile
3. pass those settings explicitly to:
   - `World`
   - `Oracle`
   - `Agent`
   - `Memory` indirectly through `Agent`
4. keep legacy constructor kwargs working by building a default profile when none is provided

This preserves current call sites such as `server/run_server.py` while making the profile the actual source of runtime behavior.

## 7. Component Changes

### 7.1 `simulation/engine.py`

The engine should stop treating profile-backed experimental behavior as an implementation detail hidden behind globals.

Required changes:

- derive internal runtime settings from `self.profile`
- construct `World(width, height, seed, runtime_settings=...)`
- construct `Oracle(world, llm, sim_logger, day_cycle, runtime_settings=...)`
- construct each `Agent(..., runtime_settings=..., memory_settings=...)`
- ensure child spawning uses the same settings as parent agents

The child path is important. If reproduction is enabled and a child is born, the child must inherit the same runtime capability policy as the run, not a default global behavior.

### 7.2 `simulation/agent.py`

`Agent` currently depends on globals for several experimental behaviors:

- planning enablement
- initial action list
- reproduction unlock behavior
- semantic-memory text composition through `Memory`

Required changes:

- accept explicit runtime settings for agent behavior
- build the initial action repertoire from enabled capabilities instead of always copying `INITIAL_ACTIONS`
- only unlock `reproduce` when the reproduction capability is enabled
- only enter the planner branch when explicit planning is enabled
- keep all-enabled behavior equivalent to current behavior

The effective action set should be capability-aware at construction time, so the backend naturally treats disabled actions as unknown.

### 7.3 `simulation/memory.py`

`Memory` should gain explicit settings for semantic-memory behavior.

Required changes:

- `add_knowledge()` becomes a no-op when semantic memory is disabled
- `should_compress()` becomes `False` when semantic memory is disabled
- `compress()` returns early without persisting semantic learnings when semantic memory is disabled
- `to_prompt()` omits the semantic knowledge section when disabled
- `inherit_from()` must not copy semantic entries when disabled

This keeps episodic memory and task memory alive while disabling only the semantic-memory layer.

### 7.4 `simulation/oracle.py`

`Oracle` is the final backend enforcement layer.

Required changes:

- accept explicit runtime settings
- reject disabled capability actions by treating them as unavailable for the agent
- block all direct and side-entry paths that would create new actions when `innovation=false`
- keep `teach` separately gated from `social`

In particular:

- `innovate` blocked by `innovation`
- `reflect_item_uses` blocked by `item_reflection`
- `communicate` and `give_item` blocked by `social`
- `teach` blocked by `social=false` or `teach=false`
- `reproduce` blocked by `reproduction=false`
- automatic affordance discovery blocked by `innovation=false`

### 7.5 `simulation/world.py`

`World` should start respecting real runtime overrides from `ExperimentProfile.world_overrides`.

Required changes:

- accept explicit runtime settings for resource behavior
- scale initial spawned resource quantities by `initial_resource_scale`
- scale regeneration chance by `regen_chance_scale`
- scale regeneration amount by `regen_amount_scale`

The goal is not to redesign world generation, only to make benchmark-controlled resource pressure real in the backend.

This step intentionally excludes:

- `world_fixture`
- map-loading or snapshot restore
- new terrain-generation profiles

## 8. Data Flow

The intended data flow is:

1. CLI or benchmark layer builds `ExperimentProfile`
2. `SimulationEngine` normalizes profile
3. Engine derives internal runtime settings
4. Engine constructs subsystems with explicit settings
5. Agent decisions and Oracle execution obey those settings
6. Event artifacts keep recording the normalized profile so the run remains self-describing

This preserves the existing artifact contract while making runtime behavior match the recorded profile.

## 9. Error Handling And Safety

The existing runtime safety rules still apply:

- LLM failures must never crash the run
- dead agents never act
- stats stay clamped
- Oracle remains the mutation authority

Additional rules for this feature:

- disabled capability actions fail closed as unavailable actions
- semantic-memory disablement must not break memory compression events or prompt rendering paths
- world resource scaling must stay deterministic for a fixed seed and profile
- all-enabled profiles must preserve current default behavior

## 10. Testing Strategy

This step should add minimal integration coverage using deterministic doubles rather than live models.

Recommended tests:

1. `explicit_planning=false`
   - use a planner double or monkeypatch to prove the planner path is not called
   - verify planning events are not emitted

2. `semantic_memory=false`
   - prove semantic compression does not persist knowledge
   - prove memory text omits `KNOWLEDGE`

3. `innovation=false`
   - force an `innovate` action and verify Oracle rejects it as unavailable
   - verify no precedent or action is added
   - verify auto-discovery is also blocked

4. `item_reflection=false`
   - force `reflect_item_uses` and verify it is unavailable

5. `social=false`
   - force `communicate`, `give_item`, and `teach`
   - verify Oracle rejects them as unavailable

6. `teach=false` with `social=true`
   - verify only `teach` is blocked while other social actions remain available

7. `reproduction=false`
   - verify `reproduce` never appears in agent actions
   - force a reproduction action and verify no `child_spawn` is produced

8. world overrides
   - verify initial resource quantities and regeneration behavior change when scales are set
   - keep tests deterministic with fixed seeds or direct RNG-friendly setup

These tests can be implemented with engine-level integration and focused subsystem tests. No live LLM is required.

## 11. What This Step Covers Versus The Prompt Step

### Backend paths that should respect the profile after this change

- whether the planner runs
- whether semantic memory exists and compresses
- whether innovation can create new actions
- whether manual item reflection can run
- whether social actions can execute
- whether teaching can execute independently of broader social capability
- whether reproduction can unlock or execute
- whether world resource pressure reflects benchmark overrides

### Paths intentionally deferred to the next prompt-surface step

- removing disabled actions from system prompts
- removing planning fields such as goal, subgoal, and plan status from prompts
- removing `KNOWLEDGE` and separating episodic vs semantic placeholders in prompt templates
- removing social prompt context such as nearby-agent sections, incoming messages, and relationships
- removing family and reproduction hints from prompts

The backend must be correct first so that prompt-surface changes become a fidelity layer, not the only enforcement layer.

## 12. Acceptance Criteria

- [ ] `SimulationEngine`, `Agent`, `Oracle`, `World`, and `Memory` receive explicit runtime settings derived from `ExperimentProfile`
- [ ] `config.py` remains a default source, not the hidden authority for experimental runtime behavior
- [ ] disabling a capability blocks it in the backend for real
- [ ] forced disabled actions are treated as unavailable actions for the agent
- [ ] all-enabled profiles preserve the current default runtime behavior
- [ ] world resource overrides affect actual backend behavior
- [ ] integration tests cover capability gating with deterministic doubles
- [ ] the design leaves prompt-surface changes for the next implementation step

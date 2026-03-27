# 01 — Architecture (Codebase-Aligned)

## Runtime Topology

- `main.py` runs headless simulations (CLI mode).
- `server/run_server.py` + `server/server.py` run FastAPI + WebSocket mode.
- `simulation/engine.py` is the orchestration core in both modes.
- `simulation/runtime_settings.py` defines the typed runtime dataclasses, while `simulation/runtime_profiles.py` builds defaults, CLI overrides, engine kwargs, and serialized artifacts.
- `main.py -> ExperimentProfile -> SimulationEngine` is the runtime boundary for CLI runs: `main.py` builds a profile from args, passes it into `SimulationEngine`, and the engine deep-copies and normalizes it into the effective `SimulationEngine.profile`.
- `SimulationEngine` derives a subsystem runtime policy from `ExperimentProfile` and injects it into `World`, `Agent`, and `Oracle`; `Memory` receives its settings through `Agent`, so backend capability enforcement and world overrides come from the profile rather than global defaults.

```
Agents -> Oracle -> World
   |        |        |
   v        v        v
Memory   Precedents Resources
  |
  v
PlanningState + Retrieval
   \        |        /
    \---- EventEmitter ----> data/runs/<run_id>/events.jsonl
                          \-> blobs/prompts + llm_raw
```

## Core Contracts

### Engine (`simulation/engine.py`)
- Owns world, agents, oracle, day cycle, lineage tracker, event emitter.
- Runs per-tick lifecycle and emits callback messages for web clients.
- Persists precedents and lineage on shutdown paths.
- Exposes an explicit `save_world_state()` snapshot export; world-state persistence is not automatic.

### Agent (`simulation/agent.py`)
- Maintains stats, dual memory, task memory, personality, inventory, relationships, and optional planning state.
- Accepts runtime settings for action repertoire and planning behavior; the explicit planner/executor loop is gated by the runtime policy.
- Owns a shared `PromptSurfaceBuilder` initialized from the effective runtime policy so executor prompts and planner-facing observation text use the same capability-aware composition boundary.
- Decides action via structured LLM response or deterministic fallback.
- Starts with a capability-filtered built-in action set; `reproduce` unlocks only when the runtime policy allows it and age requirements are met.

### Oracle (`simulation/oracle.py`)
- Sole authority applying action outcomes and world mutations.
- Uses precedents for deterministic reuse.
- Handles base actions, `drop_item` inventory placement/transfer, innovated actions, crafting, social actions, reproduction checks.
- Enforces runtime capability gates fail closed for disabled built-in actions and blocks innovation side-entry affordance discovery when innovation is disabled.
- Resolves `drop_item` inventory-to-world placement through world helpers so tile resource mutations stay Oracle-mediated.

### Event Layer (`simulation/event_emitter.py`)
- Always-on canonical telemetry per run.
- Includes lifecycle events needed for post-run reconstruction, including agent births and personality snapshots for initial and born agents.
- Stores prompt and raw LLM blobs deduplicated by hash.
- Supports planning lifecycle events in addition to decision/oracle events; see the canonical schema doc for the current emitted set and payloads.
- Observability contract: `meta.json` is written immediately on run initialization and includes the normalized `experiment_profile`; `run_start` echoes the same profile at `payload.config.experiment_profile`.
- Canonical schema: `project-cornerstone/01-architecture/events_schema.md`.

## Planning Loop

When explicit planning is enabled, agent cognition follows:

1. Observe current world and social state.
2. Retrieve relevant memory using deterministic scoring.
3. Replan if no usable plan exists, the current plan is stale, or a blocker appears.
4. Execute the next action against the active subgoal.
5. Emit planning traces into the canonical event stream.

## Invariants

1. Dead agents are never allowed to act.
2. Stats stay within clamped bounds.
3. Oracle remains the single mutation gateway for agent/world consequences.
4. Precedent lookups are deterministic for equivalent keys.
5. Event stream is append-only and machine-readable JSONL.

## Notable Supporting Modules

- `simulation/day_cycle.py`: day/sunset/night logic.
- `simulation/planning_state.py`: durable planner state and subgoal models.
- `simulation/prompt_surface.py`: shared capability-aware prompt composition for executor and planner surfaces.
- `simulation/retrieval.py`: deterministic memory relevance scoring.
- `simulation/planner.py`: structured planner call and plan parsing, now rendered through the shared prompt-surface builder instead of `prompt_loader` directly.
- `simulation/metrics_builder.py`: derives summary + timeseries from event streams, including personality-to-survival correlation metrics.
- `simulation/wandb_logger.py`: optional observer metrics to W&B, including world resource quantities grouped by type.
- `run_batch.py`: YAML-configured subprocess sweep runner.
- `server/event_bus.py`: async fan-out from simulation thread to WebSocket clients.

# 🧬 EMERGE — Master Plan (Codebase-Aligned)

_Last updated: 2026-03-26 (aligned with current repository state)_

## Vision

Build a persistent emergent world where LLM-driven agents survive, cooperate, invent, reproduce, and form long-term cultural dynamics under deterministic world rules.

## Current Product Reality

The repository is **beyond the original Phase 1 scope** and already includes:

- Rich world generation (OpenSimplex biomes + rivers + resources)
- Social actions (`communicate`, `give_item`, `teach`) with trust/relationship tracking
- Reproduction, inheritance, generations, and lineage persistence
- FastAPI + WebSocket simulation server and React UI
- Always-on event stream (`data/runs/<run_id>/events.jsonl`) and metrics builder
- Optional W&B experiment telemetry and batch execution (`run_batch.py`), including per-tick action and world-resource breakdowns
- Typed `ExperimentProfile` is the canonical per-run boundary for experimental runs; `config.py` now acts as defaults-only input, and run artifacts persist the effective normalized profile

## Phase Status (as implemented)

### Phase 0 — Foundation ✅
- Grid world + agent loop + Oracle validation + fallback without LLM

### Phase 1 — Intelligence ✅
- Dual memory (episodic + semantic)
- Prompt template system (`prompts/` + `prompt_loader.py`)
- Innovation validation with effect bounds, categories, prerequisites
- Precedent persistence

### Phase 2 — Survival Depth ✅
- Day/sunset/night cycle with vision and energy modifiers
- Expanded biome tiles and resource model
- Inventory + pickup/drop_item + crafting via innovations
- Passive healing, tile-specific risks/rest bonuses
- Item affordance discovery: crafted tools unlock concrete verb actions via the normal innovation pipeline (auto on first craft; manual via `reflect_item_uses`)

### Phase 3 — Social ✅
- Personality traits and nearby-agent perception
- Communication and relationship/trust system
- Cooperation (`give_item`) and deterministic knowledge transfer (`teach`)

### Phase 4 — Evolution 🚧 (partially implemented)
- ✅ Reproduction gating + parent costs + child spawn
- ✅ Trait inheritance/mutation and family prompt context
- ✅ Lineage tracking/persistence
- ⏳ Emergent language protocols and role specialization
- ⏳ Selection pressure analytics across generations

### Phase 5 — Visualization & Analysis 🚧 (partially implemented)
- ✅ Real-time web UI (FastAPI + WebSocket + React/Vite)
- ✅ Live world/agent state panels and pause/resume controls
- ✅ Canonical event stream + metrics extraction pipeline
- ⏳ Replay UI and timeline scrubbing
- ⏳ Genealogy visualization and richer analytics dashboards

## Priority Next Arc (recommended)

1. **Metrics maturity:** standard KPI schema (survival, innovation utility, cooperation, lineage fitness, personality-to-survival correlation)
2. **Replayability:** event-sourced replay in UI from persisted runs
3. **Culture experiments:** emergent vocabulary/coordination protocols and measurement
4. **World pressure:** weather and scarcity cycles to test adaptation robustness
5. **Determinism hardening:** stronger oracle/audit checks for long-run reproducibility

## Constraints to preserve

1. LLM calls must always have robust fallback paths.
2. Agent stats remain clamped and dead agents never act.
3. Oracle + precedents preserve deterministic outcomes where intended.
4. Keep changes atomic (one coherent feature per PR).
5. Update cornerstone docs whenever architecture or behavior shifts.

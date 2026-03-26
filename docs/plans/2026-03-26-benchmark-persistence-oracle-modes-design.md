# Benchmark Persistence And Oracle Modes Design

**Date:** 2026-03-26

## Goal

Make benchmark runtime behavior explicit for persistence reuse and oracle novelty handling so runs can compare `live`, `frozen`, and `symbolic` oracle policies without relying on seed-derived implicit behavior.

## Problem Statement

The repository already models `persistence.mode`, `persistence.clean_before_run`, `oracle.mode`, and `oracle.freeze_precedents_path` in [runtime_settings.py](/home/gusy/emerge/simulation/runtime_settings.py), but the execution path still behaves implicitly:

- `SimulationEngine` auto-loads local precedents and lineage based on the seed-derived default paths;
- persistence cleanup exists only in benchmark-specific scripts, not in the typed runtime boundary;
- `Oracle` still learns or falls back permissively on novel cases in ways that do not distinguish `live`, `frozen`, and `symbolic`;
- run artifacts serialize the profile, but they do not trace what persistence was actually cleaned or which precedent source was loaded.

This makes benchmark comparisons noisy and hides the difference between a fresh run, a replay against frozen precedents, and a human-curated symbolic ruleset.

## Scope

In scope:

- explicit runtime enforcement for `persistence.mode = none|oracle|lineage|full`;
- explicit runtime enforcement for `persistence.clean_before_run`;
- explicit oracle behavior for `oracle.mode = live|frozen|symbolic`;
- required support for `freeze_precedents_path` in `frozen` and `symbolic`;
- `meta.json` trace fields for persistence cleanup and oracle source selection;
- tests that make the behavior difference between `live`, `frozen`, and `symbolic` obvious.

Out of scope:

- introducing a new symbolic DSL or precedent file format;
- changing benchmark manifest top-level shape;
- reworking the whole oracle into separate backend classes;
- benchmark runner/session orchestration beyond what is needed for runtime correctness.

## Constraints

- Benchmark behavior must not depend on the seed as an implicit persistence policy.
- `clean_before_run` must be reflected in run metadata even when nothing was removed.
- `symbolic` must reject or mark open novelty as unresolved; it must never approve novelty by default.
- `freeze_precedents_path` is required for `frozen` and `symbolic`, and a missing or invalid file is a startup error.
- The existing precedent JSON format remains the input format for frozen and symbolic runs in this change.

## Alternatives Considered

### 1. Minimal conditionals in engine and oracle

Add a few mode checks where behavior currently occurs.

Pros:

- smallest diff;
- quickest path to green tests.

Cons:

- semantics stay scattered;
- easier to reintroduce implicit seed-based reuse later;
- harder to test and reason about novelty behavior.

### 2. Separate oracle backends for live, frozen, and symbolic

Extract dedicated backends or strategy classes.

Pros:

- clean conceptual separation;
- highly testable boundaries.

Cons:

- larger refactor than the issue requires;
- touches too many call sites for the current milestone.

### 3. Explicit runtime policy with focused helpers

Keep the current engine/oracle structure but add explicit load/cleanup/save policy in the engine and explicit novelty policy in the oracle.

Pros:

- aligns with the existing `ExperimentProfile` contract;
- keeps the change local to the runtime boundary;
- provides precise metadata and tests without a broad refactor.

Cons:

- less architecturally pure than a full strategy extraction.

## Decision

Adopt option 3.

The implementation will keep `SimulationEngine` and `Oracle` as the main runtime entry points, but make persistence and oracle mode behavior explicit through small internal helpers and metadata traces.

## Runtime Semantics

### Persistence modes

- `none`: do not load or save local precedents or local lineage.
- `oracle`: load/save local precedents only when the oracle mode permits local oracle persistence.
- `lineage`: load/save local lineage only.
- `full`: combine `oracle` and `lineage`.

The seed remains only a naming input for default local file paths. It no longer implies whether state is reused.

### `clean_before_run`

Cleanup is evaluated before subsystem load.

- `oracle|full`: remove the local precedents file if present.
- `lineage|full`: remove the local lineage file if present.
- `none`: nothing is removed.

Cleanup never touches `freeze_precedents_path`.

The run metadata records:

- whether cleanup was requested;
- which local paths were candidates for cleanup;
- which paths were actually removed.

### Oracle modes

- `live`:
  - may consult the LLM;
  - may create new precedents;
  - may save local precedents if persistence includes oracle state.
- `frozen`:
  - loads precedents only from `freeze_precedents_path`;
  - never creates or mutates precedents;
  - never saves oracle precedents at run end;
  - novel cases are closed-world misses, not permissive defaults.
- `symbolic`:
  - also loads from `freeze_precedents_path`;
  - treats that file as a human-curated ruleset/recipe set;
  - never creates or mutates precedents;
  - novel open cases return an explicit unresolved/rejected result rather than success by default.

### `freeze_precedents_path`

- optional in `live`;
- required and non-empty in `frozen` and `symbolic`;
- filesystem validation happens at runtime startup;
- missing, unreadable, or invalid JSON causes the run to fail fast with a clear error.

## Engine Changes

`SimulationEngine` gains explicit startup policy:

1. Resolve local default paths for precedents and lineage.
2. Apply `clean_before_run` to the local paths allowed by `persistence.mode`.
3. Load state according to `persistence.mode` and `oracle.mode`.

Load policy:

- `live`:
  - local precedents load only when `persistence.mode in {"oracle", "full"}` and cleanup did not remove them;
  - local lineage loads only when `persistence.mode in {"lineage", "full"}` and cleanup did not remove it.
- `frozen` and `symbolic`:
  - precedents load from `freeze_precedents_path` regardless of `persistence.mode`;
  - local seed-derived precedents are ignored;
  - local lineage still follows `persistence.mode`.

Save policy:

- oracle precedents save only in `live` when `persistence.mode in {"oracle", "full"}`;
- lineage saves only when `persistence.mode in {"lineage", "full"}`.

## Oracle Changes

The oracle gains an explicit novelty policy helper instead of allowing each call site to decide implicitly.

In `live`, existing behavior is preserved where a miss may call the LLM and then store a precedent.

In `frozen` and `symbolic`, a precedent miss becomes a closed-world miss:

- no LLM call;
- no default approval;
- no precedent write;
- return a consistent unresolved/rejected payload.

Affected novelty sites:

- physical reflection in `_oracle_reflect_physical`;
- innovation validation in `_validate_innovation`;
- custom action situation outcomes in `_resolve_custom_action`;
- cached eat-effect lookups in `_get_item_eat_effect`;
- item affordance discovery in `_discover_item_affordances` (effectively live-only).

`symbolic` uses the same JSON input structure as other precedent files for this milestone. The distinction is semantic policy, not a new format.

## Artifact Traceability

`meta.json` keeps serializing `experiment_profile` and additionally gains two trace blocks:

### `persistence_trace`

- `mode`
- `clean_before_run`
- `local_precedents_path`
- `local_lineage_path`
- `cleanup_candidates`
- `cleaned_paths`

### `oracle_trace`

- `mode`
- `freeze_precedents_path`
- `precedents_loaded_from`
- `novelty_policy`

This makes the effective runtime policy visible without inferring behavior from the seed or from ad hoc benchmark scripts.

## Validation

The manifest schema already accepts the required fields, so the new validation need is semantic validation on the effective expanded profile:

- if `oracle.mode in {"frozen", "symbolic"}`, then `freeze_precedents_path` must be present in the effective profile;
- invalid combinations should fail expansion with a clear scenario/arm-specific error;
- runtime startup still validates actual filesystem existence and parseability.

## Testing Strategy

Add or extend tests so they distinguish the modes directly:

- schema and expander tests for effective-profile validation of `freeze_precedents_path`;
- engine profile tests for cleanup behavior and `meta.json` traces;
- oracle persistence/runtime tests for:
  - `live` learning on miss;
  - `frozen` replaying a supplied snapshot without learning;
  - `symbolic` using curated precedents and rejecting unresolved novelty.

Tests should make clear that `frozen` and `symbolic` are both closed to novelty, while `symbolic` is the human-curated policy variant used for benchmark comparison.

## Edge Cases To Leave Explicit

- This change does not version precedent semantics beyond the existing JSON schema; a stale symbolic snapshot is still a user responsibility.
- `symbolic` uses the same storage shape as current precedents, so richer human-authored rule annotations would require a later format extension.
- Local lineage can still be persisted independently of oracle mode; this is intentional so reproduction benchmarks can compare oracle policies without losing lineage data.

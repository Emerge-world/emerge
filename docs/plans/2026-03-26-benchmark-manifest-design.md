# Declarative Benchmark Manifest Design

**Date:** 2026-03-26

## Goal

Define a typed, declarative benchmark manifest system that validates and expands benchmark suites from YAML without depending on `run_batch.py` or the legacy flat `experiments.yaml`.

## Problem Statement

The repository already has a typed runtime boundary in [simulation/runtime_settings.py](/home/gusy/emerge/simulation/runtime_settings.py), but benchmark configuration is still split between an older batch runner, benchmark-specific files, and an earlier manifest shape that is not aligned with `ExperimentProfile`.

For the current refactor phase, the repository needs a greenfield manifest system that can:

- define benchmark suites in versioned YAML files;
- validate them with clear, path-specific errors;
- expand deterministic `seed_sets x scenarios x arms` matrices into per-run payloads;
- generate stable run names before any execution layer exists.

This phase must stop at validation and expansion. It must not execute simulations, add benchmark-specific Python logic, or provide compatibility with the old flat YAML system.

## Scope

In scope:

- new benchmark manifest YAML schema;
- typed manifest loader and validator;
- deterministic matrix expansion;
- stable run naming;
- example manifests;
- tests for validation and expansion.

Out of scope:

- benchmark execution;
- session orchestration;
- aggregation and criteria evaluation logic;
- W&B reporting implementation;
- compatibility wrappers around `run_batch.py` or `experiments.yaml`.

## Context And Constraints

- The authoritative runtime contract is `ExperimentProfile` in [simulation/runtime_settings.py](/home/gusy/emerge/simulation/runtime_settings.py).
- The refactor tracker explicitly requires a greenfield benchmark system with manifests under `benchmarks/manifests/` and modules under `simulation/benchmark/`.
- `PyYAML` is already available in the lockfile, so YAML loading does not require a new dependency.
- The repository rules require readable validation errors, no benchmark-specific Python, and tests before claiming completion.

## Alternatives Considered

### 1. Typed manifest models plus manual validation

Model the manifest with repository-owned types in `schema.py` and validate each section with explicit code.

Pros:

- matches the existing typed runtime model;
- keeps dependency footprint unchanged;
- enables precise error messages with exact manifest paths;
- avoids silently accepting legacy or ad hoc keys.

Cons:

- requires more validation code than a looser dictionary-based approach.

### 2. Dictionary-first manifest with ad hoc validation

Load YAML into nested dictionaries and validate only where needed.

Pros:

- lower initial implementation cost.

Cons:

- weaker contract;
- higher risk of late failures during expansion;
- more room for old flat-YAML patterns to creep back in.

### 3. External schema library

Introduce a framework such as Pydantic or JSON Schema for manifest validation.

Pros:

- strong declarative validation features.

Cons:

- extra dependency and concepts;
- less direct control over repository-specific error formatting;
- unnecessary for the current bounded manifest domain.

## Decision

Adopt **typed manifest models plus manual validation**.

The manifest system will define repository-owned manifest models in `simulation/benchmark/schema.py`, keep the runtime contract aligned with `ExperimentProfile`, and reject unknown keys at every level.

## Target File Layout

```text
benchmarks/
  manifests/
    example_minimal.yaml
    example_small_suite.yaml

simulation/
  benchmark/
    __init__.py
    schema.py
    loader.py
    expander.py

tests/
  test_benchmark_schema.py
  test_benchmark_expander.py
```

## Manifest Shape

The new manifest is a closed schema with these top-level keys only:

- `version`
- `benchmark`
- `defaults`
- `seed_sets`
- `scenarios`
- `arms`
- `matrix`
- `metrics`
- `criteria`
- `wandb`

### `version`

- literal integer `1`

### `benchmark`

Required:

- `id: str`
- `version: str`

Optional:

- `description: str`

### `defaults`

Base overrides applied to every expanded run. This is not a full `ExperimentProfile` payload from the user point of view, but it uses the same nested shape.

Allowed subsections:

- `runtime`
- `capabilities`
- `persistence`
- `oracle`
- `world_overrides`
- `tags`

### `seed_sets`

Mapping of seed-set IDs to non-empty integer lists.

Example:

```yaml
seed_sets:
  smoke: [11, 22]
  eval: [101, 202, 303]
```

### `scenarios`

Mapping of scenario IDs to partial typed overrides. Each scenario may define any subset of the same allowed subsections as `defaults`.

### `arms`

Mapping of arm IDs to partial typed overrides. Each arm may define any subset of the same allowed subsections as `defaults`.

### `matrix`

Closed selection lists that determine expansion order and membership:

- `seed_sets`
- `scenarios`
- `arms`

Each list must be non-empty, contain no duplicates, and reference existing IDs.

### `metrics`

Required:

- `primary: list[str]`

Optional:

- `secondary: list[str]`

At least one primary metric is required.

### `criteria`

List of typed criterion definitions. For this phase, criteria are validated structurally and preserved in the expanded JSON, but not executed.

### `wandb`

Typed W&B settings preserved for later phases. For this phase, they are validated structurally and copied through expansion, but not used to execute anything.

## Typed Override Policy

The manifest accepts only explicit, known keys. There is no free-form configuration map.

The accepted nested runtime sections are aligned with [simulation/runtime_settings.py](/home/gusy/emerge/simulation/runtime_settings.py):

- `runtime`
  - `use_llm`
  - `model`
  - `agents`
  - `ticks`
  - `seed`
  - `width`
  - `height`
  - `start_hour`
- `capabilities`
  - `explicit_planning`
  - `semantic_memory`
  - `innovation`
  - `item_reflection`
  - `social`
  - `teach`
  - `reproduction`
- `persistence`
  - `mode`
  - `clean_before_run`
- `oracle`
  - `mode`
  - `freeze_precedents_path`
- `world_overrides`
  - `initial_resource_scale`
  - `regen_chance_scale`
  - `regen_amount_scale`
  - `world_fixture`
- `tags`
  - `list[str]`

The manifest will reject:

- unknown top-level keys;
- unknown keys inside any subsection;
- legacy flat keys such as `ticks`, `no_llm`, or `wandb` under `defaults`;
- benchmark-specific ad hoc options.

## Validation Rules

Validation is split into structural and semantic checks.

Structural checks:

- expected mapping/list/scalar types;
- required keys present;
- string IDs are non-empty;
- integer, boolean, float, and enum fields have exact types;
- top-level and nested unknown keys are rejected.

Semantic checks:

- `version == 1`;
- `seed_sets.<id>` is non-empty;
- matrix references exist;
- matrix lists contain no duplicates;
- `metrics.primary` is non-empty;
- expanded run IDs must be unique.

Validation errors are accumulated and reported together rather than failing at the first issue.

## Error Reporting

The loader raises a dedicated `ManifestValidationError` with a multi-line message.

Example format:

```text
Invalid benchmark manifest /abs/path/to/file.yaml
- version: expected literal 1
- benchmark.id: must be a non-empty string
- seed_sets.smoke[1]: expected int, got '22'
- matrix.scenarios[0]: unknown scenario 'night_start'
- arms.no_llm.runtime.foo: is not allowed
```

The message format must optimize for direct repair:

- exact manifest path;
- one bullet per issue;
- stable ordering;
- no Python trace noise in the human-facing message.

## Loader Design

`simulation/benchmark/loader.py` owns only I/O and parse orchestration.

Responsibilities:

- read YAML from disk;
- convert YAML syntax errors into a readable manifest error;
- pass the parsed document into schema validation;
- return a typed `BenchmarkManifest`.

Non-responsibilities:

- matrix expansion;
- profile merge logic;
- benchmark execution.

## Expansion Design

`simulation/benchmark/expander.py` takes a validated `BenchmarkManifest` and materializes deterministic per-run payloads.

Expansion order is fixed:

1. iterate `matrix.seed_sets` in listed order;
2. iterate seeds within each seed set in listed order;
3. iterate `matrix.scenarios` in listed order;
4. iterate `matrix.arms` in listed order.

Per-run merge order is fixed:

1. repository baseline from `build_default_profile()`;
2. manifest `defaults`;
3. scenario override;
4. arm override;
5. injected seed and benchmark metadata.

The output of expansion is a list of fully materialized run dictionaries, each containing:

- `run_id`
- `benchmark`
- `matrix`
- `profile`
- `metrics`
- `criteria`
- `wandb`

The `profile` block is complete and execution-ready from a future runner's perspective.

## Stable Run Naming

Run naming must be semantic and deterministic, not counter-based.

Proposed format:

```text
{benchmark_id}__v{benchmark_version}__ss-{seed_set}__sc-{scenario}__arm-{arm}__seed-{seed}
```

Example:

```text
survival_v1__v1__ss-smoke__sc-default_day__arm-full__seed-11
```

Rules:

- use manifest IDs only;
- preserve semantic identity;
- do not include timestamps, session IDs, or counters;
- ensure names are unique within an expanded suite;
- apply conservative ASCII slug normalization only where needed.

## Example Small Manifest

```yaml
version: 1

benchmark:
  id: survival_v1
  version: "1"
  description: Comparative survival sanity benchmark

defaults:
  runtime:
    agents: 3
    ticks: 300
    width: 15
    height: 15
    start_hour: 8
    use_llm: true
    model: qwen2.5:3b
  capabilities:
    explicit_planning: true
    semantic_memory: true
    innovation: true
    item_reflection: true
    social: true
    teach: true
    reproduction: true
  persistence:
    mode: none
    clean_before_run: true
  oracle:
    mode: live
  world_overrides: {}
  tags: [sanity]

seed_sets:
  smoke: [11, 22]

scenarios:
  default_day: {}
  night_start:
    runtime:
      start_hour: 20

arms:
  full: {}
  no_llm:
    runtime:
      use_llm: false

matrix:
  seed_sets: [smoke]
  scenarios: [default_day, night_start]
  arms: [full, no_llm]

metrics:
  primary:
    - summary.agents.survival_rate

criteria: []

wandb:
  enabled: false
```

## Example Expanded Run

Example output entry for the first run of the small suite:

```json
{
  "run_id": "survival_v1__v1__ss-smoke__sc-default_day__arm-full__seed-11",
  "benchmark": {
    "id": "survival_v1",
    "version": "1"
  },
  "matrix": {
    "seed_set": "smoke",
    "scenario_id": "default_day",
    "arm_id": "full",
    "seed": 11
  },
  "profile": {
    "runtime": {
      "use_llm": true,
      "model": "qwen2.5:3b",
      "agents": 3,
      "ticks": 300,
      "seed": 11,
      "width": 15,
      "height": 15,
      "start_hour": 8
    },
    "capabilities": {
      "explicit_planning": true,
      "semantic_memory": true,
      "innovation": true,
      "item_reflection": true,
      "social": true,
      "teach": true,
      "reproduction": true
    },
    "persistence": {
      "mode": "none",
      "clean_before_run": true
    },
    "oracle": {
      "mode": "live",
      "freeze_precedents_path": null
    },
    "benchmark": {
      "benchmark_id": "survival_v1",
      "benchmark_version": "1",
      "scenario_id": "default_day",
      "arm_id": "full",
      "seed_set": "smoke",
      "session_id": null,
      "tags": ["sanity"]
    },
    "world_overrides": {
      "initial_resource_scale": null,
      "regen_chance_scale": null,
      "regen_amount_scale": null,
      "world_fixture": null
    }
  },
  "metrics": {
    "primary": ["summary.agents.survival_rate"],
    "secondary": []
  },
  "criteria": [],
  "wandb": {
    "enabled": false
  }
}
```

## Test Strategy

Add focused tests only for the current phase.

### `tests/test_benchmark_schema.py`

Cover:

- valid minimal manifest;
- missing required keys;
- unknown keys at multiple levels;
- invalid types;
- invalid enum values;
- empty seed sets;
- unknown matrix references;
- duplicate matrix entries;
- readable aggregated error output.

### `tests/test_benchmark_expander.py`

Cover:

- deterministic cross-product expansion;
- expansion order stability;
- deep merge order `defaults -> scenario -> arm`;
- correct `runtime.seed` injection;
- correct benchmark metadata injection;
- tag concatenation with de-duplication;
- stable `run_id`;
- expected JSON payload for a small suite.

## Follow-On Work

Later phases can reuse the same expanded payloads to build:

- `benchmark.py validate`;
- `benchmark.py expand`;
- generic run execution;
- session artifacts;
- aggregation and decisions;
- W&B session reporting.

This phase deliberately stops earlier so that validation and expansion can stabilize before execution code exists.

# Benchmark Manifest Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a typed declarative benchmark manifest system that validates YAML manifests and expands deterministic run payloads without any simulation execution.

**Architecture:** Add a new `simulation/benchmark/` package with a closed-schema manifest model, a loader that turns YAML into validated manifest objects, and an expander that materializes complete per-run payloads from `seed_sets x scenarios x arms`. Reuse the existing `ExperimentProfile` runtime boundary for expanded profiles, but keep manifest models separate because manifests describe partial overrides and matrix references rather than already-expanded runs.

**Tech Stack:** Python 3.12, dataclasses, PyYAML, pytest, existing `simulation.runtime_settings` and `simulation.runtime_profiles`

---

### Task 1: Create the benchmark package scaffold

**Files:**
- Create: `simulation/benchmark/__init__.py`
- Test: none

**Step 1: Create the package file**

```python
"""Benchmark manifest loading and expansion."""
```

**Step 2: Verify import path**

Run: `uv run python -c "import simulation.benchmark; print(simulation.benchmark.__doc__)"`
Expected: prints the package docstring without import errors.

**Step 3: Commit**

```bash
git add simulation/benchmark/__init__.py
git commit -m "chore: add benchmark package scaffold"
```

### Task 2: Add failing schema validation tests

**Files:**
- Create: `tests/test_benchmark_schema.py`

**Step 1: Write the failing tests**

```python
def test_load_manifest_accepts_minimal_valid_manifest(tmp_path):
    ...


def test_load_manifest_rejects_unknown_top_level_key(tmp_path):
    ...


def test_load_manifest_rejects_unknown_nested_key(tmp_path):
    ...


def test_load_manifest_rejects_unknown_matrix_reference(tmp_path):
    ...


def test_load_manifest_reports_multiple_errors_together(tmp_path):
    ...
```

**Step 2: Run the tests to confirm failure**

Run: `uv run pytest tests/test_benchmark_schema.py -v`
Expected: FAIL because `simulation.benchmark.loader` and validation code do not exist yet.

**Step 3: Commit**

```bash
git add tests/test_benchmark_schema.py
git commit -m "test: add failing benchmark schema tests"
```

### Task 3: Implement typed manifest models and validation

**Files:**
- Create: `simulation/benchmark/schema.py`
- Modify: `simulation/benchmark/__init__.py`
- Test: `tests/test_benchmark_schema.py`

**Step 1: Add validation types and error class**

```python
@dataclass(slots=True)
class ManifestValidationIssue:
    path: str
    message: str


class ManifestValidationError(ValueError):
    ...
```

**Step 2: Add typed manifest dataclasses**

```python
@dataclass(slots=True)
class BenchmarkInfo:
    id: str
    version: str
    description: str | None = None


@dataclass(slots=True)
class ProfileOverride:
    runtime: dict[str, object] | None = None
    capabilities: dict[str, object] | None = None
    persistence: dict[str, object] | None = None
    oracle: dict[str, object] | None = None
    world_overrides: dict[str, object] | None = None
    tags: list[str] | None = None
```

**Step 3: Add a `BenchmarkManifest` dataclass and validator entrypoint**

```python
@dataclass(slots=True)
class BenchmarkManifest:
    version: int
    benchmark: BenchmarkInfo
    defaults: ProfileOverride
    seed_sets: dict[str, list[int]]
    scenarios: dict[str, ProfileOverride]
    arms: dict[str, ProfileOverride]
    matrix: MatrixSelection
    metrics: MetricsConfig
    criteria: list[dict[str, object]]
    wandb: dict[str, object]
```

**Step 4: Implement closed-schema validation helpers**

```python
def validate_manifest_document(document: object, *, source: str | None = None) -> BenchmarkManifest:
    ...
```

Include explicit checks for:

- allowed top-level keys;
- required sections;
- known nested keys only;
- enum values for persistence/oracle modes;
- non-empty IDs and seed sets;
- matrix references and duplicate entries;
- non-empty `metrics.primary`.

**Step 5: Re-export the public API**

```python
from simulation.benchmark.schema import BenchmarkManifest, ManifestValidationError
```

**Step 6: Run the schema tests**

Run: `uv run pytest tests/test_benchmark_schema.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add simulation/benchmark/__init__.py simulation/benchmark/schema.py tests/test_benchmark_schema.py
git commit -m "feat: add typed benchmark manifest validation"
```

### Task 4: Add failing loader tests for YAML parsing and error formatting

**Files:**
- Modify: `tests/test_benchmark_schema.py`

**Step 1: Add loader-focused failing tests**

```python
def test_load_manifest_parses_yaml_and_returns_manifest(tmp_path):
    ...


def test_load_manifest_wraps_yaml_syntax_errors(tmp_path):
    ...


def test_load_manifest_includes_source_path_in_validation_error(tmp_path):
    ...
```

**Step 2: Run a targeted test selection**

Run: `uv run pytest tests/test_benchmark_schema.py -k "load_manifest" -v`
Expected: FAIL because the loader has not been implemented yet.

**Step 3: Commit**

```bash
git add tests/test_benchmark_schema.py
git commit -m "test: add failing benchmark loader tests"
```

### Task 5: Implement YAML loader

**Files:**
- Create: `simulation/benchmark/loader.py`
- Test: `tests/test_benchmark_schema.py`

**Step 1: Implement `load_manifest`**

```python
def load_manifest(path: str | Path) -> BenchmarkManifest:
    with path.open("r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    return validate_manifest_document(document, source=str(path))
```

**Step 2: Wrap YAML parser errors into `ManifestValidationError`**

```python
except yaml.YAMLError as exc:
    raise ManifestValidationError.from_yaml_error(...)
```

**Step 3: Run loader and schema tests**

Run: `uv run pytest tests/test_benchmark_schema.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add simulation/benchmark/loader.py tests/test_benchmark_schema.py
git commit -m "feat: add benchmark manifest loader"
```

### Task 6: Add failing expander tests

**Files:**
- Create: `tests/test_benchmark_expander.py`

**Step 1: Write the failing tests**

```python
def test_expand_manifest_builds_seed_scenario_arm_cross_product(tmp_path):
    ...


def test_expand_manifest_applies_defaults_then_scenario_then_arm(tmp_path):
    ...


def test_expand_manifest_generates_stable_run_ids(tmp_path):
    ...


def test_expand_manifest_matches_expected_small_suite_payload(tmp_path):
    ...
```

**Step 2: Run the tests to confirm failure**

Run: `uv run pytest tests/test_benchmark_expander.py -v`
Expected: FAIL because `simulation.benchmark.expander` does not exist yet.

**Step 3: Commit**

```bash
git add tests/test_benchmark_expander.py
git commit -m "test: add failing benchmark expander tests"
```

### Task 7: Implement expansion helpers and stable run naming

**Files:**
- Create: `simulation/benchmark/expander.py`
- Test: `tests/test_benchmark_expander.py`

**Step 1: Implement stable run naming**

```python
def build_run_id(*, benchmark_id: str, benchmark_version: str, seed_set: str, scenario_id: str, arm_id: str, seed: int) -> str:
    return (
        f"{benchmark_id}__v{benchmark_version}"
        f"__ss-{seed_set}__sc-{scenario_id}__arm-{arm_id}__seed-{seed}"
    )
```

**Step 2: Implement profile merge helpers**

```python
def apply_override(profile: ExperimentProfile, override: ProfileOverride) -> None:
    ...
```

Merge order:

- `build_default_profile()`
- manifest `defaults`
- scenario override
- arm override
- injected run seed and benchmark metadata

**Step 3: Implement expansion entrypoint**

```python
def expand_manifest(manifest: BenchmarkManifest, *, selected_seed_sets: Iterable[str] | None = None) -> list[dict[str, object]]:
    ...
```

Each expanded item must include:

- `run_id`
- `benchmark`
- `matrix`
- `profile`
- `metrics`
- `criteria`
- `wandb`

**Step 4: Ensure deterministic ordering and uniqueness**

Reject duplicate `run_id` values with a clear error if they ever appear.

**Step 5: Run expander tests**

Run: `uv run pytest tests/test_benchmark_expander.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add simulation/benchmark/expander.py tests/test_benchmark_expander.py
git commit -m "feat: add benchmark manifest expansion"
```

### Task 8: Add example manifests

**Files:**
- Create: `benchmarks/manifests/example_minimal.yaml`
- Create: `benchmarks/manifests/example_small_suite.yaml`
- Test: `tests/test_benchmark_schema.py`
- Test: `tests/test_benchmark_expander.py`

**Step 1: Add a minimal valid manifest**

Include:

- one benchmark;
- one seed set;
- one scenario;
- one arm;
- one primary metric;
- empty `criteria`;
- minimal `wandb` block.

**Step 2: Add a small suite manifest**

Include:

- one seed set with two seeds;
- two scenarios;
- two arms;
- enough overrides to exercise expansion merges.

**Step 3: Point tests at the example manifests where helpful**

Use the small suite for the expected expanded JSON test if that keeps fixtures readable.

**Step 4: Run targeted benchmark tests**

Run: `uv run pytest tests/test_benchmark_schema.py tests/test_benchmark_expander.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add benchmarks/manifests/example_minimal.yaml benchmarks/manifests/example_small_suite.yaml tests/test_benchmark_schema.py tests/test_benchmark_expander.py
git commit -m "docs: add example benchmark manifests"
```

### Task 9: Update project records for the new benchmark boundary

**Files:**
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Modify: `project-cornerstone/00-master-plan/MASTER_PLAN.md`

**Step 1: Add a decision log entry**

Record that benchmark manifests now use a closed, typed schema aligned with `ExperimentProfile`, and that validation/expansion are greenfield and independent from `run_batch.py`.

**Step 2: Update the master plan status**

Note that manifest schema, loader, and matrix expansion are implemented or in progress under the benchmark refactor epic.

**Step 3: Run a quick grep review**

Run: `rg -n "benchmark manifest|typed benchmark|run_batch" project-cornerstone/00-master-plan/DECISION_LOG.md project-cornerstone/00-master-plan/MASTER_PLAN.md`
Expected: shows the new benchmark-manifest notes in both files.

**Step 4: Commit**

```bash
git add project-cornerstone/00-master-plan/DECISION_LOG.md project-cornerstone/00-master-plan/MASTER_PLAN.md
git commit -m "docs: record benchmark manifest boundary"
```

### Task 10: Run final verification for the phase

**Files:**
- Modify: none

**Step 1: Run focused benchmark tests**

Run: `uv run pytest tests/test_benchmark_schema.py tests/test_benchmark_expander.py -v`
Expected: PASS

**Step 2: Run the repository fast test suite**

Run: `uv run pytest -m "not slow"`
Expected: PASS

**Step 3: Review git status**

Run: `git status --short`
Expected: clean working tree.

**Step 4: Commit any remaining verification-only updates if needed**

```bash
git add -A
git commit -m "test: verify benchmark manifest phase"
```

Only do this step if verification exposed a real repository change that still needs to be recorded.

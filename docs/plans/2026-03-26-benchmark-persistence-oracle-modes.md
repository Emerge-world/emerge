# Benchmark Persistence And Oracle Modes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make benchmark persistence and oracle behavior explicit so runs can choose `persistence.mode`, `clean_before_run`, and `oracle.mode` deterministically, with metadata traceability and tests that distinguish `live`, `frozen`, and `symbolic`.

**Architecture:** Keep the current `SimulationEngine` and `Oracle` structure, but add explicit startup/load/save helpers in the engine, explicit novelty-policy helpers in the oracle, and semantic validation on expanded benchmark profiles. Use `meta.json` trace blocks to record what was cleaned, what was loaded, and which oracle novelty policy was active.

**Tech Stack:** Python dataclasses, pytest, existing benchmark manifest/expander code, `EventEmitter` metadata writes, JSON precedent persistence.

---

### Task 0: Create The Worktree And Baseline

**Files:**
- Modify: none
- Test: none

**Step 1: Create a dedicated worktree from the current branch head**

```bash
git worktree add -b feat/benchmark-persistence-oracle-modes /home/gusy/emerge-benchmark-persistence-oracle-modes HEAD
```

**Step 2: Move into the worktree and verify the branch**

```bash
cd /home/gusy/emerge-benchmark-persistence-oracle-modes
git branch --show-current
```

Expected: `feat/benchmark-persistence-oracle-modes`

**Step 3: Run the current targeted baseline tests**

```bash
uv run pytest \
  tests/test_benchmark_schema.py \
  tests/test_benchmark_expander.py \
  tests/test_engine_runtime_profile.py \
  tests/test_event_emitter.py \
  tests/test_oracle_persistence.py \
  tests/test_runtime_policy.py \
  tests/test_runtime_profiles.py \
  -q
```

Expected: PASS

**Step 4: Commit the already-approved docs if needed in the worktree**

```bash
git cherry-pick 26618e8
```

Expected: applies the design-doc commit in the worktree before implementation starts.

### Task 1: Validate Effective Benchmark Profiles For Frozen And Symbolic

**Files:**
- Modify: `simulation/benchmark/expander.py`
- Test: `tests/test_benchmark_expander.py`

**Step 1: Write the failing tests for effective-profile validation**

Add tests that fail expansion when the merged profile sets `oracle.mode` to `frozen` or `symbolic` without a `freeze_precedents_path`:

```python
def test_expand_manifest_rejects_frozen_profile_without_freeze_path():
    manifest = _make_manifest(
        defaults={"oracle": {"mode": "frozen"}},
    )

    with pytest.raises(ValueError, match="freeze_precedents_path"):
        expand_manifest(manifest)


def test_expand_manifest_accepts_symbolic_profile_with_freeze_path():
    manifest = _make_manifest(
        defaults={
            "oracle": {
                "mode": "symbolic",
                "freeze_precedents_path": "fixtures/symbolic.json",
            }
        },
    )

    runs = expand_manifest(manifest)

    assert runs[0]["profile"]["oracle"]["mode"] == "symbolic"
    assert runs[0]["profile"]["oracle"]["freeze_precedents_path"] == "fixtures/symbolic.json"
```

**Step 2: Run the focused test file and confirm the new cases fail**

```bash
uv run pytest tests/test_benchmark_expander.py -q
```

Expected: FAIL on the new frozen/symbolic validation cases.

**Step 3: Implement semantic validation on the expanded profile**

In `simulation/benchmark/expander.py`, add a helper that validates the fully merged `ExperimentProfile` before serializing it:

```python
def _validate_effective_profile(
    profile: ExperimentProfile,
    *,
    scenario_id: str,
    arm_id: str,
) -> None:
    if profile.oracle.mode in {"frozen", "symbolic"} and not profile.oracle.freeze_precedents_path:
        raise ValueError(
            f"Expanded profile for scenario={scenario_id!r}, arm={arm_id!r} "
            "requires oracle.freeze_precedents_path when oracle.mode is frozen or symbolic"
        )
```

Call it from `_build_profile(...)` after applying overrides and before returning the profile.

**Step 4: Re-run the focused test file**

```bash
uv run pytest tests/test_benchmark_expander.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add simulation/benchmark/expander.py tests/test_benchmark_expander.py
git commit -m "test: validate expanded oracle freeze path requirements"
```

### Task 2: Propagate Oracle Mode Through Runtime Policy

**Files:**
- Modify: `simulation/runtime_policy.py`
- Test: `tests/test_runtime_policy.py`

**Step 1: Write the failing runtime-policy test**

Extend `tests/test_runtime_policy.py` with explicit oracle mode mapping:

```python
def test_derive_runtime_policy_maps_oracle_mode_and_freeze_path():
    profile = build_default_profile()
    profile.oracle.mode = "symbolic"
    profile.oracle.freeze_precedents_path = "fixtures/symbolic.json"

    policy = derive_runtime_policy(profile)

    assert policy.oracle.mode == "symbolic"
    assert policy.oracle.freeze_precedents_path == "fixtures/symbolic.json"
```

**Step 2: Run the focused runtime-policy test**

```bash
uv run pytest tests/test_runtime_policy.py -q
```

Expected: FAIL because `OracleRuntimeSettings` does not yet carry mode/path.

**Step 3: Add mode/path fields to `OracleRuntimeSettings` and map them**

Update `simulation/runtime_policy.py` so `OracleRuntimeSettings` includes:

```python
mode: str = "live"
freeze_precedents_path: str | None = None
```

and `derive_runtime_policy(profile)` forwards:

```python
oracle=OracleRuntimeSettings(
    innovation=caps.innovation,
    item_reflection=caps.item_reflection,
    social=caps.social,
    teach=caps.teach,
    reproduction=caps.reproduction,
    mode=profile.oracle.mode,
    freeze_precedents_path=profile.oracle.freeze_precedents_path,
)
```

Append the new fields with defaults so existing test helpers constructing `OracleRuntimeSettings(...)` do not need churn.

**Step 4: Re-run the focused runtime-policy test**

```bash
uv run pytest tests/test_runtime_policy.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add simulation/runtime_policy.py tests/test_runtime_policy.py
git commit -m "feat: propagate oracle mode through runtime policy"
```

### Task 3: Add Meta Trace Support To EventEmitter

**Files:**
- Modify: `simulation/event_emitter.py`
- Test: `tests/test_event_emitter.py`

**Step 1: Write the failing metadata trace tests**

Add tests that verify `meta.json` can include the new trace blocks:

```python
def test_meta_json_includes_runtime_trace_blocks(tmp_path, monkeypatch):
    profile = _experiment_profile_dict()
    em = _make_emitter(tmp_path, monkeypatch, experiment_profile=profile)
    em.update_meta(
        persistence_trace={
            "mode": "oracle",
            "clean_before_run": True,
            "local_precedents_path": "data/precedents_42.json",
            "local_lineage_path": "data/lineage_42.json",
            "cleanup_candidates": ["data/precedents_42.json"],
            "cleaned_paths": [],
        },
        oracle_trace={
            "mode": "frozen",
            "freeze_precedents_path": "fixtures/frozen.json",
            "precedents_loaded_from": "fixtures/frozen.json",
            "novelty_policy": "reject_unresolved",
        },
    )
    em.close()

    meta = json.loads((tmp_path / "data" / "runs" / "test-run-1234" / "meta.json").read_text())

    assert meta["persistence_trace"]["mode"] == "oracle"
    assert meta["oracle_trace"]["mode"] == "frozen"
```

**Step 2: Run the focused event-emitter tests**

```bash
uv run pytest tests/test_event_emitter.py -q
```

Expected: FAIL because `EventEmitter` has no metadata update helper.

**Step 3: Implement a small metadata rewrite helper**

In `simulation/event_emitter.py`, store the initial metadata dict on the instance and add:

```python
def update_meta(self, **fields: object) -> None:
    self._meta.update(deepcopy(fields))
    (self.run_dir / "meta.json").write_text(
        json.dumps(self._meta, indent=2),
        encoding="utf-8",
    )
```

Initialize `self._meta` from the existing constructor payload and write from that single source of truth.

**Step 4: Re-run the focused event-emitter tests**

```bash
uv run pytest tests/test_event_emitter.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add simulation/event_emitter.py tests/test_event_emitter.py
git commit -m "feat: add meta trace updates to event emitter"
```

### Task 4: Make Engine Cleanup, Load, Save, And Metadata Explicit

**Files:**
- Modify: `simulation/engine.py`
- Test: `tests/test_engine_runtime_profile.py`
- Test: `tests/test_persistence_flag.py`

**Step 1: Write the failing engine-profile tests for cleanup and source selection**

Add tests like:

```python
def test_clean_before_run_removes_only_local_paths_allowed_by_persistence_mode(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "precedents_12.json").write_text("{}", encoding="utf-8")
    (tmp_path / "data" / "lineage_12.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)

    profile = replace(
        build_default_profile(),
        runtime=replace(build_default_profile().runtime, ticks=0, seed=12, use_llm=False),
        persistence=replace(build_default_profile().persistence, mode="oracle", clean_before_run=True),
    )

    SimulationEngine(profile=profile, run_digest=False)

    assert not (tmp_path / "data" / "precedents_12.json").exists()
    assert (tmp_path / "data" / "lineage_12.json").exists()


def test_frozen_mode_loads_precedents_from_freeze_path_not_local_seed_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)
    freeze_path = tmp_path / "fixtures" / "frozen.json"
    freeze_path.parent.mkdir(parents=True)
    freeze_path.write_text(
        json.dumps({"version": 1, "precedents": {"physical:rest": {"possible": True, "reason": "frozen"}}}),
        encoding="utf-8",
    )
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "precedents_7.json").write_text(
        json.dumps({"version": 1, "precedents": {"physical:rest": {"possible": True, "reason": "local"}}}),
        encoding="utf-8",
    )

    profile = replace(
        build_default_profile(),
        runtime=replace(build_default_profile().runtime, ticks=0, seed=7, use_llm=False),
        persistence=replace(build_default_profile().persistence, mode="none"),
        oracle=replace(build_default_profile().oracle, mode="frozen", freeze_precedents_path=str(freeze_path)),
    )

    engine = SimulationEngine(profile=profile, run_digest=False)

    assert engine.oracle.precedents["physical:rest"]["reason"] == "frozen"
```

Add a `meta.json` trace assertion in the same file for `persistence_trace` and `oracle_trace`.

**Step 2: Add the failing persistence-save test for frozen/symbolic**

In `tests/test_persistence_flag.py`, add a run test that shows oracle precedents are not saved in frozen mode even if `persistence="full"`:

```python
def test_frozen_oracle_never_saves_local_precedents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)
```

Use a profile-backed engine in this test so the oracle mode is explicit.

**Step 3: Run the focused engine and persistence tests**

```bash
uv run pytest tests/test_engine_runtime_profile.py tests/test_persistence_flag.py -q
```

Expected: FAIL on cleanup/load/source-trace behavior.

**Step 4: Implement explicit engine helpers**

In `simulation/engine.py`, add helpers such as:

```python
def _cleanup_local_persistence(self) -> list[str]:
    ...


def _load_runtime_state(self) -> tuple[dict[str, object], dict[str, object]]:
    ...
```

Implementation rules:

- cleanup only local seed-derived files covered by `persistence.mode`;
- `frozen` and `symbolic` load precedents from `freeze_precedents_path` only;
- `live` loads local precedents only when `persistence.mode` includes oracle state;
- `frozen` and `symbolic` never save local precedents in `finally`;
- local lineage still follows `persistence.mode`;
- call `self.event_emitter.update_meta(...)` with `persistence_trace` and `oracle_trace`.

Fail fast with `ValueError` if `oracle.mode in {"frozen", "symbolic"}` and the file is missing or invalid.

**Step 5: Re-run the focused engine and persistence tests**

```bash
uv run pytest tests/test_engine_runtime_profile.py tests/test_persistence_flag.py -q
```

Expected: PASS

**Step 6: Commit**

```bash
git add simulation/engine.py tests/test_engine_runtime_profile.py tests/test_persistence_flag.py
git commit -m "feat: make engine persistence and oracle loading explicit"
```

### Task 5: Close Oracle Novelty In Frozen And Symbolic Modes

**Files:**
- Modify: `simulation/oracle.py`
- Test: `tests/test_oracle_modes.py`
- Test: `tests/test_oracle_persistence.py`

**Step 1: Create a dedicated oracle-mode regression test file**

Add `tests/test_oracle_modes.py` with focused mode-difference tests:

```python
def test_live_mode_learns_new_physical_precedent():
    world = World(width=5, height=5, seed=42)
    llm = MagicMock()
    llm.generate_structured.return_value = _typed({"possible": True, "reason": "ok", "life_damage": 0})
    llm.last_call = {}
    oracle = Oracle(
        world=world,
        llm=llm,
        runtime_settings=OracleRuntimeSettings(
            innovation=True,
            item_reflection=True,
            social=True,
            teach=True,
            reproduction=True,
            mode="live",
        ),
    )

    result = oracle._oracle_reflect_physical("physical:traversal:tile:land", "prompt", tick=1)

    assert result["possible"] is True
    assert "physical:traversal:tile:land" in oracle.precedents


def test_frozen_mode_rejects_physical_novelty_without_writing():
    world = World(width=5, height=5, seed=42)
    oracle = Oracle(
        world=world,
        llm=MagicMock(),
        runtime_settings=OracleRuntimeSettings(
            innovation=True,
            item_reflection=True,
            social=True,
            teach=True,
            reproduction=True,
            mode="frozen",
            freeze_precedents_path="fixtures/frozen.json",
        ),
    )

    result = oracle._oracle_reflect_physical("physical:traversal:tile:unknown", "prompt", tick=1)

    assert result["possible"] is False
    assert result["reason_code"] == "ORACLE_UNRESOLVED_NOVELTY"
    assert "physical:traversal:tile:unknown" not in oracle.precedents
```

Also add symbolic tests for unresolved innovation/custom-action misses and a hit against a curated precedent.

**Step 2: Add a persistence test for explicit frozen snapshot loading**

Extend `tests/test_oracle_persistence.py` with a test that loading a valid frozen snapshot succeeds and a malformed snapshot triggers a startup-facing error helper if you add one there.

**Step 3: Run the focused oracle tests**

```bash
uv run pytest tests/test_oracle_modes.py tests/test_oracle_persistence.py -q
```

Expected: FAIL because the oracle still falls back permissively on misses.

**Step 4: Implement explicit novelty-policy helpers in `simulation/oracle.py`**

Add helpers such as:

```python
def _oracle_mode(self) -> str:
    return self.runtime_settings.mode


def _novelty_is_closed(self) -> bool:
    return self._oracle_mode() in {"frozen", "symbolic"}


def _unresolved_result(self, *, message: str, effects: dict | None = None) -> dict:
    return {
        "success": False,
        "message": message,
        "effects": effects or {},
        "reason_code": "ORACLE_UNRESOLVED_NOVELTY",
    }
```

Apply them to:

- `_oracle_reflect_physical`
- `_validate_innovation`
- `_resolve_custom_action`
- `_get_item_eat_effect`
- `_discover_item_affordances`

Implementation rules:

- `live` keeps existing LLM/default behavior;
- `frozen` and `symbolic` never call the LLM on novelty misses;
- `frozen` and `symbolic` never write new precedents on novelty misses;
- `symbolic` must never approve open novelty by default.

Preserve existing no-LLM fallback behavior for `live` so the current non-benchmark tests do not regress.

**Step 5: Re-run the focused oracle tests**

```bash
uv run pytest tests/test_oracle_modes.py tests/test_oracle_persistence.py -q
```

Expected: PASS

**Step 6: Commit**

```bash
git add simulation/oracle.py tests/test_oracle_modes.py tests/test_oracle_persistence.py
git commit -m "feat: enforce explicit oracle novelty modes"
```

### Task 6: Update Cornerstone Docs And Run Full Verification

**Files:**
- Modify: `project-cornerstone/04-oracle/oracle_context.md`
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Modify: `project-cornerstone/00-master-plan/MASTER_PLAN.md`

**Step 1: Update the oracle cornerstone context**

Document:

- explicit `live|frozen|symbolic` oracle modes;
- explicit startup behavior for frozen/symbolic snapshots;
- closed-world novelty behavior outside `live`;
- `meta.json` traceability for benchmark runs.

**Step 2: Add a decision-log entry**

Add a new immutable decision entry describing:

- why implicit seed-based reuse was removed from benchmark semantics;
- why `frozen` and `symbolic` are both closed to novelty;
- why symbolic reuses the current precedent JSON format for now.

**Step 3: Update the master plan**

Mark the runtime benchmark policy milestone as implemented or refined so the repository state stays aligned with the code.

**Step 4: Run the full required verification command**

```bash
uv run pytest -m "not slow"
```

Expected: PASS

**Step 5: Run one explicit benchmark-mode regression slice**

```bash
uv run pytest \
  tests/test_benchmark_expander.py \
  tests/test_engine_runtime_profile.py \
  tests/test_event_emitter.py \
  tests/test_oracle_modes.py \
  -q
```

Expected: PASS

**Step 6: Commit**

```bash
git add \
  project-cornerstone/04-oracle/oracle_context.md \
  project-cornerstone/00-master-plan/DECISION_LOG.md \
  project-cornerstone/00-master-plan/MASTER_PLAN.md
git commit -m "docs: record benchmark persistence and oracle mode policy"
```

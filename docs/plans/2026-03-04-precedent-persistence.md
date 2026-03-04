# Precedent Persistence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Persist oracle precedents to `data/precedents_{seed}.json` so the simulation accumulates world knowledge across runs instead of re-querying the LLM from scratch each time.

**Architecture:** Add `load_precedents(filepath)` and `save_precedents(filepath, tick, seed)` methods directly to `Oracle`. `SimulationEngine.__init__` loads on startup; `run()` and `run_with_callback()` save in a `try/finally` block.

**Tech Stack:** Python `json` + `pathlib.Path` (no new dependencies). Pytest `tmp_path` fixture for isolated tests.

---

### Task 0: Create design doc directory and commit

**Files:**
- Create: `docs/plans/` (this file is already here)

**Step 1: Stage and commit the design doc**

```bash
git add docs/plans/2026-03-04-precedent-persistence.md
git commit -m "docs: add precedent persistence design doc"
```

---

### Task 1: Add imports to oracle.py

**Files:**
- Modify: `simulation/oracle.py:1-18` (top of file)

**Step 1: Add `json` and `pathlib` imports**

In `simulation/oracle.py`, add after `import logging`:

```python
import json
from pathlib import Path
```

**Step 2: Run existing tests to confirm no breakage**

```bash
uv run pytest tests/ -m "not slow" -q
```

Expected: all pass.

**Step 3: Commit**

```bash
git add simulation/oracle.py
git commit -m "chore(oracle): add json and pathlib imports for precedent persistence"
```

---

### Task 2: Add `load_precedents` method to Oracle

**Files:**
- Modify: `simulation/oracle.py` (add method after `__init__`, before `_apply_energy_cost`)
- Test: `tests/test_oracle_persistence.py` (create)

**Step 1: Write the failing tests**

Create `tests/test_oracle_persistence.py`:

```python
"""
Tests for Oracle precedent persistence (save/load to JSON).
"""
import json
from unittest.mock import MagicMock

import pytest

from simulation.oracle import Oracle
from simulation.world import World


def _make_oracle() -> Oracle:
    world = World(width=5, height=5, seed=42)
    return Oracle(world, llm=None)


def _oracle_with_precedents() -> Oracle:
    oracle = _make_oracle()
    oracle.precedents = {
        "physical:rest": {"possible": True, "reason": "always"},
        "innovation:fish": {
            "creator": "Ada",
            "description": "catch fish",
            "tick_created": 3,
            "category": "SURVIVAL",
        },
    }
    return oracle


# ── load_precedents ──────────────────────────────────────────────────────────

def test_load_missing_file_is_noop(tmp_path):
    oracle = _make_oracle()
    oracle.load_precedents(str(tmp_path / "nonexistent.json"))
    assert oracle.precedents == {}


def test_load_corrupt_json_leaves_existing(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("THIS IS NOT JSON", encoding="utf-8")
    oracle = _make_oracle()
    oracle.precedents["existing"] = {"value": 1}
    oracle.load_precedents(str(p))
    assert oracle.precedents == {"existing": {"value": 1}}


def test_load_restores_precedents(tmp_path):
    oracle = _oracle_with_precedents()
    path = str(tmp_path / "p.json")
    oracle.save_precedents(path, tick=5, world_seed=42)

    fresh = _make_oracle()
    fresh.load_precedents(path)
    assert fresh.precedents == oracle.precedents


def test_load_merges_without_overwriting_existing(tmp_path):
    oracle = _oracle_with_precedents()
    path = str(tmp_path / "p.json")
    oracle.save_precedents(path, tick=5, world_seed=42)

    # Load into oracle that already has a different key
    receiver = _make_oracle()
    receiver.precedents["pre_existing"] = {"value": 99}
    receiver.load_precedents(path)

    assert receiver.precedents["pre_existing"] == {"value": 99}
    assert "physical:rest" in receiver.precedents
```

**Step 2: Run to confirm they fail**

```bash
uv run pytest tests/test_oracle_persistence.py -v
```

Expected: `AttributeError: 'Oracle' object has no attribute 'load_precedents'`

**Step 3: Implement `load_precedents` in Oracle**

In `simulation/oracle.py`, add this method after `__init__` (before `_apply_energy_cost` at line 56):

```python
def load_precedents(self, filepath: str) -> None:
    """Load precedents from a JSON file and merge into self.precedents.

    Silently skips if the file does not exist.
    Logs a warning and leaves existing precedents unchanged if the file is corrupt.
    """
    path = Path(filepath)
    if not path.exists():
        logger.debug("No precedent file at %s, starting fresh.", filepath)
        return
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        loaded = data.get("precedents", {})
        self.precedents.update(loaded)
        logger.info("Loaded %d precedents from %s", len(loaded), filepath)
    except (json.JSONDecodeError, KeyError, ValueError, OSError) as exc:
        logger.warning("Could not load precedents from %s: %s", filepath, exc)
```

**Step 4: Run the load tests**

```bash
uv run pytest tests/test_oracle_persistence.py -v -k "load"
```

Expected: `test_load_missing_file_is_noop` PASS, `test_load_corrupt_json_leaves_existing` PASS, `test_load_merges_without_overwriting_existing` PASS, `test_load_restores_precedents` FAIL (save not yet implemented).

**Step 5: Commit**

```bash
git add simulation/oracle.py tests/test_oracle_persistence.py
git commit -m "feat(oracle): add load_precedents method with corruption safety"
```

---

### Task 3: Add `save_precedents` method to Oracle

**Files:**
- Modify: `simulation/oracle.py` (add method after `load_precedents`)

**Step 1: Add remaining save-related tests to the test file**

Append to `tests/test_oracle_persistence.py`:

```python
# ── save_precedents ──────────────────────────────────────────────────────────

def test_save_creates_file(tmp_path):
    oracle = _oracle_with_precedents()
    path = tmp_path / "out.json"
    oracle.save_precedents(str(path), tick=10, world_seed=42)
    assert path.exists()


def test_save_schema(tmp_path):
    oracle = _oracle_with_precedents()
    path = tmp_path / "out.json"
    oracle.save_precedents(str(path), tick=10, world_seed=42)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["world_seed"] == 42
    assert data["saved_at_tick"] == 10
    assert "precedents" in data


def test_save_creates_parent_dirs(tmp_path):
    oracle = _oracle_with_precedents()
    nested = tmp_path / "deeply" / "nested" / "prec.json"
    oracle.save_precedents(str(nested), tick=1, world_seed=0)
    assert nested.exists()


def test_save_round_trip(tmp_path):
    original = _oracle_with_precedents()
    path = str(tmp_path / "round.json")
    original.save_precedents(path, tick=7, world_seed=99)

    restored = _make_oracle()
    restored.load_precedents(path)
    assert restored.precedents == original.precedents
```

**Step 2: Run to confirm new tests fail**

```bash
uv run pytest tests/test_oracle_persistence.py -v -k "save"
```

Expected: `AttributeError: 'Oracle' object has no attribute 'save_precedents'`

**Step 3: Implement `save_precedents` in Oracle**

Add this method directly after `load_precedents`:

```python
def save_precedents(
    self, filepath: str, tick: int = 0, world_seed: Optional[int] = None
) -> None:
    """Save current precedents to a JSON file.

    Creates parent directories as needed.
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "world_seed": world_seed,
        "saved_at_tick": tick,
        "precedents": self.precedents,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("Saved %d precedents to %s", len(self.precedents), filepath)
```

**Step 4: Run all persistence tests**

```bash
uv run pytest tests/test_oracle_persistence.py -v
```

Expected: all 8 tests PASS.

**Step 5: Run full test suite**

```bash
uv run pytest -m "not slow" -q
```

Expected: all pass.

**Step 6: Commit**

```bash
git add simulation/oracle.py tests/test_oracle_persistence.py
git commit -m "feat(oracle): add save_precedents method"
```

---

### Task 4: Wire auto-load and auto-save into SimulationEngine

**Files:**
- Modify: `simulation/engine.py:29-88` (`__init__`) and `simulation/engine.py:89-108` (`run`)

**Step 1: Store world seed and compute precedents path in `__init__`**

In `simulation/engine.py`, in `__init__` (around line 38), add after `self.use_llm = use_llm`:

```python
self._world_seed = world_seed
seed_str = str(world_seed) if world_seed is not None else "unseeded"
self._precedents_path = f"data/precedents_{seed_str}.json"
```

**Step 2: Load precedents after oracle is created**

In `engine.py __init__`, after the line `self.oracle = Oracle(...)` (around line 62), add:

```python
# Auto-load precedents from previous runs
self.oracle.load_precedents(self._precedents_path)
```

**Step 3: Wrap `run()` tick loop in try/finally to auto-save**

Replace the body of `run()` (lines 89-108):

```python
def run(self):
    """Run the complete simulation."""
    self._print_header()
    self._log_overview_start()

    try:
        for tick in range(1, self.max_ticks + 1):
            self.current_tick = tick
            alive_agents = [a for a in self.agents if a.alive]

            if not alive_agents:
                self._print_separator()
                print("\n☠️  ALL AGENTS HAVE DIED. End of simulation.")
                break

            self._run_tick(tick, alive_agents)

            if TICK_DELAY_SECONDS > 0:
                time.sleep(TICK_DELAY_SECONDS)
    finally:
        self.oracle.save_precedents(
            self._precedents_path, self.current_tick, self._world_seed
        )

    self._print_summary()
```

**Step 4: Also save in `run_with_callback()` finally block**

In `run_with_callback()` (around line 367), wrap the for-loop similarly:

```python
try:
    for tick in range(1, self.max_ticks + 1):
        # ... existing loop body unchanged ...
finally:
    self.oracle.save_precedents(
        self._precedents_path, self.current_tick, self._world_seed
    )

self._log_overview_end()
```

**Step 5: Run smoke test**

```bash
uv run main.py --no-llm --ticks 5 --agents 1 --seed 42
```

Expected output: no errors, and a file `data/precedents_42.json` is created.

**Step 6: Verify the file**

```bash
cat data/precedents_42.json
```

Expected: valid JSON with `version`, `world_seed`, `saved_at_tick`, `precedents` keys.

**Step 7: Run again to verify load**

```bash
uv run main.py --no-llm --ticks 5 --agents 1 --seed 42 --verbose 2>&1 | grep -i precedent
```

Expected: a log line like `INFO Loaded N precedents from data/precedents_42.json`.

**Step 8: Run full test suite**

```bash
uv run pytest -m "not slow" -q
```

Expected: all pass.

**Step 9: Commit**

```bash
git add simulation/engine.py
git commit -m "feat(engine): auto-load and auto-save oracle precedents per world seed"
```

---

### Task 5: Update cornerstone docs

**Files:**
- Modify: `project-cornerstone/04-oracle/oracle_context.md`
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`

**Step 1: Update oracle_context.md**

In `project-cornerstone/04-oracle/oracle_context.md`, find the section describing precedents as "in-memory only" and update it to reflect persistence is implemented. Change the "Phase 1 Plan" section to "Phase 1 (Implemented)".

**Step 2: Add DEC-013 to DECISION_LOG.md**

Append at the end of `project-cornerstone/00-master-plan/DECISION_LOG.md`:

```markdown
## DEC-013 — Precedent Persistence Strategy

**Date:** 2026-03-04
**Decision:** Persist oracle precedents as `data/precedents_{seed}.json`. Auto-load on engine init, auto-save in run() finally block. Minimal schema (version, seed, tick, precedents dict). No dataclass refactor yet.
**Rationale:** Keeps runs deterministic across restarts and avoids redundant LLM calls for already-validated actions. Per-seed isolation prevents cross-contamination between different world configurations. Unseeded runs use `precedents_unseeded.json`.
**Alternatives considered:** Global single file (contamination risk), PrecedentKey/Value dataclasses (deferred — YAGNI until needed).
```

**Step 3: Commit**

```bash
git add project-cornerstone/
git commit -m "docs(cornerstone): update oracle context and add DEC-013 for precedent persistence"
```

---

### Task 6: Final verification

**Step 1: Full test suite**

```bash
uv run pytest -m "not slow" -v
```

Expected: all tests PASS including the new `tests/test_oracle_persistence.py` (8 tests).

**Step 2: Clean run → second run to confirm accumulation**

```bash
rm -f data/precedents_42.json
uv run main.py --no-llm --ticks 10 --agents 2 --seed 42
cat data/precedents_42.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Precedents: {len(d[\"precedents\"])}, saved_at_tick: {d[\"saved_at_tick\"]}')"
uv run main.py --no-llm --ticks 5 --agents 1 --seed 42 --verbose 2>&1 | grep -i precedent
```

Expected second run: `Loaded N precedents from data/precedents_42.json` in logs.

**Step 3: Run /blog to document the PR after merging**

After merging, run `/blog` to generate the devlog entry.

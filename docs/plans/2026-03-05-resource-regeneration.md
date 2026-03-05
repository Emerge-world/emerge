# Resource Regeneration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Trees that have run out of fruit regrow 1–3 units at each dawn (every 24 ticks), with 30% probability per tree, using the world's own seeded RNG for determinism.

**Architecture:** `World` gets a seeded `random.Random` instance and a cached list of tree positions. `World.update_resources(tick)` checks for dawn and runs the regen lottery. `SimulationEngine._run_tick` calls it once per tick after the agent loop.

**Tech Stack:** Python `random.Random` (stdlib), pytest, existing `simulation/` module structure.

---

### Task 0: Create feature branch

**Step 1: Create and switch to branch**

```bash
cd /home/gusy/emerge
git checkout -b resource-regen
```

Expected: `Switched to a new branch 'resource-regen'`

**Step 2: Verify clean state**

```bash
git status
```

Expected: `nothing to commit, working tree clean`

---

### Task 1: Add config constants

**Files:**
- Modify: `simulation/config.py` (append after line 83, the `BASE_ACTIONS` line)

**Step 1: Add the three regeneration constants**

Open `simulation/config.py` and append at the end:

```python

# --- Resource regeneration ---
RESOURCE_REGEN_CHANCE = 0.3          # probability per depleted tree at each dawn
RESOURCE_REGEN_AMOUNT_MIN = 1        # minimum fruit spawned on regeneration
RESOURCE_REGEN_AMOUNT_MAX = 3        # maximum fruit spawned on regeneration
```

**Step 2: Verify config imports cleanly**

```bash
cd /home/gusy/emerge
uv run python -c "from simulation.config import RESOURCE_REGEN_CHANCE, RESOURCE_REGEN_AMOUNT_MIN, RESOURCE_REGEN_AMOUNT_MAX; print('OK', RESOURCE_REGEN_CHANCE)"
```

Expected: `OK 0.3`

**Step 3: Commit**

```bash
git add simulation/config.py
git commit -m "feat(config): add resource regeneration constants"
```

---

### Task 2: Write failing tests for World.update_resources

**Files:**
- Create: `tests/test_world.py`

**Step 1: Create the test file**

```python
"""
Unit tests for World resource regeneration.

Covers:
- update_resources() only triggers at dawn (tick % DAY_LENGTH == 0)
- Tick 0 is skipped (world just generated)
- Non-dawn ticks never trigger regen
- Only depleted trees (absent from self.resources) are eligible
- Regenerated quantities are within [REGEN_AMOUNT_MIN, REGEN_AMOUNT_MAX]
- All regenerated positions are on tree tiles
- Determinism: same seed → same regen at same tick
- 100% regen chance: all depleted trees regrow (uses mock patch)
"""

from unittest.mock import patch

import pytest

from simulation.world import World
from simulation.config import (
    DAY_LENGTH,
    RESOURCE_REGEN_AMOUNT_MIN,
    RESOURCE_REGEN_AMOUNT_MAX,
    TILE_TREE,
)


@pytest.fixture
def world():
    """10x10 world with fixed seed for deterministic tests."""
    return World(width=10, height=10, seed=42)


def _deplete_all(world: World) -> None:
    """Consume all fruit from every resource tile."""
    for pos in list(world.resources.keys()):
        world.consume_resource(*pos, amount=10)


# ---------------------------------------------------------------------------
# Dawn detection
# ---------------------------------------------------------------------------

def test_no_regen_on_non_dawn_ticks(world):
    """Non-dawn ticks must not trigger any regeneration."""
    _deplete_all(world)
    for tick in [1, 5, 10, 23, 25, 47]:
        result = world.update_resources(tick)
        assert result == [], f"Expected no regen at tick {tick}"


def test_no_regen_at_tick_zero(world):
    """Tick 0 is world generation — regen must be skipped."""
    _deplete_all(world)
    result = world.update_resources(0)
    assert result == []


def test_regen_triggers_at_first_dawn(world):
    """update_resources(24) runs the regen check (returns a list, may be empty)."""
    _deplete_all(world)
    result = world.update_resources(DAY_LENGTH)
    assert isinstance(result, list)


def test_regen_triggers_at_subsequent_dawns(world):
    """Regen triggers at ticks 48 and 72 as well."""
    _deplete_all(world)
    for dawn_tick in [DAY_LENGTH * 2, DAY_LENGTH * 3]:
        result = world.update_resources(dawn_tick)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Correctness of regeneration
# ---------------------------------------------------------------------------

def test_regen_only_affects_depleted_trees(world):
    """Trees that still have fruit must not be touched."""
    # Keep track of trees with fruit before regen
    trees_with_fruit = {
        pos: info["quantity"]
        for pos, info in world.resources.items()
    }
    if not trees_with_fruit:
        pytest.skip("No trees with fruit (unusual world layout)")

    world.update_resources(DAY_LENGTH)

    for pos, original_qty in trees_with_fruit.items():
        if pos in world.resources:
            assert world.resources[pos]["quantity"] == original_qty, (
                f"Tree at {pos} had fruit before dawn but quantity changed"
            )


def test_regen_quantity_in_range(world):
    """Every regenerated fruit quantity must be within [MIN, MAX]."""
    _deplete_all(world)

    with patch("simulation.world.RESOURCE_REGEN_CHANCE", 1.0):
        world.update_resources(DAY_LENGTH)

    for pos, info in world.resources.items():
        qty = info["quantity"]
        assert RESOURCE_REGEN_AMOUNT_MIN <= qty <= RESOURCE_REGEN_AMOUNT_MAX, (
            f"Quantity {qty} at {pos} is out of range"
        )


def test_regen_positions_are_tree_tiles(world):
    """Regenerated resources only appear on tree tiles."""
    _deplete_all(world)

    with patch("simulation.world.RESOURCE_REGEN_CHANCE", 1.0):
        regenerated = world.update_resources(DAY_LENGTH)

    for (x, y) in regenerated:
        assert world.get_tile(x, y) == TILE_TREE, (
            f"Regenerated resource at ({x},{y}) but tile is {world.get_tile(x, y)}"
        )


def test_all_depleted_trees_regen_when_chance_is_100(world):
    """With 100% chance, every depleted tree must regenerate."""
    _deplete_all(world)
    tree_count = len(world._tree_positions)

    with patch("simulation.world.RESOURCE_REGEN_CHANCE", 1.0):
        regenerated = world.update_resources(DAY_LENGTH)

    assert len(regenerated) == tree_count
    assert len(world.resources) == tree_count


def test_regen_returns_coords_that_got_fruit(world):
    """Returned (x, y) list must exactly match newly added resources."""
    _deplete_all(world)

    with patch("simulation.world.RESOURCE_REGEN_CHANCE", 1.0):
        regenerated = world.update_resources(DAY_LENGTH)

    assert set(regenerated) == set(world.resources.keys())


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_determinism_same_seed():
    """Two worlds with the same seed produce identical regeneration."""
    world_a = World(width=10, height=10, seed=42)
    world_b = World(width=10, height=10, seed=42)

    _deplete_all(world_a)
    _deplete_all(world_b)

    result_a = world_a.update_resources(DAY_LENGTH)
    result_b = world_b.update_resources(DAY_LENGTH)

    assert sorted(result_a) == sorted(result_b)
    assert world_a.resources == world_b.resources


def test_different_seeds_may_differ():
    """Different seeds should produce different regen (probabilistically)."""
    world_a = World(width=10, height=10, seed=1)
    world_b = World(width=10, height=10, seed=999)

    _deplete_all(world_a)
    _deplete_all(world_b)

    result_a = world_a.update_resources(DAY_LENGTH)
    result_b = world_b.update_resources(DAY_LENGTH)

    # At least the test runs without error; outcomes may differ
    assert isinstance(result_a, list)
    assert isinstance(result_b, list)
```

**Step 2: Run tests — expect FAIL (update_resources doesn't exist yet)**

```bash
cd /home/gusy/emerge
uv run pytest tests/test_world.py -v 2>&1 | head -40
```

Expected: `AttributeError: 'World' object has no attribute 'update_resources'` or `AttributeError: 'World' object has no attribute '_tree_positions'`

---

### Task 3: Implement World changes

**Files:**
- Modify: `simulation/world.py`

**Step 1: Update the import line at the top of world.py**

Current line 11–15:
```python
from simulation.config import (
    WORLD_WIDTH, WORLD_HEIGHT,
    TILE_WATER, TILE_LAND, TILE_TREE,
    WORLD_WATER_PROB, WORLD_TREE_PROB,
)
```

Replace with:
```python
from simulation.config import (
    WORLD_WIDTH, WORLD_HEIGHT,
    TILE_WATER, TILE_LAND, TILE_TREE,
    WORLD_WATER_PROB, WORLD_TREE_PROB,
    DAY_LENGTH,
    RESOURCE_REGEN_CHANCE, RESOURCE_REGEN_AMOUNT_MIN, RESOURCE_REGEN_AMOUNT_MAX,
)
```

**Step 2: Update `World.__init__` to add `_rng` and `_tree_positions`**

Current `__init__` body (lines 23–28):
```python
def __init__(self, width: int = WORLD_WIDTH, height: int = WORLD_HEIGHT, seed: Optional[int] = None):
    self.width = width
    self.height = height
    self.grid: list[list[str]] = []
    self.resources: dict[tuple[int, int], dict] = {}  # (x,y) -> resource info
    self._generate(seed)
```

Replace with:
```python
def __init__(self, width: int = WORLD_WIDTH, height: int = WORLD_HEIGHT, seed: Optional[int] = None):
    self.width = width
    self.height = height
    self.grid: list[list[str]] = []
    self.resources: dict[tuple[int, int], dict] = {}  # (x,y) -> resource info
    self._rng = random.Random(seed)       # dedicated RNG for regeneration (deterministic)
    self._tree_positions: list[tuple[int, int]] = []  # cached at generation time
    self._generate(seed)
```

**Step 3: Update `_generate` to reset and populate `_tree_positions`**

Current `_generate` (lines 30–51). Change:
1. Add `self._tree_positions = []` at the start of `_generate` (after the `if seed is not None` block)
2. Inside the `elif r < WORLD_WATER_PROB + WORLD_TREE_PROB:` block, after setting the resource, append the position

Full updated `_generate`:
```python
def _generate(self, seed: Optional[int] = None):
    """Generate the world procedurally."""
    if seed is not None:
        random.seed(seed)

    self.grid = []
    self._tree_positions = []  # reset before populating
    for y in range(self.height):
        row = []
        for x in range(self.width):
            r = random.random()
            if r < WORLD_WATER_PROB:
                tile = TILE_WATER
            elif r < WORLD_WATER_PROB + WORLD_TREE_PROB:
                tile = TILE_TREE
                # Trees have harvestable fruit
                self.resources[(x, y)] = {"type": "fruit", "quantity": random.randint(1, 5)}
                self._tree_positions.append((x, y))  # cache for fast regen iteration
            else:
                tile = TILE_LAND
            row.append(tile)
        self.grid.append(row)

    logger.info(f"World generated: {self.width}x{self.height}")
```

**Step 4: Add `update_resources` method**

Add this method after `consume_resource` (after line 78), before `get_nearby_tiles`:

```python
def update_resources(self, tick: int) -> list[tuple[int, int]]:
    """
    At each dawn (tick % DAY_LENGTH == 0, skipping tick 0), depleted trees
    have a chance to regrow fruit. Uses self._rng for determinism.

    Returns list of (x, y) positions where fruit regenerated this tick.
    """
    if tick == 0 or tick % DAY_LENGTH != 0:
        return []

    regenerated = []
    for (x, y) in self._tree_positions:
        if (x, y) not in self.resources:  # tree is depleted
            if self._rng.random() < RESOURCE_REGEN_CHANCE:
                qty = self._rng.randint(RESOURCE_REGEN_AMOUNT_MIN, RESOURCE_REGEN_AMOUNT_MAX)
                self.resources[(x, y)] = {"type": "fruit", "quantity": qty}
                regenerated.append((x, y))

    return regenerated
```

**Step 5: Run tests — expect PASS**

```bash
cd /home/gusy/emerge
uv run pytest tests/test_world.py -v
```

Expected: all tests green. If any fail, read the error carefully and fix the implementation (do not change the tests).

**Step 6: Run full test suite to check no regressions**

```bash
uv run pytest -m "not slow" -v
```

Expected: all existing tests still pass.

**Step 7: Commit**

```bash
git add simulation/world.py tests/test_world.py
git commit -m "feat(world): add dawn-triggered resource regeneration with seeded RNG"
```

---

### Task 4: Wire regeneration into the engine

**Files:**
- Modify: `simulation/engine.py:209-212`

**Step 1: Add the world update call in `_run_tick`**

In `simulation/engine.py`, find the memory compression block (around line 209):

```python
        # Memory compression
        for agent in alive_agents:
            if agent.alive and agent.memory_system.should_compress(tick):
                agent.memory_system.compress(llm=self.llm, tick=tick, agent_name=agent.name)
```

Insert the world update **before** the memory compression block:

```python
        # World update: resource regeneration at dawn
        regenerated = self.world.update_resources(tick)
        if regenerated:
            logger.info("[tick %d] %d tree(s) regenerated fruit at dawn", tick, len(regenerated))

        # Memory compression
        for agent in alive_agents:
            if agent.alive and agent.memory_system.should_compress(tick):
                agent.memory_system.compress(llm=self.llm, tick=tick, agent_name=agent.name)
```

**Step 2: Smoke test the engine**

```bash
cd /home/gusy/emerge
uv run main.py --no-llm --ticks 48 --agents 2 --seed 42 --verbose 2>&1 | grep -E "(tick|regen|fruit)" | head -20
```

Expected: simulation runs 48 ticks without crash. At tick 24, you should see regeneration log lines if any trees were depleted (unlikely with only 2 agents over 24 ticks, but no crash is the key thing).

**Step 3: Test with more agents over more ticks to see regeneration**

```bash
uv run main.py --no-llm --ticks 72 --agents 3 --seed 42 2>&1 | tail -20
```

Expected: "Remaining fruit" in final summary should be > 0 (fruit regenerated keeps the world alive).

**Step 4: Run full test suite**

```bash
uv run pytest -m "not slow"
```

Expected: all green.

**Step 5: Commit**

```bash
git add simulation/engine.py
git commit -m "feat(engine): call world.update_resources each tick for dawn regen"
```

---

### Task 5: Update cornerstone documentation

**Files:**
- Modify: `project-cornerstone/02-world/world_context.md`
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Modify: `project-cornerstone/00-master-plan/MASTER_PLAN.md`

**Step 1: Update world_context.md**

Find the section about resource regeneration (currently marked as deferred). Update it to reflect the implementation. Look for text like "Resource regeneration timing (dawn-triggered) deferred to next PR" and replace the deferred note with the actual design:

```markdown
### Resource Regeneration (DEC-015)

At each dawn (`tick % DAY_LENGTH == 0`, skipping tick 0), each depleted tree tile
rolls for fruit regeneration:

- **Trigger:** Dawn (every 24 ticks, starting tick 24)
- **Eligibility:** Only tree tiles with no active resource entry
- **Probability:** `RESOURCE_REGEN_CHANCE = 0.3` (30% per eligible tree)
- **Quantity:** `random.randint(RESOURCE_REGEN_AMOUNT_MIN, RESOURCE_REGEN_AMOUNT_MAX)` → 1–3 fruit
- **Determinism:** Uses `World._rng = random.Random(seed)`, a dedicated instance
  separate from the global `random` module used during world generation.
- **Implementation:** `World.update_resources(tick)` called from `SimulationEngine._run_tick`
```

**Step 2: Add DEC-015 to DECISION_LOG.md**

Append at the end of the file:

```markdown
## DEC-015 — Resource Regeneration: Dawn-Triggered with Probability (2026-03-05)

**Context:** Trees deplete without regenerating, causing agents to starve mid-simulation.
This makes long-run testing of Phase 2 features (inventory, crafting) impractical.

**Decision:** At each dawn (`tick % DAY_LENGTH == 0`, skip tick 0), each depleted
tree tile has a 30% chance to regrow 1–3 fruit. Uses `World._rng = random.Random(seed)`,
a dedicated RNG instance seeded identically to world generation but independent of the
global `random` module.

**Alternatives considered:**
- Every-N-ticks (simpler): rejected — ignores the day/night system we just built.
- DayCycle event system: rejected — YAGNI; adds pub/sub complexity with no other subscribers.

**Constants:** `RESOURCE_REGEN_CHANCE=0.3`, `RESOURCE_REGEN_AMOUNT_MIN=1`, `RESOURCE_REGEN_AMOUNT_MAX=3`

**Files:** `simulation/config.py`, `simulation/world.py`, `simulation/engine.py`, `tests/test_world.py`
```

**Step 3: Check off item in MASTER_PLAN.md**

In `project-cornerstone/00-master-plan/MASTER_PLAN.md`, find:

```markdown
- [ ] Resource regeneration (trees give fruit periodically)
```

Change to:

```markdown
- [x] Resource regeneration (trees give fruit periodically) — see DEC-015
```

**Step 4: Commit**

```bash
git add project-cornerstone/
git commit -m "docs(cornerstone): add DEC-015 for resource regeneration, mark Phase 2 item done"
```

---

### Task 6: Final verification

**Step 1: Full test suite**

```bash
cd /home/gusy/emerge
uv run pytest -m "not slow" -v
```

Expected: all tests pass. Note the count — should be previous count + 10 new world tests.

**Step 2: Determinism check**

Run the same seed twice and compare fruit remaining:

```bash
uv run main.py --no-llm --ticks 72 --agents 3 --seed 42 2>&1 | grep "Remaining fruit"
uv run main.py --no-llm --ticks 72 --agents 3 --seed 42 2>&1 | grep "Remaining fruit"
```

Expected: identical output both times.

**Step 3: Dawn timing check**

```bash
uv run main.py --no-llm --ticks 72 --agents 3 --seed 42 --verbose 2>&1 | grep "regenerated"
```

Expected: regen log lines appear only at ticks 24, 48, 72 (if any trees depleted by then).

**Step 4: Use the finishing skill**

```
/superpowers:finishing-a-development-branch
```

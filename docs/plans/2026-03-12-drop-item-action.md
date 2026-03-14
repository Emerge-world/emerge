# Drop Item Action Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a new built-in `drop_item` action so agents can remove items from inventory and place them onto their current tile, while updating metrics coverage and cornerstone documentation.

**Architecture:** Implement the feature as a narrow extension of the existing inventory/oracle flow described in [`docs/plans/2026-03-12-drop-item-action-design.md`](./2026-03-12-drop-item-action-design.md). The world keeps its current one-resource-stack-per-tile model, so the only world change is a small `place_resource()` helper used by the oracle. Existing metrics stay event-first: `drop_item` should show up through `agent_decision` action counting without adding a new event type.

**Tech Stack:** Python 3.12, pytest, prompt templates in `prompts/`, cornerstone docs in `project-cornerstone/`

---

### Task 1: Add World Resource Placement Helper

**Files:**
- Modify: `simulation/world.py`
- Modify: `tests/test_world.py`

**Step 1: Write the failing tests**

Add these tests to [`tests/test_world.py`](../../tests/test_world.py):

```python
def test_place_resource_creates_new_stack_on_empty_tile():
    world = World(width=5, height=5, seed=42)
    world.resources.pop((1, 1), None)

    placed = world.place_resource(1, 1, "fruit", 2)

    assert placed is True
    assert world.get_resource(1, 1) == {"type": "fruit", "quantity": 2}


def test_place_resource_merges_same_type_stack():
    world = World(width=5, height=5, seed=42)
    world.resources[(1, 1)] = {"type": "fruit", "quantity": 2}

    placed = world.place_resource(1, 1, "fruit", 3)

    assert placed is True
    assert world.get_resource(1, 1) == {"type": "fruit", "quantity": 5}


def test_place_resource_rejects_conflicting_stack():
    world = World(width=5, height=5, seed=42)
    world.resources[(1, 1)] = {"type": "stone", "quantity": 2}

    placed = world.place_resource(1, 1, "fruit", 1)

    assert placed is False
    assert world.get_resource(1, 1) == {"type": "stone", "quantity": 2}
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_world.py -k place_resource -v`

Expected: FAIL with `AttributeError: 'World' object has no attribute 'place_resource'`

**Step 3: Write minimal implementation**

Add this helper to [`simulation/world.py`](../../simulation/world.py):

```python
def place_resource(self, x: int, y: int, item: str, amount: int = 1) -> bool:
    """Place a resource stack on a tile if the tile is empty or same-typed."""
    if amount <= 0:
        return False

    existing = self.resources.get((x, y))
    if existing is None:
        self.resources[(x, y)] = {"type": item, "quantity": amount}
        return True

    if existing["type"] != item:
        return False

    existing["quantity"] += amount
    return True
```

Keep it intentionally small. Do not redesign `self.resources`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_world.py -k place_resource -v`

Expected: PASS

**Step 5: Commit**

```bash
git add simulation/world.py tests/test_world.py
git commit -m "feat: add world resource placement helper"
```

### Task 2: Add The `drop_item` Base Action Happy Path

**Files:**
- Create: `tests/test_drop_item.py`
- Modify: `simulation/config.py`
- Modify: `simulation/agent.py`
- Modify: `simulation/oracle.py`

**Step 1: Write the failing tests**

Create [`tests/test_drop_item.py`](../../tests/test_drop_item.py) with:

```python
from simulation.agent import Agent
from simulation.oracle import Oracle
from simulation.world import World


def make_world():
    world = World(width=5, height=5, seed=42)
    world.resources.clear()
    return world


def make_agent():
    agent = Agent(name="Ada", x=2, y=2)
    agent.inventory.add("fruit", 3)
    agent.energy = 20
    return agent


def test_drop_item_creates_resource_on_empty_tile():
    world = make_world()
    agent = make_agent()
    oracle = Oracle(world=world, llm=None)

    result = oracle.resolve_action(
        agent,
        {"action": "drop_item", "item": "fruit", "quantity": 2, "reason": "free space"},
        tick=1,
    )

    assert result["success"] is True
    assert agent.inventory.items == {"fruit": 1}
    assert world.get_resource(2, 2) == {"type": "fruit", "quantity": 2}


def test_drop_item_merges_same_type_tile_resource():
    world = make_world()
    world.resources[(2, 2)] = {"type": "fruit", "quantity": 1}
    agent = make_agent()
    oracle = Oracle(world=world, llm=None)

    result = oracle.resolve_action(
        agent,
        {"action": "drop_item", "item": "fruit", "quantity": 2, "reason": "stack it"},
        tick=1,
    )

    assert result["success"] is True
    assert agent.inventory.items == {"fruit": 1}
    assert world.get_resource(2, 2) == {"type": "fruit", "quantity": 3}
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_drop_item.py -v`

Expected: FAIL with `Unknown action: drop_item`

**Step 3: Write minimal implementation**

Modify [`simulation/config.py`](../../simulation/config.py):

```python
ENERGY_COST_DROP = 0

INITIAL_ACTIONS = [
    "move",
    "eat",
    "rest",
    "innovate",
    "pickup",
    "drop_item",
    "communicate",
    "give_item",
    "teach",
]
```

Modify [`simulation/agent.py`](../../simulation/agent.py):

```python
costs = {
    "move": ENERGY_COST_MOVE,
    "eat": ENERGY_COST_EAT,
    "rest": 0,
    "pickup": ENERGY_COST_PICKUP,
    "drop_item": ENERGY_COST_DROP,
    "innovate": ENERGY_COST_INNOVATE,
    "give_item": GIVE_ITEM_ENERGY_COST,
    "teach": TEACH_ENERGY_COST_TEACHER,
}
```

Modify [`simulation/oracle.py`](../../simulation/oracle.py):

```python
elif action_type == "drop_item":
    return self._resolve_drop_item(agent, action, tick)
```

Add the new resolver:

```python
def _resolve_drop_item(self, agent: Agent, action: dict, tick: int) -> dict:
    item = (action.get("item") or "").strip().lower()
    try:
        quantity = int(action.get("quantity", 1))
    except (ValueError, TypeError):
        quantity = 1

    if not item:
        return {"success": False, "message": "Item is required.", "effects": {}}
    if quantity <= 0:
        return {"success": False, "message": "Quantity must be at least 1.", "effects": {}}
    if not agent.inventory.has(item, quantity):
        return {"success": False, "message": f"You don't have {quantity}x {item}.", "effects": {}}
    if not self.world.place_resource(agent.x, agent.y, item, quantity):
        return {"success": False, "message": f"Cannot drop {item} on this tile.", "effects": {}}

    agent.inventory.remove(item, quantity)
    msg = f"{agent.name} dropped {quantity}x {item} at ({agent.x},{agent.y})."
    self._log(tick, msg)
    agent.add_memory(f"I dropped {quantity}x {item} on my current tile.")
    return {"success": True, "message": msg, "effects": {}}
```

Do not add extra branches yet. Get the happy path working first.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_drop_item.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_drop_item.py simulation/config.py simulation/agent.py simulation/oracle.py
git commit -m "feat: add drop item base action"
```

### Task 3: Harden `drop_item` Validation And Atomicity

**Files:**
- Modify: `tests/test_drop_item.py`
- Modify: `simulation/oracle.py`

**Step 1: Write the failing tests**

Extend [`tests/test_drop_item.py`](../../tests/test_drop_item.py) with:

```python
def test_drop_item_rejects_non_positive_quantity():
    world = make_world()
    agent = make_agent()
    oracle = Oracle(world=world, llm=None)

    result = oracle.resolve_action(
        agent,
        {"action": "drop_item", "item": "fruit", "quantity": 0, "reason": "bad"},
        tick=1,
    )

    assert result["success"] is False
    assert agent.inventory.items == {"fruit": 3}
    assert world.get_resource(2, 2) is None


def test_drop_item_defaults_invalid_quantity_to_one():
    world = make_world()
    agent = make_agent()
    oracle = Oracle(world=world, llm=None)

    result = oracle.resolve_action(
        agent,
        {"action": "drop_item", "item": "fruit", "quantity": None, "reason": "default"},
        tick=1,
    )

    assert result["success"] is True
    assert agent.inventory.items == {"fruit": 2}
    assert world.get_resource(2, 2) == {"type": "fruit", "quantity": 1}


def test_drop_item_fails_when_inventory_lacks_item():
    world = make_world()
    agent = make_agent()
    oracle = Oracle(world=world, llm=None)

    result = oracle.resolve_action(
        agent,
        {"action": "drop_item", "item": "stone", "quantity": 1, "reason": "impossible"},
        tick=1,
    )

    assert result["success"] is False
    assert world.get_resource(2, 2) is None


def test_drop_item_fails_on_conflicting_tile_resource_without_mutation():
    world = make_world()
    world.resources[(2, 2)] = {"type": "stone", "quantity": 4}
    agent = make_agent()
    oracle = Oracle(world=world, llm=None)

    result = oracle.resolve_action(
        agent,
        {"action": "drop_item", "item": "fruit", "quantity": 2, "reason": "conflict"},
        tick=1,
    )

    assert result["success"] is False
    assert agent.inventory.items == {"fruit": 3}
    assert world.get_resource(2, 2) == {"type": "stone", "quantity": 4}


def test_drop_item_adds_memory_on_success():
    world = make_world()
    agent = make_agent()
    oracle = Oracle(world=world, llm=None)

    oracle.resolve_action(
        agent,
        {"action": "drop_item", "item": "fruit", "quantity": 1, "reason": "remember this"},
        tick=1,
    )

    assert any("dropped 1x fruit" in memory.lower() for memory in agent.memory)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_drop_item.py -v`

Expected: at least one FAIL around validation, conflict handling, or memory text

**Step 3: Write minimal implementation**

Refine [`simulation/oracle.py`](../../simulation/oracle.py):

- normalize `item` with `.strip().lower()`
- keep invalid `quantity` fallback to `1`
- reject blank `item`
- reject non-positive quantities
- fail before mutating inventory when the tile holds a different resource type
- keep failure paths mutation-free
- make success memory/message specific enough for the test

Target shape:

```python
if not item:
    return {"success": False, "message": "Item is required.", "effects": {}}

if quantity <= 0:
    return {"success": False, "message": "Quantity must be at least 1.", "effects": {}}

if not agent.inventory.has(item, quantity):
    return {"success": False, "message": f"You don't have {quantity}x {item}.", "effects": {}}

placed = self.world.place_resource(agent.x, agent.y, item, quantity)
if not placed:
    return {
        "success": False,
        "message": f"{agent.name} cannot drop {item} here because the tile already holds another resource.",
        "effects": {},
    }
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_drop_item.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_drop_item.py simulation/oracle.py
git commit -m "test: harden drop item validation"
```

### Task 4: Document The Action In Prompts And Add Metrics Coverage

**Files:**
- Modify: `prompts/agent/system.txt`
- Modify: `simulation/schemas.py`
- Modify: `tests/test_agent_prompts.py`
- Modify: `tests/test_metrics_builder.py`

**Step 1: Write the failing tests**

Add this prompt test to [`tests/test_agent_prompts.py`](../../tests/test_agent_prompts.py):

```python
def test_system_prompt_documents_drop_item():
    agent = Agent(name="Ada", x=5, y=5)

    prompt = agent._build_system_prompt()

    assert '{"action": "drop_item"' in prompt
    assert '"item": "<item_name>"' in prompt
```

Add this regression to [`tests/test_metrics_builder.py`](../../tests/test_metrics_builder.py):

```python
def test_actions_by_type_counts_drop_item(self, tmp_path):
    run_dir = tmp_path / "test-run"
    events = _minimal_run()
    events.append(
        {
            "run_id": "test-run",
            "tick": 3,
            "sim_time": {"day": 1, "hour": 8},
            "event_type": "agent_decision",
            "agent_id": "Ada",
            "payload": {
                "parsed_action": {"action": "drop_item"},
                "parse_ok": True,
                "action_origin": "base",
            },
        }
    )
    _write_events(run_dir, events)

    MetricsBuilder(run_dir).build()
    summary = json.loads((run_dir / "metrics" / "summary.json").read_text())

    assert summary["actions"]["by_type"]["drop_item"] == 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agent_prompts.py -k drop_item -v`

Expected: FAIL because the system prompt does not document the `drop_item` action format yet

**Step 3: Write minimal implementation**

Update [`prompts/agent/system.txt`](../../prompts/agent/system.txt):

```text
- drop_item: {"action": "drop_item", "item": "<item_name>", "quantity": 1, "reason": "..."}
  (drop an inventory item onto your current tile; fails if the tile already holds a different resource)
```

Update the inline schema comments in [`simulation/schemas.py`](../../simulation/schemas.py):

```python
item: Optional[str] = None            # give_item / eat (inventory) / drop_item
quantity: Optional[int] = None        # give_item / drop_item
```

No runtime change should be necessary in [`simulation/metrics_builder.py`](../../simulation/metrics_builder.py). The new test should pass because action counting is already generic.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agent_prompts.py -k drop_item -v`

Expected: PASS

Run: `uv run pytest tests/test_metrics_builder.py -k drop_item -v`

Expected: PASS

**Step 5: Commit**

```bash
git add prompts/agent/system.txt simulation/schemas.py tests/test_agent_prompts.py tests/test_metrics_builder.py
git commit -m "docs: document drop item prompt and metrics coverage"
```

### Task 5: Update Cornerstone And Planning Docs

**Files:**
- Modify: `project-cornerstone/00-master-plan/MASTER_PLAN.md`
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Modify: `project-cornerstone/01-architecture/architecture_context.md`
- Modify: `project-cornerstone/03-agents/agents_context.md`
- Modify: `project-cornerstone/04-oracle/oracle_context.md`

**Step 1: Write the doc changes**

Update the cornerstone files so they all agree on the new built-in action:

- add `drop_item` to the built-in action list in [`project-cornerstone/03-agents/agents_context.md`](../../project-cornerstone/03-agents/agents_context.md)
- add `drop_item` to the built-in oracle flow in [`project-cornerstone/04-oracle/oracle_context.md`](../../project-cornerstone/04-oracle/oracle_context.md)
- note in [`project-cornerstone/01-architecture/architecture_context.md`](../../project-cornerstone/01-architecture/architecture_context.md) that inventory placement is resolved through the oracle
- update inventory capability wording in [`project-cornerstone/00-master-plan/MASTER_PLAN.md`](../../project-cornerstone/00-master-plan/MASTER_PLAN.md)
- add a decision-log entry in [`project-cornerstone/00-master-plan/DECISION_LOG.md`](../../project-cornerstone/00-master-plan/DECISION_LOG.md) recording:

```text
Dropped items are placed on the current tile only.
The world remains one resource stack per tile.
drop_item succeeds on empty or same-type stacks and fails on conflicting resource types.
```

**Step 2: Verify the docs mention the new action consistently**

Run:

```bash
rg -n "drop_item|drop item" \
  project-cornerstone/00-master-plan/MASTER_PLAN.md \
  project-cornerstone/00-master-plan/DECISION_LOG.md \
  project-cornerstone/01-architecture/architecture_context.md \
  project-cornerstone/03-agents/agents_context.md \
  project-cornerstone/04-oracle/oracle_context.md
```

Expected: each file shows at least one relevant match

**Step 3: Commit**

```bash
git add \
  project-cornerstone/00-master-plan/MASTER_PLAN.md \
  project-cornerstone/00-master-plan/DECISION_LOG.md \
  project-cornerstone/01-architecture/architecture_context.md \
  project-cornerstone/03-agents/agents_context.md \
  project-cornerstone/04-oracle/oracle_context.md
git commit -m "docs: update cornerstone for drop item action"
```

### Task 6: Final Verification

**Files:**
- No new file edits

**Step 1: Run focused feature tests**

Run:

```bash
uv run pytest tests/test_world.py -k place_resource -v
uv run pytest tests/test_drop_item.py tests/test_agent_prompts.py tests/test_metrics_builder.py -v
```

Expected: PASS

**Step 2: Run the project-required non-slow suite**

Run: `uv run pytest -m "not slow"`

Expected: PASS

**Step 3: Smoke-test the simulation**

Run: `uv run main.py --no-llm --ticks 5 --agents 1`

Expected: simulation completes without crashing

**Step 4: Commit any final touch-ups only if verification required code changes**

```bash
git status --short
```

If verification exposed issues and you had to patch code, commit those specific changes with a narrow message such as:

```bash
git add <exact files>
git commit -m "fix: finalize drop item action"
```

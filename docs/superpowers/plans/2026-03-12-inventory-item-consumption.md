# Inventory Item Consumption Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow agents to eat items from their inventory by adding an optional `item` field to the `eat` action.

**Architecture:** Add an early-return branch at the top of `Oracle._resolve_eat` that intercepts when `action["item"]` is set, consumes from `agent.inventory` instead of world resources, and reuses the existing `_get_item_eat_effect` LLM/precedent lookup. The world-resource path is untouched. Update the agent system prompt and schema comment to document the new field.

**Tech Stack:** Python, pytest, uv (`uv run pytest`)

---

## Chunk 1: Tests + Oracle implementation

### Task 1: Write the six failing tests

**Files:**
- Create: `tests/test_eat_inventory.py`

**Context:** Follow the exact patterns from `tests/test_eat.py`. The helper functions (`_make_world`, `_make_agent`, `_make_oracle`, `_place_resource`) are duplicated here for isolation. Precedents are pre-seeded at `oracle.precedents["physical:eat:<type>"]` — do NOT mock `generate_structured`.

- [ ] **Step 1: Create the test file**

```python
# tests/test_eat_inventory.py
"""
Unit tests for eating items from inventory (issue: agents picking up items
but never consuming them).

Covers:
- Eat from inventory: success, hunger reduced, item removed, energy cost
- Eat from inventory: memory entry added
- Eat from inventory: life_change applied for harmful items
- Eat from inventory: failure when item not in inventory
- Regression: eat without item field still consumes world resource, not inventory
"""

from unittest.mock import MagicMock

import pytest

from simulation.agent import Agent
from simulation.oracle import Oracle
from simulation.world import World
from simulation.config import AGENT_START_LIFE, ENERGY_COST_EAT


# ---------------------------------------------------------------------------
# Helpers (same patterns as test_eat.py)
# ---------------------------------------------------------------------------

def _make_world(seed: int = 42) -> World:
    return World(width=5, height=5, seed=seed)


def _make_agent(x: int = 2, y: int = 2) -> Agent:
    return Agent(name="Tester", x=x, y=y)


def _make_oracle(world: World) -> Oracle:
    return Oracle(world=world, llm=None)


def _place_resource(world: World, x: int, y: int, resource_type: str, quantity: int = 3):
    world.resources[(x, y)] = {"type": resource_type, "quantity": quantity}


def _clear_adjacent(world: World, x: int, y: int):
    """Remove all resources at agent position and 4 cardinal neighbours."""
    for pos in [(x, y), (x+1, y), (x-1, y), (x, y+1), (x, y-1)]:
        world.resources.pop(pos, None)


# ---------------------------------------------------------------------------
# Tests: eat from inventory
# ---------------------------------------------------------------------------

class TestEatFromInventory:
    def test_eat_from_inventory_success(self):
        """Eating fruit from inventory succeeds, removes item, reduces hunger."""
        world = _make_world()
        agent = _make_agent()
        agent.hunger = 60
        _clear_adjacent(world, agent.x, agent.y)
        agent.inventory.add("fruit", 1)
        oracle = _make_oracle(world)
        oracle.precedents["physical:eat:fruit"] = {
            "possible": True, "hunger_reduction": 20, "life_change": 0, "reason": "edible"
        }

        result = oracle.resolve_action(agent, {"action": "eat", "item": "fruit"}, tick=1)

        assert result["success"] is True
        assert not agent.inventory.has("fruit")
        assert agent.hunger == 40
        assert result["effects"]["life"] == 0

    def test_eat_from_inventory_energy_cost(self):
        """Eating from inventory deducts ENERGY_COST_EAT energy."""
        world = _make_world()
        agent = _make_agent()
        agent.hunger = 60
        agent.energy = 50
        _clear_adjacent(world, agent.x, agent.y)
        agent.inventory.add("fruit", 1)
        oracle = _make_oracle(world)
        oracle.precedents["physical:eat:fruit"] = {
            "possible": True, "hunger_reduction": 20, "life_change": 0, "reason": "edible"
        }

        oracle.resolve_action(agent, {"action": "eat", "item": "fruit"}, tick=1)

        assert agent.energy == 50 - ENERGY_COST_EAT

    def test_eat_from_inventory_memory_update(self):
        """Eating from inventory writes a memory entry mentioning 'inventory'."""
        world = _make_world()
        agent = _make_agent()
        agent.hunger = 60
        _clear_adjacent(world, agent.x, agent.y)
        agent.inventory.add("fruit", 1)
        oracle = _make_oracle(world)
        oracle.precedents["physical:eat:fruit"] = {
            "possible": True, "hunger_reduction": 20, "life_change": 0, "reason": "edible"
        }

        oracle.resolve_action(agent, {"action": "eat", "item": "fruit"}, tick=1)

        assert any("inventory" in m for m in agent.memory)

    def test_eat_from_inventory_no_item(self):
        """Eating an item not in inventory returns failure and leaves inventory unchanged."""
        world = _make_world()
        agent = _make_agent()
        _clear_adjacent(world, agent.x, agent.y)
        oracle = _make_oracle(world)

        result = oracle.resolve_action(agent, {"action": "eat", "item": "stone"}, tick=1)

        assert result["success"] is False
        assert agent.inventory.total() == 0

    def test_eat_from_inventory_life_change(self):
        """Eating a harmful item from inventory reduces life."""
        world = _make_world()
        agent = _make_agent()
        agent.hunger = 60
        _clear_adjacent(world, agent.x, agent.y)
        agent.inventory.add("mushroom", 1)
        oracle = _make_oracle(world)
        oracle.precedents["physical:eat:mushroom"] = {
            "possible": True, "hunger_reduction": 5, "life_change": -10, "reason": "toxic"
        }

        initial_life = agent.life
        oracle.resolve_action(agent, {"action": "eat", "item": "mushroom"}, tick=1)

        assert agent.life == initial_life - 10

    def test_eat_world_resource_when_inventory_nonempty(self):
        """eat without item field still consumes world resource, not inventory."""
        world = _make_world()
        agent = _make_agent()
        agent.hunger = 60
        _clear_adjacent(world, agent.x, agent.y)
        # Place a world resource adjacent to agent
        _place_resource(world, 3, 2, "fruit", quantity=1)
        # Also give agent fruit in inventory
        agent.inventory.add("fruit", 1)
        oracle = _make_oracle(world)

        result = oracle.resolve_action(agent, {"action": "eat"}, tick=1)

        # World resource consumed
        assert result["success"] is True
        assert world.get_resource(3, 2) is None
        # Inventory unchanged
        assert agent.inventory.items == {"fruit": 1}
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
uv run pytest tests/test_eat_inventory.py -v
```

Expected: All 6 tests FAIL. Most will fail because the inventory branch doesn't exist yet in `_resolve_eat`, so `eat` with `item` field will fall through to the world-resource loop and return failure (no world resource available). The regression test (`test_eat_world_resource_when_inventory_nonempty`) may pass already — that's fine, it should still be green after implementation.

---

### Task 2: Implement the inventory branch in `_resolve_eat`

**Files:**
- Modify: `simulation/oracle.py:284-342`

- [ ] **Step 1: Open `simulation/oracle.py` and locate `_resolve_eat` (line 284)**

The method starts at line 284. Insert the inventory branch immediately after the method signature and before `positions_to_check`.

- [ ] **Step 2: Add the inventory branch**

Insert the following block **between** the `def _resolve_eat(...)` signature line and the existing `positions_to_check = [` line. Do NOT duplicate `positions_to_check = [` — it must appear exactly once (already present further down).

The old string to find and replace (the entire opening of the method — signature + first line of body):
```python
    def _resolve_eat(self, agent: Agent, action: dict, tick: int) -> dict:
        positions_to_check = [
```

Replace with (the signature, the new inventory branch, and then the world-path comment leading into the same `positions_to_check` line):
```python
    def _resolve_eat(self, agent: Agent, action: dict, tick: int) -> dict:
        # --- Inventory path: agent explicitly specifies item to eat ---
        item = action.get("item", "").strip().lower()
        if item:
            if not agent.inventory.has(item):
                return {
                    "success": False,
                    "message": f"{agent.name} tried to eat {item} but has none in inventory.",
                    "effects": {},
                }
            effect = self._get_item_eat_effect(item, tick)
            if not effect["possible"]:
                return {
                    "success": False,
                    "message": f"{agent.name} cannot eat {item}: {effect['reason']}.",
                    "effects": {},
                }
            agent.inventory.remove(item, 1)
            agent.modify_hunger(-effect["hunger_reduction"])
            if effect.get("life_change"):
                agent.modify_life(effect["life_change"])
            cost = self._apply_energy_cost(agent, ENERGY_COST_EAT, tick)
            msg = (
                f"{agent.name} ate {item} from inventory. "
                f"Hunger -{effect['hunger_reduction']} → {agent.hunger}."
            )
            self._log(tick, msg)
            agent.add_memory(
                f"I ate {item} from my inventory. "
                f"Hunger -{effect['hunger_reduction']} → {agent.hunger}. Energy: {agent.energy}."
            )
            return {
                "success": True,
                "message": msg,
                "effects": {
                    "hunger": -effect["hunger_reduction"],
                    "life": effect.get("life_change", 0),
                    "energy": -cost,
                },
            }

        # --- World path: eat from tile at current or adjacent position ---
        positions_to_check = [
```

- [ ] **Step 3: Run the new tests**

```bash
uv run pytest tests/test_eat_inventory.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 4: Run the existing eat tests to confirm no regression**

```bash
uv run pytest tests/test_eat.py -v
```

Expected: All existing tests PASS.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest -m "not slow"
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_eat_inventory.py simulation/oracle.py
git commit -m "feat: allow agents to eat items from inventory via eat action item field"
```

---

## Chunk 2: Prompt and schema updates

### Task 3: Update the agent system prompt

**Files:**
- Modify: `prompts/agent/system.txt:13`

The current line 13 reads:
```
- eat: {"action": "eat", "reason": "..."} (eat food at current or adjacent tile)
```

- [ ] **Step 1: Update the eat line in `prompts/agent/system.txt`**

Change it to:
```
- eat: {"action": "eat", "reason": "..."} (eat food at current or adjacent tile; add "item": "<name>" to eat from inventory instead)
```

- [ ] **Step 2: Verify the change looks right**

```bash
grep -n "eat" prompts/agent/system.txt
```

Expected output includes:
```
- eat: {"action": "eat", "reason": "..."} (eat food at current or adjacent tile; add "item": "<name>" to eat from inventory instead)
```

### Task 4: Update the schema comment

**Files:**
- Modify: `simulation/schemas.py:61`

The current line reads:
```python
    item: Optional[str] = None          # give_item
```

- [ ] **Step 1: Update the comment**

Change it to:
```python
    item: Optional[str] = None          # give_item / eat (inventory)
```

- [ ] **Step 2: Commit both prompt and schema changes**

```bash
git add prompts/agent/system.txt simulation/schemas.py
git commit -m "docs: update eat action prompt and schema comment for inventory eating"
```

- [ ] **Step 3: Smoke test with no-LLM mode**

```bash
uv run main.py --no-llm --ticks 5 --agents 1
```

Expected: Simulation runs to completion with no errors.

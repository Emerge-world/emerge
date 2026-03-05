# Agent Inventory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a quantity-based inventory system to agents, with a `pickup` base action, so agents can collect world resources for future use (crafting, etc.).

**Architecture:** New `Inventory` class in `simulation/inventory.py` (mirrors the `Memory` class pattern) assigned to each agent at construction. The Oracle handles `pickup` action resolution. Inventory appears in the decision prompt only when non-empty.

**Tech Stack:** Python 3.12+, pytest — no new dependencies.

---

## Task 1: Create `simulation/inventory.py`

**Files:**
- Create: `simulation/inventory.py`
- Test: `tests/test_inventory.py`

**Step 1: Write the failing tests**

Create `tests/test_inventory.py`:

```python
"""Unit tests for the Inventory class."""
import pytest
from simulation.inventory import Inventory


class TestInventoryAdd:
    def test_add_to_empty(self):
        inv = Inventory(capacity=10)
        added = inv.add("fruit", 3)
        assert added == 3
        assert inv.items["fruit"] == 3

    def test_add_clips_to_capacity(self):
        inv = Inventory(capacity=5)
        added = inv.add("fruit", 10)
        assert added == 5
        assert inv.total() == 5

    def test_add_multiple_types(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 3)
        inv.add("stone", 2)
        assert inv.items["fruit"] == 3
        assert inv.items["stone"] == 2
        assert inv.total() == 5

    def test_add_when_full_returns_zero(self):
        inv = Inventory(capacity=3)
        inv.add("fruit", 3)
        added = inv.add("stone", 1)
        assert added == 0
        assert inv.total() == 3

    def test_add_partially_fills(self):
        inv = Inventory(capacity=5)
        inv.add("fruit", 3)
        added = inv.add("stone", 4)  # only 2 slots left
        assert added == 2
        assert inv.total() == 5


class TestInventoryRemove:
    def test_remove_success(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 3)
        result = inv.remove("fruit", 2)
        assert result is True
        assert inv.items["fruit"] == 1

    def test_remove_deletes_key_at_zero(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 2)
        inv.remove("fruit", 2)
        assert "fruit" not in inv.items

    def test_remove_fails_not_enough(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 1)
        result = inv.remove("fruit", 5)
        assert result is False
        assert inv.items["fruit"] == 1  # unchanged

    def test_remove_fails_missing_item(self):
        inv = Inventory(capacity=10)
        result = inv.remove("stone", 1)
        assert result is False


class TestInventoryHas:
    def test_has_enough(self):
        inv = Inventory(capacity=10)
        inv.add("stone", 3)
        assert inv.has("stone", 3) is True
        assert inv.has("stone", 1) is True

    def test_has_not_enough(self):
        inv = Inventory(capacity=10)
        inv.add("stone", 2)
        assert inv.has("stone", 3) is False

    def test_has_missing_item(self):
        inv = Inventory(capacity=10)
        assert inv.has("fruit", 1) is False

    def test_has_default_qty_one(self):
        inv = Inventory(capacity=10)
        inv.add("mushroom", 1)
        assert inv.has("mushroom") is True


class TestInventoryCapacity:
    def test_total_empty(self):
        inv = Inventory(capacity=10)
        assert inv.total() == 0

    def test_total_mixed(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 2)
        inv.add("stone", 3)
        assert inv.total() == 5

    def test_free_space(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 3)
        assert inv.free_space() == 7

    def test_is_empty_true(self):
        assert Inventory(capacity=10).is_empty() is True

    def test_is_empty_false(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 1)
        assert inv.is_empty() is False


class TestInventoryPrompt:
    def test_to_prompt_empty(self):
        inv = Inventory(capacity=10)
        assert inv.to_prompt() == ""

    def test_to_prompt_with_items(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 2)
        inv.add("stone", 1)
        prompt = inv.to_prompt()
        assert "fruit x2" in prompt
        assert "stone x1" in prompt
        assert "3/10" in prompt
        assert prompt.startswith("INVENTORY:")

    def test_to_prompt_sorted_alphabetically(self):
        inv = Inventory(capacity=10)
        inv.add("stone", 1)
        inv.add("fruit", 2)
        prompt = inv.to_prompt()
        assert prompt.index("fruit") < prompt.index("stone")


class TestInventorySerialization:
    def test_to_dict(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 3)
        d = inv.to_dict()
        assert d == {"items": {"fruit": 3}, "capacity": 10}

    def test_from_dict_roundtrip(self):
        inv = Inventory(capacity=15)
        inv.add("fruit", 4)
        inv.add("stone", 2)
        restored = Inventory.from_dict(inv.to_dict())
        assert restored.capacity == 15
        assert restored.items == {"fruit": 4, "stone": 2}
        assert restored.total() == 6

    def test_from_dict_empty(self):
        d = {"items": {}, "capacity": 10}
        inv = Inventory.from_dict(d)
        assert inv.is_empty()
        assert inv.capacity == 10
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/gusy/emerge
uv run pytest tests/test_inventory.py -v
```

Expected: `ModuleNotFoundError: No module named 'simulation.inventory'`

**Step 3: Implement `simulation/inventory.py`**

```python
"""
Agent inventory: carries items collected from the world.
Capacity is measured by total quantity (not unique item types).
"""


class Inventory:
    """Quantity-based item inventory for an agent."""

    def __init__(self, capacity: int = 10):
        self.items: dict[str, int] = {}
        self.capacity: int = capacity

    def add(self, item: str, qty: int) -> int:
        """Add qty of item. Returns actual qty added (clipped to free space)."""
        can_add = min(qty, self.free_space())
        if can_add > 0:
            self.items[item] = self.items.get(item, 0) + can_add
        return can_add

    def remove(self, item: str, qty: int) -> bool:
        """Remove qty of item. Returns True if had enough, False otherwise."""
        if not self.has(item, qty):
            return False
        self.items[item] -= qty
        if self.items[item] == 0:
            del self.items[item]
        return True

    def has(self, item: str, qty: int = 1) -> bool:
        """Return True if carrying at least qty of item."""
        return self.items.get(item, 0) >= qty

    def total(self) -> int:
        """Total number of items carried (sum of all quantities)."""
        return sum(self.items.values())

    def free_space(self) -> int:
        """Remaining capacity."""
        return self.capacity - self.total()

    def is_empty(self) -> bool:
        return self.total() == 0

    def to_prompt(self) -> str:
        """Returns inventory line for the decision prompt. Empty string if empty."""
        if self.is_empty():
            return ""
        parts = [f"{item} x{qty}" for item, qty in sorted(self.items.items())]
        return f"INVENTORY: {', '.join(parts)} ({self.total()}/{self.capacity})"

    def to_dict(self) -> dict:
        return {"items": dict(self.items), "capacity": self.capacity}

    @classmethod
    def from_dict(cls, data: dict) -> "Inventory":
        inv = cls(capacity=data.get("capacity", 10))
        inv.items = dict(data.get("items", {}))
        return inv
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_inventory.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add simulation/inventory.py tests/test_inventory.py
git commit -m "feat(inventory): add Inventory class with capacity and serialization"
```

---

## Task 2: Add `AGENT_INVENTORY_CAPACITY` to config and wire `Inventory` into `Agent`

**Files:**
- Modify: `simulation/config.py:126-127`
- Modify: `simulation/agent.py:9-16` (imports), `simulation/agent.py:33-57` (`__init__`), `simulation/agent.py:219-247` (`_build_decision_prompt`), `simulation/agent.py:280-292` (`get_status`)

**Step 1: Add config constant**

In `simulation/config.py`, after line 127 (`BASE_ACTIONS = ["move", "eat", "rest", "innovate"]`), add:

```python
# --- Inventory ---
AGENT_INVENTORY_CAPACITY = 10   # maximum total items an agent can carry
```

Also change `BASE_ACTIONS` on line 127:

```python
BASE_ACTIONS = ["move", "eat", "rest", "innovate", "pickup"]
```

**Step 2: Update `simulation/agent.py`**

**2a. Add imports at top of file** (after existing imports, around line 16):

```python
from simulation.inventory import Inventory
from simulation.config import (
    AGENT_MAX_LIFE, AGENT_MAX_HUNGER, AGENT_MAX_ENERGY,
    AGENT_START_LIFE, AGENT_START_HUNGER, AGENT_START_ENERGY,
    HUNGER_PER_TICK, HUNGER_DAMAGE_THRESHOLD, HUNGER_DAMAGE_PER_TICK,
    ENERGY_COST_MOVE, ENERGY_COST_EAT, ENERGY_COST_INNOVATE,
    ENERGY_RECOVERY_REST, ENERGY_LOW_THRESHOLD, ENERGY_DAMAGE_PER_TICK,
    BASE_ACTIONS, AGENT_VISION_RADIUS, AGENT_INVENTORY_CAPACITY,
)
```

**2b. Add inventory in `__init__`** (after `self.memory_system = Memory()` at line 49):

```python
        # Inventory (quantity-based, max AGENT_INVENTORY_CAPACITY total items)
        self.inventory = Inventory(capacity=AGENT_INVENTORY_CAPACITY)
```

**2c. Inject inventory into decision prompt** in `_build_decision_prompt` (currently lines 219-247).

The `decision.txt` template has `$time_info` as the first line. We need to pass an `inventory_info` variable. Update the `render()` call to include it:

```python
    def _build_decision_prompt(self, nearby_tiles: list[dict], tick: int,
                               time_description: str = "") -> str:
        ascii_grid = self._build_ascii_grid(nearby_tiles)
        resource_hints = self._build_resource_hints(nearby_tiles)
        memory_text = self.get_recent_memory()

        if self.energy <= 0:
            status_effects = prompt_loader.load("agent/energy_critical")
        elif self.energy <= ENERGY_LOW_THRESHOLD:
            status_effects = prompt_loader.load("agent/energy_low")
        else:
            status_effects = ""

        inventory_info = self.inventory.to_prompt()  # empty string if empty

        return prompt_loader.render(
            "agent/decision",
            tick=tick,
            life=self.life,
            max_life=AGENT_MAX_LIFE,
            hunger=self.hunger,
            max_hunger=AGENT_MAX_HUNGER,
            hunger_threshold=HUNGER_DAMAGE_THRESHOLD,
            energy=self.energy,
            max_energy=AGENT_MAX_ENERGY,
            ascii_grid=ascii_grid,
            resource_hints=resource_hints,
            memory_text=memory_text,
            status_effects=status_effects,
            time_info=time_description,
            inventory_info=inventory_info,
        )
```

**2d. Extend `get_status()`** to include inventory (currently lines 280-292):

```python
    def get_status(self) -> dict:
        return {
            "name": self.name,
            "position": (self.x, self.y),
            "life": self.life,
            "hunger": self.hunger,
            "energy": self.energy,
            "alive": self.alive,
            "actions": self.actions,
            "memory_entries": self.memory_system.total_entries,
            "memory_episodic": len(self.memory_system.episodic),
            "memory_semantic": len(self.memory_system.semantic),
            "inventory": self.inventory.to_dict(),
        }
```

**Step 3: Update `prompts/agent/decision.txt`**

Current content is:
```
$time_info
TICK $tick - What do you do next?

YOUR STATS: Life=$life/$max_life, Hunger=$hunger/$max_hunger (danger at ${hunger_threshold}+), Energy=$energy/$max_energy
$status_effects
YOUR VISION (7x7 grid, you are @):
$ascii_grid

NEARBY RESOURCES:
$resource_hints

YOUR MEMORY:
$memory_text

Respond with a JSON object.
```

Add `$inventory_info` after the STATS line (it renders as empty string if inventory is empty):

```
$time_info
TICK $tick - What do you do next?

YOUR STATS: Life=$life/$max_life, Hunger=$hunger/$max_hunger (danger at ${hunger_threshold}+), Energy=$energy/$max_energy
$status_effects
$inventory_info
YOUR VISION (7x7 grid, you are @):
$ascii_grid

NEARBY RESOURCES:
$resource_hints

YOUR MEMORY:
$memory_text

Respond with a JSON object.
```

**Step 4: Update `prompts/agent/system.txt`**

Add `pickup` to the action format section. After the `innovate` line, add:

```
- pickup: {"action": "pickup", "reason": "..."} (collect 1 item from your current tile into inventory)
```

**Step 5: Run full test suite**

```bash
uv run pytest -m "not slow" -v
```

Expected: All existing tests PASS (no regressions). `get_status()` now returns `"inventory"` key.

**Step 6: Smoke test**

```bash
uv run main.py --no-llm --ticks 5 --agents 1
```

Expected: simulation runs without errors.

**Step 7: Commit**

```bash
git add simulation/config.py simulation/agent.py prompts/agent/decision.txt prompts/agent/system.txt
git commit -m "feat(inventory): wire Inventory into Agent and add pickup to BASE_ACTIONS"
```

---

## Task 3: Implement `pickup` action in Oracle

**Files:**
- Modify: `simulation/oracle.py:116-141` (`resolve_action`), `simulation/oracle.py:322-399` (`_resolve_innovate`)
- Test: `tests/test_oracle_pickup.py` (new file)

**Step 1: Write the failing tests**

Create `tests/test_oracle_pickup.py`:

```python
"""Tests for Oracle pickup action resolution."""
import pytest
from simulation.agent import Agent
from simulation.oracle import Oracle
from simulation.world import World
from simulation.config import AGENT_INVENTORY_CAPACITY


def _make_world(seed: int = 42, width: int = 20, height: int = 20) -> World:
    return World(width=width, height=height, seed=seed)


def _make_oracle(world: World) -> Oracle:
    return Oracle(world=world, llm=None)


def _find_tile_with_resource(world: World, resource_type: str = None):
    """Return (x, y) of first tile with a resource, optionally filtered by type."""
    for (x, y), res in world.resources.items():
        if resource_type is None or res["type"] == resource_type:
            if res.get("quantity", 0) > 0:
                return (x, y)
    return None


class TestOraclePickup:
    def test_pickup_success(self):
        """Agent picks up 1 item from tile with resource."""
        world = _make_world()
        pos = _find_tile_with_resource(world)
        if pos is None:
            pytest.skip("No tile with resource in generated world")
        x, y = pos
        resource_type = world.resources[(x, y)]["type"]
        qty_before = world.resources[(x, y)]["quantity"]

        oracle = _make_oracle(world)
        agent = Agent(x=x, y=y)

        result = oracle.resolve_action(agent, {"action": "pickup"}, tick=1)

        assert result["success"] is True
        assert agent.inventory.has(resource_type, 1)
        # World resource decremented by 1 (unless water which is infinite)
        if resource_type != "water":
            assert world.resources.get((x, y), {}).get("quantity", 0) == qty_before - 1

    def test_pickup_no_resource(self):
        """Agent picks up from empty tile → failure."""
        world = _make_world()
        oracle = _make_oracle(world)

        # Find a land tile without resources
        land_pos = None
        for y in range(world.height):
            for x in range(world.width):
                if world.get_tile(x, y) == "land" and world.get_resource(x, y) is None:
                    land_pos = (x, y)
                    break
            if land_pos:
                break

        if land_pos is None:
            pytest.skip("No resource-free land tile in this world")

        agent = Agent(x=land_pos[0], y=land_pos[1])
        result = oracle.resolve_action(agent, {"action": "pickup"}, tick=1)

        assert result["success"] is False
        assert agent.inventory.is_empty()

    def test_pickup_inventory_full(self):
        """Agent with full inventory cannot pick up."""
        world = _make_world()
        pos = _find_tile_with_resource(world)
        if pos is None:
            pytest.skip("No tile with resource in generated world")
        x, y = pos

        oracle = _make_oracle(world)
        agent = Agent(x=x, y=y)

        # Fill inventory to capacity with existing items
        agent.inventory.add("stone", AGENT_INVENTORY_CAPACITY)
        assert agent.inventory.free_space() == 0

        result = oracle.resolve_action(agent, {"action": "pickup"}, tick=1)

        assert result["success"] is False
        assert "full" in result["message"].lower()

    def test_pickup_world_resource_decremented(self):
        """Pickup removes exactly 1 from world resource (non-water)."""
        world = _make_world()
        pos = _find_tile_with_resource(world, resource_type="fruit")
        if pos is None:
            pytest.skip("No fruit in generated world")
        x, y = pos
        qty_before = world.resources[(x, y)]["quantity"]

        oracle = _make_oracle(world)
        agent = Agent(x=x, y=y)
        oracle.resolve_action(agent, {"action": "pickup"}, tick=1)

        remaining = world.resources.get((x, y), {}).get("quantity", 0)
        assert remaining == qty_before - 1

    def test_pickup_adds_to_inventory(self):
        """Pickup adds the resource type to agent inventory."""
        world = _make_world()
        pos = _find_tile_with_resource(world, resource_type="fruit")
        if pos is None:
            pytest.skip("No fruit in generated world")
        x, y = pos

        oracle = _make_oracle(world)
        agent = Agent(x=x, y=y)
        oracle.resolve_action(agent, {"action": "pickup"}, tick=1)

        assert agent.inventory.has("fruit", 1)
        assert agent.inventory.total() == 1

    def test_agent_status_includes_inventory(self):
        """get_status() returns inventory field."""
        agent = Agent(x=0, y=0)
        status = agent.get_status()
        assert "inventory" in status
        assert "items" in status["inventory"]
        assert "capacity" in status["inventory"]


class TestOracleInnovateRequiresItems:
    """Oracle checks requires.items before LLM call for innovations."""

    def test_innovate_fails_missing_required_item(self):
        """Innovation with item requirement fails if agent lacks the item."""
        world = _make_world()
        oracle = _make_oracle(world)

        # Find a land tile for the agent
        land_pos = None
        for y in range(world.height):
            for x in range(world.width):
                if world.get_tile(x, y) == "land":
                    land_pos = (x, y)
                    break
            if land_pos:
                break

        if land_pos is None:
            pytest.skip("No land tile in world")

        agent = Agent(x=land_pos[0], y=land_pos[1])
        # Agent has no items in inventory

        action = {
            "action": "innovate",
            "new_action_name": "build_shelter",
            "description": "build a shelter from wood",
            "requires": {"items": {"wood": 3}},
        }
        result = oracle.resolve_action(agent, action, tick=1)

        assert result["success"] is False
        assert "build_shelter" not in agent.actions
        assert "wood" in result["message"].lower() or "item" in result["message"].lower()

    def test_innovate_succeeds_with_required_items(self):
        """Innovation with item requirement succeeds if agent has the items (no LLM)."""
        world = _make_world()
        oracle = _make_oracle(world)  # no LLM → auto-approves

        # Place agent on land
        land_pos = None
        for y in range(world.height):
            for x in range(world.width):
                if world.get_tile(x, y) == "land":
                    land_pos = (x, y)
                    break
            if land_pos:
                break

        if land_pos is None:
            pytest.skip("No land tile in world")

        agent = Agent(x=land_pos[0], y=land_pos[1])
        agent.inventory.add("stone", 3)  # give agent required items

        action = {
            "action": "innovate",
            "new_action_name": "make_knife",
            "description": "carve stone into a knife",
            "requires": {"items": {"stone": 2}},
        }
        result = oracle.resolve_action(agent, action, tick=1)

        # Without LLM, oracle auto-approves innovations
        assert result["success"] is True
        assert "make_knife" in agent.actions
        # Items should NOT be consumed (crafting is next PR)
        assert agent.inventory.has("stone", 3)
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_oracle_pickup.py -v
```

Expected: Most tests FAIL because `pickup` action is not yet routed in Oracle.

**Step 3: Implement `_resolve_pickup` in Oracle**

In `simulation/oracle.py`, in the `resolve_action` method (lines 116-141), add `pickup` routing before the custom action branch:

```python
    def resolve_action(self, agent: Agent, action: dict, tick: int) -> dict:
        action_type = action.get("action", "none")

        if action_type == "move":
            return self._resolve_move(agent, action, tick)
        elif action_type == "eat":
            return self._resolve_eat(agent, action, tick)
        elif action_type == "rest":
            return self._resolve_rest(agent, action, tick)
        elif action_type == "innovate":
            return self._resolve_innovate(agent, action, tick)
        elif action_type == "pickup":
            return self._resolve_pickup(agent, tick)
        elif action_type in agent.actions:
            return self._resolve_custom_action(agent, action, tick)
        else:
            return {
                "success": False,
                "message": f"Unknown action: {action_type}",
                "effects": {},
            }
```

Then add the `_resolve_pickup` method (after `_resolve_innovate`, before the custom actions section):

```python
    def _resolve_pickup(self, agent: Agent, tick: int) -> dict:
        """Agent picks up 1 item from their current tile."""
        x, y = agent.x, agent.y
        resource = self.world.get_resource(x, y)

        if not resource or resource.get("quantity", 0) <= 0:
            msg = f"{agent.name} tried to pick up but there's nothing here."
            self._log(tick, msg)
            agent.add_memory("I tried to pick something up but there was nothing on this tile.")
            return {"success": False, "message": msg, "effects": {}}

        if agent.inventory.free_space() <= 0:
            msg = (
                f"{agent.name} tried to pick up but inventory is full "
                f"({agent.inventory.capacity}/{agent.inventory.capacity})."
            )
            self._log(tick, msg)
            agent.add_memory(
                f"I tried to pick something up but my inventory is full ({agent.inventory.total()}/{agent.inventory.capacity})."
            )
            return {"success": False, "message": msg, "effects": {}}

        item_type = resource["type"]
        self.world.consume_resource(x, y, 1)
        agent.inventory.add(item_type, 1)

        total = agent.inventory.total()
        cap = agent.inventory.capacity
        msg = f"{agent.name} picked up 1 {item_type} (inventory: {total}/{cap})."
        self._log(tick, msg)
        agent.add_memory(
            f"I picked up 1 {item_type} from this tile. Inventory: {agent.inventory.to_prompt()}."
        )
        return {"success": True, "message": msg, "effects": {}}
```

**Step 4: Add `requires.items` check to `_resolve_innovate`**

In `simulation/oracle.py`, inside `_resolve_innovate` (around line 353), after the `min_energy` check block:

```python
            # Check item prerequisites (inventory)
            required_items = requires.get("items")
            if isinstance(required_items, dict):
                for item, qty in required_items.items():
                    if not agent.inventory.has(item, int(qty)):
                        msg = (
                            f"{agent.name} cannot innovate '{new_action_name}': "
                            f"requires {qty}x {item} in inventory (has {agent.inventory.items.get(item, 0)})."
                        )
                        self._log(tick, msg)
                        agent.add_memory(
                            f"I tried to innovate '{new_action_name}' but I need {qty}x {item} (I have {agent.inventory.items.get(item, 0)})."
                        )
                        return {"success": False, "message": msg, "effects": {}}
```

**Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_oracle_pickup.py -v
```

Expected: All tests PASS.

**Step 6: Run full test suite**

```bash
uv run pytest -m "not slow" -v
```

Expected: All tests PASS.

**Step 7: Commit**

```bash
git add simulation/oracle.py tests/test_oracle_pickup.py
git commit -m "feat(inventory): add pickup action to Oracle and requires.items innovation check"
```

---

## Task 4: Update cornerstone documentation

**Files:**
- Modify: `project-cornerstone/03-agents/agents_context.md`
- Modify: `project-cornerstone/06-innovation-system/innovation-system_context.md`
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`

**Step 1: Update `project-cornerstone/03-agents/agents_context.md`**

Find the section describing Agent fields. Add the inventory field. Look for the stats/fields section and add:

```markdown
### Inventory

```python
agent.inventory = Inventory(capacity=AGENT_INVENTORY_CAPACITY)  # default 10
# items: {"fruit": 2, "stone": 1} — quantity-based (not slot-based)
```

- Capacity = total item quantity (e.g., {fruit: 3, stone: 7} = full at capacity 10)
- Appears in decision prompt only when non-empty: `INVENTORY: fruit x2, stone x1 (3/10)`
- Serialized in `get_status()` → `{"items": {...}, "capacity": 10}`
- `pickup` base action lets agents add 1 item per tick from their current tile
```

**Step 2: Update `project-cornerstone/06-innovation-system/innovation-system_context.md`**

Find the `## Phase 2 — Crafting & Prerequisites` section. Update the `Inventory` subsection to reflect the actual implementation. Find the `requires` format section and add `items` key:

```markdown
### Innovation Request Format (updated)

```json
{
    "action": "innovate",
    "new_action_name": "make_knife",
    "description": "carve stone into a knife",
    "reason": "I have stone and need a tool",
    "requires": {
        "tile": "cave",
        "min_energy": 20,
        "items": {"stone": 2}
    }
}
```

`requires.items` is checked deterministically before any LLM call. Items are verified but NOT consumed on innovation (item consumption is part of crafting, next phase).
```

**Step 3: Add DEC-017 to `project-cornerstone/00-master-plan/DECISION_LOG.md`**

Append to the decision log:

```markdown
## DEC-017 — Agent Inventory System (Phase 2)

**Date:** 2026-03-05
**Status:** Implemented

**Decision:** Add a quantity-based inventory system to agents.

**Key choices:**
- **Quantity-based capacity** (not slot-based): 10 total items is the limit. {fruit: 3, stone: 7} = full.
- **Gather-then-consume model**: `eat` is unchanged. New `pickup` base action stores items.
- **`pickup` as base action**: All agents start with it (not innovatable).
- **Prompt-efficient**: Inventory only appears in prompt when non-empty.
- **Separate `Inventory` class** (`simulation/inventory.py`): mirrors the `Memory` pattern.
- **`requires.items` in innovations**: Oracle checks item prerequisites before LLM call. Items are verified but NOT consumed (crafting is a separate feature).

**Files added:** `simulation/inventory.py`, `tests/test_inventory.py`, `tests/test_oracle_pickup.py`
**Files modified:** `simulation/agent.py`, `simulation/oracle.py`, `simulation/config.py`, `prompts/agent/decision.txt`, `prompts/agent/system.txt`
```

**Step 4: Commit**

```bash
git add project-cornerstone/
git commit -m "docs(cornerstone): document inventory system as DEC-017"
```

---

## Task 5: End-to-end verification

**Step 1: Run full test suite**

```bash
uv run pytest -m "not slow" -v
```

Expected: All tests PASS.

**Step 2: Smoke test (no LLM)**

```bash
uv run main.py --no-llm --ticks 20 --agents 3
```

Expected: Runs without error. Check console output for any `pickup` actions by agents.

**Step 3: Verify agent status includes inventory**

```bash
uv run main.py --no-llm --ticks 5 --agents 1 --save-state
```

Expected: State file in `data/` includes `inventory` field in agent data.

**Step 4: Verify inventory appears in prompt (optional, LLM run)**

```bash
uv run main.py --agents 2 --ticks 15 --seed 42 --verbose
```

Expected: If agent picks up items, their next decision prompt includes `INVENTORY: ...`.

---

## Out of Scope (Next PRs)

- Basic crafting: consuming inventory items to create new ones via innovation
- Drop/discard action
- Item trading between agents (Phase 3)
- Inventory persistence across simulation runs

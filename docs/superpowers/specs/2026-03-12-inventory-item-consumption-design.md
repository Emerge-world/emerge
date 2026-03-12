# Inventory Item Consumption Design

**Date:** 2026-03-12
**Status:** Approved

## Problem

Agents can pick up items into their inventory (`pickup` action) but `eat` only searches world resources at the current or adjacent tile. Items in inventory are never consumed, making pickup strategically useless for food.

## Goal

Allow agents to explicitly eat items from their inventory by specifying an `item` field on the `eat` action.

## Decision

Extend the existing `eat` action with an optional `item` field. When present, the oracle consumes from inventory instead of searching world resources. When absent, behavior is unchanged (world resources only).

## Design

### 1. Oracle — `simulation/oracle.py` (`_resolve_eat`)

Add an early-return branch at the top of `_resolve_eat`, before the world-resource loop:

```python
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
```

Notes:
- `.strip().lower()` normalises LLM output — item keys in inventory are always lowercase (set by `pickup` from `world.get_resource()`)
- `_get_item_eat_effect` handles editability via LLM + precedent cache; returns `possible: false` for stone, water, etc.
- No new oracle prompts needed.
- No schema field additions needed — `AgentDecisionResponse.item` is already `Optional[str]`.

### 2. Schema comment — `simulation/schemas.py`

Update the inline comment on the `item` field in `AgentDecisionResponse`:

```python
item: Optional[str] = None          # give_item / eat (inventory)
```

### 3. Agent system prompt — `prompts/agent/system.txt`

Change the `eat` line:

**Before:**
```
- eat: {"action": "eat", "reason": "..."} (eat food at current or adjacent tile)
```

**After:**
```
- eat: {"action": "eat", "reason": "..."} (eat food at current or adjacent tile; add "item": "<name>" to eat from inventory instead)
```

The agent already sees their inventory contents via the existing `$inventory_info` variable in `decision.txt` (e.g., `INVENTORY: fruit x2 (2/10)`). No change to `decision.txt` is needed.

### 4. Tests

Six new unit tests using the existing `MockLLM` pattern in `tests/test_eat.py` (or a new `tests/test_eat_inventory.py`).

**Test setup notes:**
- All tests that require a specific eat effect (hunger reduction, life change) must **pre-seed the oracle precedent** rather than mocking `generate_structured`. This is the existing pattern used throughout `test_eat.py` (e.g., `oracle.precedents["item_eat:fruit"] = {...}`), and avoids the `generate_json` vs `generate_structured` mock ambiguity.
- Tests that assert "no world resource nearby" must explicitly clear adjacent tiles: `for pos in [(x,y),(x+1,y),(x-1,y),(x,y+1),(x,y-1)]: world.resources.pop(pos, None)`.
- Tests that assert on energy deduction must set a known starting energy before the call (e.g., `agent.energy = 50`) and assert `agent.energy == 50 - ENERGY_COST_EAT`.

**Tests:**

- **`test_eat_from_inventory_success`** — pre-seed `oracle.precedents["physical:eat:fruit"] = {"possible": True, "hunger_reduction": 20, "life_change": 0}`. Agent has `fruit x1` in inventory, all adjacent tiles cleared. Action `{"action": "eat", "item": "fruit"}` → result success, `agent.inventory.has("fruit") == False`, hunger reduced by 20, `result["effects"]["life"] == 0`.
- **`test_eat_from_inventory_energy_cost`** — same setup, set `agent.energy = 50` before call → `agent.energy == 50 - ENERGY_COST_EAT`.
- **`test_eat_from_inventory_memory_update`** — same setup → `assert any("inventory" in m for m in agent.memory)`.
- **`test_eat_from_inventory_no_item`** — no stone in inventory, action `{"action": "eat", "item": "stone"}` → `result["success"] == False`, `agent.inventory.total() == 0`.
- **`test_eat_from_inventory_life_change`** — pre-seed `oracle.precedents["physical:eat:mushroom"] = {"possible": True, "hunger_reduction": 5, "life_change": -10}`. Agent has `mushroom x1`. Action `{"action": "eat", "item": "mushroom"}` → `agent.life == initial_life - 10`.
- **`test_eat_world_resource_when_inventory_nonempty`** — agent has `fruit x1` in inventory and a fruit tile is placed at an adjacent position. Action `{"action": "eat"}` (no `item` field) → world resource consumed, `agent.inventory.items == {"fruit": 1}` (unchanged).

## What does NOT change

- `eat` without `item` — unchanged (world resources only)
- `_fallback_decision` — unchanged (no-LLM fallback stays world-resource only)
- `pickup` action — unchanged
- `give_item`, `teach`, `communicate` — unchanged
- `prompts/agent/decision.txt` — unchanged
- No new base actions added

## Touch Points

| File | Change |
|---|---|
| `simulation/oracle.py` | Add inventory branch in `_resolve_eat` (with `.strip().lower()` normalisation) |
| `simulation/schemas.py` | Update `item` field comment to include `eat` |
| `prompts/agent/system.txt` | Update `eat` action description |
| `tests/` | 6 new unit tests |

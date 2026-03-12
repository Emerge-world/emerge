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
item = action.get("item", "").strip()
if item:
    if not agent.inventory.has(item):
        return {
            "success": False,
            "message": f"{agent.name} tried to eat {item} but has none in inventory.",
            "effects": {},
        }
    effect = self._get_item_eat_effect(item, tick)   # existing oracle LLM / precedent lookup
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

- `_get_item_eat_effect` already handles editability via LLM + precedent cache (returns `possible: false` for stone, water, etc.)
- No new oracle prompts needed.
- No schema changes needed — `AgentDecisionResponse.item` is already `Optional[str]`.

### 2. Agent system prompt — `prompts/agent/system.txt`

Change the `eat` line:

**Before:**
```
- eat: {"action": "eat", "reason": "..."} (eat food at current or adjacent tile)
```

**After:**
```
- eat: {"action": "eat", "reason": "..."} (eat food at current or adjacent tile; add "item": "<name>" to eat from inventory instead)
```

No changes to `prompts/agent/decision.txt` — the existing `INVENTORY:` line already shows carried items. Agents will see their inventory and connect it to the updated `eat` format.

### 3. Tests

Two new unit tests using `MockLLM`:

- **`test_eat_from_inventory_success`** — agent has `fruit x1` in inventory, no world resource nearby, action `{"action": "eat", "item": "fruit"}` → inventory decremented, hunger reduced, success.
- **`test_eat_from_inventory_no_item`** — agent has no matching item, action `{"action": "eat", "item": "stone"}` → failure, inventory unchanged.

## What does NOT change

- `eat` without `item` — unchanged (world resources only)
- `_fallback_decision` — unchanged (no-LLM fallback stays world-resource only)
- `pickup` action — unchanged
- `give_item`, `teach`, `communicate` — unchanged
- No new base actions added

## Touch Points

| File | Change |
|---|---|
| `simulation/oracle.py` | Add inventory branch in `_resolve_eat` |
| `prompts/agent/system.txt` | Update `eat` action description |
| `tests/` | 2 new unit tests |

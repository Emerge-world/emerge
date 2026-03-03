# 06 — Innovation System

## Concept

Innovation is the heart of emergence. Agents can invent new actions that didn't exist in the original code. The oracle validates whether they make sense and establishes their effects.

## Current State (Phase 1 — Implemented ✅)

### Flow

1. Agent decides `{"action": "innovate", "new_action_name": "fish", "description": "catch fish from water", "requires": {"tile": "water"}}`
2. Oracle checks `requires` prerequisites (tile, min_energy) — **without LLM call**; fails fast if unmet
3. Oracle validates with LLM: is it reasonable? Is it different from existing actions? Returns `approved` + `category`
4. If approved: action added to `agent.actions`, precedent stored with `category` and `tick_created`
5. When the agent uses `"fish"`, oracle determines effect with LLM
6. Effect is **clamped** by `_clamp_innovation_effects()` before being stored as a precedent
7. All subsequent uses of the same action on the same tile type use the cached (clamped) precedent

### Innovation Request Format

```json
{
    "action": "innovate",
    "new_action_name": "fish",
    "description": "catch fish from the river",
    "reason": "I'm hungry and near water",
    "requires": {
        "tile": "water",
        "min_energy": 20
    }
}
```

`requires` is optional. Only include fields that apply. Missing or non-dict `requires` is ignored.

### Oracle Validation (pre-LLM checks in `_resolve_innovate`)

```
1. new_action_name must be non-empty
2. new_action_name must not already be in agent.actions (base or innovated)
3. If requires.tile set → current tile must match
4. If requires.min_energy set → agent.energy must be >= min_energy
5. Then: LLM validates semantic plausibility + redundancy (existing actions passed in prompt)
```

### Innovation Categories

The oracle LLM assigns a category to every approved innovation:

```
SURVIVAL    → fish, gather_berries, find_water, hunt
CRAFTING    → make_spear, build_shelter, weave_basket, make_fire
EXPLORATION → climb_tree (see farther), scout_area, mark_trail
SOCIAL      → signal, call_for_help, share_food (Phase 3)
```

Category is stored in the `innovation:<name>` precedent and shown in the 🆕 log line.

### Effect Bounds (enforced by `Oracle._clamp_innovation_effects`)

Defined in `simulation/config.py` as `INNOVATION_EFFECT_BOUNDS`:

```python
INNOVATION_EFFECT_BOUNDS = {
    "hunger": (-30, 10),    # max -30 hunger (very good food), max +10
    "energy": (-20, 20),    # max -20 (very tired), max +20 (very rested)
    "life":   (-15, 10),    # max -15 damage, max +10 healing
}
```

Applied after every `_oracle_judge_custom_action()` call, before the result is cached. Unknown keys (e.g. future `gold`) are passed through unchanged.

### Key config values

| Constant | Value | Meaning |
|---|---|---|
| `ENERGY_COST_INNOVATE` | 10 | Energy spent when innovation is approved |
| `INNOVATION_EFFECT_BOUNDS` | see above | Safe stat-delta ranges for custom actions |

### Known remaining issues

1. **No `nearby_resource` prerequisite**: `requires` supports `tile` and `min_energy` only. Item prerequisites deferred to Phase 2 (inventory system required).
2. **No material cost**: Innovating costs energy only, not resources. Deferred to Phase 2.
3. **No precedent persistence**: Innovation precedents are lost between runs. Planned for Phase 1 (JSON save/load).

## Phase 2 — Crafting & Prerequisites

### Inventory

For innovations like "build_shelter" to work, agents need inventory:

```python
class Inventory:
    items: dict[str, int]  # {"wood": 3, "stone": 1, "fruit": 2}
    max_slots: int = 10
    
    def add(self, item: str, qty: int): ...
    def remove(self, item: str, qty: int): ...
    def has(self, item: str, qty: int) -> bool: ...
```

### Recipes as precedents

When an agent innovates something that requires materials, the oracle records the "recipe":

```python
# Precedent for "build_shelter":
{
    "action": "build_shelter",
    "requires_items": {"wood": 5},
    "requires_tile": ["forest", "land"],
    "effects": {"energy": -15},
    "world_effect": "creates shelter at (x,y)",  # new: effects on the world
    "time_cost": 3  # ticks it takes (future)
}
```

## Considerations for Claude Code

- Innovation is the hardest feature to test because it depends on the LLM. Create tests with LLM mocks.
- Maintain a list of "expected" innovations in tests: if an agent invents "fly" and the oracle approves it, the test fails.
- Balance is critical: if innovating is too easy, agents invent everything in 10 ticks. If it's too hard, they never innovate.
- Special logging for innovations: each new innovation should be a highlighted event in the logs.

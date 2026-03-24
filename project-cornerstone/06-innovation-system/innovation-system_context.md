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

`requires` is optional. Only include fields that apply. Missing or non-dict `requires` is ignored.

`requires.items` is checked deterministically before any LLM call. Items are verified but NOT consumed on innovation approval — consumption happens at execution time via `_apply_crafting_recipe` (see DEC-018).

### Oracle Validation (pre-LLM checks in `_resolve_innovate`)

```
1. new_action_name must be non-empty
2. new_action_name must not already be in agent.actions (base or innovated)
3. If requires.tile set → current tile must match
4. If requires.min_energy set → agent.energy must be >= min_energy
5. If requires.items set → agent.inventory must have all required items (verified, not consumed)
6. Then: LLM validates semantic plausibility + redundancy (existing actions passed in prompt)
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

1. **No `nearby_resource` prerequisite**: `requires` supports `tile`, `min_energy`, and `items`. ~~Item prerequisites deferred to Phase 2 (inventory system required).~~ ✅ Resolved — `requires.items` implemented (DEC-017).
2. ~~**No material cost**: Crafting (item consumption) is deferred to the next Phase 2 PR.~~ ✅ Resolved — crafting fully implemented (DEC-018). Items are consumed from inventory at execution time; `produces` items are added.
3. **No precedent persistence**: ~~Innovation precedents are lost between runs.~~ ✅ Resolved — JSON save/load implemented (DEC-013).
4. ~~**Crafted items don't unlock follow-on actions**: produced inventory items were passive state with no path to new verbs.~~ ✅ Resolved — item affordance discovery implemented (DEC-045); see section below.

## Phase 2 — Crafting & Prerequisites

### Inventory *(implemented — see DEC-017)*

Agents now carry a quantity-based inventory. Implemented in `simulation/inventory.py`:

```python
class Inventory:
    items: dict[str, int]  # {"wood": 3, "stone": 1, "fruit": 2}
    capacity: int = 10     # total item quantity, not slots

    def add(self, item: str, qty: int): ...
    def remove(self, item: str, qty: int): ...
    def has(self, item: str, qty: int) -> bool: ...
```

### Crafting *(implemented — see DEC-018)*

Crafting is a fully emergent CRAFTING-category innovatable action. Agents propose a `produces` field alongside `requires.items` when innovating.

#### Innovation request format (with crafting fields)

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
    },
    "produces": {"knife": 1}
}
```

#### Crafting execution flow

1. Agent executes a previously approved crafting action
2. `_resolve_custom_action` checks `requires.items` against current inventory — **fail-fast, no LLM call**
3. If materials missing: generic failure message returned (no item names revealed — preserves emergence)
4. If materials present: `_apply_crafting_recipe` is called
   - Consumes `requires.items` from inventory
   - Applies stat effects (energy cost of labor, clamped)
   - Adds `produces` items to inventory
   - Logs any inconsistencies (e.g. remove more than held)

#### Storage in precedent

At innovation approval time (`_resolve_innovate`), both `requires` and `produces` are stored in `precedents["innovation:<name>"]`. Every subsequent execution reads from this cached record — no additional LLM calls.

#### Oracle validation

`_validate_innovation` passes `produces` to the LLM prompt so it can check physical plausibility of the recipe (e.g. "does carving stone produce a knife?" is reasonable; "does eating fruit produce gold?" is not).

## Item Affordance Discovery — Craft → Discover → Use Loop *(implemented — see DEC-045)*

Crafting a new item type for the first time now triggers automatic affordance discovery, closing the gap between crafted tools and concrete new verbs.

### Flow

```
Agent executes a CRAFTING innovation (e.g. make_knife)
  └── _apply_crafting_recipe succeeds, produces stone_knife
      └── _trigger_post_craft_affordances fires (first craft of stone_knife for this agent)
          └── _discover_item_affordances(agent, "stone_knife")
              ├── LLM suggests candidate verbs: ["stab", "cut_branches"]
              ├── _validate_innovation("stab", ...) → approved
              │   └── stab added to agent.actions with requires.items: {stone_knife: 1}
              ├── _validate_innovation("cut_branches", ...) → approved
              │   └── cut_branches added to agent.actions with requires.items: {stone_knife: 1}
              └── agent.auto_reflected_items.add("stone_knife")
```

### Key properties

- **Idempotent**: auto-trigger fires only once per agent per item type (tracked in `agent.auto_reflected_items`).
- **Non-blocking**: if discovery fails (LLM error, all candidates rejected), crafting still succeeds.
- **Verb-shaped**: candidates must be concrete verbs, not `use_<item>` wrappers.
- **Tool-gated execution**: every discovered action stores `requires.items: {item: 1}` so it fails deterministically without the tool.
- **No extra energy cost for auto-discovery**: the crafting action itself represents the effort.
- **Manual re-reflection**: `reflect_item_uses` (5 energy) lets agents deliberately discover additional uses for any held item after the initial automatic pass.
- **Standard analytics**: derived innovations emit normal `innovation_attempt` / `innovation_validated` events with extra fields: `origin_item`, `discovery_mode` (`"auto"` / `"manual"`), `trigger_action`.

### Prompt

`prompts/oracle/item_affordance_system.txt` — focused prompt asking the LLM for a short list (0–3) of concrete physical verb actions for a specific item. Kept brief to limit LLM tokens and avoid generic wrappers.

## Considerations for Claude Code

- Innovation is the hardest feature to test because it depends on the LLM. Create tests with LLM mocks.
- Maintain a list of "expected" innovations in tests: if an agent invents "fly" and the oracle approves it, the test fails.
- Balance is critical: if innovating is too easy, agents invent everything in 10 ticks. If it's too hard, they never innovate.
- Special logging for innovations: each new innovation should be a highlighted event in the logs.
- Item affordance discovery reuses the existing innovation event pipeline — no separate counters needed.
- Tool-aware precedent keys (`custom_action:{action}:tile:{tile}:tools:{item}:{qty}`) must be used for all actions derived from items to prevent outcome collisions with tool-free variants.

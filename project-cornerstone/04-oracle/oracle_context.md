# 04 — Oracle System

## Implemented

The following oracle methods are live:

- **Oracle runtime modes**: The oracle now runs in explicit `live`, `frozen`, or `symbolic` modes. `live` keeps the historical precedent-learning behavior. `frozen` and `symbolic` are closed-world modes: they load a curated precedent snapshot at startup and reject unresolved novelty with `ORACLE_UNRESOLVED_NOVELTY` instead of consulting the LLM or writing new precedents.
- **`_oracle_reflect_physical()`**: In `live`, the LLM judges traversability once per novel tile-type/action context and caches the result as a precedent. In `frozen`/`symbolic`, misses are rejected unless the precedent already exists in the curated snapshot.
- **`_get_fruit_effect()`**: LLM determines hunger reduction for eating fruit (temperature=0.2, baseline ~20 hunger points). Result cached as a precedent.
- **`_validate_innovation()`**: In `live`, the LLM approves or rejects proposed new action names (temperature=0.3). In `frozen`/`symbolic`, unresolved innovation attempts fail closed instead of defaulting to approval.
- **`_oracle_judge_custom_action()`**: LLM determines the effects of an approved custom action (temperature=0.3). Result cached as a precedent.
- **8-direction movement**: Move action supports N, NE, E, SE, S, SW, W, NW.
- **Precedents**: Currently plain string-keyed dicts in memory (not `PrecedentKey`/`PrecedentValue` dataclasses).
- **Persistence**: Benchmark/runtime startup is now explicit. `SimulationEngine` decides local cleanup and load behavior from `persistence.mode`, `clean_before_run`, and `oracle.mode`. `live` may reuse local seed-scoped precedent files when oracle persistence is enabled. `frozen` and `symbolic` load precedents only from `oracle.freeze_precedents_path` and never save new local oracle precedents at shutdown. `save_precedents` still never raises — it catches `OSError`/`TypeError`/`ValueError` so a disk error in a `finally` block cannot mask a simulation exception.
- **`_discover_item_affordances(agent, item_name)`**: In `live`, calls the LLM (via `prompts/oracle/item_affordance_system.txt`) to generate a short list of concrete verb actions enabled by `item_name`. Each candidate is run through `_validate_innovation` + `_oracle_judge_custom_action`. Approved candidates are registered as normal innovations with `requires.items` set to gate on the enabling tool. In `frozen`/`symbolic`, novelty misses skip affordance discovery entirely.
- **`_trigger_post_craft_affordances(agent, produced_items, crafting_action_name)`**: Called after a successful crafting execution. For each produced item type not yet in `agent.auto_reflected_items`, calls `_discover_item_affordances` and marks the item as discovered. Discovery failure is silent and non-blocking — crafting always succeeds regardless.
- **`_resolve_reflect_item_uses(agent, action_dict)`**: Resolves the built-in `reflect_item_uses` action. Deducts 5 energy, validates that the agent holds the requested item, then calls `_discover_item_affordances`. Returns `success=False` with no energy cost when the inventory is empty or the requested item is not held.
- **Tool-aware custom-action precedent keys**: item-derived actions use the extended key format `custom_action:{action}:tile:{tile}:tools:{item}:{qty}` so that outcomes with and without a tool remain distinct precedent entries (addresses the generic-key known issue).
- **Runtime capability enforcement**: `Oracle` now accepts explicit runtime settings derived from `ExperimentProfile` and fails closed for disabled built-in actions (`innovate`, `reflect_item_uses`, `communicate`, `give_item`, `teach`, `reproduce`) before dispatching to action handlers.
- **Benchmark traceability**: Benchmark-oriented runs persist `persistence_trace` and `oracle_trace` into `data/runs/<run_id>/meta.json`, recording what local paths were eligible for cleanup, what was actually cleaned, where precedents were loaded from, and which oracle novelty policy was active.

**Pending for Phase 1:**
- `PrecedentKey`/`PrecedentValue` dataclasses (planned structured keys, currently plain strings — deferred as YAGNI)

---

## Current State (Phase 0)

The oracle is the world's arbiter. It validates actions, determines results, and maintains consistency via precedents.

### Current flow
```
Agent decides action → Oracle.resolve_action()
  ├── move:     Validate walkability, move, spend energy
  ├── eat:      Consume an edible inventory item or an edible resource on the current / adjacent tile
  ├── rest:     Recover energy
  ├── pickup:   Collect 1 item from the current tile into inventory
  ├── drop_item: Place inventory items on the current tile if the stack is empty or same-typed
  ├── communicate / give_item / teach: Resolve social built-in actions deterministically
  ├── reproduce: Validate age/health/adjacency/cooldown, then spawn child
  ├── innovate: Validate with LLM, register new action
  └── custom:   Search precedent or ask LLM to determine result
```

### Precedent system (current)
- Dict in-memory: `str → dict`
- Keys like `"fruit_hunger_reduction"`, `"innovation:build_shelter"`, `"custom_action:fish:tile:water"`
- If precedent exists → use saved result
- If not in `live` → ask LLM or fall back deterministically, then save as precedent
- If not in `frozen`/`symbolic` → reject unresolved novelty without writing new precedent data

### Known issues

1. ~~**Precedents too generic**: `"custom_action:fish:tile:water"` doesn't distinguish if the agent has tools or not.~~ ✅ Resolved — item-derived actions now use tool-aware keys: `custom_action:{action}:tile:{tile}:tools:{item}:{qty}` (DEC-045).
2. **Persistence**: Implemented — local seed-scoped precedent reuse is now explicit runtime policy, not an implicit benchmark behavior. Closed oracle modes load curated snapshots via `oracle.freeze_precedents_path`, and benchmark traces record the effective load/cleanup behavior in `meta.json`.
3. **Fragile keys**: Manual strings, easy for two "equal" situations to have different keys.
4. **No versioning**: If we adjust an effect, old precedents become inconsistent.

## Phase 1 — Robust Precedents

### Structured precedent key

```python
@dataclass
class PrecedentKey:
    action: str                    # "eat", "fish", "build_shelter"
    tile_type: str                 # "land", "tree", "water"
    resource_present: bool         # is there a resource on the tile?
    agent_has_tool: str | None     # relevant tool (Phase 2)
    
    def to_key(self) -> str:
        parts = [self.action, self.tile_type, str(self.resource_present)]
        if self.agent_has_tool:
            parts.append(self.agent_has_tool)
        return ":".join(parts)

@dataclass
class PrecedentValue:
    success: bool
    effects: dict[str, int]       # {"hunger": -20, "energy": -5}
    message: str
    created_tick: int
    created_by: str               # name of the agent that caused it first
    times_applied: int = 1
```

### Persistence

**Implemented.** Precedents are persisted as `data/precedents_{seed}.json` with a minimal JSON schema (`version`, `seed`, `tick`, `precedents` dict). Runtime startup and shutdown now distinguish three cases:

- `oracle.mode="live"`: local precedents are eligible for load/save only when `persistence.mode` includes oracle state.
- `oracle.mode="frozen"` or `oracle.mode="symbolic"`: precedents must load from `oracle.freeze_precedents_path`; startup fails fast if the snapshot is missing or invalid; local oracle precedent files are never written at shutdown.
- `clean_before_run=true`: only the local seed-scoped files covered by `persistence.mode` are removed before startup.

Benchmark runs also persist `persistence_trace` and `oracle_trace` in `meta.json` so post-run analysis can see exactly what was cleaned, what local paths were considered, which snapshot was loaded, and whether novelty was `live_learning` or `reject_unresolved`.

### Oracle Decision Tree

Before calling the LLM, the oracle follows a deterministic decision tree:

```
Is there an established physical-law precedent for this action's context?
├── Yes → apply cached physical judgment
└── No
    ├── In live mode → Oracle LLM reflects on physical plausibility → cache as precedent
    └── In frozen/symbolic mode → reject unresolved novelty immediately

If physical judgment says "possible":
    Does exact outcome precedent exist?
    ├── Yes → apply precedent
    ├── In live mode and no exact outcome precedent → LLM determines effects → cache as precedent
    └── In frozen/symbolic mode and no exact outcome precedent → reject unresolved novelty immediately

If physical judgment says "not possible":
    → Return failure immediately
```

### Validation of innovated actions

The oracle needs clear rules for which innovations to approve:

```
APPROVE if:
- It's a physically plausible action in a primitive world
- The agent has the necessary resources/position
- Doesn't violate world physics (no flying, no teleporting)

REJECT if:
- It's magical or supernatural
- Requires technology that doesn't exist in the world
- It's too powerful (build city in 1 tick)
- It's an action that already exists with another name
```

## Considerations for Claude Code

- Base actions now call `_oracle_reflect_physical()` once per novel situation. In `live`, results are cached as precedents; in `frozen`/`symbolic`, misses fail closed.
- Only `live` mode may call the oracle's LLM for novelty misses. Closed modes remain deterministic by rejecting unresolved novelty.
- Tests must verify: same input → same output (determinism), precedents are reused, invalid actions return success=false.
- The oracle NEVER mutates tile resources directly except through `World` helpers such as `consume_resource()` and `place_resource()`.
- Logging: each oracle decision must remain in the world_log with tick, agent, action, and result.

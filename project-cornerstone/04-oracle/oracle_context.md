# 04 — Oracle System

## Implemented

The following oracle methods are live:

- **`_oracle_reflect_physical()`**: LLM judges traversability once per novel tile-type/action context, then caches the result as a precedent. Subsequent calls for the same context are fully LLM-free.
- **`_get_fruit_effect()`**: LLM determines hunger reduction for eating fruit (temperature=0.2, baseline ~20 hunger points). Result cached as a precedent.
- **`_validate_innovation()`**: LLM approves or rejects proposed new action names (temperature=0.3). Approved actions are registered; rejected ones return failure.
- **`_oracle_judge_custom_action()`**: LLM determines the effects of an approved custom action (temperature=0.3). Result cached as a precedent.
- **8-direction movement**: Move action supports N, NE, E, SE, S, SW, W, NW.
- **Precedents**: Currently plain string-keyed dicts in memory (not `PrecedentKey`/`PrecedentValue` dataclasses).
- **Persistence**: Implemented. Precedents are saved to `data/precedents_{seed}.json` at the end of every run and auto-loaded on engine init. Unseeded runs use `data/precedents_unseeded.json`. `save_precedents` never raises — it catches `OSError`/`TypeError`/`ValueError` so a disk error in a `finally` block cannot mask a simulation exception.

**Pending for Phase 1:**
- `PrecedentKey`/`PrecedentValue` dataclasses (planned structured keys, currently plain strings — deferred as YAGNI)

---

## Current State (Phase 0)

The oracle is the world's arbiter. It validates actions, determines results, and maintains consistency via precedents.

### Current flow
```
Agent decides action → Oracle.resolve_action()
  ├── move:     Validate walkability, move, spend energy
  ├── eat:      Search nearby resource, consume, reduce hunger
  ├── rest:     Recover energy
  ├── pickup:   Collect 1 item from the current tile into inventory
  ├── communicate / give_item / teach: Resolve social built-in actions deterministically
  ├── reproduce: Validate age/health/adjacency/cooldown, then spawn child
  ├── innovate: Validate with LLM, register new action
  └── custom:   Search precedent or ask LLM to determine result
```

### Precedent system (current)
- Dict in-memory: `str → dict`
- Keys like `"fruit_hunger_reduction"`, `"innovation:build_shelter"`, `"custom_action:fish:tile:water"`
- If precedent exists → use saved result
- If not → ask LLM → save as precedent

### Known issues

1. **Precedents too generic**: `"custom_action:fish:tile:water"` doesn't distinguish if the agent has tools or not.
2. **Persistence**: Implemented — precedents are saved to `data/precedents_{seed}.json` and reloaded on next run with the same seed. Cross-run consistency is now maintained without redundant LLM calls.
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

**Implemented.** Precedents are persisted as `data/precedents_{seed}.json` with a minimal JSON schema (`version`, `seed`, `tick`, `precedents` dict). The engine auto-loads the file on init and auto-saves it in `run()` / `run_with_callback()` `finally` blocks. Per-seed isolation prevents cross-contamination between different world configurations. `save_precedents` is exception-safe (catches `OSError`/`TypeError`/`ValueError`).

### Oracle Decision Tree

Before calling the LLM, the oracle follows a deterministic decision tree:

```
Is there an established physical-law precedent for this action's context?
├── Yes → apply cached physical judgment
└── No
    └── Oracle LLM reflects on physical plausibility → cache as precedent

If physical judgment says "possible":
    Does exact outcome precedent exist?
    ├── Yes → apply precedent
    └── No → LLM determines effects → cache as precedent

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

- Base actions now call `_oracle_reflect_physical()` once per novel situation. Results are cached as precedents — subsequent calls are fully deterministic and LLM-free.
- Only `innovate` and custom actions call the oracle's LLM for effect determination.
- Tests must verify: same input → same output (determinism), precedents are reused, invalid actions return success=false.
- The oracle NEVER modifies the world directly except via consume_resource().
- Logging: each oracle decision must remain in the world_log with tick, agent, action, and result.

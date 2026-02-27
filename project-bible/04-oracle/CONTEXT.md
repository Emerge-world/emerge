# 04 — Oracle System

## Current State (Phase 0)

The oracle is the world's arbiter. It validates actions, determines results, and maintains consistency via precedents.

### Current flow
```
Agent decides action → Oracle.resolve_action()
  ├── move:     Validate walkability, move, spend energy
  ├── eat:      Search nearby resource, consume, reduce hunger
  ├── rest:     Recover energy
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
2. **No persistence**: Precedents are lost between executions.
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

```python
# Save precedents as JSON at the end of each simulation
# Load them at the start of the next to maintain cross-run consistency
# File: data/precedents_{world_seed}.json
```

### Oracle Decision Tree

Before calling the LLM, the oracle follows a deterministic decision tree:

```
Is it a base action (move/eat/rest)?
├── Yes → resolve with hardcoded logic (no LLM)
└── No
    Does exact precedent exist?
    ├── Yes → apply precedent
    └── No
        Does similar precedent exist (same action, different tile)?
        ├── Yes → use as hint for LLM
        └── No → LLM decides freely
        → Save result as new precedent
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

- Base actions (move, eat, rest) NEVER call the LLM. They're deterministic.
- Only `innovate` and custom actions call the oracle's LLM.
- Tests must verify: same input → same output (determinism), precedents are reused, invalid actions return success=false.
- The oracle NEVER modifies the world directly except via consume_resource().
- Logging: each oracle decision must remain in the world_log with tick, agent, action, and result.

# 08 — Evolution & Culture (Phase 4)

> **Status: Phase 4 implemented (DEC-026, 2026-03-09).** Reproduction, inheritance, and lineage are live.
> Emergent culture metrics are a future concern (Phase 5+).

## Implementation Status (Phase 4)

### Files modified/created
| File | Change |
|---|---|
| `simulation/config.py` | Reproduction constants, `AGENT_NAME_POOL` (32 names), child stats |
| `simulation/lineage.py` | **NEW** — `LineageRecord`, `LineageTracker` (save/load JSON) |
| `simulation/agent.py` | `last_reproduce_tick`, `children_names`, `get_family_prompt()` |
| `simulation/oracle.py` | `_resolve_reproduce()`, `_find_spawn_near()` |
| `simulation/engine.py` | `_spawn_child()`, `_pick_child_name()`, death/innovation recording |
| `simulation/personality.py` | `Personality.blend()` class method |
| `simulation/memory.py` | `Memory.inherit_from()` method |
| `prompts/agent/decision.txt` | `$family_info` section, reproduce action hint |
| `tests/test_reproduction.py` | **NEW** — 32 unit tests |

### Key constants (see `config.py`)
- Requirements: `life >= 70`, `hunger <= 30`, `energy >= 50`, `age >= 100 ticks`
- Cooldown: 48 ticks per agent
- Parent cost: `-30 life, +30 hunger, -30 energy`
- Child stats: `life=50, hunger=40, energy=40`

## Concept

Agents reproduce, transmit knowledge to their descendants, and the species evolves across generations. Culture emerges from the accumulation of innovations and relationships.

## Reproduction

### Requirements to reproduce
```python
REPRODUCTION_REQUIREMENTS = {
    "min_life": 70,
    "max_hunger": 30,      # can't be hungry
    "min_energy": 50,
    "min_ticks_alive": 100, # must have survived long enough
    "needs_partner": True,   # requires another adjacent agent (Phase 3)
}
```

### Inheritance

The child inherits:
```python
child = Agent(
    # Position: next to parents
    x=parent.x, y=parent.y,
    
    # Personality: mix of parents + mutation
    personality=blend_traits(parent_a.personality, parent_b.personality, mutation=0.1),
    
    # Base memory: summary of parents' knowledge (not specific memories)
    # "Your parents taught you: fruit reduces hunger, the north has forests, shelter protects from storms"
    inherited_knowledge=compress_parental_knowledge(parent_a, parent_b),
    
    # Actions: base actions + innovations shared by parents
    actions=BASE_ACTIONS + shared_innovations(parent_a, parent_b),
)
```

### Mutación de personalidad

```python
def blend_traits(a: dict, b: dict, mutation: float = 0.1) -> dict:
    child = {}
    for trait in a:
        # 50% de cada padre + ruido
        base = (a[trait] + b[trait]) / 2
        noise = random.gauss(0, mutation)
        child[trait] = max(0.0, min(1.0, base + noise))
    return child
```

## Generations and lineage

```python
class Lineage:
    agent_id: int
    parent_a_id: int | None
    parent_b_id: int | None
    generation: int
    born_tick: int
    died_tick: int | None
    innovations_created: list[str]
    children_ids: list[int]
    
# Persist as queryable genealogical tree
```

## Natural selection

Fitness is not calculated explicitly. It emerges from:
- Agents that survive longer → more opportunities to reproduce
- Agents that innovate → children inherit innovations → advantage
- Agents that cooperate → access to more resources → survive longer
- Traits that help survive → are transmitted more

### Metrics to monitor
```
- Average survival ticks per generation
- Number of unique innovations per generation
- Trait diversity in the population
- Cooperation vs competition ratio
```

## Emergent culture

### Culture signals
- Innovations shared by >50% of the population
- Unprogrammed behavior patterns (e.g., everyone rests at night)
- "Traditions": actions transmitted across generations without obvious utility
- Specialization: agents that systematically do one thing

### Emergent roles

Don't program roles. Monitor if they emerge:
```
- Explorer: agent that moves a lot and shares information
- Gatherer: agent that stays near resources
- Builder: agent that innovates and builds
- Teacher: agent that teaches many innovations
```

## Considerations for Claude Code

- Evolution needs VERY long simulations (1000+ ticks). Optimize performance first.
- We'll need complete persistence: world + agents + precedents + lineage between executions.
- Evolution tests are inherently statistical: "in 10 runs of 500 ticks, at least 3 show X".
- Consider using Claude API (Haiku) for this phase — 3B models probably don't have enough capacity for cultural narrative.

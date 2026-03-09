# Phase 4: Reproduction & Inheritance Design

> Date: 2026-03-09
> Status: Design approved
> Scope: `reproduce` action, child spawning, trait/knowledge inheritance, lineage tracking

## Context

Phase 3 (Social) is complete. Agents can communicate, cooperate (`give_item`), teach innovations, and track relationships with trust. Generational fields (`generation`, `parent_ids`, `born_tick`) were added as Phase 4 groundwork in Phase 3c (DEC-025). The simulation now needs reproduction to create multi-generational dynamics and natural selection pressure.

## Design Decisions

### Reproduction Trigger: LLM-Decided Action
- Agent actively chooses `reproduce` as an action (like `give_item`/`teach`)
- Fits "emergence over prescription" — the LLM decides when to reproduce based on context
- Single initiator targets a nearby agent; Oracle validates both meet requirements

### Population Control: Soft Cap via Resources
- No hard population limit
- More agents = more hunger pressure = more deaths
- Population self-regulates through carrying capacity

### Child Start: Vulnerable Infant
- Reduced stats force dependence on parents
- Creates emergent parenting behavior through existing social mechanics

---

## The `reproduce` Action

**Action format:**
```json
{"action": "reproduce", "target": "Clara", "reason": "We are both healthy and well-fed"}
```

**Requirements (both initiator AND target must meet):**

| Requirement | Value | Rationale |
|---|---|---|
| `min_life` | 70 | Must be healthy |
| `max_hunger` | 30 | Must be well-fed |
| `min_energy` | 50 | Needs reserves |
| `min_ticks_alive` | 100 | ~4 days survival gate |
| Adjacency | Manhattan <= 1 | Must be next to partner |
| Target alive | True | - |
| Cooldown | 48 ticks (2 days) | Per-agent, prevents spam |

**Cost to BOTH parents:**
- Life: -30
- Hunger: +30
- Energy: -30

**`reproduce` is a BASE_ACTION** — all agents can do it from birth.

---

## Child Spawning

**Position:** Adjacent empty land tile near parents. If none exists, reproduction fails.

**Initial stats (vulnerable infant):**

| Stat | Value |
|---|---|
| Life | 50 |
| Hunger | 40 |
| Energy | 40 |

---

## Inheritance

### Personality (Trait Blending)
```
for each trait in [courage, curiosity, patience, sociability]:
    base = (parent_a.trait + parent_b.trait) / 2
    mutation = random.gauss(0, 0.1)  # +/-10% std deviation
    child.trait = clamp(base + mutation, 0.0, 1.0)
```

### Knowledge (Compressed Memories)
- Child inherits up to 5 semantic memories from each parent
- Prefixed with "[Inherited]" to distinguish from personal experience
- Seeded as initial semantic memory
- No episodic memories inherited (those are personal)

### Innovations
- Child inherits innovations known to **both** parents (shared knowledge)
- Plus all BASE_ACTIONS
- Single-parent innovations must be taught post-birth

### Generational Tracking
- `child.generation = max(parent_a.generation, parent_b.generation) + 1`
- `child.parent_ids = [parent_a.name, parent_b.name]`
- `child.born_tick = current_tick`

---

## Naming

Extended name pool (30+ names). Children draw from unused names. When pool exhausts, use generation suffixes ("Ada-G2").

---

## Lineage Tracking

**New file: `simulation/lineage.py`**

```python
@dataclass
class LineageRecord:
    agent_name: str
    parent_names: list[str]   # [] for gen-0
    generation: int
    born_tick: int
    died_tick: int | None
    innovations_created: list[str]
    children_names: list[str]

class LineageTracker:
    records: dict[str, LineageRecord]

    def record_birth(agent_name, parent_names, generation, tick)
    def record_death(agent_name, tick)
    def record_innovation(agent_name, innovation_name)
    def record_child(parent_name, child_name)
    def save(path) / load(path)  # JSON persistence
```

Persisted to `data/lineage_{seed}.json`.

---

## Relationship Bootstrapping

When a child is born:
- Both parents get a Relationship with child at **trust=0.75** (bonded)
- Child gets relationships with both parents at **trust=0.75**
- This strongly encourages emergent parenting (LLM sees "bonded" status)

---

## Prompt Changes

**Decision prompt additions:**
- `reproduce` listed in available actions with description and requirements hint
- Family context line: "You are generation 2, born on tick 150. Parents: Ada, Bruno."
- Children line if applicable: "Your children: Clara (alive, nearby), Dante (dead)"

---

## Files to Modify/Create

| File | Change |
|---|---|
| `simulation/config.py` | Reproduction constants, extended name pool, child stats |
| `simulation/lineage.py` | **NEW** — LineageRecord, LineageTracker |
| `simulation/agent.py` | `last_reproduce_tick` field, family info in prompt, inheritance init |
| `simulation/oracle.py` | `_resolve_reproduce()` resolver |
| `simulation/engine.py` | LineageTracker integration, child spawning, death recording |
| `simulation/personality.py` | `blend()` class method for trait inheritance |
| `simulation/memory.py` | `inherit_from()` method for knowledge transfer |
| `prompts/agent/decision.txt` | Add reproduce action, family context |
| `tests/test_reproduction.py` | **NEW** — unit tests for reproduction mechanics |
| `project-cornerstone/08-evolution/evolution_context.md` | Update with implementation status |
| `project-cornerstone/00-master-plan/DECISION_LOG.md` | DEC-026: Reproduction design |

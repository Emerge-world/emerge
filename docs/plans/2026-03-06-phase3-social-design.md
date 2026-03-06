# Phase 3 Social System — Design Document

> Status: Approved
> Date: 2026-03-06
> Context: Phase 2 (Survival Depth) complete. Agents are solitary survivors. Phase 3 introduces social behavior.

## Motivation

Agents currently exist in isolation. They never see each other, cannot communicate, and have no social identity. Phase 3 changes this: agents gain personality, perceive their neighbors, form relationships, and develop social behaviors — from cooperation and teaching to emergent conflict. This lays the social and biological groundwork for Phase 4 (reproduction and evolution).

## Key Design Decisions

- **Reproduction deferred to Phase 4**: Phase 3 lays groundwork only (generational tracking + relationship bonding)
- **Conflict is emergent**: Aggression is not a base action; agents innovate it (Oracle validates with high cost + mutual risk)
- **Personality via prompt injection**: Traits described in natural language in the system prompt; LLM interprets them
- **Three sub-phases**: 3a (personality + perception) → 3b (communication + conflict + trust) → 3c (cooperation + teaching + generational tracking)

---

## Sub-Phase Overview

| Sub-phase | Focus | Builds On |
|-----------|-------|-----------|
| **3a** | Personality + Social Perception | Phase 2 complete |
| **3b** | Communication + Conflict + Trust | 3a |
| **3c** | Cooperation + Teaching + Generational Tracking | 3b |

---

## Phase 3a: Personality + Social Perception

### Personality System

**New file:** `simulation/personality.py`

```python
@dataclass
class Personality:
    courage: float     # 0.0-1.0 (bolder = innovates risky actions, confronts)
    curiosity: float   # 0.0-1.0 (explores, innovates more)
    patience: float    # 0.0-1.0 (high = rests/waits; low = acts impulsively)
    sociability: float # 0.0-1.0 (seeks out other agents, communicates)

    @classmethod
    def random(cls) -> "Personality":
        return cls(*[round(random.random(), 2) for _ in range(4)])

    def to_prompt(self) -> str:
        # Returns natural language for system prompt injection
        # Example: "You are courageous (0.8) and highly curious (0.9),
        #           somewhat patient (0.4), and very social (0.7)."
```

**Agent changes** (`simulation/agent.py`):
- Add `personality: Personality` field (default: `Personality.random()`)
- Inject via `prompts/agent/system.txt`:
  ```
  Your personality: {personality_description}
  Let this naturally guide how you interpret situations and choose actions.
  ```

### Social Perception

**World changes** (`simulation/world.py`):
- New method: `get_agents_in_radius(agent, agents_list, radius) -> list[tuple[Agent, int]]`
  - Returns `(agent, distance)` pairs for all alive agents within radius
  - Excludes the querying agent itself

**Agent changes** (`simulation/agent.py`):
- New method: `nearby_agents_prompt(visible_agents: list[tuple[Agent, int]]) -> str`
  - Fuzzy stats: `hunger > 50` → "looks hungry", `energy < 30` → "looks tired", `life < 50` → "looks hurt"
  - Fuzzy inventory: `len(inventory.items) > 0` → "carrying items"
  - Empty case: returns empty string (no section in prompt)
  - Output format:
    ```
    NEARBY AGENTS:
    - Bruno @ (8,5), 2 tiles away. Looks healthy. Carrying items.
    - Kai @ (6,7), 3 tiles away. Looks hungry. Looks tired.
    ```

**Engine changes** (`simulation/engine.py`):
- Each tick, gather `world.get_agents_in_radius(agent, all_agents, AGENT_VISION_RADIUS)` per agent
- Pass `nearby_agents` to `agent.decide_action()`

**Prompt changes** (`prompts/agent/decision.txt`):
- Add `{nearby_agents}` section after the grid display (omitted if empty)

### Critical Files (3a)

| File | Change |
|------|--------|
| `simulation/personality.py` | New file |
| `simulation/agent.py` | Add `personality` field, `nearby_agents_prompt()` |
| `simulation/world.py` | Add `get_agents_in_radius()` |
| `simulation/engine.py` | Gather + pass nearby agents each tick |
| `prompts/agent/system.txt` | Add `{personality_description}` |
| `prompts/agent/decision.txt` | Add `{nearby_agents}` section |

### Tests (3a)

- `test_personality.py`: `Personality.random()` produces 4 floats in [0.0, 1.0]; `to_prompt()` returns non-empty string; deterministic with fixed seed
- `test_perception.py`: Agent at center sees agents within radius; does not see agents outside radius; excludes self; night vision radius reduction respected

---

## Phase 3b: Communication + Conflict + Trust

### Communication System

**New base action:** `communicate`

```json
{"action": "communicate", "target": "Bruno", "message": "There is fruit east of the river.", "intent": "share_info"}
```

Valid intents: `share_info`, `request_help`, `warn`, `trade_offer`

**Oracle resolution** (`_resolve_communicate()`):
- Validate target exists and is alive
- Validate target is within vision radius
- Cost: 3 energy
- Queue `IncomingMessage` in `target.incoming_messages`
- Rate limit: max 1 communicate per agent per tick (prevents spam)

**New file:** `simulation/message.py`

```python
@dataclass
class IncomingMessage:
    sender: str
    tick: int
    message: str
    intent: str
```

**Agent changes** (`simulation/agent.py`):
- Add `incoming_messages: list[IncomingMessage]`
- Add `get_messages_prompt() -> str` (empty string if no messages)
- Messages cleared after being included in decision prompt each tick

**Prompt additions** (`prompts/agent/decision.txt`):
```
INCOMING MESSAGES:
- Bruno (tick 12): "There is fruit east of the river." [share_info]
```

### Emergent Conflict

Aggression is **not a base action**. Agents can innovate `attack`, `steal`, `threaten`.

Oracle evaluation for conflict innovations:
- High energy cost (≥15 for attacker)
- Mutual risk: attacker also risks life/energy loss
- Automatic trust penalty for victim (see trust table)
- Oracle LLM hint: "Aggression has social consequences and mutual physical risk. Is this plausible?"

**Resource competition rule** (Oracle change, `simulation/oracle.py`):
- When two agents attempt the same resource in the same tick: award to agent with **lower hunger** (most desperate)
- Losing agent receives episodic memory: `"Bruno took the fruit I was going for (tick 23)"`
- Trust penalty: -0.05 from loser toward winner

### Trust & Reputation System

**New file:** `simulation/relationship.py`

```python
@dataclass
class Relationship:
    target: str
    trust: float = 0.0    # -1.0 to 1.0, starts neutral
    cooperations: int = 0
    conflicts: int = 0
    last_tick: int = 0
    bonded: bool = False  # Phase 4 reproduction trigger

    @property
    def status(self) -> str:
        if self.trust > 0.6:  return "friendly"
        if self.trust > 0.2:  return "neutral"
        if self.trust > -0.3: return "wary"
        return "hostile"
```

**Trust update table:**

| Event | Delta |
|-------|-------|
| Cooperation (share food, build together) | +0.10 |
| Teaching accepted | +0.20 |
| Shared food (recipient view) | +0.15 |
| Resource competition loss | -0.05 |
| Steal (victim view) | -0.20 |
| Attack (victim view) | -0.40 |

**Bonding trigger** (Phase 4 groundwork):
- When `trust >= 0.75` AND `cooperations >= 3` → set `bonded = True`
- Bonded status is the prerequisite for reproduction (Phase 4)

**Agent changes** (`simulation/agent.py`):
- Add `relationships: dict[str, Relationship]`
- Add `get_relationships_prompt() -> str` (empty string if no relationships)
- Prompt section: only shows agents with at least 1 interaction

**Prompt additions** (`prompts/agent/decision.txt`):
```
RELATIONSHIPS:
- Bruno: Friendly (trust: 0.7), last interacted 3 ticks ago
- Kai: Wary (trust: -0.1)
```

### Critical Files (3b)

| File | Change |
|------|--------|
| `simulation/relationship.py` | New file |
| `simulation/message.py` | New file |
| `simulation/agent.py` | Add `relationships`, `incoming_messages` |
| `simulation/oracle.py` | Add `_resolve_communicate()`, trust updates, resource competition rule |
| `simulation/engine.py` | Trust update helper method |
| `prompts/agent/decision.txt` | Add `{incoming_messages}`, `{relationships}` sections |

### Tests (3b)

- `test_communication.py`: message queued to target; delivered next tick; cleared after delivery; invalid/out-of-range target rejected; energy cost applied
- `test_trust.py`: cooperation increments trust correctly; attack decrements correctly; bonded flag sets at threshold
- `test_resource_competition.py`: hungrier agent wins contested resource; loser gets correct memory entry; trust penalty applied

---

## Phase 3c: Cooperation + Teaching + Generational Tracking

### Cooperation: `share_food` (new base action)

```json
{"action": "share_food", "target": "Bruno", "item": "fruit", "quantity": 1}
```

**Oracle resolution** (`_resolve_share_food()`):
- Validate: target adjacent (≤1 tile), target alive, giver has item, target has inventory space
- Cost: 2 energy for giver
- Transfer: remove from giver's inventory, add to target's inventory
- Trust: target's trust for giver +0.15; `cooperations` counter incremented
- Episodic memory: both agents record the event

`build_together` remains innovatable — consistent with emergence principle.

### Teaching: `teach` (new base action)

```json
{"action": "teach", "target": "Kai", "skill": "craft_spear"}
```

**Oracle resolution** (`_resolve_teach()`):
- Validate: teacher knows `innovation:craft_spear` in precedents; target adjacent; target does NOT already know it
- Cost: teacher -8 energy, learner -5 energy
- Transfer: copy `precedents["innovation:craft_spear"]` → add to target's `actions` list and store in target's precedents
- Trust: +0.20 for both agents; `cooperations` incremented for both
- Episodic memory: `"I taught Kai craft_spear (tick 45)"` / `"Bruno taught me craft_spear (tick 45)"`
- **No LLM call** — deterministic knowledge transfer via precedent copy (DEC-024)

### Generational Tracking (Phase 4 groundwork)

**Agent changes** (`simulation/agent.py`):

```python
generation: int = 0         # 0 = original simulation agents
parent_ids: list[str] = []  # names/IDs of parents (empty for generation 0)
born_tick: int = 0          # tick when agent was spawned (0 for originals)
```

These fields are **stored but unused in Phase 3**. Phase 4 (reproduction) will:
- Check `bonded` flag from Relationship (set in 3b) as reproduction trigger
- Create child `Agent` with `generation = max(parent.generation) + 1`
- Blend parent personalities with mutation
- Inherit parent innovations (merge precedent sets)

### Config additions (`simulation/config.py`)

```python
TEACH_ENERGY_COST_TEACHER = 8
TEACH_ENERGY_COST_LEARNER = 5
SHARE_FOOD_ENERGY_COST = 2
BONDING_TRUST_THRESHOLD = 0.75
BONDING_COOPERATION_MINIMUM = 3
```

### Critical Files (3c)

| File | Change |
|------|--------|
| `simulation/agent.py` | Add `generation`, `parent_ids`, `born_tick` fields |
| `simulation/oracle.py` | Add `_resolve_share_food()`, `_resolve_teach()` |
| `simulation/config.py` | Add cooperation/teaching energy constants + bonding thresholds |

### Tests (3c)

- `test_cooperation.py`: `share_food` transfers item correctly; fails if target inventory full; fails if giver lacks item; trust updated correctly
- `test_teaching.py`: `teach` copies innovation to learner's actions + precedents; fails if teacher doesn't know skill; fails if target already knows it; fails if not adjacent
- `test_generational_tracking.py`: original agents have `generation=0`, empty `parent_ids`, `born_tick=0`

---

## Decision Log Entries

Add to `project-cornerstone/00-master-plan/DECISION_LOG.md` as each sub-phase completes:

- **DEC-020**: Personality via prompt injection (natural language in system prompt, not probability modifiers)
- **DEC-021**: Emergent conflict (aggression not a base action; Oracle evaluates innovated conflict with ≥15 energy cost + mutual risk)
- **DEC-022**: Resource competition rule (lowest hunger wins contested resource; Oracle resolves ties)
- **DEC-023**: Generational tracking in Phase 3c (reproduction remains Phase 4; Phase 3 adds only the 3 tracking fields)
- **DEC-024**: Teaching as deterministic precedent copy (no LLM call needed; preconditions enforced by Oracle)

---

## Verification (End-to-End)

```bash
# 1. Smoke test after each sub-phase (no LLM)
uv run main.py --no-llm --ticks 10 --agents 3

# 2. Unit tests (fast)
uv run pytest -m "not slow"

# 3. Full LLM simulation after 3a (check personality in prompts)
uv run main.py --agents 3 --ticks 30 --seed 42 --save-log --verbose
# Verify in log: system prompts include personality descriptions
# Verify in log: NEARBY AGENTS section appears in decision prompts

# 4. Full LLM simulation after 3b (check social actions)
uv run main.py --agents 3 --ticks 50 --seed 42 --save-log --verbose
# Verify: communicate actions logged
# Verify: trust changes logged after interactions
# Verify: RELATIONSHIPS section in decision prompts

# 5. Sub-phase specific tests
uv run pytest tests/test_personality.py tests/test_perception.py -v       # 3a
uv run pytest tests/test_communication.py tests/test_trust.py -v          # 3b
uv run pytest tests/test_cooperation.py tests/test_teaching.py -v         # 3c
```

---

## MASTER_PLAN.md Updates

After each sub-phase, update Phase 3 checklist in `project-cornerstone/00-master-plan/MASTER_PLAN.md`:

- 3a: `[x] Personality system (prompt injection)` + `[x] Social perception (nearby agents in vision radius)`
- 3b: `[x] Communication (speak, signal)` + `[x] Conflict (emergent, resource competition rule)` + `[x] Reputation and relationships`
- 3c: `[x] Cooperation (share food)` + `[x] Knowledge transmission (teach innovations)` + `[x] Generational tracking (Phase 4 groundwork)`

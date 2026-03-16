# 03 — Agent System

## Current Cognition Stack

The following agent cognition features are live:

- **Compact 7×7 ASCII grid**: Nearby tiles are rendered as a compact ASCII grid (`@`=agent, `F`=fruit, `t`=tree, `W`=water, `.`=land, `#`=obstacle) instead of a JSON list.
- **Directional resource hints**: The decision prompt includes natural-language hints like `"fruit 2 tiles NORTH"` so the agent can act without parsing the full grid.
- **Few-shot examples**: `prompts/agent/system.txt` contains 2–3 worked examples of good decisions baked into the system prompt.
- **Template prompt system**: Prompts are stored as `prompts/agent/system.txt` and `prompts/agent/decision.txt`, loaded and cached by `simulation/prompt_loader.py` using `string.Template`. See DEC-005.
- **Dual memory system**: Episodic (short-term, max 20) + semantic (long-term, max 30) memory. See DEC-009, implemented in `simulation/memory.py`.
- **Task memory**: bounded planning/task ledger used to retain recent plan outcomes and blockers.
- **Deterministic retrieval**: planner and executor select relevant memory via keyword-and-state scoring rather than pure recency slices.
- **Explicit planner/executor loop**: when `ENABLE_EXPLICIT_PLANNING` is enabled, agents can create structured plans, execute subgoals, and emit planning events.
- **Personality system**: personality traits are implemented and injected into the system prompt via `simulation/personality.py`.

---

## Current State

Each agent has:
- **Stats**: life (0-100), hunger (0-100, more = worse), energy (0-100)
  - **Passive healing**: agents regenerate +1 life/tick when hunger < 50 AND energy > 30 (DEC-011)
- **Position**: `(x, y)` in the grid
- **Memory**: `Memory` class with episodic, semantic, and task memory stores
- **Planning state**: `PlanningState` with goal, subgoals, status, confidence, and blocker tracking
- **Initial actions**: `["move", "eat", "rest", "innovate", "pickup", "drop_item", "communicate", "give_item", "teach"]`
  - `reproduce` is built-in but NOT available at birth; it unlocks once `current_tick - born_tick >= 100`
- **LLM**: vLLM/OpenAI-compatible structured outputs via `simulation/llm_client.py`
- **Planner**: optional `Planner` wrapper reusing the same LLM client with structured planner output
- **Personality**: courage, curiosity, patience, sociability

### Known Issues

1. **Explicit planning is feature-flagged off by default**: `ENABLE_EXPLICIT_PLANNING = False` keeps the old reactive loop as the baseline until more tuning lands.
2. **Token budget remains tight**: planner and executor prompts add new context, so prompt-size discipline still matters.
3. **Fallback remains simple**: the no-LLM mode still follows hand-written heuristics rather than durable plans.

## Memory And Planning

### Dual memory system *(implemented — see DEC-009)*

Code lives in `simulation/memory.py`. Compression prompt in `prompts/agent/memory_compression.txt`.

```
MEMORY
├── Episodic (short-term)
│   └── Last 20 actions and results as-is
│   └── Used directly in the prompt
│
└── Semantic (long-term)
    └── Compressed summaries every 10 ticks
    └── "Learned that eating fruit reduces hunger ~20 points"
    └── "The north area of the map has many trees"
    └── "When my energy drops below 20, I must rest"
    └── Generated with an LLM compression call
```

**Proposed implementation:**
```python
class Memory:
    def __init__(self):
        self.episodic: list[str] = []       # max 20, raw events
        self.semantic: list[str] = []       # max 30, compressed knowledge
        self.last_compression_tick: int = 0

    def add_episode(self, entry: str):
        self.episodic.append(entry)
        if len(self.episodic) > 20:
            self.episodic.pop(0)

    def compress(self, llm: LLMClient, tick: int):
        """Every 10 ticks, compress episodic into semantic."""
        if tick - self.last_compression_tick < 10:
            return
        # Ask LLM to extract learnings
        # Prompt: "Given these recent experiences, what are the key lessons?"
        # Add results to self.semantic
        self.last_compression_tick = tick

    def to_prompt(self) -> str:
        sem = "\n".join(f"- [KNOW] {s}" for s in self.semantic[-10:])
        epi = "\n".join(f"- [RECENT] {e}" for e in self.episodic[-10:])
        return f"KNOWLEDGE:\n{sem}\n\nRECENT EVENTS:\n{epi}"
```

### Task memory + deterministic retrieval *(implemented)*

The `Memory` class now also keeps a bounded task-memory ledger:

```python
@dataclass
class TaskMemoryEntry:
    tick: int
    kind: str
    summary: str
    goal: str = ""
    outcome: str = ""
```

- **Purpose**: retain recent plan results, blockers, and short summaries that help future replanning.
- **Bounded size**: capped by `TASK_MEMORY_MAX`.
- **Retrieval**: `simulation/retrieval.py` ranks semantic, episodic, and task-memory entries against the current state.
- **Contexts**:
  - planner context uses `PLANNER_CONTEXT_MAX`
  - executor context uses `EXECUTOR_CONTEXT_MAX`

### Explicit planner/executor loop *(implemented behind flag)*

Code lives in `simulation/planning_state.py`, `simulation/planner.py`, and `simulation/agent.py`.

```python
self.planning_state = PlanningState.empty()
self.planner = Planner(llm) if llm else None
```

- **Planner cadence**: runs only when `ENABLE_EXPLICIT_PLANNING` is true and the current plan needs refresh.
- **Replanning triggers**:
  - no usable plan
  - stale/blocked/completed/abandoned plan
  - periodic refresh via `PLAN_REFRESH_INTERVAL`
- **Executor prompt additions**:
  - `CURRENT GOAL`
  - `ACTIVE SUBGOAL`
  - `PLAN STATUS`
- **Planner output**: structured goal, goal type, subgoals, success signals, abort conditions, confidence, and rationale summary.
- **Observability**: agent decisions can carry a hidden `_planning_trace` consumed by `simulation/engine.py`.

### EBS Autonomy component *(rebuilt — see DEC-041)*

Weight: 13% of total EBS. Three sub-scores:

| Sub-score | Weight | Signals |
|---|---|---|
| `behavioral_initiative` | 25% | avg(`proactive_rate`, `env_contingent_rate`) |
| `knowledge_accumulation` | 37.5% | avg(`semantic_growth`, `compression_yield`) |
| `planning_effectiveness` | 37.5% | avg(`plan_completion_rate`, `planning_activity`) |

- `semantic_growth` — mean final `memory_semantic` count / `MEMORY_SEMANTIC_MAX` across agents (from `agent_state` events)
- `compression_yield` — mean `min(1, learnings / episode_count)` per compression event
- `plan_completion_rate` — `subgoals_completed / (subgoals_completed + subgoals_failed)`; 0 when planning disabled
- `planning_activity` — `min(1, planning_signal / action_total)`

All six underlying signals are exposed in `ebs.json` under `components.autonomy.detail`.

### Inventory *(implemented — see DEC-017)*

```python
agent.inventory = Inventory(capacity=AGENT_INVENTORY_CAPACITY)  # default 10
# items: {"fruit": 2, "stone": 1} — quantity-based (not slot-based)
```

- **Capacity**: measured by total item quantity (e.g., `{fruit: 3, stone: 7}` = full at capacity 10)
- **Prompt**: appears in decision prompt only when non-empty: `INVENTORY: fruit x2, stone x1 (3/10)`
- **Serialized** in `get_status()` → `{"items": {...}, "capacity": 10}`
- **`pickup` base action**: agents start with it — pick up 1 item per tick from their current tile (no energy cost)
- **`drop_item` base action**: agents start with it — place inventory items onto their current tile (no energy cost); succeeds on empty/same-type stacks and fails on conflicting resource types
- **`give_item` base action** *(Phase 3c)*: transfer any inventory item to an adjacent agent (manhattan dist ≤ 1); costs 2 energy; builds +0.15 trust on receiver toward giver; both get episodic memory
- **`teach` base action** *(Phase 3c)*: deterministically copy an owned innovation to a visible agent (dist ≤ AGENT_VISION_RADIUS); costs 8 energy (teacher) + 5 energy (learner); both gain +0.20 trust; no LLM call (DEC-024)
- **Source**: `simulation/inventory.py` — `Inventory` class

### Generational tracking fields *(Phase 3c — Phase 4 groundwork)*

Added to `Agent.__init__()`:
```python
self.generation: int = 0      # Generation number (0 = original)
self.parent_ids: list[str] = []  # Names of parent agents
self.born_tick: int = 0       # Tick at which agent was born/spawned
```
All default to inert values. Included in `get_status()`. Populated by Phase 4 reproduction logic.

### Personality system *(implemented in Phase 3)*

Each agent is born with traits that influence its decisions:

```python
PERSONALITY_TRAITS = {
    "courage": (0.0, 1.0),      # 0=coward, 1=daredevil
    "curiosity": (0.0, 1.0),    # 0=conservative, 1=explorer
    "patience": (0.0, 1.0),     # 0=impulsive, 1=methodical
    "sociability": (0.0, 1.0),  # 0=solitary, 1=gregarious
}
# Included in the agent's system prompt:
# "You are Ada. You are very curious (0.9) but impatient (0.2).
#  You tend to explore new areas rather than stay in safe zones."
```

### Prompt improvements *(implemented — see "Current Cognition Stack" above)*

The following improvements have been applied. Details for reference:

1. **Reduce tokens**: Nearby tiles as compact grid, not list.
   ```
   Instead of: [{"x":5,"y":3,"tile":"land","distance":2}, ...]
   Use:      .T.WL
              TL.LT   (L=land, T=tree, W=water, .=empty, @=you)
              L@TLL
   ```

2. **Few-shot examples**: Include 2-3 examples of good decisions in the system prompt.
   ```
   Example: Stats: Life=80, Hunger=65, Energy=30
   Nearby: tree with fruit 1 tile east
   Good decision: {"action":"eat","reason":"hunger is high and food is adjacent"}
   ```

3. **Prompt caching**: Ollama supports keep_alive. The agent's system prompt changes little between ticks, so leverage context caching.

### Expanded stats (Phase 2)

```python
# To add in the future:
- thirst: int        # Thirst, works like hunger but with water
- temperature: int   # Affected by weather and shelter
- health: int        # Different from "life": diseases, injuries
```

## Considerations for Claude Code

- When refactoring memory, maintain backward compatibility with the current string list.
- Agent tests must verify: stats never out of bounds, dead agents never act, memory/task-memory caps work.
- Planning changes must preserve fallback behavior when planner calls fail or structured output is invalid.
- Planning events should remain small and deterministic; they feed `events.jsonl` and `EBSBuilder`.
- Prompts ALWAYS in English (Qwen 2.5-3B performs much better).
- If the LLM returns invalid JSON, the fallback MUST work. Never crash due to a bad response.
- Each prompt change → evaluate with 10 runs of 30 ticks and measure % of coherent decisions.

# 03 — Agent System

## Implemented in Phase 1

The following prompt improvements are already live:

- **Compact 7×7 ASCII grid**: Nearby tiles are rendered as a compact ASCII grid (`@`=agent, `F`=fruit, `t`=tree, `W`=water, `.`=land, `#`=obstacle) instead of a JSON list.
- **Directional resource hints**: The decision prompt includes natural-language hints like `"fruit 2 tiles NORTH"` so the agent can act without parsing the full grid.
- **Few-shot examples**: `prompts/agent/system.txt` contains 2–3 worked examples of good decisions baked into the system prompt.
- **Template prompt system**: Prompts are stored as `prompts/agent/system.txt` and `prompts/agent/decision.txt`, loaded and cached by `simulation/prompt_loader.py` using `string.Template`. See DEC-005.
- **Dual memory system**: Episodic (short-term, max 20) + semantic (long-term, max 30) memory. The decision prompt includes 10 semantic + 10 episodic entries via `memory.to_prompt()`. See DEC-009, implemented in `simulation/memory.py`.

Phase 1 is complete. Personality system is scheduled for **Phase 3** (see DEC-014).

---

## Current State (Phase 0)

Each agent has:
- **Stats**: life (0-100), hunger (0-100, more = worse), energy (0-100)
  - **Passive healing**: agents regenerate +1 life/tick when hunger < 50 AND energy > 30 (DEC-011)
- **Posición**: (x, y) in the grid
- **Memoria**: `Memory` class with episodic (max 20, raw events) + semantic (max 30, compressed knowledge)
- **Acciones iniciales**: `["move", "eat", "rest", "innovate", "pickup", "drop_item", "communicate", "give_item", "teach"]`
  - `reproduce` is built-in but NOT available at birth; it unlocks once `current_tick - born_tick >= 100`
- **LLM**: Ollama 

### Known Issues

1. **No personality**: All agents are identical except for their position and memory.
2. **Token budget**: With dual memory + compact grid, prompts are ~500-750 tokens per call vs <300 target. Compression helps but token budget enforcement is not yet implemented.
3. **Too simple fallback**: The mode without LLM always oscillates between two tiles.

## Phase 1 — Intelligence

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

### Personality system *(Phase 3 — deferred, see DEC-014)*

Each agent will be born with traits that influence their decisions. All four traits are implemented together in Phase 3 alongside social mechanics, where they can meaningfully affect agent behavior:

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

### Prompt improvements *(implemented — see "Implemented in Phase 1" above)*

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
- Agent tests must verify: stats never out of bounds, dead agents never act, memory cap works.
- Prompts ALWAYS in English (Qwen 2.5-3B performs much better).
- If the LLM returns invalid JSON, the fallback MUST work. Never crash due to a bad response.
- Each prompt change → evaluate with 10 runs of 30 ticks and measure % of coherent decisions.

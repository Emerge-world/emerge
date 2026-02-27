# 03 — Agent System

## Current State (Phase 0)

Each agent has:
- **Stats**: vida (0-100), hambre (0-100, más = peor), energía (0-100)
- **Posición**: (x, y) en el grid
- **Memoria**: lista de strings, cap 50, FIFO
- **Acciones**: lista de strings empezando con `["move", "eat", "rest", "innovate"]`
- **LLM**: referencia al cliente Ollama compartido

### Known Issues

1. **Unstructured memory**: Everything is plain text. Doesn't distinguish between facts, experiences, and knowledge.
2. **No personality**: All agents are identical except for their position and memory.
3. **Long prompt**: With 50 memories + nearby tiles, the prompt gets large for a 3B model.
4. **Too simple fallback**: The mode without LLM always oscillates between two tiles.

## Phase 1 — Intelligence

### Dual memory system

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

### Personality system

Each agent is born with traits that influence their decisions:

```python
PERSONALITY_TRAITS = {
    "courage": (0.0, 1.0),      # 0=coward, 1=daredevil
    "curiosity": (0.0, 1.0),    # 0=conservative, 1=explorer
    "patience": (0.0, 1.0),     # 0=impulsive, 1=methodical
    "sociability": (0.0, 1.0),  # 0=solitary, 1=gregarious (Phase 3)
}
# Included in the agent's system prompt:
# "You are Ada. You are very curious (0.9) but impatient (0.2).
#  You tend to explore new areas rather than stay in safe zones."
```

### Prompt improvements

The current prompt is functional but not optimal for a 3B model. Improvements:

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

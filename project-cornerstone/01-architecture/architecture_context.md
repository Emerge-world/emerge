# 01 — Architecture

## System Overview

```
┌─────────────────────────────────────────────────┐
│                  SimulationEngine               │
│  (orchestrates tick loop, manages lifecycle)    │
├─────────────┬──────────────┬────────────────────┤
│             │              │                    │
│   Agent 1   │   Agent 2    │   Agent N          │
│  ┌────────┐ │  ┌────────┐  │  ┌────────┐        │
│  │ LLM    │ │  │ LLM    │  │  │ LLM    │        │
│  │ Memory │ │  │ Memory │  │  │ Memory │        │
│  │ Stats  │ │  │ Stats  │  │  │ Stats  │        │
│  └───┬────┘ │  └───┬────┘  │  └───┬────┘        │
│      │      │      │       │      │             │
│      └──────┴──────┴───────┴──────┘             │
│                    │ action                     │
│                    ▼                            │
│             ┌──────────────┐                    │
│             │   Oracle     │                    │
│             │  ┌────────┐  │                    │
│             │  │ LLM    │  │                    │
│             │  │Preceds │  │                    │
│             │  └────────┘  │                    │
│             └──────┬───────┘                    │
│                    │ result                     │
│                    ▼                            │
│             ┌──────────────┐                    │
│             │   World      │                    │
│             │  (10x10 grid)│                    │
│             │  resources   │                    │
│             └──────────────┘                    │
└─────────────────────────────────────────────────┘
```

## Tick Lifecycle (each simulated hour)

```
FOR each alive agent:
    1. PERCEIVE  → world.get_nearby_tiles(agent.x, agent.y, radius)
    2. DECIDE    → agent.decide_action(nearby, tick)  [LLM call]
    3. VALIDATE  → oracle.resolve_action(agent, action, tick)  [possible LLM call]
    4. APPLY     → modify agent stats + world state
    5. DEGRADE   → agent.apply_tick_effects()  [hunger rises, possible damage]
    6. RECORD    → agent.add_memory() + oracle.world_log
```

## Module Contracts

### World → Agent
- `get_nearby_tiles(x, y, radius)` → `list[dict]` con tiles visibles
- `get_tile(x, y)` → tipo de tile
- `get_resource(x, y)` → recurso disponible o None

### Agent → Oracle
- `decide_action()` → `dict` with `{"action": str, ...params, "reason": str}`
- The agent NEVER modifies its own stats directly (except in apply_tick_effects)

### Oracle → World
- `consume_resource(x, y, amount)` → actual quantity consumed
- The oracle is the ONLY one that modifies world state

### Oracle → Agent
- Modifica stats via `agent.modify_hunger()`, `agent.modify_energy()`, `agent.modify_life()`
- Añade memoria via `agent.add_memory()`

## Invariants (must never break)

1. A dead agent NEVER acts.
2. Stats NEVER go below 0 or above their maximum.
3. The oracle ALWAYS produces the same result for the same situation (precedents).
4. Each tick processes ALL alive agents before moving to the next tick.

## File Structure (current)

```
project-root/
├── main.py                    # Entry point + CLI
├── simulation/
│   ├── __init__.py
│   ├── config.py              # All tunable constants
│   ├── llm_client.py          # Ollama wrapper
│   ├── world.py               # 2D grid + resources
│   ├── agent.py               # Agent class + LLM decision
│   ├── oracle.py              # Action validation + precedents
│   ├── engine.py              # Tick loop orchestration
│   ├── sim_logger.py          # Per-run markdown logging (logs/ dir)
│   ├── prompt_loader.py       # string.Template loader, cached
│   ├── memory.py              # Dual memory system (episodic + semantic) — DEC-009
│   ├── audit_recorder.py      # Behavioral audit recording — DEC-008
│   └── audit_compare.py       # Audit run comparison CLI
├── prompts/
│   ├── agent/
│   │   ├── system.txt         # Fixed system prompt (name, actions, grid legend, few-shot examples)
│   │   ├── decision.txt       # Variable user prompt (tick, stats, grid, resources, memory)
│   │   ├── energy_critical.txt # Status effect prompt (energy critical)
│   │   ├── energy_low.txt     # Status effect prompt (energy low)
│   │   └── memory_compression.txt # Memory compression prompt
│   └── oracle/
│       ├── physical_system.txt
│       ├── innovation_system.txt
│       ├── custom_action_system.txt
│       └── fruit_effect.txt
├── tests/
│   ├── test_audit.py          # Audit system tests
│   └── test_memory.py         # Dual memory system tests
├── data/
└── project-cornerstone/       # This knowledge base
```

## File Structure (target Phase 2+)

```
project-root/
├── main.py
├── simulation/
│   ├── __init__.py
│   ├── config.py
│   ├── llm/
│   │   ├── client.py          # Base LLM client
│   │   ├── ollama.py          # Ollama implementation
│   │   ├── anthropic.py       # Claude API implementation
│   │   └── prompts.py         # Prompt templates centralizados
│   ├── world/
│   │   ├── grid.py            # Core grid logic
│   │   ├── resources.py       # Resource management
│   │   ├── weather.py         # Weather system
│   │   └── generator.py       # World generation (Perlin noise, biomes)
│   ├── agents/
│   │   ├── agent.py           # Core agent
│   │   ├── memory.py          # Memory system (short + long term)
│   │   ├── personality.py     # Personality traits
│   │   ├── inventory.py       # Item management
│   │   └── needs.py           # Hunger, energy, etc.
│   ├── oracle/
│   │   ├── oracle.py          # Core oracle
│   │   ├── precedents.py      # Precedent DB
│   │   └── validators.py      # Action-specific validators
│   ├── actions/
│   │   ├── base.py            # Base action classes
│   │   ├── movement.py
│   │   ├── survival.py
│   │   └── innovation.py
│   └── engine.py
├── tests/
│   ├── test_world.py
│   ├── test_agent.py
│   ├── test_oracle.py
│   └── test_integration.py
├── data/
│   ├── logs/
│   ├── worlds/
│   └── replays/
└── project-cornerstone/
```

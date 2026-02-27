# 🧬 Life Simulation - Autonomous Agents with LLM

Life and evolution simulation using agents controlled by language models (Qwen 2.5-3B via Ollama).

## Architecture

```
main.py                    ← Entry point
simulation/
├── config.py              ← Global configuration (stats, world, LLM)
├── llm_client.py          ← Ollama client
├── world.py               ← 2D world (50x50, tiles: water/land/tree)
├── agent.py               ← Agent with life/hunger/energy, memory, LLM
├── oracle.py              ← Oracle: validates actions, maintains consistency
└── engine.py              ← Simulation engine (tick loop)
```

## Requirements

- Python 3.10+
- [Ollama](https://ollama.ai/) running locally
- Qwen 2.5-3B model: `ollama pull qwen2.5:3b`

```bash
pip install requests
```

## Usage

```bash
# Basic run (3 agents, 30 ticks)
python main.py

# Customize
python main.py --agents 5 --ticks 100 --seed 42

# Without LLM (rule-based fallback mode)
python main.py --no-llm --ticks 50

# With detailed logging and log saving
python main.py --verbose --save-log --save-state
```

## Mechanics

### Agents
- **Life** (0-100): If it reaches 0, the agent dies.
- **Hunger** (0-100): Increases +3/tick. Above 70, causes -5 life/tick.
- **Energy** (0-100): Spent on actions, recovered by resting.

### Base actions
| Action   | Energy cost | Effect |
|----------|------------|--------|
| move     | 5          | Move one tile (N/S/E/W) |
| eat      | 2          | Eat nearby fruit → reduces hunger |
| rest     | 0          | Recover +15 energy |
| innovate | 10         | Invent a new action |

### Innovation
Agents can invent new actions. The oracle validates whether they make sense and determines their effects. Results are recorded as precedents to maintain consistency.

### Oracle
- Validates all agent actions
- Maintains a precedent memory for determinism
- If an effect was previously determined, the same result is reused

## Configuration

Edit `simulation/config.py` to adjust world, agent, LLM parameters, etc.

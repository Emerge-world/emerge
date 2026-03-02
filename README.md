# Emerge: Life Simulation via Autonomous LLM Agents

Agents controlled by language models (Qwen 2.5-3B via Ollama) survive in a 2D world — eating, resting, moving, and inventing new actions. An Oracle validates every action and maintains world consistency through precedents.

## Architecture

```
main.py                        ← CLI entry point
server/
├── run_server.py              ← Web server entry point
├── server.py                  ← FastAPI app + WebSocket endpoint
└── event_bus.py               ← Async bridge: sim thread → WebSocket clients
simulation/
├── config.py                  ← All tunable constants
├── engine.py                  ← Tick loop (CLI + web callback modes)
├── world.py                   ← 2D grid (50×50, tiles: water/land/tree)
├── agent.py                   ← Agent: life/hunger/energy, memory, LLM decisions
├── oracle.py                  ← Validates actions, enforces precedents
├── llm_client.py              ← Ollama client
└── sim_logger.py              ← Structured markdown logging
UI/
├── src/
│   ├── components/            ← WorldGrid, AgentPanel, AgentCard, StatusBar
│   ├── hooks/useSimulation.ts ← WebSocket state management
│   └── types.ts               ← Shared TypeScript interfaces
└── public/assets/             ← Drop Kenney tileset PNG here (optional)
```

## Requirements

### Python
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager (recommended) or pip
- [Ollama](https://ollama.ai/) running locally with `ollama pull qwen2.5:3b`

```bash
uv sync          # installs all Python dependencies
```

Or with pip:
```bash
pip install fastapi[standard] uvicorn[standard] requests
```

### Node.js (web UI only)
- Node.js 18+

```bash
cd UI && npm install
```

## Usage

### Web UI (recommended)

Start the simulation server, then the frontend dev server:

```bash
# Terminal 1 — Python backend (port 8000)
uv run python server/run_server.py --agents 3 --seed 42

# Without LLM (fast, no Ollama needed)
uv run python server/run_server.py --no-llm --agents 3

# Terminal 2 — React frontend (port 5173)
cd UI && npm run dev
```

Open [http://localhost:5173](http://localhost:5173). The UI will connect automatically.

**Web server options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--agents N` | 3 | Number of agents |
| `--ticks N` | 500 | Max simulation ticks |
| `--seed N` | random | World generation seed |
| `--no-llm` | — | Rule-based fallback (no Ollama needed) |
| `--port N` | 8000 | HTTP port |
| `--tick-delay F` | 0.5 | Seconds between ticks |

### CLI (headless)

```bash
# Basic run (3 agents, 30 ticks)
uv run main.py

# Customize
uv run main.py --agents 5 --ticks 100 --seed 42

# Without LLM (rule-based fallback)
uv run main.py --no-llm --ticks 50

# Save logs and world state
uv run main.py --verbose --save-log --save-state
```

## Web UI Features

- **Top-down grid view** — 50×50 tile canvas with water, land, and tree tiles
- **Agent tracking** — colored dots showing each agent's position, updated each tick
- **Click to inspect** — click any agent to highlight their 7×7 vision radius
- **Stats sidebar** — live life / hunger / energy bars per agent
- **Memory feed** — last 10 memory entries per agent, most recent first
- **Pause / Resume** — control the simulation from the browser
- **Auto-reconnect** — the frontend reconnects automatically if the server restarts

### Optional: Kenney Tileset

The grid falls back to solid colored squares by default. To use pixel-art sprites:

1. Download a 16×16 top-down tileset from [kenney.nl](https://kenney.nl/assets) (e.g. *Tiny Town*)
2. Place the PNG at `UI/public/assets/tileset.png`
3. Update the `SPRITE_MAP` constants at the top of `UI/src/components/WorldGrid.tsx` to match the source coordinates in your sheet

## Mechanics

### Agents

| Stat | Range | Description |
|------|-------|-------------|
| Life | 0–100 | Reaches 0 → agent dies |
| Hunger | 0–100 | Increases +1/tick; above 80 causes −3 life/tick |
| Energy | 0–100 | Spent on actions; reaching 0 causes −2 life/tick |

### Base Actions

| Action | Energy cost | Effect |
|--------|------------|--------|
| move | 3 | Move one tile (N/S/E/W) |
| eat | 2 | Consume fruit from adjacent tree → reduces hunger |
| rest | 0 | Recover +50 energy |
| innovate | 0 | Invent a new action (Oracle validates) |

### Vision

Each agent perceives a **7×7 tile area** (radius 3) centred on itself, including tile types, distances, and visible resources. This is rendered as the vision overlay in the UI when an agent is selected.

### Innovation

Agents can invent entirely new actions via `innovate`. The Oracle LLM judges whether the action is physically plausible and determines its effects (stat changes). Results are cached as **precedents** — the same situation always produces the same outcome.

### Oracle

- Validates every agent action before applying it
- Maintains a precedent dictionary for determinism: same input → same output
- Falls back to rule-based resolution when no LLM is available

## API Reference

The server exposes a small REST + WebSocket API:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Server status and current tick |
| `/api/state` | GET | Full world snapshot (tiles, agents) |
| `/api/control/pause` | POST | Pause the simulation |
| `/api/control/resume` | POST | Resume the simulation |
| `/ws` | WebSocket | Live stream of `init`, `tick`, and `control` messages |

## Configuration

Edit `simulation/config.py` to tune world generation, agent stats, LLM settings, and tick speed.

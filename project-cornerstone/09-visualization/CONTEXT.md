# 09 — Visualization (Phase 5)

> DO NOT implement until Phase 3 stable. Plan stack beforehand.

## Concept

Real-time web dashboard showing the world, agents, and statistics. Replay capability.

## Architecture

```
┌──────────────┐     WebSocket      ┌──────────────────────┐
│  Simulation  │ ──────────────────→ │  Frontend (React)    │
│  Engine      │  events stream     │  ├── Grid (Pixi.js)  │
│  (Python)    │ ←────────────────── │  ├── Stats Panel     │
└──────┬───────┘   controls          │  ├── Log Feed        │
       │                             │  ├── Charts          │
       │  REST API                   │  └── Replay Controls │
       │                             └──────────────────────┘
┌──────┴───────┐
│  FastAPI     │
│  Server      │
│  - /ws       │  WebSocket for live events
│  - /api/     │  REST for state queries
│  - /replay/  │  Replay from saved logs
└──────────────┘
```

## Event Stream Format

```json
{
    "tick": 42,
    "timestamp": "2026-02-27T14:30:00",
    "events": [
        {
            "type": "agent_move",
            "agent": "Ada",
            "from": [10, 15],
            "to": [11, 15],
            "stats": {"life": 85, "hunger": 30, "energy": 60}
        },
        {
            "type": "agent_eat",
            "agent": "Bruno",
            "position": [5, 8],
            "resource": "fruit",
            "hunger_change": -20
        },
        {
            "type": "innovation",
            "agent": "Clara",
            "action_name": "build_shelter",
            "description": "..."
        },
        {
            "type": "agent_death",
            "agent": "Dante",
            "cause": "starvation",
            "survived_ticks": 67
        }
    ]
}
```

## Grid Rendering (Pixi.js)

```
Tile sprites:
  water   → blue with animated wave
  land    → green/brown
  tree    → green with tree sprite
  shelter → tile with structure (innovated)

Agent sprites:
  alive   → unique colored circle per agent
  hungry  → blinking red border
  tired   → semi-transparent sprite
  dead    → red X

Overlay:
  vision radius → highlight tiles that selected agent can see
  resource qty  → number on tiles with resources
  paths         → line showing agent's recent movement
```

## Charts (Recharts / D3)

```
- Line chart: stats of each agent over time
- Area chart: total resources in the world
- Bar chart: actions by type per tick
- Scatter: agent positions over time (heatmap)
- Tree: genealogical tree (Phase 4)
- Network: relationship graph (Phase 3)
```

## Considerations for Claude Code

- Visualization should NOT couple the simulation to the frontend. Sim must be able to run without dashboard.
- Use an Observer/EventBus pattern: engine emits events, server retransmits them.
- Prioritize grid + stats. Charts and replay are nice-to-have.
- Replay only needs event logs (JSON lines), not complete state.

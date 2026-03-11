# 09 — Visualization (Current + Next)

## What already exists in code

- Backend: FastAPI server with REST + WebSocket (`server/server.py`).
- Frontend: React + Vite app in `UI/`.
- Live features implemented:
  - world grid rendering
  - agent selection panel and status cards
  - pause/resume controls
  - websocket auto-reconnect flow via `useSimulation`

## Current architecture

- Simulation runs in a background thread.
- Tick/control messages are fanned out by `server/event_bus.py`.
- Browser receives `init`, `tick`, and `control` messages.

## Gaps to reach full Phase 5 intent

1. Replay interface from persisted run events (`data/runs/<run_id>/events.jsonl`)
2. Time-series charts from `metrics_builder` artifacts
3. Genealogy/lineage visual view
4. Comparative run dashboard (multi-seed / multi-config)

## Recommended implementation order

1. Read-only replay page (single run)
2. Metrics panel (summary + timeseries)
3. Lineage tree view
4. Cross-run comparison table

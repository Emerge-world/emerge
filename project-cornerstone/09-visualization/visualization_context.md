# 09 — Visualization (Current + Next)

## What already exists in code

- Backend: FastAPI server with REST + WebSocket (`server/server.py`).
- Frontend: React + Vite app in `UI/`.
- Live features implemented:
  - world grid rendering
  - agent selection panel and status cards
  - pause/resume controls
  - websocket auto-reconnect flow via `useSimulation`
- Docs visualization surface planned and designed:
  - standalone interactive metrics explainer under `docs/metrics-explainer/`
  - editorial explanation plus optional loading of real run metric artifacts

## Current architecture

- Simulation runs in a background thread.
- Tick/control messages are fanned out by `server/event_bus.py`.
- Browser receives `init`, `tick`, and `control` messages.
- Post-run metric artifacts are written under `data/runs/<run_id>/metrics/` and are the intended data source for the docs explainer.

## Gaps to reach full Phase 5 intent

1. Replay interface from persisted run events (`data/runs/<run_id>/events.jsonl`)
2. Docs-owned explainer page implementation for metrics and EBS (`docs/metrics-explainer/`)
3. Time-series charts from `metrics_builder` artifacts
4. Genealogy/lineage visual view
5. Comparative run dashboard (multi-seed / multi-config)

## Recommended implementation order

1. Docs-owned metrics explainer with sample fixtures and optional run artifact loading
2. Read-only replay page (single run)
3. Metrics panel (summary + timeseries)
4. Lineage tree view
5. Cross-run comparison table

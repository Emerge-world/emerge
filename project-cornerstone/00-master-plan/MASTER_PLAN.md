# 🧬 EMERGE — Master Plan

> Life and evolution simulation using autonomous agents controlled by LLM.

## Vision

Build an emergent world where agents controlled by language models learn to survive, innovate tools, develop culture and evolve as a species — without hardcoded rules beyond the physics of the world.

## Design Principles

1. **Emergence over prescription**: We don't program behaviors; agents discover them.
2. **Oracle determinism**: Same action + same context = same result. Always.
3. **Memory as identity**: Agents are their memories. Without memory, there's no personality.
4. **Incremental complexity**: Each phase must work stably BEFORE moving forward.
5. **LLM-agnostic**: The architecture doesn't depend on a specific model. Ollama today, API tomorrow.

---

## Phase Roadmap

### PHASE 0 — Foundation ✅ (COMPLETED)
- [x] 2D World (10x10 default, configurable) with tiles (water, land, tree)
- [x] Agents with life, hunger, energy
- [x] Base actions: move, eat, rest, innovate
- [x] Oracle with validation and precedents
- [x] Simulation engine with ticks
- [x] Fallback mode without LLM
- [x] Console output with stat bars

### PHASE 1 — Intelligence ✅ (COMPLETED)
- [x] Improved prompts for smarter decisions (compact ASCII grid, resource hints, few-shot examples, `prompts/` template system)
- [x] Structured logging (markdown `sim_logger.py`; structlog JSON planned for later in Phase 1)
- [x] Short and long-term memory (episodic + semantic)
- [x] Improved innovation system with robust validation (`requires` prerequisites, effect bounds, categories, redundancy via LLM prompt — see DEC-011)
- [x] Unit and integration tests (MockLLM) — `test_audit`, `test_memory`, `test_day_cycle`, `test_innovation` (20 tests)
- [x] Precedent persistence (JSON save/load) — (DEC-013)
- **Context**: `01-architecture/`, `03-agents/`, `05-llm-integration/`

### PHASE 2 — Survival Depth ✅ (COMPLETED)
- [x] Day/night cycle with effects on agents (1 tick=1 hour, 3 periods, vision reduction, night energy ×1.5 — see DEC-010)
- [x] Resource regeneration (trees give fruit periodically) — see DEC-015
- [x] New tile types and resources (stone, rivers, caves) — see DEC-016
- [x] Object inventory for agents (see DEC-017)
- [x] Basic crafting as an innovatable action (see DEC-018)
- [x] Rethink agent and oracle prompts to incorporate new world complexity
- [x] Logging updates to assess new mechanics visually (see DEC-019)
- **Context**: `02-world/`, `06-innovation-system/`

### PHASE 3 — Social
- [ ] Personality system (courage, curiosity, patience) — individual behavioral traits
- [ ] Sociability trait as bridge between personality and social behaviors
- [ ] Perception of other agents
- [ ] Communication (speak, signal)
- [ ] Cooperation (share food, build together)
- [ ] Conflict (compete for resources)
- [ ] Knowledge transmission (teach innovations)
- [ ] Reputation and relationships
- [ ] Social memory (who did what to whom)
- **Context**: `07-interaction/`

### PHASE 4 — Culture & Evolution
- [ ] Emergent language between agents
- [ ] Reproduction and inheritance (traits, base memory)
- [ ] Generations and lineage
- [ ] Emergent roles (gatherer, explorer, builder)
- [ ] Settlements and territory
- [ ] Natural selection by fitness
- **Context**: `08-evolution/`

### PHASE 5 — Visualization & Analysis
- [ ] Web dashboard with real-time 2D grid
- [ ] Agent stats charts
- [ ] Simulation replay
- [ ] Activity heatmaps
- [ ] Genealogical tree
- [ ] Video export
- **Context**: `09-visualization/`

### PHASE 6 — Future Work
- [ ] Weather (rain, drought) affecting resources
- **Context**: `02-world/`

---

## Tech Stack

| Component         | Technology              | Reason                             |
|-------------------|-------------------------|------------------------------------|
| Core              | Python 3.12+            | ML ecosystem, fast dev             |
| LLM               | Ollama (Qwen 3.5-4B)   | Local, free, fast                  |
| Future LLM        | Claude API / OpenAI     | When we need more capacity         |
| Testing           | pytest + hypothesis     | Property-based testing for sim     |
| Logging           | `sim_logger.py` (markdown per-run); structlog (JSON lines) planned | Parseable, queryable |
| Visualization     | FastAPI + React/Pixi.js | When we reach Phase 5              |
| CI/CD             | GitHub Actions          | Automatic tests on each PR         |
| Data              | SQLite → PostgreSQL     | To persist simulations             |

---

## Rules for Claude Code

Any Claude Code session working on this project MUST:

1. **Read first** the MASTER_PLAN.md and the relevant section context.
2. **Don't break existing tests** — run `pytest` before committing.
3. **Follow the current phase** — don't implement features from future phases.
4. **Document decisions** in the relevant context if there's ambiguity.
5. **One PR = one feature** — atomic changes, not massive refactors.

---

## Success Metrics per Phase

| Phase | Metric                                                     |
|-------|-------------------------------------------------------------|
| 0     | Simulation runs 100 ticks without crash                     |
| 1     | Agents make coherent decisions >80% of the time             |
| 2     | Agents survive >50 ticks on average with active weather     |
| 3     | Agents cooperate spontaneously at least once in 100 ticks   |
| 4     | At least 1 differentiated role emerges without programming  |
| 5     | Dashboard shows simulation in real-time without lag         |

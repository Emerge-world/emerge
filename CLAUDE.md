# CLAUDE.md

## Project: Emerge — Life Simulation with Autonomous LLM Agents

### What is this?

A simulation where human-like agents controlled by LLMs (Qwen 2.5-3B via Ollama) try to survive in a 2D world. Agents eat, rest, move, and can innovate entirely new actions. An Oracle validates everything and maintains world consistency through precedents.

### Knowledge Base

**READ BEFORE CODING.** The `project-bible/` directory contains everything you need:

```
project-bible/
├── 00-master-plan/
│   ├── MASTER_PLAN.md          ← START HERE. Roadmap, phases, metrics.
│   └── DECISION_LOG.md         ← Architectural decisions. Add new ones here.
├── 01-architecture/CONTEXT.md  ← System diagram, tick lifecycle, module contracts, invariants.
├── 02-world/CONTEXT.md         ← Grid system, resources, weather/day-night plans.
├── 03-agents/CONTEXT.md        ← Memory, personality, prompts, stats.
├── 04-oracle/CONTEXT.md        ← Validation, precedents, determinism rules.
├── 05-llm-integration/CONTEXT.md ← Ollama, prompts, optimization, model upgrade path.
├── 06-innovation-system/CONTEXT.md ← How agents invent new actions, crafting plans.
├── 07-interaction/CONTEXT.md   ← Social features (Phase 3, don't implement yet).
├── 08-evolution/CONTEXT.md     ← Reproduction, generations (Phase 4, don't implement yet).
├── 09-visualization/CONTEXT.md ← Dashboard plans (Phase 5, don't implement yet).
├── 10-testing/CONTEXT.md       ← Testing strategy, MockLLM, layers.
├── 11-devops/CONTEXT.md        ← CI/CD, logging, environment setup.
└── 12-tooling/CONTEXT.md       ← When to use Claude Code vs Project, automations.
```

### Current Phase: Phase 1 — Intelligence

**Focus areas (in order):**
1. Dual memory system (episodic + semantic)
2. Personality traits for agents
3. Prompt optimization (compact grid, few-shot examples)
4. Structured logging (structlog, JSON lines)
5. Unit + integration tests with MockLLM
6. Precedent persistence (save/load JSON)

**DO NOT implement:** social interaction, evolution, visualization, weather — these are future phases.

### Quick Commands

```bash
# Smoke test (no LLM needed)
python main.py --no-llm --ticks 5 --agents 1

# Full test with LLM
python main.py --agents 3 --ticks 30 --seed 42

# Run tests
pytest -m "not slow"

# Run with verbose logging
python main.py --agents 3 --ticks 10 --verbose --save-log --save-state
```

### Hard Rules

1. **Tests pass before commit.** Always run `pytest -m "not slow"`.
2. **LLM never crashes the system.** Every LLM call has a fallback. Every JSON parse has try/except.
3. **Stats are always clamped.** Life, hunger, energy: always between 0 and max.
4. **Dead agents never act.** Check `agent.alive` before every operation.
5. **Oracle is deterministic.** Same input → same output. Use precedents.
6. **Prompts in English.** Qwen 2.5-3B performs significantly better in English.
7. **One feature per PR.** Atomic changes, never massive refactors.
8. **Update the bible.** If you make a design decision, add it to DECISION_LOG.md.

# CLAUDE.md

## Project: Emerge — Life Simulation with Autonomous LLM Agents

### What is this?

A simulation where human-like agents controlled by LLMs (via vLLM) try to survive in a 2D world. Agents eat, rest, move, and can innovate entirely new actions. An Oracle validates everything and maintains world consistency through precedents.

### Knowledge Base

**READ BEFORE CODING.** The `project-cornerstone/` directory contains everything you need. Start with `MASTER_PLAN.md` for current phase status and priorities.

```
project-cornerstone/
├── 00-master-plan/
│   ├── MASTER_PLAN.md                          ← START HERE. Roadmap, phases, metrics.
│   └── DECISION_LOG.md                         ← Architectural decisions. Add new ones here.
├── 01-architecture/architecture_context.md     ← System diagram, tick lifecycle, module contracts, invariants.
├── 02-world/world_context.md                   ← Grid system, resources, weather/day-night plans.
├── 03-agents/agents_context.md                 ← Memory, personality, prompts, stats.
├── 04-oracle/oracle_context.md                 ← Validation, precedents, determinism rules.
├── 05-llm-integration/llm-integration_context.md ← vLLM, prompts, optimization, model upgrade path.
├── 06-innovation-system/innovation-system_context.md ← How agents invent new actions, crafting plans.
├── 07-interaction/interaction_context.md       ← Social features.
├── 08-evolution/evolution_context.md           ← Reproduction, generations.
├── 09-visualization/visualization_context.md   ← Dashboard and replay plans.
├── 10-testing/testing_context.md               ← Testing strategy, MockLLM, layers.
├── 11-devops/devops_context.md                 ← CI/CD, logging, environment setup.
└── 12-tooling/tooling_context.md               ← When to use Claude Code vs Project, automations.
```

### Quick Commands

```bash
# Smoke test (no LLM needed)
uv run main.py --no-llm --ticks 5 --agents 1

# Full test with LLM
uv run main.py --agents 3 --ticks 30 --seed 42

# Run tests
uv run pytest -m "not slow"

# Run with verbose logging
uv run main.py --agents 3 --ticks 10 --verbose --save-log --save-state

# Generate devlog post after merging a PR (run before starting next feature)
/blog         # most recent merged PR
/blog 11      # specific PR number
```

### Hard Rules

1. **Tests pass before commit.** Always run `uv run pytest -m "not slow"`.
2. **LLM never crashes the system.** Every LLM call has a fallback. Every JSON parse has try/except.
3. **Stats are always clamped.** Life, hunger, energy: always between 0 and max.
4. **Dead agents never act.** Check `agent.alive` before every operation.
5. **Oracle is deterministic.** Same input → same output. Use precedents.
6. **Update the cornerstone.** If you make a design decision, add it to DECISION_LOG.md and update the context files for any modified domain.
7. **Always develop in worktrees.** Keep `main` clean and stable. Use `git worktree` for feature branches.
8. **Keep the metrics updated.** If you add or change a feature, update relevant metrics in the code and MASTER_PLAN.md.

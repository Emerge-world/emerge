# 12 — Tooling, Workflows & Fail-safes

## When to use which tool

### Claude Code (CLI agent)

Use for **concrete implementation tasks** that touch code:

| Task                                                | Example command                               |
|-----------------------------------------------------|---------------------------------------------------|
| Implement new feature                               | "Implement dual memory system per 03-agents/agents_context.md" |
| Refactor module                                     | "Split oracle.py into oracle.py + precedents.py"  |
| Write tests                                         | "Write unit tests for world.py, see 10-testing/testing_context.md" |
| Fix a bug                                          | "Agents keep moving to water tiles, fix walkability check" |
| Add dependency and configure                        | "Add structlog, configure JSON logging per 11-devops/devops_context.md" |
| Code review                                         | "Review this PR for issues, run tests"            |
| Optimize performance                                | "Parallelize agent decisions with ThreadPool"     |
| Migrate/update                                      | "Upgrade LLM client to support Anthropic API"     |

**Golden rule**: If the output is **code that goes into a commit**, use Claude Code.

**Tips para Claude Code en este proyecto:**
```bash
# Siempre iniciar sesiones con contexto:
claude "Read project-cornerstone/00-master-plan/MASTER_PLAN.md and
        project-cornerstone/01-architecture/architecture_context.md.
        Then implement X."

# Para features grandes, dar el contexto específico:
claude "Read project-cornerstone/03-agents/agents_context.md section 'Sistema de memoria dual'.
        Implement the Memory class. Write tests. Run them."

# Para bugs, dar logs:
claude "Here's the error log: [paste].
        Read project-cornerstone/04-oracle/oracle_context.md and fix the precedent key collision."
```

### Claude Project (claude.ai con knowledge base)

Use for **planning, design, and decisions** that don't directly touch code:

| Task                                                 | Why Project                                  |
|------------------------------------------------------|----------------------------------------------|
| Design a new feature                                 | Needs back-and-forth, exploring options      |
| Define the format of a new module                    | Design before implementation                 |
| Debate technical trade-offs                          | "SQLite or PostgreSQL for persistence?"      |
| Update project-cornerstone documents                       | Narrative context, not code                  |
| Prompt engineering for agents/oracle                 | Fast iteration, see outputs, adjust          |
| Analyze simulation logs and extract insights         | Upload logs, ask for analysis                |
| Plan the next phase                                  | Refine roadmap with real data                |
| Onboard new contributor                              | Explain project, answer questions            |

**Golden rule**: If the output is **knowledge, decisions, or documents**, use Claude Project.

**Setup del Project:**
1. Crear proyecto "Emerge — Life Simulation" en claude.ai
2. Subir todo el `project-cornerstone/` como knowledge base
3. Subir el código fuente actual
4. Custom instructions: "You are a co-founder building Emerge. Always reference the project-cornerstone when answering. Suggest updating context docs when decisions are made."

### Typical combo (daily workflow)

```
1. [Project] "I want to implement the day/night cycle. How should it affect agents?"
   → Discussion, design, update of 02-world/world_context.md

2. [Project] "Write detailed specs for Claude Code to implement"
   → Output: clear specs with format, invariants, expected tests

3. [Claude Code] "Read project-cornerstone/02-world/world_context.md section 'Day/night cycle'.
                   Implement the day/night cycle. Write tests. Run them."
   → Implementation, tests, commit

4. [Project] "Here are logs from 50 ticks with day/night. Do agents behave well?"
   → Analysis, adjustments, iteration

5. [Claude Code] "Adjust night vision penalty from -2 to -1, 
                   agents are dying too fast at night"
   → Quick fix, commit
```

---

## Devlog System

After every merged PR, generate a developer diary post using the `/blog` Claude Code skill.

### Invoke

```bash
/blog          # generates post for the most recent merged PR
/blog 11       # generates post for a specific PR number
```

### What it does

The skill reads the git diff, commit log, and relevant `project-cornerstone/` context files, then writes a first-person English diary entry to `blog/posts/YYYY-MM-DD-<slug>.md`. The post covers:
- **What I built** — the feature in plain language
- **Why it matters** — connection to Emerge's vision
- **Things to consider** — open questions and implications
- **What's next** — reflection on what this opens up

### Standard

Run `/blog` **before starting the next feature** after a PR is merged. Commit the post with:

```bash
git add blog/posts/<filename>.md
git commit -m "docs(blog): add devlog post for PR #N"
```

Posts live in `blog/posts/`. Serve locally with Quartz:

```bash
cd blog && npx quartz create && npx quartz build --serve
```

### Skill file

`~/.claude/skills/blog/SKILL.md` — globally available in Claude Code.

---

## Recommended automations

### 1. Simulation Runner (script)

```python
#!/usr/bin/env python3
"""run_batch.py — Runs N simulations and generates report."""

import subprocess
import json
import statistics

RUNS = 10
TICKS = 50
AGENTS = 3
SEED_BASE = 100

results = []
for i in range(RUNS):
    seed = SEED_BASE + i
    cmd = f"python main.py --agents {AGENTS} --ticks {TICKS} --seed {seed} --save-state --no-llm"
    subprocess.run(cmd, shell=True)
    
    with open("world_state.json") as f:
        state = json.load(f)
    results.append(state)

# Analysis
alive_counts = [sum(1 for a in r["agents"] if a["alive"]) for r in results]
print(f"Survival rate: {statistics.mean(alive_counts)}/{AGENTS}")
print(f"Min: {min(alive_counts)}, Max: {max(alive_counts)}")
```

### 2. Prompt Evaluator (script)

```python
"""eval_prompts.py — Evaluates LLM decision quality."""

# Runs simulation, analyzes decisions, scores coherence.
# Criteria:
#   - Did it eat when hunger > 50 and food available? (+1)
#   - Did it rest when energy < 20? (+1)
#   - Did it try to eat without nearby food? (-1)
#   - Did it move toward food when hunger > 30? (+1)
#   - Did it innovate something useful? (+2)
#   - Did it innovate something absurd? (-2)
```

### 3. Regression Watcher (CI)

```yaml
# In CI: compare simulation metrics before/after each PR
# If survival rate drops >20%, automatic flag
# Save baselines in data/baselines/
```

### 4. Log Analyzer (claude.ai automation)

```
Monthly workflow:
1. Collect logs from the last 50 simulations
2. Upload to Claude Project
3. Ask: "Analyze patterns, anomalies, and suggest improvements"
4. Update project-cornerstone with findings
```

---

## Fail-safes

### Against the LLM

| Risk                            | Mitigation                                          |
|---------------------------------|-----------------------------------------------------|
| Ollama down                     | Automatic fallback to simple rules                  |
| Invalid JSON                    | 5 parsing layers (see 05-llm-integration/llm-integration_context.md)|
| Non-existent action             | Oracle rejects, agent receives feedback             |
| Absurd action approved          | Effect bounds on innovations, behavioral tests      |
| Prompt too long                 | Token counting, truncate memory if necessary        |
| Model hallucinating             | Low temperature for oracle, post-LLM validation     |
| Model very slow                 | 120s timeout, retry once, then fallback             |

### Against simulation bugs

| Risk                            | Mitigation                                          |
|---------------------------------|-----------------------------------------------------|
| Stats out of range              | Clamp in ALL modify_*() methods                     |
| Agent on invalid tile           | Validate position after each move                   |
| Infinite tick loop              | Explicit `infinite` support; runs still stop on extinction or user interruption |
| Negative resources              | Clamp in consume_resource()                         |
| World with no walkable tiles    | find_spawn_point() with exhaustive fallback         |
| Cascade death                   | OK — it's emergent. Just monitor                    |

### Against data loss

| Risk                            | Mitigation                                          |
|---------------------------------|-----------------------------------------------------|
| Crash mid-simulation            | Auto-save state every 10 ticks                      |
| Lost precedents                 | Save to disk after each new precedent               |
| Deleted logs                    | Log rotation, save last 100 simulations             |
| Corrupt world                   | Validation when loading JSON, regenerate if invalid |

---

## Additional skills to integrate

### MCP Servers (if using Claude Code with MCP)

```json
{
    "mcpServers": {
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/emerge"]
        },
        "github": {
            "command": "npx", 
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": { "GITHUB_TOKEN": "..." }
        }
    }
}
```

### Herramientas complementarias

| Herramienta         | Para qué                                    | Cuándo integrar |
|---------------------|----------------------------------------------|-----------------|
| **Weights & Biases** | Tracking simulation metrics                 | Phase 1         |
| **DVC**              | Simulation data versioning                  | Phase 2         |
| **Grafana + Loki**   | Real-time log dashboards                    | Phase 5         |
| **Ollama Modelfile** | Custom system prompt baked into model       | Phase 1         |
| **LiteLLM**         | Unified multi-provider LLM proxy            | Phase 2         |

### Claude Code CLAUDE.md (poner en raíz del repo)

```markdown
# CLAUDE.md

## Project: Emerge — Life Simulation with LLM Agents

### Quick Reference
- Read `project-cornerstone/00-master-plan/MASTER_PLAN.md` for full context
- Current phase: Phase 1 (Intelligence)
- Run tests: `pytest -m "not slow"`
- Run simulation: `python main.py --no-llm --ticks 5` (smoke test)
- Run with LLM: `python main.py --agents 3 --ticks 30`

### Architecture
- Entry: `main.py`
- Core: `simulation/` package
- Knowledge base: `project-cornerstone/`
- Tests: `tests/`

### Rules
1. Always run tests before committing
2. Don't implement features from future phases
3. Update relevant context docs when making design decisions
4. JSON from LLM must NEVER crash the system — always have fallbacks
5. Prompts are in English (better for small models)

### Current Priorities
1. Dual memory system (episodic + semantic)
2. Personality traits
3. Structured logging
4. Unit + integration tests
5. Prompt optimization for Qwen 2.5-3B
```

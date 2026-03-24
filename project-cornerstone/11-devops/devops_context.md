# 11 — DevOps & Environment

## Development Environment

### Requirements
```
Python 3.12+
uv (package manager — replaces pip/venv)
Git
Optional: reachable OpenAI-compatible LLM endpoint if not running with --no-llm
Optional: Weights & Biases account if using --wandb
```

### Setup

```bash
# 1. Clone repo
git clone <repo-url> && cd emerge

# 2. Install uv if not present
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Run (uv manages the virtualenv automatically from pyproject.toml)
uv run main.py --no-llm --ticks 5 --agents 1

# 4. Full run with LLM (requires configured OpenAI-compatible endpoint)
uv run main.py --ticks 5 --agents 1

# Add a runtime dependency
uv add <package>

# Add a dev dependency
uv add --dev <package>
```

> **Note**: There is no `requirements.txt`. All dependencies are declared in `pyproject.toml` and locked in `uv.lock`.

### pyproject.toml dependencies (current)

```toml
# Runtime
openai>=1.0.0
fastapi[standard]>=0.115
uvicorn[standard]>=0.32
opensimplex>=0.4
wandb>=0.25.0

# Dev
pytest>=9.0.2
```

## Git Workflow

### Branching

```
main          ← always stable, tests passing
├── dev       ← integration, tests passing
│   ├── feat/memory-dual      ← feature branches
│   ├── feat/perlin-worldgen
│   ├── fix/json-parsing
│   └── refactor/oracle-split
```

### Commit Messages

```
feat: add dual memory system (episodic + semantic)
fix: handle invalid JSON from LLM gracefully
refactor: split oracle into oracle + precedents
test: add behavioral tests for agent decisions
docs: update innovation system context
perf: parallelize agent decisions with ThreadPool
```

### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    hooks:
      - id: ruff
      - id: ruff-format
  - repo: local
    hooks:
      - id: pytest-fast
        name: Run fast tests
        entry: uv run pytest -m "not slow" --tb=short -q
        language: system
        pass_filenames: false
```

## CI/CD (GitHub Actions)

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install uv
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pytest -m "not slow" --cov=simulation --cov-fail-under=70
```

## Monitoring & Logging

### Current artifacts

Two output layers exist today:

1. Canonical run artifacts under `data/runs/<run_id>/`
2. Human-readable markdown logs under `logs/sim_<timestamp>/` from `simulation/sim_logger.py`

Canonical run directory:
```
data/runs/<run_id>/
├── meta.json
├── events.jsonl
├── blobs/
│   ├── prompts/
│   └── llm_raw/
├── metrics/
│   ├── summary.json
│   ├── timeseries.jsonl
│   └── ebs.json
└── llm_digest/        # when digest generation is enabled
```

`simulation/sim_logger.py` writes human-readable markdown files to `logs/sim_<timestamp>/`. See DEC-006.

```
logs/
└── sim_<timestamp>/
    ├── overview.md        # Config, world summary, agent roster, final summary
    ├── tick_0001.md       # Per-tick summary (all agents, actions, results)
    ├── agents/
    │   └── Ada.md         # Per-agent log (all decisions across ticks)
    └── oracle.md          # Per-oracle-call log (input, precedent hit/miss, result)
```

Enable with `--save-log` flag: `uv run main.py --save-log --ticks 30 --agents 3`

## Considerations for Claude Code

- Never break `uv run main.py --no-llm` — it's the fastest smoke test.
- LLM prompts and raw responses already persist under `data/runs/<run_id>/blobs/`; use `--save-log` only when you also want the plain-text `simulation_log.txt` export.
- All commands use `uv run` — never call `python` directly.
- Experiment automation should treat `data/runs/<run_id>/metrics/` as canonical input and write separate decision artifacts rather than mutating run artifacts in place.
- Cohort suites and prioritization outputs should be machine-readable first so later dashboards and report plugins can render the same evidence trail.

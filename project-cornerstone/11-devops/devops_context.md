# 11 — DevOps & Environment

## Development Environment

### Requirements
```
Python 3.12+
uv (package manager — replaces pip/venv)
Ollama (with qwen2.5:3b downloaded)
Git
```

### Setup

```bash
# 1. Clone repo
git clone <repo-url> && cd emerge

# 2. Install uv if not present
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Run (uv manages the virtualenv automatically from pyproject.toml)
uv run main.py --no-llm --ticks 5 --agents 1

# 4. Verify Ollama
ollama list  # must show qwen2.5:3b
# If not: ollama pull qwen2.5:3b

# 5. Full run with LLM
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
requests>=2.32.5

# Dev
pytest>=9.0.2
```

### pyproject.toml dependencies (Phase 1+)

```toml
# Runtime additions
structlog>=24.0.0      # Structured JSON logging (planned)
noise>=1.2.2           # Perlin noise for world gen (Phase 2)

# Dev additions
pytest-cov>=5.0.0
ruff>=0.3.0            # Linter + formatter
mypy>=1.8.0            # Type checking
pre-commit>=3.6.0      # Git hooks
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

### Current: Markdown logging (sim_logger.py)

`simulation/sim_logger.py` writes human-readable markdown files to `logs/sim_<timestamp>/`. See DEC-006.

```
logs/
└── sim_<timestamp>/
    ├── tick_001.md        # Per-tick summary (all agents, actions, results)
    ├── agent_Ada.md       # Per-agent log (all decisions across ticks)
    └── oracle_calls.md    # Per-oracle-call log (input, precedent hit/miss, result)
```

Enable with `--save-log` flag: `uv run main.py --save-log --ticks 30 --agents 3`

### Planned: structlog JSON lines (Phase 1)

Once core behavior is stable, `sim_logger.py` will be supplemented or replaced with structlog JSON lines for machine-parseability:

```python
import structlog
logger = structlog.get_logger()

logger.info("agent_action",
    agent="Ada",
    action="move",
    from_pos=(4, 3),
    to_pos=(5, 3),
    tick=42,
    energy=85
)
# Output: {"event":"agent_action","agent":"Ada","action":"move","from_pos":[4,3],"to_pos":[5,3],"tick":42,"energy":85,"timestamp":"..."}
```

Target log files (JSON lines format):
```
data/logs/
├── sim_{timestamp}_events.jsonl    # World events
├── sim_{timestamp}_decisions.jsonl # LLM decisions with prompts/responses
└── sim_{timestamp}_console.log     # Console output
```

## Considerations for Claude Code

- The first PR of Phase 1 should be: `pyproject.toml` dev deps + pytest setup + pre-commit + CI/CD.
- Never break `uv run main.py --no-llm` — it's the fastest smoke test.
- LLM logs (prompts + responses) are gold for debugging. Save them with `--save-log`.
- All commands use `uv run` — never call `python` directly.
- Experiment automation should treat `data/runs/<run_id>/metrics/` as canonical input and write separate decision artifacts rather than mutating run artifacts in place.
- Cohort suites and prioritization outputs should be machine-readable first so later dashboards and report plugins can render the same evidence trail.

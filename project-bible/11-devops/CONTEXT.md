# 11 — DevOps & Environment

## Development Environment

### Requirements
```
Python 3.11+
Ollama (with qwen2.5:3b downloaded)
Git
```

### Setup

```bash
# 1. Clone repo
git clone <repo-url> && cd emerge

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Verify Ollama
ollama list  # must show qwen2.5:3b
# If not: ollama pull qwen2.5:3b

# 5. Verify it works
python main.py --no-llm --ticks 5 --agents 1
python main.py --ticks 5 --agents 1  # with Ollama
```

### requirements.txt (current)

```
requests>=2.31.0
```

### requirements.txt (Phase 1+)

```
requests>=2.31.0
structlog>=24.0.0
pytest>=8.0.0
pytest-cov>=5.0.0
hypothesis>=6.100.0
noise>=1.2.2           # Perlin noise for world gen
pydantic>=2.5.0        # Data validation
```

### requirements-dev.txt

```
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
        entry: pytest -m "not slow" --tb=short -q
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
          python-version: '3.11'
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: ruff check .
      - run: ruff format --check .
      - run: pytest -m "not slow" --cov=simulation --cov-fail-under=70
```

## Monitoring & Logging

### Structured Logging (Phase 1)

```python
import structlog

logger = structlog.get_logger()

# Instead of:
logger.info(f"Agent Ada moved to (5, 3)")

# Use:
logger.info("agent_action", 
    agent="Ada", 
    action="move", 
    from_pos=(4, 3), 
    to_pos=(5, 3),
    tick=42,
    energy=85
)

# Output (JSON lines):
# {"event":"agent_action","agent":"Ada","action":"move","from_pos":[4,3],"to_pos":[5,3],"tick":42,"energy":85,"timestamp":"2026-02-27T14:30:00"}
```

### Log Files

```
data/logs/
├── sim_{timestamp}_events.jsonl    # World events (JSON lines)
├── sim_{timestamp}_decisions.jsonl # LLM decisions with prompts/responses
├── sim_{timestamp}_console.log     # Console output
```

## Considerations for Claude Code

- The first PR of Phase 1 should be: requirements.txt + pytest + pre-commit + CI/CD.
- Never break `python main.py --no-llm` — it's the fastest smoke test.
- LLM logs (prompts + responses) are gold for debugging. Save them always.

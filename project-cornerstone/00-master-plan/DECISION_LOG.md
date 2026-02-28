# Decision Log

> Log of important technical decisions. Each entry is immutable once written.

## Format

```
### DEC-XXX: Title
- **Date**: YYYY-MM-DD
- **Context**: Why the decision arose
- **Decision**: What we decided
- **Rejected alternatives**: What else we considered
- **Consequences**: What this decision implies
```

---

### DEC-001: Initial LLM model
- **Date**: 2026-02-27
- **Context**: We need a model that runs locally, fast, and handles JSON.
- **Decision**: Qwen 2.5-3B via Ollama.
- **Rejected alternatives**: Llama 3 8B (too slow for 5 agents), Phi-3 (worse at JSON), GPT-4 API (cost).
- **Consequences**: Prompts must be concise. Responses in English. JSON parsing must be robust with fallbacks.

### DEC-002: Centralized oracle architecture
- **Date**: 2026-02-27
- **Context**: We need a consistent arbiter for actions.
- **Decision**: A central oracle with its own LLM + precedent system (dict in-memory).
- **Rejected alternatives**: Hardcoded rules (limits innovation), consensus between agents (too complex).
- **Consequences**: The oracle is a single point of failure. If its LLM fails, the entire simulation fails. Add deterministic fallbacks.

### DEC-003: Memory as list of strings
- **Date**: 2026-02-27
- **Context**: Agents need to remember what they've done.
- **Decision**: Simple list of strings with cap of 50 entries, FIFO.
- **Rejected alternatives**: Database per agent (overengineering), embeddings + RAG (Phase 1+).
- **Consequences**: Memory is volatile (lost between executions). In Phase 1 it must be persisted. The cap of 50 may be insufficient — monitor.

### DEC-005: Template-based prompt system
- **Date**: 2026-02-28
- **Context**: Prompt text was embedded directly in Python source, making iteration and experimentation slow.
- **Decision**: Prompts stored as `prompts/<module>/<name>.txt` with `$variable` substitution via `string.Template`. Loaded and cached by `simulation/prompt_loader.py`.
- **Rejected alternatives**: Jinja2 templates (unnecessary dependency for simple substitution), f-strings in code (hard to edit without touching logic).
- **Consequences**: All prompt changes require updating template files, not source files. `prompt_loader.py` caches templates on first load to avoid repeated disk reads.

### DEC-006: Markdown-based simulation logging (sim_logger.py)
- **Date**: 2026-02-28
- **Context**: structlog JSON lines were planned, but during early development a human-readable format was more valuable for manual inspection.
- **Decision**: Use custom `simulation/sim_logger.py` writing human-readable markdown files (per-tick, per-agent, per-oracle-call) to `logs/sim_<timestamp>/`.
- **Rejected alternatives**: structlog JSON lines (machine-parseable but hard to read during debugging), Python `logging` module (no structure).
- **Consequences**: Logs are not machine-parseable. Transition to structlog JSON is planned as a Phase 1 milestone once core behavior is stable.

### DEC-007: uv as package manager
- **Date**: 2026-02-28
- **Context**: Standard `pip`/`venv` workflow requires manual virtualenv management and doesn't provide a lock file by default.
- **Decision**: Use `uv` (not `pip`/`venv`) for all dependency management. Lock file via `uv.lock`. All execution via `uv run`.
- **Rejected alternatives**: `pip` + `venv` (slower installs, no lockfile), `poetry` (heavy), `conda` (overkill for this project).
- **Consequences**: All commands must be prefixed `uv run`. New runtime deps added via `uv add <pkg>`. Dev deps via `uv add --dev <pkg>`. `requirements.txt` is not used; `pyproject.toml` is the single source of truth.

### DEC-004: Oracle physical reflection replaces hardcoded base-action rules
- **Date**: 2026-02-27
- **Context**: Agents were inventing actions (like diagonal movement) that the Oracle rejected programmatically without ever consulting its own LLM reasoning. The Oracle should embody world physics, not hardcode them.
- **Decision**: Remove hardcoded programmatic rules from base actions (move, eat, rest). All actions route through `_oracle_reflect_physical()`: the Oracle's LLM reasons about physical plausibility once per novel situation, then caches the result as a precedent. Move now supports all 8 compass directions (N/NE/E/SE/S/SW/W/NW).
- **Rejected alternatives**: Keep hardcoded rules but add diagonal support (doesn't fix the architectural inconsistency; Oracle bypasses its own reasoning).
- **Consequences**: ~4-6 new LLM calls on first run (one per tile type / action context). After warm-up, all base-action resolution is precedent-driven (no additional LLM calls). Fallback defaults apply when LLM is unavailable.

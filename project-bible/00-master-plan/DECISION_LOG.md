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

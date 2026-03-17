# 05 — LLM Integration (Codebase-Aligned)

## Current implementation

- Main client: `simulation/llm_client.py`
- Config defaults target OpenAI-compatible vLLM endpoint (`VLLM_BASE_URL` + `VLLM_MODEL`).
- Structured responses are used for agent decisions and oracle validations.
- Structured schemas cap free-text fields so decision/planner calls stay compact and are less likely to emit truncated JSON.
- Agent decision structured output now uses conditional JSON Schema rules (`if`/`then`) so built-in actions require their action-specific fields while custom approved innovations remain schema-compatible.
- Callers can override `max_tokens`, and high-frequency decision/planner/oracle calls use smaller per-call budgets than the global default.
- Fallback behavior is present when parsing/LLM calls fail.
- When `generate_structured()` is called with `AgentDecisionResponse` and Pydantic validation fails solely because `reason` exceeds 240 characters, the client truncates `reason` deterministically and re-validates. The repaired decision is returned normally (`parse_ok=True`). Successful repairs emit a `WARNING` log and write `repaired_reason_too_long`, `repaired_fields`, and `original_reason_length` into `last_call`. All other validation failures, malformed JSON, and truncated responses continue to return `None`.

## Prompt system

- Prompt templates are file-based under `prompts/agent` and `prompts/oracle`.
- `simulation/prompt_loader.py` handles template loading/caching.
- Agent prompts include memory, perception, relationships, and family context.
- The agent system prompt must stay aligned with built-in action examples because missing example fields now invalidate the response at the schema boundary.

## Traceability

- `EventEmitter` stores rendered prompts and raw LLM responses under run blobs.
- This enables post-hoc debugging and metrics correlation without re-running simulations.

## Near-term improvements

1. Explicit provider abstraction (vLLM, Ollama, hosted APIs)
2. Per-call retry/backoff policies with structured error taxonomy
3. Prompt version tagging in run metadata for experiment analysis

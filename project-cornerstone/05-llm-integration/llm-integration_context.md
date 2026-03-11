# 05 — LLM Integration (Codebase-Aligned)

## Current implementation

- Main client: `simulation/llm_client.py`
- Config defaults target OpenAI-compatible vLLM endpoint (`VLLM_BASE_URL` + `VLLM_MODEL`).
- Structured responses are used for agent decisions and oracle validations.
- Fallback behavior is present when parsing/LLM calls fail.

## Prompt system

- Prompt templates are file-based under `prompts/agent` and `prompts/oracle`.
- `simulation/prompt_loader.py` handles template loading/caching.
- Agent prompts include memory, perception, relationships, and family context.

## Traceability

- `EventEmitter` stores rendered prompts and raw LLM responses under run blobs.
- This enables post-hoc debugging and metrics correlation without re-running simulations.

## Near-term improvements

1. Explicit provider abstraction (vLLM, Ollama, hosted APIs)
2. Per-call retry/backoff policies with structured error taxonomy
3. Prompt version tagging in run metadata for experiment analysis

# 10 — Testing Strategy (Codebase-Aligned)

## Current status

The repository already has broad pytest coverage across core systems, including:

- world generation/regeneration/day cycle
- memory, personality, perception prompts
- oracle behavior (innovation, pickup, tile effects, persistence)
- social actions (communication, trust, give_item, teach)
- reproduction/generational logic
- event emitter, metrics builder, run_batch, W&B logger

See `tests/` for concrete files (e.g., `test_reproduction.py`, `test_event_emitter.py`, `test_metrics_builder.py`).

## Testing layers in practice

1. **Deterministic unit tests** for pure logic and validators.
2. **Integration tests with mocked LLM behavior** for decision/oracle flows.
3. **Optional live-model runs** outside default fast suite.

## Recommended additions

- Deterministic replay test: rebuild state from events and compare final snapshot.
- Contract tests for websocket payload schemas (`init`, `tick`, `control`).
- Golden-run regression fixtures for selected seeds and configs.

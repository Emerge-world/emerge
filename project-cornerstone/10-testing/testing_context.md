# 10 — Testing Strategy (Codebase-Aligned)

## Current status

The repository already has broad pytest coverage across core systems, including:

- world generation/regeneration/day cycle
- scarcity config application and benchmark suite validation
- memory, personality, perception prompts
- oracle behavior (innovation, pickup, tile effects, persistence)
- social actions (communication, trust, give_item, teach)
- reproduction/generational logic
- event emitter, metrics builder, scarcity metrics, benchmark reporting, run_batch, W&B logger

See `tests/` for concrete files (e.g., `test_reproduction.py`, `test_event_emitter.py`, `test_metrics_builder.py`).

## Testing layers in practice

1. **Deterministic unit tests** for pure logic and validators.
2. **Integration tests with mocked LLM behavior** for decision/oracle flows.
3. **Benchmark pipeline tests** for suite parsing, manifest writing, and baseline-vs-candidate aggregation.
4. **Optional live-model runs** outside default fast suite.

## Recommended additions

- Deterministic replay test: rebuild state from events and compare final snapshot.
- Contract tests for websocket payload schemas (`init`, `tick`, `control`).
- Golden-run regression fixtures for selected seeds and configs.
- Golden-decision regression fixtures for experiment gating and prioritization artifacts.
- Unit coverage for cohort aggregation, baseline-vs-candidate comparison, and policy evaluation on synthetic run metrics.
- Small end-to-end benchmark smoke runs that verify `run_benchmark.py` plus `metrics/scarcity.json` generation without requiring live LLM calls.

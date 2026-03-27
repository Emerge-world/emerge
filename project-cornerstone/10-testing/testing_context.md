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
- Runtime-profile regression coverage now lives in `tests/test_runtime_profile_capabilities.py`, which exercises planning-off, semantic-memory-off, innovation-off, item-reflection-off, social-off, teach-off, and reproduction-off backend paths against the real engine/subsystem wiring.
- Prompt-surface regression coverage now lives in `tests/test_prompt_surface.py`, with full rendered executor/planner goldens stored under `tests/golden/prompts/` so prompt wording and capability ablations stay aligned.

## Testing layers in practice

1. **Deterministic unit tests** for pure logic and validators.
2. **Integration tests with mocked LLM behavior** for decision/oracle flows.
3. **Optional live-model runs** outside default fast suite.

## Recommended additions

- Deterministic replay test: rebuild state from events and compare final snapshot.
- Contract tests for `events.jsonl` event schemas so producer and analytics payloads stay aligned.
- Contract tests for websocket payload schemas (`init`, `tick`, `control`).
- Golden-run regression fixtures for selected seeds and configs.
- Golden-decision regression fixtures for experiment gating and prioritization artifacts.
- Unit coverage for cohort aggregation, baseline-vs-candidate comparison, and policy evaluation on synthetic run metrics.

## Item affordance discovery coverage expectations *(DEC-045)*

Coverage currently lives in `tests/test_innovation.py`:

| Area | What to verify |
|---|---|
| Auto-trigger on first craft | Successful crafting of a new item type calls `_discover_item_affordances` exactly once |
| Idempotence | Crafting the same item type a second time does NOT re-trigger discovery |
| Approved derived actions | Validated candidates are added to `agent.actions` with `requires.items` set |
| Manual reflection | `reflect_item_uses` resolves correctly, charges 5 energy, calls discovery |
| Empty inventory guard | `reflect_item_uses` with empty inventory returns success=False without charging energy |
| Tool-aware precedent keys | Custom-action keys for item-derived actions include the tool suffix |
| Event emission | Derived innovations emit `innovation_attempt` / `innovation_validated` with `origin_item`, `discovery_mode`, `trigger_action` fields |
| Discovery failure is non-blocking | LLM error or all-rejected candidates during auto-discovery does not affect crafting result |
| Duplicate candidate handling | Candidate names already in `agent.actions` are silently skipped |

## Canonical seed sets

Use these fixed seeds to keep runs reproducible and comparable across branches.

| Tier | Purpose | Seeds |
|---|---|---|
| **smoke** | Fast sanity check after any change — 2 runs, no LLM needed | `11, 22` |
| **dev** | Regular dev validation — covers 5 world configurations | `101, 202, 303, 404, 505` |
| **eval** | Full evaluation suite — 10 seeds for statistically meaningful results | `1101, 1202, 1303, 1404, 1505, 1606, 1707, 1808, 1909, 2010` |

**When to use each tier:**

- **smoke** — before every commit: `uv run main.py --no-llm --ticks 5 --seed 11` and `--seed 22`.
- **dev** — when iterating on a feature branch; catches regressions across diverse worlds.
- **eval** — before merging to `main` or publishing benchmark numbers; use with `run_batch.py`.

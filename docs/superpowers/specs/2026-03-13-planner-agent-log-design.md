# Planner Agent Log Design

**Date:** 2026-03-13
**Status:** Approved

## Problem

The explicit planning branch can generate long-term plans, but the planner LLM call is not written into the per-simulation markdown logs under `logs/sim_<timestamp>/agents/`. Standard action decisions already include full prompt and response details there, but planner calls remain invisible in the agent log.

## Goal

Make planner LLM calls available in each simulation's per-agent markdown log by appending the full planner call details to `logs/sim_<timestamp>/agents/<Name>.md`.

The logged planner details should include:

- planner system prompt
- planner user prompt
- raw LLM response
- parsed plan that was accepted and converted into `PlanningState`

## Decision

Implement planner logging through the existing hidden planning trace path.

The planner runtime should capture planner-call details, thread them through `_planning_trace`, and let `SimulationEngine` hand them to `SimLogger`, which will append the formatted planner block to the per-agent markdown log.

## Design

### 1. Trace Flow

When `Agent.decide_action()` triggers a replan and `Planner.plan()` returns a new plan, the hidden planning trace should include planner-call details in addition to the existing `plan_created` or `plan_updated` metadata.

That planner trace payload should contain:

- `system_prompt`
- `user_prompt`
- `raw_response`
- `parsed_plan`

This keeps planner logging aligned with the existing action-decision logging architecture, where the engine consumes hidden traces and delegates all file output to `SimLogger`.

### 2. Logging Destination And Format

Planner logs should be written only to the per-agent markdown file:

- `logs/sim_<timestamp>/agents/<Name>.md`

Do not write planner details to:

- `tick_*.md`
- `oracle.md`
- `events.jsonl`

The planner log entry should use the same markdown style as existing decision logs:

- `## Tick NNNN`
- planner subsection title
- `<details>` blocks for system prompt, planner prompt, and raw response
- a rendered parsed-plan block

The parsed-plan block should contain the structured plan that was accepted, not just a summary string.

### 3. Runtime Boundaries

`SimLogger` should gain a dedicated method for planner-call logging.

`SimulationEngine` should call that method only when a planner trace is present for the tick.

`Planner` and `Agent` should not write files directly.

### 4. Error Handling

Planner logging must remain observational only.

If planning is disabled, no replan occurs, or the planner returns `None`, the simulation behavior stays unchanged and no planner log entry is written.

Logging must not create a new failure path for decision-making.

## Testing

Add focused tests that verify:

- a successful replan writes full planner details into `agents/<Name>.md`
- no planner log entry is written when no plan is created

Keep the tests narrow and centered on the current planning/logging flow rather than expanding into unrelated metrics or event-stream changes.

## Out Of Scope

- adding planner entries to `events.jsonl`
- adding planner entries to `tick_*.md`
- changing planner cadence or replanning rules
- changing planner schema or `PlanningState`
- changing oracle logging

## Touch Points

| File | Change |
|---|---|
| `simulation/planner.py` | Expose planner-call trace data needed for logging |
| `simulation/agent.py` | Attach planner trace data to `_planning_trace` when replanning succeeds |
| `simulation/engine.py` | Consume planner trace and forward it to `SimLogger` |
| `simulation/sim_logger.py` | Add planner log writer for `agents/<Name>.md` |
| `tests/` | Add focused coverage for planner logging and the no-log path |

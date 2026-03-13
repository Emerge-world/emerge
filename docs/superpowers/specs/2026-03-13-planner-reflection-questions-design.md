# Planner Reflection Questions Design

**Date:** 2026-03-13
**Status:** Approved

## Problem

The explicit planning branch already has a dedicated planner prompt in `prompts/agent/planner.txt`, but that prompt only gives the model the current observation, the current plan, and relevant memory. It does not explicitly ask the model to reflect on whether its long-term objective still makes sense or whether the plan is making progress.

## Goal

Improve long-term plan quality on `feat/agent-long-term-planning` by adding four reflection questions to the planner prompt:

- What is my long-term goal?
- Am I getting closer to that goal?
- Could I do this more efficiently?
- Do I need to change my goal?

## Decision

Implement this as prompt-only guidance in `prompts/agent/planner.txt`.

The runtime planning flow, JSON schema, and planning state remain unchanged. The planner should consider the questions internally before returning the existing structured plan response.

## Design

### 1. Planner Prompt

Update `prompts/agent/planner.txt` to add a compact reflection block after the existing plan context. The added text should instruct the model to silently consider the four questions and then return the same compact structured plan as before.

The prompt should stay compact. The questions are a planning checklist, not new output fields.

### 2. Runtime Behavior

No code-path changes are required in:

- `simulation/planner.py`
- `simulation/schemas.py`
- `simulation/planning_state.py`
- `simulation/agent.py`
- planning events or metrics

`Planner.plan()` should continue to render the same template, call `generate_structured(...)`, and build `PlanningState` from the same `AgentPlanResponse` schema.

### 3. Error Handling

No error-handling behavior changes.

If the LLM returns invalid output or `None`, the existing planner fallback behavior remains the safety boundary. This change must not introduce any new parsing requirements or failure modes.

## Testing

Add a narrow prompt regression test that renders the planner prompt and asserts that all four questions are present.

This should verify the requested behavior directly without trying to assert on emergent LLM reasoning quality.

## Out Of Scope

- adding new fields to `AgentPlanResponse`
- storing planner reflections in `PlanningState`
- emitting new events or metrics
- changing replanning cadence or heuristics
- modifying executor prompts
- modifying `prompts/agent/planner_system.txt`

## Touch Points

| File | Change |
|---|---|
| `prompts/agent/planner.txt` | Add the four reflection questions as planner guidance |
| `tests/test_planner.py` | Add or update one prompt-focused test that asserts the rendered planner prompt includes the four questions |

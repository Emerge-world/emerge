# Decision Reason Repair Design

**Date:** 2026-03-17
**Status:** Approved

## Problem

`AgentDecisionResponse.reason` is currently capped at 160 characters. The executor prompt now carries enough context that the model occasionally returns an otherwise valid action with a longer explanation. When that happens, Pydantic rejects the entire structured response, `LLMClient.generate_structured()` returns `None`, and the agent falls back to the rule-based policy.

That keeps the simulation alive, but it discards a valid action because of a non-structural explanation field.

## Goal

Preserve valid agent decisions when the only schema violation is an overlong `reason`, while keeping strict validation for malformed JSON and behavior-affecting field errors.

## Decision

Implement a hybrid fix for the executor decision path:

- widen the decision-only `reason` cap from 160 to 240 characters
- keep all other shared `ReasonText` users unchanged
- add a deterministic repair path in `LLMClient.generate_structured()` for `AgentDecisionResponse` only
- repair only the `reason` field when it is the sole validation failure and the failure type is `string_too_long`

All other validation failures continue to return `None` and use the existing agent fallback path.

## Design

### 1. Schema Boundary

Do not broaden the shared `ReasonText` alias globally.

Instead, give `AgentDecisionResponse.reason` its own decision-specific bound at 240 characters. The rest of the structured schemas keep their current limits so oracle and planner envelopes do not silently widen.

The agent system prompt should also be tightened to state the bound explicitly:

`Keep reason under 240 characters and grounded in the immediate situation.`

`DECISION_RESPONSE_MAX_TOKENS` remains unchanged at 256. The reported failure is caused by a field-level limit, not evidence that the full response budget is too small.

### 2. Client Repair Path

Add the repair logic to `simulation/llm_client.py`, where sanitized raw JSON is already converted into a typed model.

Normal flow stays the same:

1. call the OpenAI-compatible endpoint with JSON Schema guidance
2. reject responses with `finish_reason == "length"`
3. sanitize control characters
4. extract the JSON object from the raw content
5. validate against the requested Pydantic model

If validation fails:

- only consider repair when `response_model is AgentDecisionResponse`
- only consider repair when the sanitized payload is valid JSON
- inspect the validation errors and require that:
  - the only failing field is `reason`
  - the failure type is `string_too_long`
- truncate `reason` deterministically to the decision limit
- re-run normal validation once against the repaired payload

If the repaired payload validates, return the typed decision.

If any of the checks fail, return `None` exactly as today.

This repair path must not:

- retry the LLM call
- summarize or rewrite the text semantically
- repair malformed JSON
- repair truncated `finish_reason == "length"` responses
- repair missing action-specific fields such as `direction`, `item`, `quantity`, `target`, or `skill`

This keeps the safety boundary strict for structural errors while salvaging good decisions that only violate the explanation limit.

### 3. Observability

Successful repairs should be visible in logs and the existing LLM trace.

When a decision is salvaged:

- emit a warning log that includes the response model and original `reason` length
- add repair metadata to `self.last_call`, for example:
  - `repaired_reason_too_long: true`
  - `repaired_fields: ["reason"]`
  - `original_reason_length: <n>`

Because the repaired payload is validated successfully, the agent decision should continue through the normal `parse_ok=True` path. This change should not create a new event type or mark the decision as a fallback parse failure.

### 4. Prompt Update

Update `prompts/agent/system.txt` so the instruction matches the new runtime contract:

- keep the existing “reasons brief” guidance
- add the explicit 240-character ceiling for `reason`

This is a supporting guardrail, not the primary enforcement mechanism.

### 5. Tests

Add deterministic unit coverage in `tests/test_llm_client.py`.

Required cases:

- schema cap test now expects `AgentDecisionResponse.reason.maxLength == 240`
- salvage case: valid decision JSON except an overlong `reason` returns a typed `AgentDecisionResponse`, preserves the chosen action, and truncates `reason`
- repair metadata case: salvaged response writes the expected repair keys to `last_call`
- non-repairable validation case: for example `{"action":"move","reason":"ok"}` with no `direction` still returns `None`
- malformed JSON case still returns `None`
- `finish_reason == "length"` case still returns `None`

These tests should stay at the `LLMClient` layer. No new simulation-level integration coverage is required for this change.

## Error Handling

- Overlong `reason` as the only invalid field: repair and continue
- Any other validation error: return `None`
- Malformed JSON: return `None`
- Length-truncated generation: return `None`
- Connection or API exceptions: return `None`

This preserves the current guarantee that the LLM never crashes the simulation.

## What Does Not Change

- planner, oracle, and item-effect reason limits
- `DECISION_RESPONSE_MAX_TOKENS`
- agent fallback policy in `simulation/agent.py`
- event schema and parse-failure accounting for truly invalid responses
- action-specific required-field validation logic

## Documentation Updates During Implementation

The implementation should also update:

- `project-cornerstone/00-master-plan/DECISION_LOG.md` with the runtime repair decision
- `project-cornerstone/05-llm-integration/llm-integration_context.md` so the decision-path salvage behavior is documented

No metric additions are required for this fix.

## Touch Points

| File | Change |
|---|---|
| `simulation/schemas.py` | Add a decision-specific reason bound and apply it to `AgentDecisionResponse.reason` |
| `simulation/llm_client.py` | Add narrow repair logic for overlong decision reasons and trace metadata |
| `prompts/agent/system.txt` | State the 240-character decision-reason limit explicitly |
| `tests/test_llm_client.py` | Add/update unit tests for the new cap, repair success, and non-repair cases |
| `project-cornerstone/00-master-plan/DECISION_LOG.md` | Record the runtime repair decision during implementation |
| `project-cornerstone/05-llm-integration/llm-integration_context.md` | Document the executor decision repair behavior during implementation |

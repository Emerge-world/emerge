# Decision Reason Repair Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Salvage valid `AgentDecisionResponse` objects when the only schema violation is an overlong `reason` field, by widening the decision-specific cap to 240 chars and adding a deterministic truncation repair path in `LLMClient`.

**Architecture:** Add a `DecisionReasonText` alias (max 240) to `schemas.py` and apply it only to `AgentDecisionResponse.reason`. In `llm_client.py`, catch `ValidationError` after `model_validate_json`, check that the sole failure is `reason` being `string_too_long`, truncate deterministically, and re-validate. All other failures return `None` unchanged.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, uv

---

## File Map

| File | Change |
|---|---|
| `simulation/schemas.py` | Add `DecisionReasonText = Annotated[str, Field(max_length=240)]`; change `AgentDecisionResponse.reason` type from `ReasonText` to `DecisionReasonText` |
| `simulation/llm_client.py` | Add `import json`; import `ValidationError` from pydantic; import `AgentDecisionResponse` from schemas; add `_repair_decision_reason()` private method; call it from `generate_structured()` on `ValidationError` |
| `prompts/agent/system.txt` | Append 240-character ceiling instruction to the closing line |
| `tests/test_llm_client.py` | Update `test_decision_schema_caps_reason_length` to expect 240; add five new test cases |
| `project-cornerstone/00-master-plan/DECISION_LOG.md` | Add DEC-044 entry |
| `project-cornerstone/05-llm-integration/llm-integration_context.md` | Document the repair behavior in the "Current implementation" section |

---

## Chunk 1: Schema boundary — widen `AgentDecisionResponse.reason` to 240

### Task 1: Update the schema-cap test to the new limit (failing)

**Files:**
- Modify: `tests/test_llm_client.py:101-104`

- [ ] **Step 1: Update the existing cap test to expect 240**

Change line 104 in `tests/test_llm_client.py`:

```python
def test_decision_schema_caps_reason_length(self):
    schema = AgentDecisionResponse.model_json_schema()

    assert schema["properties"]["reason"]["maxLength"] == 240
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_llm_client.py::TestGenerateStructured::test_decision_schema_caps_reason_length -v
```

Expected: `FAILED — AssertionError: assert 160 == 240`

---

### Task 2: Add `DecisionReasonText` and apply it to `AgentDecisionResponse`

**Files:**
- Modify: `simulation/schemas.py` (text aliases block + `AgentDecisionResponse`)

- [ ] **Step 1: Add the decision-specific alias after `ReasonText`**

> **Important:** `MediumText = Annotated[str, Field(max_length=240)]` already exists in
> `schemas.py`. Do **not** reuse it here. `MediumText` is already shared with planner and
> oracle response models. Using it for `AgentDecisionResponse.reason` would silently widen
> those envelopes — exactly the coupling the spec forbids. `DecisionReasonText` must be a
> distinct, named alias so the boundary is explicit and auditable.

```python
ReasonText = Annotated[str, Field(max_length=160)]
DecisionReasonText = Annotated[str, Field(max_length=240)]
MediumText = Annotated[str, Field(max_length=240)]   # existing — do not remove
```

(Insert `DecisionReasonText` between `ReasonText` and `MediumText`.)

- [ ] **Step 2: Change `AgentDecisionResponse.reason` to use `DecisionReasonText`**

Find the line `reason: ReasonText` inside `AgentDecisionResponse` (search for it — the
line number shifts by one after the insertion in Step 1) and change it to:

```python
reason: DecisionReasonText
```

- [ ] **Step 3: Run the updated cap test**

```bash
uv run pytest tests/test_llm_client.py::TestGenerateStructured::test_decision_schema_caps_reason_length -v
```

Expected: `PASSED`

- [ ] **Step 4: Run the full test suite and verify shared-type isolation**

```bash
uv run pytest -m "not slow" -v
```

Expected: all tests pass, including `test_plan_schema_caps_goal_and_rationale_length` which
asserts `goal.maxLength == 160` and `rationale_summary.maxLength == 240`. That test is the
primary regression guard confirming that `ReasonText` and `MediumText` were not changed.

- [ ] **Step 5: Commit**

```bash
git add simulation/schemas.py tests/test_llm_client.py
git commit -m "feat(schemas): widen AgentDecisionResponse reason cap to 240"
```

---

## Chunk 2: Repair path in `LLMClient`

### Task 3: Add failing tests for repair behavior

**Files:**
- Modify: `tests/test_llm_client.py`

> **Note:** `test_decision_schema_caps_reason_length` (the assertion `maxLength == 240`) was
> already updated in Chunk 1, Task 1. Do not touch it again here.

- [ ] **Step 1: Add `import json` at the top of the test file**

Add after line 5 (`import json`):

```python
import json
```

(It's already present — check line 5. If not present, add it.)

- [ ] **Step 2: Update `_client_with_response` to set `finish_reason` explicitly**

The shared helper currently leaves `finish_reason` as a `MagicMock()`. Update it so
tests don't rely on accidental `MagicMock() != "length"` equality:

```python
def _client_with_response(self, content: str) -> LLMClient:
    client = LLMClient()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = content
    mock_response.choices[0].finish_reason = "stop"
    client._client = MagicMock()
    client._client.chat.completions.create.return_value = mock_response
    return client
```

- [ ] **Step 3: Add the five new test methods to `TestGenerateStructured`**

Append after `test_built_in_action_does_not_fall_back_to_custom_variant` (currently the last test):

```python
def test_salvages_decision_with_overlong_reason(self):
    """Valid decision JSON with a reason that exceeds 240 chars is repaired and returned."""
    long_reason = "x" * 241
    payload = json.dumps({"action": "move", "reason": long_reason, "direction": "north"})
    client = self._client_with_response(payload)

    result = client.generate_structured("prompt", AgentDecisionResponse)

    assert isinstance(result, AgentDecisionResponse)
    assert result.action == "move"
    assert result.direction == "north"
    assert len(result.reason) == 240
    assert result.reason == "x" * 240

def test_repair_writes_metadata_to_last_call(self):
    """When a decision reason is salvaged, repair metadata is written to last_call."""
    long_reason = "y" * 250
    payload = json.dumps({"action": "rest", "reason": long_reason})
    client = self._client_with_response(payload)

    client.generate_structured("prompt", AgentDecisionResponse)

    assert client.last_call.get("repaired_reason_too_long") is True
    assert client.last_call.get("repaired_fields") == ["reason"]
    assert client.last_call.get("original_reason_length") == 250

def test_repair_not_applied_for_missing_required_action_fields(self):
    """A move decision missing direction cannot be repaired even if reason is also long."""
    long_reason = "z" * 241
    payload = json.dumps({"action": "move", "reason": long_reason})  # no direction
    client = self._client_with_response(payload)

    result = client.generate_structured("prompt", AgentDecisionResponse)

    assert result is None

def test_repair_not_applied_to_non_decision_models(self):
    """Overlong reason in PhysicalReflectionResponse is not repaired; returns None."""
    long_reason = "a" * 170  # exceeds ReasonText limit of 160
    payload = json.dumps({"possible": True, "reason": long_reason, "life_damage": 0})
    client = self._client_with_response(payload)

    result = client.generate_structured("prompt", PhysicalReflectionResponse)

    assert result is None

def test_malformed_json_returns_none(self):
    """A response that is not valid JSON returns None."""
    client = self._client_with_response("{not valid json")

    result = client.generate_structured("prompt", AgentDecisionResponse)

    assert result is None
```

- [ ] **Step 4: Run the new tests to verify they all fail (or error)**

```bash
uv run pytest tests/test_llm_client.py::TestGenerateStructured::test_salvages_decision_with_overlong_reason tests/test_llm_client.py::TestGenerateStructured::test_repair_writes_metadata_to_last_call tests/test_llm_client.py::TestGenerateStructured::test_repair_not_applied_for_missing_required_action_fields tests/test_llm_client.py::TestGenerateStructured::test_repair_not_applied_to_non_decision_models tests/test_llm_client.py::TestGenerateStructured::test_malformed_json_returns_none -v
```

Expected:
- `test_salvages_decision_with_overlong_reason` — FAILED (returns `None` today)
- `test_repair_writes_metadata_to_last_call` — FAILED (keys missing)
- `test_repair_not_applied_for_missing_required_action_fields` — PASSED (already returns `None`)
- `test_repair_not_applied_to_non_decision_models` — PASSED (already returns `None`)
- `test_malformed_json_returns_none` — PASSED (already returns `None`)

Note: the last three passing is correct — they describe behaviour that must not regress.

---

### Task 4: Implement the repair path in `LLMClient`

**Files:**
- Modify: `simulation/llm_client.py`

- [ ] **Step 1: Add missing imports at the top of `llm_client.py`**

After `import logging` and `from typing import TypeVar, Type`, add:

```python
import json

from pydantic import BaseModel, ValidationError
```

The file currently imports `from pydantic import BaseModel` — change that line to also import `ValidationError`.

- [ ] **Step 2: Add `AgentDecisionResponse` import**

After the existing simulation imports block, add:

```python
from simulation.schemas import AgentDecisionResponse
```

Full imports block at the top of `llm_client.py` after your changes:

```python
import json
import logging
from typing import TypeVar, Type

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from simulation.config import (
    VLLM_BASE_URL,
    VLLM_MODEL,
    VLLM_API_KEY,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
)
from simulation.schemas import AgentDecisionResponse
```

- [ ] **Step 3: Add the `_repair_decision_reason` private method to `LLMClient`**

Add this method after `generate_structured` and before `is_available`:

```python
def _repair_decision_reason(
    self,
    response_model: Type[T],
    sanitized: str,
    ve: ValidationError,
) -> T | None:
    """
    Attempt to repair an AgentDecisionResponse where reason is the sole overlong field.

    Returns a repaired typed model if the only validation failure is reason being
    string_too_long. Returns None in all other cases — the caller must handle
    the original ValidationError.
    """
    if response_model is not AgentDecisionResponse:
        return None

    # Repair requires parseable JSON
    try:
        data = json.loads(sanitized)
    except json.JSONDecodeError:
        return None

    errors = ve.errors()
    if not (
        len(errors) == 1
        and errors[0]["type"] == "string_too_long"
        and errors[0]["loc"] == ("reason",)
    ):
        return None

    original_length = len(data.get("reason", ""))
    data["reason"] = data["reason"][:240]

    logger.warning(
        f"Repaired overlong reason in {response_model.__name__} "
        f"(original_length={original_length})"
    )
    self.last_call["repaired_reason_too_long"] = True
    self.last_call["repaired_fields"] = ["reason"]
    self.last_call["original_reason_length"] = original_length

    try:
        return response_model.model_validate(data)
    except ValidationError:
        return None
```

- [ ] **Step 4: Restructure the validation call in `generate_structured` to use the repair path**

Replace the single line at the end of the `try` block:

```python
return response_model.model_validate_json(sanitized)
```

with:

```python
try:
    return response_model.model_validate_json(sanitized)
except ValidationError as ve:
    repaired = self._repair_decision_reason(response_model, sanitized, ve)
    if repaired is not None:
        return repaired
    raise
```

The full `generate_structured` method after changes:

```python
def generate_structured(
    self,
    prompt: str,
    response_model: Type[T],
    system_prompt: str = "",
    temperature: float = LLM_TEMPERATURE,
    max_tokens: int = LLM_MAX_TOKENS,
) -> T | None:
    """Calls vllm with structured_outputs constraint. Returns typed model or None on error."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    self.last_call = {
        "system_prompt": system_prompt,
        "user_prompt": prompt,
        "raw_response": "",
    }

    try:
        logger.debug(f"LLM request to {self.model}: {prompt[:120]}...")
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "schema": response_model.model_json_schema(),
                },
            },
            extra_body={
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        choice = response.choices[0]
        raw = choice.message.content or ""
        self.last_call["raw_response"] = raw
        if choice.finish_reason == "length":
            logger.warning(
                f"LLM response truncated (max_tokens={max_tokens}) for {response_model.__name__}"
            )
            return None
        logger.debug(f"LLM response: {raw[:200]}...")
        # Strip control characters that vllm occasionally injects into string values
        sanitized = "".join(ch for ch in raw if ch >= " " or ch in "\n\r\t")
        # Extract just the JSON object — vllm sometimes appends trailing text
        start = sanitized.find("{")
        end = sanitized.rfind("}") + 1
        if start != -1 and end > start:
            sanitized = sanitized[start:end]
        try:
            return response_model.model_validate_json(sanitized)
        except ValidationError as ve:
            repaired = self._repair_decision_reason(response_model, sanitized, ve)
            if repaired is not None:
                return repaired
            raise
    except Exception as e:
        logger.error(f"Error calling vllm: {e}")
        return None
```

- [ ] **Step 5: Run all new tests plus the length-truncation regression test**

```bash
uv run pytest tests/test_llm_client.py::TestGenerateStructured::test_salvages_decision_with_overlong_reason tests/test_llm_client.py::TestGenerateStructured::test_repair_writes_metadata_to_last_call tests/test_llm_client.py::TestGenerateStructured::test_repair_not_applied_for_missing_required_action_fields tests/test_llm_client.py::TestGenerateStructured::test_repair_not_applied_to_non_decision_models tests/test_llm_client.py::TestGenerateStructured::test_malformed_json_returns_none tests/test_llm_client.py::TestGenerateStructured::test_returns_none_when_response_truncated -v
```

Expected: all 6 PASSED. `test_returns_none_when_response_truncated` is the spec-required
regression guard confirming `finish_reason == "length"` still returns `None` after the
`generate_structured` restructuring.

- [ ] **Step 6: Run the full test suite**

```bash
uv run pytest -m "not slow" -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add simulation/llm_client.py tests/test_llm_client.py
git commit -m "feat(llm_client): add deterministic repair path for overlong decision reasons"
```

---

## Chunk 3: Prompt update and cornerstone documentation

### Task 5: Update the agent system prompt

**Files:**
- Modify: `prompts/agent/system.txt:49`

- [ ] **Step 1: Add the 240-character ceiling to the closing instruction**

The last line of `prompts/agent/system.txt` currently reads:

```
Always respond ONLY with a valid JSON object. Keep reasons brief and grounded in the current situation.
```

Change it to:

```
Always respond ONLY with a valid JSON object. Keep reason brief, under 240 characters, and grounded in the immediate situation.
```

- [ ] **Step 2: Run the smoke test to confirm the prompt loads without error**

```bash
uv run main.py --no-llm --ticks 5 --agents 1
```

Expected: exits cleanly, no errors.

- [ ] **Step 3: Commit**

```bash
git add prompts/agent/system.txt
git commit -m "docs(prompts): state 240-char decision reason ceiling in agent system prompt"
```

---

### Task 6: Update DECISION_LOG.md

**Files:**
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`

- [ ] **Step 1: Append DEC-044 at the end of the file**

```markdown
### DEC-044: Decision reason field repair — truncate on `string_too_long` validation failure
- **Date**: 2026-03-17
- **Context**: `AgentDecisionResponse.reason` was capped at 160 characters. As executor prompts grew richer, the model occasionally returned valid decisions with longer explanations. Pydantic rejected the entire response, causing `generate_structured()` to return `None` and the agent to fall back to the rule-based policy — discarding a structurally sound decision.
- **Decision**: Widen the decision-only reason cap from 160 to 240 characters via a new `DecisionReasonText` alias. Add a deterministic repair path in `LLMClient.generate_structured()` that fires only for `AgentDecisionResponse` when the sole validation failure is `reason` being `string_too_long`. Repair truncates the field to 240 chars and re-validates. All other failures return `None` unchanged.
- **Rejected alternatives**: Raise the shared `ReasonText` limit globally (silently widens oracle/planner envelopes); retry the LLM call with a tighter prompt (non-deterministic, adds latency); silently drop the `reason` field (loses observability).
- **Consequences**: One new private method in `LLMClient`. Repair emits a `WARNING` log and writes `repaired_reason_too_long`, `repaired_fields`, and `original_reason_length` to `last_call`. No new event types, no fallback-parse accounting. `DECISION_RESPONSE_MAX_TOKENS` unchanged.
```

- [ ] **Step 2: Commit**

```bash
git add project-cornerstone/00-master-plan/DECISION_LOG.md
git commit -m "docs(cornerstone): add DEC-044 decision reason repair decision"
```

---

### Task 7: Update `llm-integration_context.md`

**Files:**
- Modify: `project-cornerstone/05-llm-integration/llm-integration_context.md`

- [ ] **Step 1: Add a repair-path subsection under "Current implementation"**

After the line:

```
- Fallback behavior is present when parsing/LLM calls fail.
```

Add:

```markdown
- When `generate_structured()` is called with `AgentDecisionResponse` and Pydantic validation fails solely because `reason` exceeds 240 characters, the client truncates `reason` deterministically and re-validates. The repaired decision is returned normally (`parse_ok=True`). Successful repairs emit a `WARNING` log and write `repaired_reason_too_long`, `repaired_fields`, and `original_reason_length` into `last_call`. All other validation failures, malformed JSON, and truncated responses continue to return `None`.
```

- [ ] **Step 2: Commit**

```bash
git add project-cornerstone/05-llm-integration/llm-integration_context.md
git commit -m "docs(cornerstone): document executor decision repair behavior in llm-integration context"
```

---

## Final verification

- [ ] **Run full test suite one last time**

```bash
uv run pytest -m "not slow" -v
```

Expected: all tests pass.

- [ ] **Run smoke test**

```bash
uv run main.py --no-llm --ticks 5 --agents 1
```

Expected: clean exit.

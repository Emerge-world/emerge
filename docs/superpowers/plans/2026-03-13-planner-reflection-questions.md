# Planner Reflection Questions Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four reflection questions to the long-term planner prompt so agents explicitly reconsider goal fit and efficiency before generating a structured plan.

**Architecture:** Keep the planning runtime unchanged. Add the reflection checklist only to `prompts/agent/planner.txt`, then add a prompt regression test in `tests/test_planner.py` that renders the template through `simulation/prompt_loader.py` and asserts the four questions are present. This preserves the current `Planner.plan()` flow and `AgentPlanResponse` schema while still locking in the requested behavior.

**Tech Stack:** Python 3.12, pytest, string.Template prompt rendering, uv

---

**Spec Reference:** `docs/superpowers/specs/2026-03-13-planner-reflection-questions-design.md`

## File Structure

- `prompts/agent/planner.txt`
  Purpose: planner user prompt template rendered by `Planner.plan()`. This is the only behavior-changing file.
- `tests/test_planner.py`
  Purpose: planner module regression tests. Add one prompt-focused test here rather than creating a new test file.
- `simulation/prompt_loader.py`
  Purpose: existing template renderer. Do not modify it; use it in the new test so the assertion exercises the real prompt file.
- `simulation/planner.py`
  Purpose: existing planner entrypoint. Do not modify it for this task.

## Chunk 1: Add Prompt Guidance And Prompt Regression Coverage

### Task 1: Add a failing prompt regression test, update the planner prompt, and verify no regressions

**Files:**
- Modify: `tests/test_planner.py:1-53`
- Modify: `prompts/agent/planner.txt:1-12`
- Reference only: `simulation/prompt_loader.py:13-22`
- Reference only: `simulation/planner.py:9-53`

- [ ] **Step 1: Write the failing prompt regression test**

Add imports and a new test to `tests/test_planner.py`:

```python
from simulation import prompt_loader
```

```python
def test_planner_prompt_includes_reflection_questions():
    prompt = prompt_loader.render(
        "agent/planner",
        tick=5,
        observation_text="fruit east",
        planner_context="- fruit helps",
        current_plan="stabilize food",
    )

    assert "What is my long-term goal?" in prompt
    assert "Am I getting closer to that goal?" in prompt
    assert "Could I do this more efficiently?" in prompt
    assert "Do I need to change my goal?" in prompt
```

Notes:
- Render the template directly instead of mocking `Planner`. That keeps the test focused on the exact prompt file the user asked to change.
- Keep the existing planner state tests untouched.

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```bash
uv run pytest tests/test_planner.py::test_planner_prompt_includes_reflection_questions -v
```

Expected: FAIL because `prompts/agent/planner.txt` does not yet contain the four questions.

- [ ] **Step 3: Update `prompts/agent/planner.txt` with the reflection checklist**

Add a compact block after `RELEVANT MEMORY:` and before the final return instruction.

Use text with this shape:

```text
PLANNING QUESTIONS:
- What is my long-term goal?
- Am I getting closer to that goal?
- Could I do this more efficiently?
- Do I need to change my goal?

Consider these questions silently, then return a compact structured plan.
```

Implementation notes:
- Keep the prompt concise; do not add new placeholders or JSON fields.
- Preserve the current template variables: `$tick`, `$observation_text`, `$current_plan`, `$planner_context`.
- Do not modify `prompts/agent/planner_system.txt`.

- [ ] **Step 4: Run the targeted planner test file**

Run:

```bash
uv run pytest tests/test_planner.py -v
```

Expected: PASS. The new prompt regression test and the existing planner behavior tests should all pass.

- [ ] **Step 5: Run the required full regression suite**

Run:

```bash
uv run pytest -m "not slow"
```

Expected: PASS. This is required by `AGENTS.md` before claiming the change is complete.

- [ ] **Step 6: Commit the implementation**

Run:

```bash
git add prompts/agent/planner.txt tests/test_planner.py
git commit -m "feat: add planner reflection questions"
```

Expected: one atomic commit containing the prompt update and its regression test.

## Execution Notes

- YAGNI: do not add new planner schema fields, planner state fields, events, or metrics.
- Keep the change prompt-only as approved in the spec.
- If the prompt wording needs slight adjustment for brevity, preserve the exact four user-requested questions verbatim.

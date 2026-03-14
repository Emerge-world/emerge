# Planner Agent Log Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Append full planner LLM call details to each simulation's per-agent markdown log when a replan succeeds.

**Architecture:** Keep planner logging inside the existing hidden trace flow. `Planner` captures the planner LLM call details, `Agent.decide_action()` attaches them to `_planning_trace`, `SimulationEngine` forwards that trace to `SimLogger`, and `SimLogger` appends a planner block only to `logs/sim_<timestamp>/agents/<Name>.md`. No planner details should be written to tick logs, oracle logs, or the event stream.

**Tech Stack:** Python 3.12, pytest, markdown file logging, uv

---

**Spec Reference:** `docs/superpowers/specs/2026-03-13-planner-agent-log-design.md`

## File Structure

- `simulation/planner.py`
  Purpose: build plans and expose the planner LLM call trace for the most recent successful plan.
- `simulation/agent.py`
  Purpose: attach planner-call details to `_planning_trace` when replanning succeeds.
- `simulation/engine.py`
  Purpose: consume hidden planner trace metadata and forward it to `SimLogger`.
- `simulation/sim_logger.py`
  Purpose: append planner-call markdown blocks to `agents/<Name>.md` only.
- `tests/test_agent_planning.py`
  Purpose: verify successful replanning includes planner-call details in hidden trace output.
- `tests/test_visual_logging.py`
  Purpose: verify `SimLogger` formats and writes planner-call details into the per-agent log.
- `tests/test_engine_planning_events.py`
  Purpose: verify engine wiring logs planner details when the trace exists and stays quiet when it does not.

## Chunk 1: Capture Planner LLM Trace In The Planning Path

### Task 1: Add a failing regression test and thread planner-call details through `_planning_trace`

**Files:**
- Modify: `tests/test_agent_planning.py:1-76`
- Modify: `simulation/planner.py:1-64`
- Modify: `simulation/agent.py:373-427`

- [ ] **Step 1: Write the failing planning-trace regression test**

Add a new test to `tests/test_agent_planning.py` that verifies a successful replan includes full planner-call details in `_planning_trace`.

Use a custom `llm.generate_structured` side effect so the test controls `llm.last_call` separately for the planner call and the executor decision call:

```python
def test_successful_replan_includes_planner_llm_trace(monkeypatch):
    llm = MagicMock()
    llm.last_call = {}

    plan_response = AgentPlanResponse(
        goal="stabilize food",
        goal_type="survival",
        subgoals=[
            PlanSubgoalResponse(
                description="move toward fruit",
                kind="move",
                target="fruit",
                preconditions=["fruit visible"],
                completion_signal="adjacent to fruit",
                failure_signal="fruit disappears",
                priority=1,
            )
        ],
        horizon="short",
        success_signals=["eat fruit"],
        abort_conditions=["energy <= 10"],
        confidence=0.8,
        rationale_summary="fruit visible",
    )
    decision_response = AgentDecisionResponse(action="move", direction="east", reason="following plan")

    def fake_generate_structured(prompt, schema, system_prompt="", temperature=None):
        if schema is AgentPlanResponse:
            llm.last_call = {
                "system_prompt": system_prompt,
                "user_prompt": prompt,
                "raw_response": '{"goal":"stabilize food"}',
            }
            return plan_response
        llm.last_call = {
            "system_prompt": system_prompt,
            "user_prompt": prompt,
            "raw_response": '{"action":"move","direction":"east","reason":"following plan"}',
        }
        return decision_response

    llm.generate_structured.side_effect = fake_generate_structured
    agent = Agent(name="Ada", x=5, y=5, llm=llm)
    monkeypatch.setattr("simulation.agent.ENABLE_EXPLICIT_PLANNING", True)

    action = agent.decide_action([{"x": 5, "y": 5, "tile": "land", "distance": 0}], tick=2)

    planner_trace = action["_planning_trace"]["planner_llm"]
    assert planner_trace["system_prompt"]
    assert "Build or refresh your plan" in planner_trace["user_prompt"]
    assert planner_trace["raw_response"] == '{"goal":"stabilize food"}'
    assert planner_trace["parsed_plan"]["goal"] == "stabilize food"
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```bash
uv run pytest tests/test_agent_planning.py::test_successful_replan_includes_planner_llm_trace -v
```

Expected: FAIL because `_planning_trace` does not yet contain planner-call details.

- [ ] **Step 3: Implement planner trace capture in `simulation/planner.py` and `simulation/agent.py`**

In `simulation/planner.py`:

- add `self.last_call: dict = {}` in `Planner.__init__`
- clear `self.last_call` on early return paths (`no llm` or `typed is None`)
- after a successful planner call, capture the planner LLM trace and parsed plan

Implementation shape:

```python
class Planner:
    def __init__(self, llm):
        self.llm = llm
        self.last_call: dict = {}
```

```python
if not self.llm:
    self.last_call = {}
    return None
```

```python
typed = self.llm.generate_structured(...)
if typed is None:
    self.last_call = {}
    return None

llm_trace = dict(self.llm.last_call) if self.llm.last_call else {}
self.last_call = {
    "system_prompt": llm_trace.get("system_prompt", system_prompt),
    "user_prompt": llm_trace.get("user_prompt", user_prompt),
    "raw_response": llm_trace.get("raw_response", ""),
    "parsed_plan": typed.model_dump(),
}
```

In `simulation/agent.py`, when `new_plan is not None`, attach the planner trace before returning the action:

```python
planner_llm = dict(self.planner.last_call) if self.planner and self.planner.last_call else {}
if planner_llm:
    planning_trace["planner_llm"] = planner_llm
```

Notes:
- Keep planner logging observational only.
- Do not add planner details to `events.jsonl`.
- Do not write files from `Planner` or `Agent`.

- [ ] **Step 4: Run the targeted planning tests**

Run:

```bash
uv run pytest tests/test_agent_planning.py -v
```

Expected: PASS. The new planner-trace regression test and the existing planning tests should all pass.

- [ ] **Step 5: Commit the trace capture**

Run:

```bash
git add simulation/planner.py simulation/agent.py tests/test_agent_planning.py
git commit -m "feat: capture planner llm traces"
```

Expected: one commit that adds planner-call trace capture without touching logging files yet.

## Chunk 2: Write Planner Details Into Per-Agent Logs

### Task 2: Add planner log formatting, engine wiring, and no-noise integration coverage

**Files:**
- Modify: `tests/test_visual_logging.py`
- Modify: `tests/test_engine_planning_events.py`
- Modify: `simulation/sim_logger.py:18-264`
- Modify: `simulation/engine.py:256-291`

- [ ] **Step 1: Write the failing logging tests**

In `tests/test_visual_logging.py`, add a helper to read the per-agent file:

```python
def _read_agent(logger: SimLogger, agent_name: str = "Ada") -> str:
    path = os.path.join(logger.run_dir, "agents", f"{agent_name}.md")
    with open(path, encoding="utf-8") as f:
        return f.read()
```

Add a logger-format test:

```python
class TestSimLoggerPlannerBlock:
    def test_planner_block_written_to_agent_file(self, logger):
        agent = _mock_agent()
        logger.log_agent_plan(
            tick=1,
            agent=agent,
            system_prompt="planner system",
            user_prompt="planner prompt",
            raw_response='{"goal":"stabilize food"}',
            parsed_plan={"goal": "stabilize food", "subgoals": []},
        )

        content = _read_agent(logger, "Ada")
        assert "Planner" in content
        assert "planner system" in content
        assert "planner prompt" in content
        assert '{"goal":"stabilize food"}' in content
        assert "stabilize food" in content
```

In `tests/test_engine_planning_events.py`, add two engine wiring tests:

```python
def _read_agent_log(engine: SimulationEngine, agent_name: str) -> str:
    path = Path(engine.sim_logger.run_dir) / "agents" / f"{agent_name}.md"
    return path.read_text()
```

```python
def test_engine_logs_planner_call_to_agent_file(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    action = {
        "action": "move",
        "direction": "east",
        "reason": "following plan",
        "_planning_trace": {
            "plan_created": {"goal": "stabilize food"},
            "planner_llm": {
                "system_prompt": "planner system",
                "user_prompt": "planner prompt",
                "raw_response": '{"goal":"stabilize food"}',
                "parsed_plan": {"goal": "stabilize food", "subgoals": []},
            },
        },
    }
    with patch.object(engine.agents[0], "decide_action", return_value=action):
        engine.run()

    content = _read_agent_log(engine, engine.agents[0].name)
    assert "### Planner" in content
    assert "planner prompt" in content
```

```python
def test_engine_does_not_log_planner_call_without_trace(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    action = {"action": "move", "direction": "east", "reason": "following plan"}
    with patch.object(engine.agents[0], "decide_action", return_value=action):
        engine.run()

    content = _read_agent_log(engine, engine.agents[0].name)
    assert "### Planner" not in content
```

- [ ] **Step 2: Run the new logging tests to verify they fail**

Run:

```bash
uv run pytest tests/test_visual_logging.py tests/test_engine_planning_events.py -v
```

Expected: FAIL because `SimLogger` does not yet have `log_agent_plan(...)` and `SimulationEngine` does not yet forward planner trace to it.

- [ ] **Step 3: Implement planner log formatting and engine wiring**

In `simulation/sim_logger.py`:

- add `import json`
- add `log_agent_plan(...)`
- add a dedicated formatting helper, similar to `_format_decision_block`

Implementation shape:

```python
def log_agent_plan(self, tick: int, agent, system_prompt: str,
                   user_prompt: str, raw_response: str, parsed_plan: dict):
    block = self._format_planner_block(
        system_prompt, user_prompt, raw_response, parsed_plan
    )
    self._append(self._agent_file(agent.name), f"## Tick {tick:04d}\n\n{block}")
```

```python
@staticmethod
def _format_planner_block(system_prompt, user_prompt, raw_response, parsed_plan) -> str:
    parsed_json = json.dumps(parsed_plan, indent=2, sort_keys=True)
    return (
        "### Planner\n\n"
        "<details>\n<summary>System prompt</summary>\n\n"
        f"```\n{system_prompt}\n```\n\n</details>\n\n"
        "<details>\n<summary>Planner prompt</summary>\n\n"
        f"```\n{user_prompt}\n```\n\n</details>\n\n"
        "<details>\n<summary>Raw LLM response</summary>\n\n"
        f"```\n{raw_response}\n```\n\n</details>\n\n"
        f"### Parsed plan\n\n```json\n{parsed_json}\n```\n\n"
    )
```

In `simulation/engine.py`, extract planner logging data before event emission and decision logging:

```python
planning_trace = action.pop("_planning_trace", None) or {}
planner_llm = planning_trace.pop("planner_llm", None)
```

Then, after `planning_trace` is extracted and before or after the normal decision log call, add:

```python
if planner_llm:
    self.sim_logger.log_agent_plan(
        tick,
        agent,
        system_prompt=planner_llm.get("system_prompt", ""),
        user_prompt=planner_llm.get("user_prompt", ""),
        raw_response=planner_llm.get("raw_response", ""),
        parsed_plan=planner_llm.get("parsed_plan", {}),
    )
```

Notes:
- Keep planner details out of `tick_*.md`, `oracle.md`, and `events.jsonl`.
- Do not change existing action decision logging behavior.
- Pop `planner_llm` out of `planning_trace` before plan event emission so non-event metadata stays out of the event payload logic.

- [ ] **Step 4: Run the targeted logging and planning tests**

Run:

```bash
uv run pytest tests/test_agent_planning.py tests/test_visual_logging.py tests/test_engine_planning_events.py -v
```

Expected: PASS. Planner trace capture, logger formatting, and engine wiring should all be covered.

- [ ] **Step 5: Run the required full regression suite**

Run:

```bash
uv run pytest -m "not slow"
```

Expected: PASS. This is required by `AGENTS.md` before claiming the feature is complete.

- [ ] **Step 6: Commit the planner logging feature**

Run:

```bash
git add simulation/planner.py simulation/agent.py simulation/engine.py simulation/sim_logger.py tests/test_agent_planning.py tests/test_visual_logging.py tests/test_engine_planning_events.py
git commit -m "feat: log planner calls in agent markdown logs"
```

Expected: one commit that adds planner-call logging to per-agent markdown files and the associated regression coverage.

## Execution Notes

- Preserve the existing planner and action runtime behavior; this feature is logging-only.
- Keep the planner log entry agent-file-only.
- If the exact section title needs adjustment for readability, keep `Planner prompt` distinct from the normal decision `User prompt`.

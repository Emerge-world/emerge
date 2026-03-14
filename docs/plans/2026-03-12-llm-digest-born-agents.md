# LLM Digest Born Agents Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `llm_digest` include agents born after tick 0 and attach lineage metadata to their run-level and per-agent digest outputs.

**Architecture:** Emit a canonical `agent_birth` event from the engine, then teach `DigestBuilder` to discover agents and lineage from `events.jsonl` rather than the initial roster alone. Render the new lineage data in both JSON and markdown while keeping older runs digestable.

**Tech Stack:** Python 3.12, pytest, stdlib JSON/Path handling, existing digest pipeline under `simulation/digest/`

---

### Task 1: Add failing digest builder tests for born agents

**Files:**
- Modify: `tests/test_digest_builder.py`
- Test: `tests/test_digest_builder.py`

**Step 1: Write the failing test**

Add a synthetic event fixture where `run_start` lists only `Ada`, an `agent_birth` event introduces `Kira`, and `Kira` later emits `agent_decision` and `agent_state` events.

Expected assertions:

```python
assert "Kira" in [agent["agent_id"] for agent in run_data["agents"]]
assert (tmp_path / "llm_digest" / "agents" / "Kira.json").exists()
assert kira_summary["generation"] == 1
assert kira_summary["born_tick"] == 5
assert kira_summary["parent_ids"] == ["Ada", "Bruno"]
assert kira_agent["lineage"]["is_born_agent"] is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_digest_builder.py::TestDigestBuilderOutput::test_includes_born_agents_with_lineage_metadata -v`

Expected: FAIL because `Kira` is missing from `run_digest.json` and no lineage metadata exists yet.

**Step 3: Write minimal implementation**

Do not implement yet. This task ends once the failing test is in place and validated.

**Step 4: Commit**

```bash
git add tests/test_digest_builder.py
git commit -m "test: cover born agents in llm digest"
```

### Task 2: Add failing renderer tests for lineage fields

**Files:**
- Modify: `tests/test_digest_renderer.py`
- Test: `tests/test_digest_renderer.py`

**Step 1: Write the failing test**

Extend the minimal run and agent digest fixtures to include lineage data, then assert:

```python
assert "| Agent | Status | Generation | Born Tick |" in run_md
assert "## Lineage" in agent_md
assert "Original settler" in agent_md or "Parents" in agent_md
```

Also add a fallback-oriented assertion that markdown uses `unknown` instead of `None` for missing lineage values.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_digest_renderer.py::TestDigestRenderer::test_renders_lineage_metadata_in_markdown -v`

Expected: FAIL because the markdown templates do not render lineage fields yet.

**Step 3: Write minimal implementation**

Do not implement yet. This task ends once the failing renderer test is in place and validated.

**Step 4: Commit**

```bash
git add tests/test_digest_renderer.py
git commit -m "test: cover digest lineage rendering"
```

### Task 3: Implement canonical birth event and digest lineage extraction

**Files:**
- Modify: `simulation/event_emitter.py`
- Modify: `simulation/engine.py`
- Modify: `simulation/digest/digest_builder.py`
- Test: `tests/test_digest_builder.py`

**Step 1: Implement `emit_agent_birth()`**

Add an emitter method that writes:

```python
self._emit("agent_birth", tick, {
    "child_name": child.name,
    "generation": child.generation,
    "born_tick": child.born_tick,
    "parent_ids": list(child.parent_ids),
    "pos": [child.x, child.y],
}, agent_id=child.name)
```

**Step 2: Emit the event from the engine**

In `simulation/engine.py`, call the new emitter immediately after `_spawn_child(...)` returns and before later child activity in the same tick can appear.

**Step 3: Replace agent discovery in `DigestBuilder`**

Implement helper methods that:

- collect ordered agent IDs from `run_start`, `agent_birth`, and all event `agent_id`s
- build a lineage index with safe defaults
- pass lineage metadata into both `_build_run_digest()` and `_build_agent_digest()`

Use output shapes like:

```python
{
    "generation": 1,
    "born_tick": 5,
    "parent_ids": ["Ada", "Bruno"],
    "is_born_agent": True,
}
```

Fallback shape for older runs:

```python
{
    "generation": None,
    "born_tick": None,
    "parent_ids": [],
    "is_born_agent": False,
}
```

**Step 4: Run targeted tests**

Run: `uv run pytest tests/test_digest_builder.py -v`

Expected: PASS, including the new born-agent test.

**Step 5: Commit**

```bash
git add simulation/event_emitter.py simulation/engine.py simulation/digest/digest_builder.py tests/test_digest_builder.py
git commit -m "fix: include born agents in llm digest"
```

### Task 4: Render lineage metadata and document the decision

**Files:**
- Modify: `simulation/digest/digest_renderer.py`
- Modify: `tests/test_digest_renderer.py`
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Test: `tests/test_digest_renderer.py`

**Step 1: Update markdown rendering**

In `simulation/digest/digest_renderer.py`, add:

- generation and born tick columns in the run digest agent table
- a `## Lineage` section in agent markdown
- `unknown` display for missing lineage values

**Step 2: Document the design decision**

Add a new decision-log entry stating that born-agent digest lineage comes from canonical run events (`agent_birth`) rather than external lineage persistence files.

**Step 3: Run renderer tests**

Run: `uv run pytest tests/test_digest_renderer.py -v`

Expected: PASS, including the new lineage-rendering test.

**Step 4: Run full non-slow verification**

Run: `uv run pytest -m "not slow"`

Expected: PASS.

**Step 5: Commit**

```bash
git add simulation/digest/digest_renderer.py tests/test_digest_renderer.py project-cornerstone/00-master-plan/DECISION_LOG.md
git commit -m "feat: render digest lineage metadata"
```

# EBS Autonomy Rebuild Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three Autonomy sub-scores in `EBSBuilder` with `behavioral_initiative`, `knowledge_accumulation`, and `planning_effectiveness` to measure long-term memory and planning depth.

**Architecture:** Single-pass accumulator changes in `ebs_builder.py` (new `last_semantic` dict + extend `learnings_log` to store `episode_count`); one new field added to `emit_agent_state` in `event_emitter.py`; old test assertions updated to use the new key structure.

**Tech Stack:** Python 3.12, pytest, `simulation/ebs_builder.py`, `simulation/event_emitter.py`, `tests/test_ebs_builder.py`

**Spec:** `docs/superpowers/specs/2026-03-16-ebs-autonomy-rebuild-design.md`

---

## Chunk 1: EBSBuilder — new tests + implementation

### Task 1: Write failing tests for new Autonomy signals

**Files:**
- Modify: `tests/test_ebs_builder.py`

- [ ] **Step 1: Update `_agent_state` helper to accept `memory_semantic`**

In `tests/test_ebs_builder.py`, replace the existing `_agent_state` helper:

```python
def _agent_state(tick: int, agent: str = "Ada", hunger: float = 20, energy: float = 80,
                 life: float = 100, memory_semantic: int = 0) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "agent_state", "agent_id": agent,
        "payload": {"hunger": hunger, "energy": energy, "life": life, "alive": True,
                    "memory_semantic": memory_semantic},
    }
```

- [ ] **Step 2: Add tests for `semantic_growth` and `compression_yield` signals**

Add a new test class after `TestStabilityComponent`:

```python
# ------------------------------------------------------------------ #
# EBSBuilder — Autonomy component (rebuilt)
# ------------------------------------------------------------------ #

class TestAutonomyRebuilt:
    def test_semantic_growth_nonzero_when_memory_semantic_present(self, tmp_path):
        """Agent ends run with 15/30 semantic entries → semantic_growth = 0.5."""
        events = [
            _run_start(),
            _agent_state(1, memory_semantic=15),
            _agent_state(5, memory_semantic=15),
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        detail = data["components"]["autonomy"]["detail"]
        assert detail["semantic_growth"] == pytest.approx(0.5)

    def test_semantic_growth_uses_last_agent_state_per_agent(self, tmp_path):
        """Only the final agent_state per agent contributes to semantic_growth."""
        events = [
            _run_start(),
            _agent_state(1, memory_semantic=5),
            _agent_state(10, memory_semantic=20),  # last → 20/30 ≈ 0.667
            _run_end(tick=10),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        detail = data["components"]["autonomy"]["detail"]
        assert detail["semantic_growth"] == pytest.approx(20 / 30, abs=1e-3)

    def test_semantic_growth_zero_when_no_agent_state_events(self, tmp_path):
        events = [_run_start(), _run_end()]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert data["components"]["autonomy"]["detail"]["semantic_growth"] == 0.0

    def test_compression_yield_nonzero_when_learnings_present(self, tmp_path):
        """Compression event: 5 episodes → 2 learnings → yield = 2/5 = 0.4."""
        events = [
            _run_start(),
            _memory_compression(10, learnings=["fruit restores hunger", "rest near water"]),
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        # _memory_compression helper sets episode_count=5
        assert data["components"]["autonomy"]["detail"]["compression_yield"] == pytest.approx(0.4)

    def test_compression_yield_capped_at_one(self, tmp_path):
        """More learnings than episodes → yield capped at 1.0."""
        events = [
            _run_start(),
            {
                "run_id": "test", "tick": 10, "event_type": "memory_compression_result",
                "agent_id": "Ada",
                "payload": {"episode_count": 2, "learnings": ["a", "b", "c", "d"]},
            },
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert data["components"]["autonomy"]["detail"]["compression_yield"] == pytest.approx(1.0)

    def test_compression_yield_zero_when_no_compression_events(self, tmp_path):
        events = [_run_start(), _run_end()]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert data["components"]["autonomy"]["detail"]["compression_yield"] == 0.0

    def test_plan_completion_rate_uses_subgoal_events(self, tmp_path):
        """2 completed, 1 failed → plan_completion_rate = 2/3 ≈ 0.667."""
        events = [
            _run_start(),
            _agent_decision(1, action="move"),
            {"run_id": "test", "tick": 1, "event_type": "subgoal_completed", "agent_id": "Ada", "payload": {}},
            {"run_id": "test", "tick": 2, "event_type": "subgoal_completed", "agent_id": "Ada", "payload": {}},
            {"run_id": "test", "tick": 3, "event_type": "subgoal_failed", "agent_id": "Ada", "payload": {}},
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert data["components"]["autonomy"]["detail"]["plan_completion_rate"] == pytest.approx(2 / 3, abs=1e-3)

    def test_plan_completion_rate_zero_when_no_subgoals(self, tmp_path):
        events = [_run_start(), _agent_decision(1), _run_end()]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert data["components"]["autonomy"]["detail"]["plan_completion_rate"] == 0.0

    def test_autonomy_sub_scores_keys_present(self, tmp_path):
        """Output must have the three new sub_scores and a detail block."""
        events = [_run_start(), _run_end()]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        autonomy = data["components"]["autonomy"]
        assert set(autonomy["sub_scores"].keys()) == {
            "behavioral_initiative", "knowledge_accumulation", "planning_effectiveness"
        }
        assert "detail" in autonomy
        assert set(autonomy["detail"].keys()) == {
            "proactive_rate", "env_contingent_rate",
            "semantic_growth", "compression_yield",
            "plan_completion_rate", "planning_activity",
        }

    def test_autonomy_score_formula(self, tmp_path):
        """Verify formula: 0.25*bi + 0.375*ka + 0.375*pe (all signals exercised)."""
        events = [
            _run_start(),
            # behavioral: proactive move (hunger=20, fruit east, move east)
            _agent_perception(1, hunger=20, resources_nearby=[{"type": "fruit", "tile": "forest", "dx": 1, "dy": 0}]),
            _agent_decision(1, action="move", direction="east"),
            # knowledge: 15/30 semantic, 2/5 compression yield
            _agent_state(1, memory_semantic=15),
            _memory_compression(10, learnings=["a", "b"]),
            # planning: 1 completed, 1 failed
            {"run_id": "test", "tick": 2, "event_type": "subgoal_completed", "agent_id": "Ada", "payload": {}},
            {"run_id": "test", "tick": 3, "event_type": "subgoal_failed", "agent_id": "Ada", "payload": {}},
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        detail = data["components"]["autonomy"]["detail"]
        sub = data["components"]["autonomy"]["sub_scores"]

        # Verify sub-scores are averages of their signals
        assert sub["behavioral_initiative"] == pytest.approx(
            (detail["proactive_rate"] + detail["env_contingent_rate"]) / 2, abs=1e-3
        )
        assert sub["knowledge_accumulation"] == pytest.approx(
            (detail["semantic_growth"] + detail["compression_yield"]) / 2, abs=1e-3
        )
        assert sub["planning_effectiveness"] == pytest.approx(
            (detail["plan_completion_rate"] + detail["planning_activity"]) / 2, abs=1e-3
        )
        # Verify score formula
        expected_score = 100 * (
            0.25 * sub["behavioral_initiative"]
            + 0.375 * sub["knowledge_accumulation"]
            + 0.375 * sub["planning_effectiveness"]
        )
        assert data["components"]["autonomy"]["score"] == pytest.approx(expected_score, abs=0.01)
```

- [ ] **Step 3: Run new tests to verify they all fail**

```bash
cd /home/gusy/emerge
uv run pytest tests/test_ebs_builder.py::TestAutonomyRebuilt -v
```

Expected: All 10 tests FAIL — either `KeyError` on old key names or `AssertionError` because EBSBuilder hasn't been updated yet.

- [ ] **Step 4: Commit failing tests**

```bash
git add tests/test_ebs_builder.py
git commit -m "test(ebs): add failing tests for rebuilt Autonomy component"
```

---

### Task 2: Implement EBSBuilder changes

**Files:**
- Modify: `simulation/ebs_builder.py:17` (import)
- Modify: `simulation/ebs_builder.py:144` (accumulator block)
- Modify: `simulation/ebs_builder.py:191-199` (agent_state handler)
- Modify: `simulation/ebs_builder.py:261-265` (memory_compression handler)
- Modify: `simulation/ebs_builder.py:395-404` (autonomy scoring)
- Modify: `simulation/ebs_builder.py:481-489` (output dict)

- [ ] **Step 1: Add MEMORY_SEMANTIC_MAX to the config import**

In `simulation/ebs_builder.py`, replace line 17:

```python
from simulation.config import EBS_LONGEVITY_REFERENCE_AGENT_TICKS
```

with:

```python
from simulation.config import EBS_LONGEVITY_REFERENCE_AGENT_TICKS, MEMORY_SEMANTIC_MAX
```

- [ ] **Step 2: Add `last_semantic` accumulator to the accumulators block**

In the accumulators block (after `max_tick_seen = 0`), add:

```python
last_semantic: dict[str, int] = {}  # agent_id → final memory_semantic count
```

So the block ends:

```python
        total_ticks_from_run_end: int | None = None
        max_tick_seen = 0
        last_semantic: dict[str, int] = {}  # agent_id → final memory_semantic count
```

- [ ] **Step 3: Capture `memory_semantic` in the `agent_state` handler**

In the `elif et == "agent_state":` block (around line 191), add one line:

```python
                elif et == "agent_state":
                    if agent_id:
                        state_history.setdefault(agent_id, []).append({
                            "tick": tick,
                            "hunger": p.get("hunger", 0),
                            "energy": p.get("energy", 0),
                            "life": p.get("life", 0),
                            "alive": p.get("alive", False),
                        })
                        last_semantic[agent_id] = p.get("memory_semantic", 0)
```

- [ ] **Step 4: Extend `learnings_log` to store `episode_count`**

In the `elif et == "memory_compression_result":` block (around line 261), replace:

```python
                elif et == "memory_compression_result":
                    learnings_log.append({
                        "tick": tick, "agent_id": agent_id,
                        "learnings": p.get("learnings", []),
                    })
```

with:

```python
                elif et == "memory_compression_result":
                    learnings_log.append({
                        "tick": tick, "agent_id": agent_id,
                        "learnings": p.get("learnings", []),
                        "episode_count": p.get("episode_count", 0),
                    })
```

- [ ] **Step 5: Replace the Autonomy scoring block**

Replace the entire `# Autonomy` block (lines 395–404):

```python
        # Autonomy
        proactive_rate = proactive_moves / total_moves if total_moves else 0.0
        env_contingent_rate = contingent_attempts / n_attempts if n_attempts else 0.0
        planning_signal = subgoals_completed + subgoals_failed
        self_generated_subgoals = min(1.0, planning_signal / action_total) if action_total else 0.0
        autonomy_score = 100 * (
            0.40 * proactive_rate
            + 0.30 * env_contingent_rate
            + 0.30 * self_generated_subgoals
        )
```

with:

```python
        # Autonomy — rebuilt sub-scores
        # behavioral_initiative: consolidation of two existing behavioral signals
        proactive_rate = proactive_moves / total_moves if total_moves else 0.0
        env_contingent_rate = contingent_attempts / n_attempts if n_attempts else 0.0
        behavioral_initiative = (proactive_rate + env_contingent_rate) / 2

        # knowledge_accumulation: semantic memory growth + compression density
        semantic_growth = (
            sum(v / MEMORY_SEMANTIC_MAX for v in last_semantic.values()) / len(last_semantic)
            if last_semantic else 0.0
        )
        compression_events = [
            e for e in learnings_log if e.get("episode_count", 0) > 0
        ]
        compression_yield = (
            sum(min(1.0, len(e["learnings"]) / e["episode_count"]) for e in compression_events)
            / len(compression_events)
            if compression_events else 0.0
        )
        knowledge_accumulation = (semantic_growth + compression_yield) / 2

        # planning_effectiveness: completion quality + activity quantity
        planning_signal = subgoals_completed + subgoals_failed
        plan_completion_rate = (
            subgoals_completed / planning_signal if planning_signal else 0.0
        )
        planning_activity = min(1.0, planning_signal / action_total) if action_total else 0.0
        planning_effectiveness = (plan_completion_rate + planning_activity) / 2

        autonomy_score = 100 * (
            0.25 * behavioral_initiative
            + 0.375 * knowledge_accumulation
            + 0.375 * planning_effectiveness
        )
```

- [ ] **Step 6: Update the autonomy output dict**

Replace the `"autonomy"` block in the return dict (lines 481–489):

```python
                "autonomy": {
                    "score": round(autonomy_score, 2),
                    "weight": _WEIGHTS["autonomy"],
                    "sub_scores": {
                        "proactive_resource_acquisition": round(proactive_rate, 4),
                        "environment_contingent_innovation": round(env_contingent_rate, 4),
                        "self_generated_subgoals": round(self_generated_subgoals, 4),
                    },
                },
```

with:

```python
                "autonomy": {
                    "score": round(autonomy_score, 2),
                    "weight": _WEIGHTS["autonomy"],
                    "sub_scores": {
                        "behavioral_initiative": round(behavioral_initiative, 4),
                        "knowledge_accumulation": round(knowledge_accumulation, 4),
                        "planning_effectiveness": round(planning_effectiveness, 4),
                    },
                    "detail": {
                        "proactive_rate": round(proactive_rate, 4),
                        "env_contingent_rate": round(env_contingent_rate, 4),
                        "semantic_growth": round(semantic_growth, 4),
                        "compression_yield": round(compression_yield, 4),
                        "plan_completion_rate": round(plan_completion_rate, 4),
                        "planning_activity": round(planning_activity, 4),
                    },
                },
```

- [ ] **Step 7: Run the new tests — verify they pass**

```bash
uv run pytest tests/test_ebs_builder.py::TestAutonomyRebuilt -v
```

Expected: All 10 tests PASS.

- [ ] **Step 8: Run the full test suite to identify which old tests now break**

```bash
uv run pytest tests/test_ebs_builder.py -v
```

Expected: All `TestAutonomyRebuilt` tests PASS. Five tests in `TestAutonomyComponent` FAIL with `KeyError` (they reference deleted key names `proactive_resource_acquisition` and `self_generated_subgoals`). **Do not commit yet — fix the old tests in Task 3 first.**

---

### Task 3: Fix old Autonomy tests

**Files:**
- Modify: `tests/test_ebs_builder.py` (class `TestAutonomyComponent`)

The five old tests now reference keys that no longer exist under `sub_scores`. Update them to use the `detail` block for the underlying signals.

- [ ] **Step 1: Update `test_proactive_move_toward_resource`**

Replace:
```python
        assert data["components"]["autonomy"]["sub_scores"]["proactive_resource_acquisition"] == 1.0
```
with:
```python
        assert data["components"]["autonomy"]["detail"]["proactive_rate"] == 1.0
```

- [ ] **Step 2: Update `test_hungry_move_not_proactive`**

Replace:
```python
        assert data["components"]["autonomy"]["sub_scores"]["proactive_resource_acquisition"] == 0.0
```
with:
```python
        assert data["components"]["autonomy"]["detail"]["proactive_rate"] == 0.0
```

- [ ] **Step 3: Update `test_move_away_from_resource_not_proactive`**

Replace:
```python
        assert data["components"]["autonomy"]["sub_scores"]["proactive_resource_acquisition"] == 0.0
```
with:
```python
        assert data["components"]["autonomy"]["detail"]["proactive_rate"] == 0.0
```

- [ ] **Step 4: Update `test_self_generated_subgoals_still_zero_without_planning_events`**

Replace:
```python
        assert data["components"]["autonomy"]["sub_scores"]["self_generated_subgoals"] == 0.0
```
with:
```python
        assert data["components"]["autonomy"]["detail"]["planning_activity"] == 0.0
```

- [ ] **Step 5: Update `test_self_generated_subgoals_uses_planning_events`**

Replace:
```python
        assert data["components"]["autonomy"]["sub_scores"]["self_generated_subgoals"] > 0.0
```
with:
```python
        assert data["components"]["autonomy"]["detail"]["planning_activity"] > 0.0
```

- [ ] **Step 6: Run the full test suite — verify all pass**

```bash
uv run pytest tests/test_ebs_builder.py -v
```

Expected: All tests PASS. No failures.

- [ ] **Step 7: Run the broader test suite to catch any regressions**

```bash
uv run pytest -m "not slow" -v
```

Expected: All tests PASS.

- [ ] **Step 8: Commit both the implementation and the test fixes together (all green)**

```bash
git add simulation/ebs_builder.py tests/test_ebs_builder.py
git commit -m "feat(ebs): rebuild Autonomy component with behavioral_initiative, knowledge_accumulation, planning_effectiveness"
```

---

## Chunk 2: Emitter + docs

### Task 4: Add memory_semantic to emit_agent_state

**Files:**
- Modify: `simulation/event_emitter.py:235-244`

- [ ] **Step 1: Add `memory_semantic` to the `emit_agent_state` payload**

In `simulation/event_emitter.py`, replace the `emit_agent_state` method:

```python
    def emit_agent_state(self, tick: int, agent):
        """Emit after agent.apply_tick_effects(). Captures final post-tick state."""
        self._emit("agent_state", tick, {
            "life": agent.life,
            "hunger": agent.hunger,
            "energy": agent.energy,
            "pos": [agent.x, agent.y],
            "alive": agent.alive,
            "inventory": dict(agent.inventory.items),
        }, agent_id=agent.name)
```

with:

```python
    def emit_agent_state(self, tick: int, agent):
        """Emit after agent.apply_tick_effects(). Captures final post-tick state."""
        self._emit("agent_state", tick, {
            "life": agent.life,
            "hunger": agent.hunger,
            "energy": agent.energy,
            "pos": [agent.x, agent.y],
            "alive": agent.alive,
            "inventory": dict(agent.inventory.items),
            "memory_semantic": len(agent.memory_system.semantic),
        }, agent_id=agent.name)
```

- [ ] **Step 2: Run the full test suite — verify no regressions**

```bash
uv run pytest -m "not slow" -v
```

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add simulation/event_emitter.py
git commit -m "feat(events): add memory_semantic count to agent_state event payload"
```

---

### Task 5: Update cornerstone docs

**Files:**
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Modify: `project-cornerstone/03-agents/agents_context.md`

- [ ] **Step 1: Add decision entry to DECISION_LOG.md**

Append to the end of `project-cornerstone/00-master-plan/DECISION_LOG.md`:

```markdown
### DEC-041: EBS Autonomy component rebuilt for long-term memory and planning
- **Date**: 2026-03-16
- **Context**: PR #45 introduced task memory, deterministic retrieval, and an explicit planner/executor loop, but the Autonomy component still only measured reactive behavioral signals (proactive moves, environment-contingent innovation, raw subgoal activity). Knowledge accumulation and planning effectiveness were unmeasured.
- **Decision**: Rebuild Autonomy internals. Keep 13% weight. Replace three sub-scores with: `behavioral_initiative` (25%, consolidation of old behavioral signals), `knowledge_accumulation` (37.5%, semantic_growth + compression_yield), `planning_effectiveness` (37.5%, plan_completion_rate + planning_activity). Add a `detail` dict alongside `sub_scores` to expose all six underlying signals for debugging.
- **Rejected alternatives**: Adding a separate Memory component (would require weight redistribution across all components); raising Autonomy weight beyond 13% (out of scope per user decision).
- **Consequences**: Runs with `ENABLE_EXPLICIT_PLANNING=False` will score 0 on `planning_effectiveness` — this is honest, not a bug. `agent_state` events now include `memory_semantic` count. The `learnings_log` accumulator now stores `episode_count` alongside learnings.
```

- [ ] **Step 2: Add EBS Autonomy section to agents_context.md**

`project-cornerstone/03-agents/agents_context.md` has no EBS section yet. Insert the following block **after** the `### Explicit planner/executor loop` subsection (after the line ending "...feed `events.jsonl` and `EBSBuilder`." in that section):

```markdown
### EBS Autonomy component *(rebuilt — see DEC-041)*

Weight: 13% of total EBS. Three sub-scores:

| Sub-score | Weight | Signals |
|---|---|---|
| `behavioral_initiative` | 25% | avg(`proactive_rate`, `env_contingent_rate`) |
| `knowledge_accumulation` | 37.5% | avg(`semantic_growth`, `compression_yield`) |
| `planning_effectiveness` | 37.5% | avg(`plan_completion_rate`, `planning_activity`) |

- `semantic_growth` — mean final `memory_semantic` count / `MEMORY_SEMANTIC_MAX` across agents (from `agent_state` events)
- `compression_yield` — mean `min(1, learnings / episode_count)` per compression event
- `plan_completion_rate` — `subgoals_completed / (subgoals_completed + subgoals_failed)`; 0 when planning disabled
- `planning_activity` — `min(1, planning_signal / action_total)`

All six underlying signals are exposed in `ebs.json` under `components.autonomy.detail`.
```

- [ ] **Step 3: Run tests one final time**

```bash
uv run pytest -m "not slow"
```

Expected: All tests PASS.

- [ ] **Step 4: Commit docs**

```bash
git add project-cornerstone/00-master-plan/DECISION_LOG.md
git add project-cornerstone/03-agents/agents_context.md
git commit -m "docs: update cornerstone for EBS Autonomy rebuild (DEC-041)"
```

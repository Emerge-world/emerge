# EBS Longevity Component Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 6th EBS component — Longevity — that rewards runs where agents survive longer and larger populations are sustained, compatible with infinite-tick runs.

**Architecture:** Two sub-scores (population_vitality and absolute_longevity) combine equally into a longevity_score weighted at 15%. Existing weights are trimmed proportionally (×0.85). All changes are confined to `ebs_builder.py` and its test file.

**Tech Stack:** Python stdlib only (`math.exp`). No new dependencies.

---

## Chunk 1: Longevity Component

### File Map

- Modify: `simulation/ebs_builder.py` — add constant, rebalance weights, extend accumulator, add scoring, extend output
- Modify: `tests/test_ebs_builder.py` — add `TestLongevityComponent` class, update `test_all_components_present`

---

### Task 1: Write the failing tests

**Files:**
- Modify: `tests/test_ebs_builder.py`

- [ ] **Step 1: Add a `_run_start_multi` helper and `_agent_state_dead` helper after the existing helpers (around line 109)**

```python
def _run_start_multi(agent_names: list[str], run_id: str = "test") -> dict:
    return {
        "run_id": run_id, "tick": 0, "event_type": "run_start", "agent_id": None,
        "payload": {"config": {"agent_names": agent_names}, "model_id": "test", "world_seed": 1},
    }


def _agent_state_dead(tick: int, agent: str) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "agent_state", "agent_id": agent,
        "payload": {"hunger": 100, "energy": 0, "life": 0, "alive": False},
    }
```

- [ ] **Step 2: Append the `TestLongevityComponent` class at the end of `tests/test_ebs_builder.py`**

```python
# ------------------------------------------------------------------ #
# EBSBuilder — Longevity component
# ------------------------------------------------------------------ #

class TestLongevityComponent:
    def test_all_agents_alive_full_run_population_vitality_is_one(self, tmp_path):
        """1 agent alive all 3 ticks → population_vitality == 1.0."""
        events = [
            _run_start(),           # agent_names = ["Ada"]
            _agent_state(1),        # alive=True
            _agent_state(2),        # alive=True
            _agent_state(3),        # alive=True
            _run_end(tick=3),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        lon = data["components"]["longevity"]
        assert lon["sub_scores"]["population_vitality"] == pytest.approx(1.0)
        assert lon["score"] > 0.0

    def test_agent_dies_halfway_lowers_population_vitality(self, tmp_path):
        """2 agents alive ticks 1-5 then dead ticks 6-10 → population_vitality == 0.5."""
        events = [_run_start_multi(["Ada", "Eve"])]
        for t in range(1, 6):
            events.append(_agent_state(t, "Ada"))
            events.append(_agent_state(t, "Eve"))
        for t in range(6, 11):
            events.append(_agent_state_dead(t, "Ada"))
            events.append(_agent_state_dead(t, "Eve"))
        events.append(_run_end(tick=10))
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        # 10 alive events / (2 agents * 10 ticks) = 0.5
        assert data["components"]["longevity"]["sub_scores"]["population_vitality"] == pytest.approx(0.5)

    def test_more_agents_same_duration_higher_absolute_longevity(self, tmp_path):
        """5 agents all alive 10 ticks scores higher absolute_longevity than 3 agents."""
        def build_run(path: Path, agents: list[str]) -> dict:
            events = [_run_start_multi(agents)]
            for t in range(1, 11):
                for a in agents:
                    events.append(_agent_state(t, a))
            events.append(_run_end(tick=10))
            _write_events(path, events)
            EBSBuilder(path).build()
            return json.loads((path / "metrics" / "ebs.json").read_text())

        data_5 = build_run(tmp_path / "five", ["A", "B", "C", "D", "E"])
        data_3 = build_run(tmp_path / "three", ["A", "B", "C"])
        abs_5 = data_5["components"]["longevity"]["sub_scores"]["absolute_longevity"]
        abs_3 = data_3["components"]["longevity"]["sub_scores"]["absolute_longevity"]
        assert abs_5 > abs_3

    def test_longer_run_higher_absolute_longevity(self, tmp_path):
        """3 agents alive 8000 ticks scores higher absolute_longevity than 500 ticks."""
        def build_run(path: Path, ticks: int) -> dict:
            events = [_run_start_multi(["A", "B", "C"])]
            for t in range(1, ticks + 1):
                for a in ["A", "B", "C"]:
                    events.append(_agent_state(t, a))
            events.append(_run_end(tick=ticks))
            _write_events(path, events)
            EBSBuilder(path).build()
            return json.loads((path / "metrics" / "ebs.json").read_text())

        data_long = build_run(tmp_path / "long", 8000)
        data_short = build_run(tmp_path / "short", 500)
        abs_long = data_long["components"]["longevity"]["sub_scores"]["absolute_longevity"]
        abs_short = data_short["components"]["longevity"]["sub_scores"]["absolute_longevity"]
        assert abs_long > abs_short

    def test_no_agent_state_events_graceful_zero(self, tmp_path):
        """No agent_state events → all longevity sub-scores default to 0.0, no crash."""
        events = [_run_start(), _run_end(tick=10)]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        lon = data["components"]["longevity"]
        assert lon["sub_scores"]["population_vitality"] == 0.0
        assert lon["sub_scores"]["absolute_longevity"] == 0.0
        assert lon["score"] == 0.0

    def test_no_run_end_falls_back_to_max_tick_seen(self, tmp_path):
        """No run_end event → uses max tick seen; computes without crashing."""
        events = [
            _run_start(),   # agent_names = ["Ada"]
            _agent_state(1),
            _agent_state(5),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        lon = data["components"]["longevity"]
        # max_tick_seen=5, initial_agents=1, alive_ticks=2 → pop_vitality = 2/5 = 0.4
        assert lon["sub_scores"]["population_vitality"] == pytest.approx(0.4)
        assert 0.0 <= lon["score"] <= 100.0
```

- [ ] **Step 3: Update `TestOutputSchema.test_all_components_present` to include `"longevity"`**

In `tests/test_ebs_builder.py`, find:
```python
        for key in ("novelty", "utility", "realization", "stability", "autonomy"):
            assert key in data["components"]
```
Replace with:
```python
        for key in ("novelty", "utility", "realization", "stability", "autonomy", "longevity"):
            assert key in data["components"]
```

- [ ] **Step 4: Run the new tests to confirm they fail**

```bash
uv run pytest tests/test_ebs_builder.py::TestLongevityComponent tests/test_ebs_builder.py::TestOutputSchema::test_all_components_present -v
```

Expected: all new tests **FAIL** (KeyError or AssertionError — `"longevity"` not yet present)

---

### Task 2: Implement the Longevity component

**Files:**
- Modify: `simulation/ebs_builder.py`

- [ ] **Step 1: Add `import math` at the top of `simulation/ebs_builder.py`**

Find:
```python
import json
import re
from pathlib import Path
```
Replace with:
```python
import json
import math
import re
from pathlib import Path
```

- [ ] **Step 2: Add the longevity constant after the existing `_HUNGER_*` constants (around line 39)**

Find:
```python
_HUNGER_URGENT_THRESHOLD = 60  # above this → resource-scarce state (environment_contingent_innovation)
_HUNGER_PROACTIVE_THRESHOLD = 60  # below this → hunger non-urgent (proactive move)
```
Replace with:
```python
_HUNGER_URGENT_THRESHOLD = 60  # above this → resource-scarce state (environment_contingent_innovation)
_HUNGER_PROACTIVE_THRESHOLD = 60  # below this → hunger non-urgent (proactive move)

_LONGEVITY_REFERENCE_AGENT_TICKS = 1500  # λ: ~3 agents × 500 ticks baseline
```

- [ ] **Step 3: Replace the `_WEIGHTS` dict with the rebalanced weights**

Find:
```python
_WEIGHTS = {
    "novelty": 0.30,
    "utility": 0.20,
    "realization": 0.20,
    "stability": 0.15,
    "autonomy": 0.15,
}
```
Replace with:
```python
_WEIGHTS = {
    "novelty":     0.25,  # was 0.30
    "utility":     0.17,  # was 0.20
    "realization": 0.17,  # was 0.20
    "stability":   0.13,  # was 0.15
    "autonomy":    0.13,  # was 0.15
    "longevity":   0.15,  # new
}
```

- [ ] **Step 4: Add longevity accumulators at the top of `_compute` (after the existing accumulator declarations)**

Find:
```python
        parse_fails = 0
        action_total = 0
        innovation_attempts = 0
        innovation_approved = 0
```
Replace with:
```python
        parse_fails = 0
        action_total = 0
        innovation_attempts = 0
        innovation_approved = 0
        initial_agents = 0
        total_ticks_from_run_end: int | None = None
        max_tick_seen = 0
```

- [ ] **Step 5: Track `max_tick_seen` on every event and capture `initial_agents` from `run_start`**

Find:
```python
                et = ev.get("event_type")
                tick = ev.get("tick", 0)
                agent_id = ev.get("agent_id")
                p = ev.get("payload", {})

                if et == "run_start":
                    run_id = ev.get("run_id")
```
Replace with:
```python
                et = ev.get("event_type")
                tick = ev.get("tick", 0)
                agent_id = ev.get("agent_id")
                p = ev.get("payload", {})

                if tick > max_tick_seen:
                    max_tick_seen = tick

                if et == "run_start":
                    run_id = ev.get("run_id")
                    initial_agents = len(p.get("config", {}).get("agent_names", []))
```

- [ ] **Step 6: Add `alive` to `state_history` entries and capture `total_ticks` from `run_end`**

Find:
```python
                elif et == "agent_state":
                    if agent_id:
                        state_history.setdefault(agent_id, []).append({
                            "tick": tick,
                            "hunger": p.get("hunger", 0),
                            "energy": p.get("energy", 0),
                            "life": p.get("life", 0),
                        })
```
Replace with:
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
```

Find in the same loop block (the `run_end` handler does not exist yet; the loop currently only has `run_start`, `agent_decision`, `agent_state`, `agent_perception`, `oracle_resolution`, `innovation_attempt`, `innovation_validated`, `custom_action_executed`, `memory_compression_result`). Add a `run_end` handler after `memory_compression_result`:

Find:
```python
                elif et == "memory_compression_result":
                    learnings_log.append({
                        "tick": tick, "agent_id": agent_id,
                        "learnings": p.get("learnings", []),
                    })
```
Replace with:
```python
                elif et == "memory_compression_result":
                    learnings_log.append({
                        "tick": tick, "agent_id": agent_id,
                        "learnings": p.get("learnings", []),
                    })

                elif et == "run_end":
                    total_ticks_from_run_end = p.get("total_ticks")
```

- [ ] **Step 7: Resolve `total_ticks` after the loop and add longevity scoring**

Find the comment `# Final EBS` and the lines immediately above it (Autonomy scoring):

```python
        # Autonomy
        proactive_rate = proactive_moves / total_moves if total_moves else 0.0
        env_contingent_rate = contingent_attempts / n_attempts if n_attempts else 0.0
        autonomy_score = 100 * (0.40 * proactive_rate + 0.30 * env_contingent_rate)

        # Final EBS
```
Replace with:
```python
        # Autonomy
        proactive_rate = proactive_moves / total_moves if total_moves else 0.0
        env_contingent_rate = contingent_attempts / n_attempts if n_attempts else 0.0
        autonomy_score = 100 * (0.40 * proactive_rate + 0.30 * env_contingent_rate)

        # Longevity
        total_ticks = total_ticks_from_run_end if total_ticks_from_run_end is not None else max_tick_seen
        total_agent_ticks = sum(
            sum(1 for s in states if s.get("alive"))
            for states in state_history.values()
        )
        if initial_agents > 0 and total_ticks > 0:
            population_vitality = total_agent_ticks / (initial_agents * total_ticks)
        else:
            population_vitality = 0.0
        absolute_longevity = 1 - math.exp(-total_agent_ticks / _LONGEVITY_REFERENCE_AGENT_TICKS)
        longevity_score = 100 * (0.5 * population_vitality + 0.5 * absolute_longevity)

        # Final EBS
```

- [ ] **Step 8: Update the final EBS computation to include longevity**

Find:
```python
        ebs = (
            _WEIGHTS["novelty"] * novelty_score
            + _WEIGHTS["utility"] * utility_score
            + _WEIGHTS["realization"] * realization_score
            + _WEIGHTS["stability"] * stability_score
            + _WEIGHTS["autonomy"] * autonomy_score
        )
```
Replace with:
```python
        ebs = (
            _WEIGHTS["novelty"] * novelty_score
            + _WEIGHTS["utility"] * utility_score
            + _WEIGHTS["realization"] * realization_score
            + _WEIGHTS["stability"] * stability_score
            + _WEIGHTS["autonomy"] * autonomy_score
            + _WEIGHTS["longevity"] * longevity_score
        )
```

- [ ] **Step 9: Add `longevity` to the output `components` dict**

Find:
```python
                "autonomy": {
                    "score": round(autonomy_score, 2),
                    "weight": _WEIGHTS["autonomy"],
                    "sub_scores": {
                        "proactive_resource_acquisition": round(proactive_rate, 4),
                        "environment_contingent_innovation": round(env_contingent_rate, 4),
                        "self_generated_subgoals": 0.0,
                    },
                },
            },
```
Replace with:
```python
                "autonomy": {
                    "score": round(autonomy_score, 2),
                    "weight": _WEIGHTS["autonomy"],
                    "sub_scores": {
                        "proactive_resource_acquisition": round(proactive_rate, 4),
                        "environment_contingent_innovation": round(env_contingent_rate, 4),
                        "self_generated_subgoals": 0.0,
                    },
                },
                "longevity": {
                    "score": round(longevity_score, 2),
                    "weight": _WEIGHTS["longevity"],
                    "sub_scores": {
                        "population_vitality": round(population_vitality, 4),
                        "absolute_longevity": round(absolute_longevity, 4),
                    },
                },
            },
```

---

### Task 3: Verify and commit

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest tests/test_ebs_builder.py -v
```

Expected: all tests **PASS** including the 6 new `TestLongevityComponent` tests

- [ ] **Step 2: Run the smoke test to confirm end-to-end nothing is broken**

```bash
uv run main.py --no-llm --ticks 5 --agents 1
```

Expected: exits cleanly, no tracebacks

- [ ] **Step 2b: (advisory) Update stale docstring in `TestEBSBuilderEdgeCases.test_empty_events_file`**

The existing docstring says `"Stability defaults to 100 (no failures), contributing 15 pts → ebs == 15.0"`. After rebalancing, stability weight is 0.13 not 0.15. Update the docstring:

Find in `tests/test_ebs_builder.py`:
```python
    def test_empty_events_file(self, tmp_path):
        """build() handles completely empty events.jsonl without crashing.
        Stability defaults to 100 (no failures), contributing 15 pts → ebs == 15.0."""
```
Replace with:
```python
    def test_empty_events_file(self, tmp_path):
        """build() handles completely empty events.jsonl without crashing.
        Stability defaults to 100 (no failures); ebs is > 0."""
```

- [ ] **Step 3: Run the full non-slow test suite**

```bash
uv run pytest -m "not slow"
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add simulation/ebs_builder.py tests/test_ebs_builder.py
git commit -m "feat(ebs): add Longevity component (population_vitality + absolute_longevity, 15% weight)"
```

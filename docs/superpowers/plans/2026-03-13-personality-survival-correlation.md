# Personality-Survival Correlation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist agent personality snapshots in canonical run artifacts and compute a per-run Pearson correlation between each personality trait and survival length, including agents born mid-run.

**Architecture:** Keep the feature inside the existing event-sourced metrics pipeline. `EventEmitter` gets additive personality fields on `run_start` and `agent_birth`; `SimulationEngine` passes initial agent profiles into `run_start`; `MetricsBuilder` stays the single source for `metrics/summary.json`, adding a small personality-survival section computed from event data only. Cornerstone docs are updated after the code lands.

**Tech Stack:** Python 3.12 stdlib (`json`, `statistics`, `dataclasses`), pytest, uv, markdown docs in `project-cornerstone/`

**Spec:** `docs/superpowers/specs/2026-03-13-personality-survival-correlation-design.md`

---

## File Structure

| File | Change | Responsibility |
|------|--------|----------------|
| `simulation/event_emitter.py` | Modify | Add additive personality payloads to `run_start` and `agent_birth` |
| `simulation/engine.py` | Modify | Pass initial agent profiles into `emit_run_start()` in both run entrypoints |
| `simulation/metrics_builder.py` | Modify | Reconstruct entry/death windows and compute `summary["personality_survival"]` |
| `tests/test_event_emitter.py` | Modify | Contract tests for `agent_profiles` and birth personality payloads |
| `tests/test_metrics_builder.py` | Modify | Deterministic unit tests for trait/lifespan correlation, born-agent inclusion, and backward compatibility |
| `tests/test_engine_personality_metrics.py` | Create | End-to-end wiring checks for emitted profiles and generated summary block |
| `project-cornerstone/00-master-plan/MASTER_PLAN.md` | Modify | Record the new metric in the roadmap/current reality |
| `project-cornerstone/00-master-plan/DECISION_LOG.md` | Modify | Log the event-sourced personality-survival analytics decision |
| `project-cornerstone/01-architecture/architecture_context.md` | Modify | Document personality snapshots in the event layer and the new summary metric |

---

## Chunk 1: Capture Personality In Run Artifacts

### Task 1: Extend EventEmitter contracts for personality snapshots

**Files:**
- Modify: `simulation/event_emitter.py`
- Modify: `tests/test_event_emitter.py`

- [ ] **Step 1: Write the failing EventEmitter tests**

Add this import near the top of `tests/test_event_emitter.py`:

```python
from simulation.personality import Personality
```

Update `_mock_agent()` so test doubles can carry a real personality:

```python
def _mock_agent(
    name="Ada",
    life=100.0,
    hunger=5.0,
    energy=90.0,
    x=3,
    y=4,
    alive=True,
    inventory=None,
    personality=None,
):
    agent = MagicMock()
    agent.name = name
    agent.life = life
    agent.hunger = hunger
    agent.energy = energy
    agent.x = x
    agent.y = y
    agent.alive = alive
    agent.inventory.items = inventory or {}
    agent.personality = personality or Personality(
        courage=0.8,
        curiosity=0.3,
        patience=0.6,
        sociability=0.1,
    )
    return agent
```

Add these tests:

```python
class TestRunStartPersonality:
    def test_payload_includes_agent_profiles(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_start(
            ["Ada", "Bruno"],
            "my-model",
            7,
            20,
            20,
            100,
            agent_profiles=[
                {
                    "name": "Ada",
                    "personality": {
                        "courage": 0.8,
                        "curiosity": 0.2,
                        "patience": 0.6,
                        "sociability": 0.4,
                    },
                },
                {
                    "name": "Bruno",
                    "personality": {
                        "courage": 0.3,
                        "curiosity": 0.9,
                        "patience": 0.5,
                        "sociability": 0.1,
                    },
                },
            ],
        )
        em.close()

        profiles = _read_events(tmp_path)[0]["payload"]["config"]["agent_profiles"]
        assert [p["name"] for p in profiles] == ["Ada", "Bruno"]
        assert profiles[0]["personality"]["courage"] == 0.8
        assert profiles[1]["personality"]["sociability"] == 0.1


class TestAgentBirthPersonality:
    def test_birth_payload_includes_personality(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        child = _mock_agent(
            name="Kira",
            x=4,
            y=5,
            personality=Personality(
                courage=0.56,
                curiosity=0.41,
                patience=0.73,
                sociability=0.28,
            ),
        )
        child.generation = 1
        child.born_tick = 12
        child.parent_ids = ["Ada", "Bruno"]

        em.emit_agent_birth(12, child)
        em.close()

        payload = _read_events(tmp_path)[0]["payload"]
        assert payload["personality"] == {
            "courage": 0.56,
            "curiosity": 0.41,
            "patience": 0.73,
            "sociability": 0.28,
        }
```

- [ ] **Step 2: Run the targeted tests and verify they fail**

Run:

```bash
uv run pytest tests/test_event_emitter.py -k "agent_profiles or birth_payload_includes_personality" -v
```

Expected:
- `TypeError` because `emit_run_start()` does not accept `agent_profiles`
- or assertion failure because `emit_agent_birth()` does not emit `personality`

- [ ] **Step 3: Implement the EventEmitter schema changes**

In `simulation/event_emitter.py`:

1. Add `asdict` import:

```python
from dataclasses import asdict
```

2. Extend `emit_run_start()` to accept an optional `agent_profiles` parameter:

```python
def emit_run_start(
    self,
    agent_names: list[str],
    model_id: str,
    world_seed: Optional[int],
    width: int,
    height: int,
    max_ticks: int,
    agent_profiles: Optional[list[dict]] = None,
):
    config = {
        "width": width,
        "height": height,
        "max_ticks": max_ticks,
        "agent_count": len(agent_names),
        "agent_names": agent_names,
    }
    if agent_profiles is not None:
        config["agent_profiles"] = agent_profiles
    self._emit("run_start", 0, {
        "config": config,
        "model_id": model_id,
        "world_seed": world_seed,
    })
```

3. Extend `emit_agent_birth()` to include the child's personality snapshot:

```python
def emit_agent_birth(self, tick: int, agent) -> None:
    self._emit("agent_birth", tick, {
        "child_name": agent.name,
        "generation": agent.generation,
        "born_tick": agent.born_tick,
        "parent_ids": list(agent.parent_ids),
        "pos": [agent.x, agent.y],
        "personality": asdict(agent.personality),
    }, agent_id=agent.name)
```

- [ ] **Step 4: Run the EventEmitter tests and verify they pass**

Run:

```bash
uv run pytest tests/test_event_emitter.py -v
```

Expected: PASS for the full file, including the new personality payload assertions.

- [ ] **Step 5: Commit**

```bash
git add simulation/event_emitter.py tests/test_event_emitter.py
git commit -m "feat: emit personality snapshots in run events"
```

### Task 2: Wire initial agent profiles through the engine

**Files:**
- Modify: `simulation/engine.py`
- Create: `tests/test_engine_personality_metrics.py`

- [ ] **Step 1: Write the failing engine wiring test**

Create `tests/test_engine_personality_metrics.py`:

```python
"""Integration tests for personality metrics wiring in SimulationEngine."""

import json
from pathlib import Path

from simulation.engine import SimulationEngine


def _read_events(run_dir: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]


def _make_engine(tmp_path, monkeypatch, agents=2, ticks=2) -> SimulationEngine:
    monkeypatch.chdir(tmp_path)
    return SimulationEngine(num_agents=agents, use_llm=False, max_ticks=ticks, world_seed=42)


class TestEnginePersonalityEventWiring:
    def test_run_start_includes_initial_agent_profiles(self, tmp_path, monkeypatch):
        engine = _make_engine(tmp_path, monkeypatch, agents=2, ticks=1)
        engine.run()

        run_start = next(
            event
            for event in _read_events(engine.event_emitter.run_dir)
            if event["event_type"] == "run_start"
        )
        profiles = run_start["payload"]["config"]["agent_profiles"]

        assert len(profiles) == 2
        assert {profile["name"] for profile in profiles} == {agent.name for agent in engine.agents}
        assert set(profiles[0]["personality"].keys()) == {
            "courage",
            "curiosity",
            "patience",
            "sociability",
        }
```

- [ ] **Step 2: Run the new engine test and verify it fails**

Run:

```bash
uv run pytest tests/test_engine_personality_metrics.py::TestEnginePersonalityEventWiring::test_run_start_includes_initial_agent_profiles -v
```

Expected: `KeyError: 'agent_profiles'`

- [ ] **Step 3: Implement engine wiring for initial profiles**

In `simulation/engine.py`:

1. Add the import:

```python
from dataclasses import asdict
```

2. Add a focused helper near the other small helpers:

```python
@staticmethod
def _agent_profile(agent) -> dict:
    return {
        "name": agent.name,
        "personality": asdict(agent.personality),
    }
```

3. Pass `agent_profiles` into both `emit_run_start()` call sites:

```python
self.event_emitter.emit_run_start(
    agent_names=[a.name for a in self.agents],
    model_id=self.llm.model if self.llm else "none",
    world_seed=self._world_seed,
    width=self.world.width,
    height=self.world.height,
    max_ticks=self.max_ticks,
    agent_profiles=[self._agent_profile(a) for a in self.agents],
)
```

Apply that change in both `run()` and `run_with_callback()`.

- [ ] **Step 4: Run the engine integration test and verify it passes**

Run:

```bash
uv run pytest tests/test_engine_personality_metrics.py::TestEnginePersonalityEventWiring::test_run_start_includes_initial_agent_profiles -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add simulation/engine.py tests/test_engine_personality_metrics.py
git commit -m "feat: wire initial personality profiles into run start events"
```

---

## Chunk 2: Compute Personality-Survival Summary

### Task 3: Add deterministic MetricsBuilder tests for trait/lifespan correlation

**Files:**
- Modify: `tests/test_metrics_builder.py`

- [ ] **Step 1: Write the failing MetricsBuilder tests**

Add this helper near `_minimal_run()` in `tests/test_metrics_builder.py`:

```python
def _personality_survival_run(run_id: str = "trait-run") -> list[dict]:
    return [
        {
            "run_id": run_id,
            "seed": 42,
            "tick": 0,
            "sim_time": None,
            "event_type": "run_start",
            "agent_id": None,
            "payload": {
                "config": {
                    "width": 15,
                    "height": 15,
                    "max_ticks": 3,
                    "agent_count": 2,
                    "agent_names": ["Ada", "Bruno"],
                    "agent_profiles": [
                        {
                            "name": "Ada",
                            "personality": {
                                "courage": 0.1,
                                "curiosity": 0.9,
                                "patience": 0.2,
                                "sociability": 0.6,
                            },
                        },
                        {
                            "name": "Bruno",
                            "personality": {
                                "courage": 0.9,
                                "curiosity": 0.1,
                                "patience": 0.2,
                                "sociability": 0.2,
                            },
                        },
                    ],
                },
                "model_id": "test-model",
                "world_seed": 42,
            },
        },
        {
            "run_id": run_id,
            "tick": 1,
            "sim_time": {"day": 1, "hour": 6},
            "event_type": "agent_state",
            "agent_id": "Ada",
            "payload": {
                "life": 0,
                "hunger": 100,
                "energy": 0,
                "pos": [1, 1],
                "alive": False,
                "inventory": {},
            },
        },
        {
            "run_id": run_id,
            "tick": 1,
            "sim_time": {"day": 1, "hour": 6},
            "event_type": "agent_state",
            "agent_id": "Bruno",
            "payload": {
                "life": 90,
                "hunger": 5,
                "energy": 80,
                "pos": [2, 2],
                "alive": True,
                "inventory": {},
            },
        },
        {
            "run_id": run_id,
            "tick": 2,
            "sim_time": {"day": 1, "hour": 7},
            "event_type": "agent_birth",
            "agent_id": "Kira",
            "payload": {
                "child_name": "Kira",
                "generation": 1,
                "born_tick": 2,
                "parent_ids": ["Ada", "Bruno"],
                "pos": [3, 3],
                "personality": {
                    "courage": 0.5,
                    "curiosity": 0.5,
                    "patience": 0.2,
                    "sociability": 0.9,
                },
            },
        },
        {
            "run_id": run_id,
            "tick": 3,
            "sim_time": {"day": 1, "hour": 8},
            "event_type": "run_end",
            "agent_id": None,
            "payload": {
                "survivors": ["Bruno", "Kira"],
                "total_ticks": 3,
            },
        },
    ]
```

Add this new test class:

```python
class TestPersonalitySurvivalSummary:
    def test_summary_adds_personality_survival_block(self, tmp_path):
        run_dir = tmp_path / "trait-run"
        _write_events(run_dir, _personality_survival_run())
        MetricsBuilder(run_dir).build()

        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        ps = summary["personality_survival"]

        assert ps["method"] == "pearson_correlation"
        assert ps["lifespan_unit"] == "ticks_alive_since_entry"
        assert ps["sample_size"] == 3
        assert ps["trait_correlations"]["courage"] == 1.0
        assert ps["trait_correlations"]["curiosity"] == -1.0
        assert ps["trait_correlations"]["patience"] is None
        assert ps["best_trait"] == "courage"
        assert ps["best_correlation"] == 1.0

    def test_survivors_and_born_agents_use_run_end_when_no_death_tick(self, tmp_path):
        run_dir = tmp_path / "trait-run"
        _write_events(run_dir, _personality_survival_run())
        MetricsBuilder(run_dir).build()

        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        assert summary["personality_survival"]["sample_size"] == 3

    def test_old_runs_without_agent_profiles_return_null_personality_summary(self, tmp_path):
        run_dir = tmp_path / "legacy-run"
        _write_events(run_dir, _minimal_run())
        MetricsBuilder(run_dir).build()

        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        ps = summary["personality_survival"]

        assert ps["sample_size"] == 0
        assert ps["trait_correlations"] == {
            "courage": None,
            "curiosity": None,
            "patience": None,
            "sociability": None,
        }
        assert ps["best_trait"] is None
        assert ps["best_correlation"] is None

    def test_one_usable_agent_returns_null_correlations(self, tmp_path):
        run_dir = tmp_path / "one-agent"
        one_agent_events = [
            {
                "run_id": "one-agent",
                "seed": 42,
                "tick": 0,
                "sim_time": None,
                "event_type": "run_start",
                "agent_id": None,
                "payload": {
                    "config": {
                        "width": 15,
                        "height": 15,
                        "max_ticks": 1,
                        "agent_count": 1,
                        "agent_names": ["Ada"],
                        "agent_profiles": [
                            {
                                "name": "Ada",
                                "personality": {
                                    "courage": 0.1,
                                    "curiosity": 0.9,
                                    "patience": 0.2,
                                    "sociability": 0.6,
                                },
                            }
                        ],
                    },
                    "model_id": "test-model",
                    "world_seed": 42,
                },
            },
            {
                "run_id": "one-agent",
                "tick": 1,
                "sim_time": {"day": 1, "hour": 6},
                "event_type": "run_end",
                "agent_id": None,
                "payload": {
                    "survivors": ["Ada"],
                    "total_ticks": 1,
                },
            },
        ]
        _write_events(run_dir, one_agent_events)
        MetricsBuilder(run_dir).build()

        summary = json.loads((run_dir / "metrics" / "summary.json").read_text())
        assert summary["personality_survival"]["sample_size"] == 1
        assert summary["personality_survival"]["trait_correlations"]["courage"] is None
        assert summary["personality_survival"]["best_trait"] is None
```

- [ ] **Step 2: Run the new MetricsBuilder tests and verify they fail**

Run:

```bash
uv run pytest tests/test_metrics_builder.py -k personality_survival -v
```

Expected: `KeyError: 'personality_survival'`

- [ ] **Step 3: Implement the personality-survival summary in MetricsBuilder**

In `simulation/metrics_builder.py`:

1. Add the stdlib import:

```python
import statistics
```

2. Add a private helper for the null/default block:

```python
def _empty_personality_survival(self, sample_size: int = 0) -> dict:
    return {
        "method": "pearson_correlation",
        "lifespan_unit": "ticks_alive_since_entry",
        "sample_size": sample_size,
        "trait_correlations": {
            "courage": None,
            "curiosity": None,
            "patience": None,
            "sociability": None,
        },
        "best_trait": None,
        "best_correlation": None,
    }
```

3. Add accumulators inside `_compute()`:

```python
agent_traits: dict[str, dict[str, float]] = {}
agent_entry_tick: dict[str, int] = {}
agent_terminal_tick: dict[str, int] = {}
```

4. Extend event parsing:

```python
if et == "run_start":
    run_id = ev.get("run_id")
    cfg = ev.get("payload", {}).get("config", {})
    initial_agents = set(cfg.get("agent_names", []))
    for profile in cfg.get("agent_profiles", []):
        name = profile.get("name")
        personality = profile.get("personality")
        if name and isinstance(personality, dict):
            agent_traits[name] = personality
            agent_entry_tick[name] = 1

elif et == "agent_birth":
    payload = ev.get("payload", {})
    child_name = payload.get("child_name") or ev.get("agent_id")
    personality = payload.get("personality")
    born_tick = payload.get("born_tick", tick)
    if child_name and isinstance(personality, dict):
        agent_traits[child_name] = personality
        agent_entry_tick[child_name] = born_tick

elif et == "agent_state":
    ...
    if agent_id:
        was_alive = prev_alive.get(agent_id, True)
        is_alive = p.get("alive", True)
        if was_alive and not is_alive:
            b["deaths"] += 1
            deaths += 1
            agent_terminal_tick.setdefault(agent_id, tick)
        prev_alive[agent_id] = is_alive
```

5. After the single pass, build the sample vectors:

```python
personality_survival = self._empty_personality_survival()
rows: list[tuple[dict[str, float], int]] = []

for agent_name, traits in agent_traits.items():
    entry_tick = agent_entry_tick.get(agent_name)
    if entry_tick is None:
        continue
    terminal_tick = agent_terminal_tick.get(agent_name, total_ticks)
    lifespan_ticks = terminal_tick - entry_tick + 1
    if lifespan_ticks <= 0:
        continue
    rows.append((traits, lifespan_ticks))

personality_survival = self._empty_personality_survival(sample_size=len(rows))
if len(rows) >= 2:
    lifespans = [lifespan for _, lifespan in rows]
    for trait in ("courage", "curiosity", "patience", "sociability"):
        values = [traits.get(trait) for traits, _ in rows]
        if any(v is None for v in values):
            continue
        try:
            coefficient = round(statistics.correlation(values, lifespans), 4)
        except statistics.StatisticsError:
            coefficient = None
        personality_survival["trait_correlations"][trait] = coefficient

    valid = {
        trait: value
        for trait, value in personality_survival["trait_correlations"].items()
        if value is not None
    }
    if valid:
        best_trait = max(valid, key=valid.get)
        personality_survival["best_trait"] = best_trait
        personality_survival["best_correlation"] = valid[best_trait]
```

6. Add the block to `summary`:

```python
"personality_survival": personality_survival,
```

Keep the existing `agents`, `actions`, and `innovations` sections unchanged.

- [ ] **Step 4: Run the MetricsBuilder tests and verify they pass**

Run:

```bash
uv run pytest tests/test_metrics_builder.py -v
```

Expected: PASS for the full file, including the new personality-survival tests and all existing summary/timeseries assertions.

- [ ] **Step 5: Commit**

```bash
git add simulation/metrics_builder.py tests/test_metrics_builder.py
git commit -m "feat: add personality survival correlation metric"
```

### Task 4: Add an end-to-end run artifact smoke test for the summary block

**Files:**
- Modify: `tests/test_engine_personality_metrics.py`

- [ ] **Step 1: Extend the engine integration test file with a summary assertion**

Add this test to `tests/test_engine_personality_metrics.py`:

```python
class TestEnginePersonalityMetricArtifacts:
    def test_run_builds_personality_survival_summary(self, tmp_path, monkeypatch):
        engine = _make_engine(tmp_path, monkeypatch, agents=2, ticks=2)
        engine.run()

        summary = json.loads(
            (engine.event_emitter.run_dir / "metrics" / "summary.json").read_text(encoding="utf-8")
        )

        assert "personality_survival" in summary
        assert summary["personality_survival"]["method"] == "pearson_correlation"
        assert summary["personality_survival"]["sample_size"] == 2
```

- [ ] **Step 2: Run the engine integration file and verify it passes**

Run:

```bash
uv run pytest tests/test_engine_personality_metrics.py -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_engine_personality_metrics.py
git commit -m "test: cover personality metric run artifacts end to end"
```

---

## Chunk 3: Documentation And Final Verification

### Task 5: Update cornerstone docs for the new metric

**Files:**
- Modify: `project-cornerstone/00-master-plan/MASTER_PLAN.md`
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Modify: `project-cornerstone/01-architecture/architecture_context.md`

- [ ] **Step 1: Update the master plan**

In `project-cornerstone/00-master-plan/MASTER_PLAN.md`, extend the metrics maturity wording so the current analysis surface explicitly includes personality-to-survival analytics. Keep the change additive and high-level, for example:

```markdown
1. **Metrics maturity:** standard KPI schema (survival, innovation utility, cooperation, lineage fitness, personality-to-survival correlation)
```

- [ ] **Step 2: Add a decision log entry**

Append a new decision entry to `project-cornerstone/00-master-plan/DECISION_LOG.md` using the existing format:

```markdown
### DEC-036: Personality-survival analytics stay event-sourced
- **Date**: 2026-03-13
- **Context**: Personality traits influence behavior, but run artifacts did not preserve trait snapshots, so there was no deterministic way to analyze which traits align with longer survival.
- **Decision**: Persist personality snapshots once per agent in canonical run events (`run_start` for initial agents, `agent_birth` for born agents) and compute per-run Pearson correlations in `metrics/summary.json`.
- **Rejected alternatives**: Reading mutable external files such as lineage state, storing per-tick personality snapshots, or introducing a separate analytics builder for this narrow metric.
- **Consequences**: Run artifacts remain self-contained for this metric, born agents are included, and old runs degrade cleanly to null coefficients when trait snapshots are unavailable.
```

- [ ] **Step 3: Update the architecture context**

In `project-cornerstone/01-architecture/architecture_context.md`, update:

1. The Event Layer bullets to mention personality snapshots on lifecycle events.
2. The `simulation/metrics_builder.py` bullet to mention the new `personality_survival` summary block.

Keep the edits concise and codebase-aligned.

- [ ] **Step 4: Commit**

```bash
git add project-cornerstone/00-master-plan/MASTER_PLAN.md project-cornerstone/00-master-plan/DECISION_LOG.md project-cornerstone/01-architecture/architecture_context.md
git commit -m "docs: record personality survival analytics"
```

### Task 6: Final verification before completion

**Files:**
- Verify only; no planned file edits

- [ ] **Step 1: Run targeted tests**

Run:

```bash
uv run pytest tests/test_event_emitter.py tests/test_metrics_builder.py tests/test_engine_personality_metrics.py -v
```

Expected: PASS

- [ ] **Step 2: Run the required fast suite**

Run:

```bash
uv run pytest -m "not slow"
```

Expected: PASS

- [ ] **Step 3: Run a no-LLM smoke simulation and inspect artifacts**

Run:

```bash
uv run main.py --no-llm --ticks 5 --agents 2
```

Expected:
- simulation completes without crashing
- the newest run directory contains `events.jsonl` and `metrics/summary.json`
- `metrics/summary.json` includes `personality_survival`

- [ ] **Step 4: Commit the final verified state**

```bash
git status --short
```

Expected:
- no unexpected modified files remain
- if all earlier task-level commits were made, the worktree should already be clean here

- [ ] **Step 5: Record verification evidence in the handoff**

Capture in the final execution summary:
- exact test commands run
- whether the smoke run was completed
- location of the generated `summary.json`

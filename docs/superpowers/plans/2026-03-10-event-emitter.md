# EventEmitter (Canonical JSONL) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the opt-in `AuditRecorder` with an always-on `EventEmitter` that writes a canonical `events.jsonl` stream to `data/runs/<run_id>/` every run.

**Architecture:** A new `EventEmitter` class is created in `simulation/event_emitter.py`. It writes `meta.json` and `events.jsonl` (line-buffered) to a UUID-keyed directory under `data/runs/`. The engine creates the emitter at init and calls typed emit methods at five points in the tick loop. The old `AuditRecorder` and its comparison CLI are deleted.

**Tech Stack:** Python stdlib only (`json`, `uuid`, `datetime`, `pathlib`). No new dependencies. Tests use `pytest` with `tmp_path` and `unittest.mock.MagicMock`.

**Spec:** `docs/plans/2026-03-10-metrics.md`, approved design in `/home/gusy/.claude/plans/dynamic-orbiting-clarke.md`

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `simulation/event_emitter.py` | EventEmitter class — all JSONL emission logic |
| Create | `tests/test_event_emitter.py` | Unit tests for EventEmitter in isolation |
| Modify | `simulation/engine.py` | Wire EventEmitter; remove AuditRecorder |
| Modify | `main.py` | Remove `--audit` flag |
| Delete | `simulation/audit_recorder.py` | Replaced by EventEmitter |
| Delete | `simulation/audit_compare.py` | Metrics layer will replace this in PR3 |
| Delete | `tests/test_audit.py` | Tests replaced by test_event_emitter.py |
| Modify | `project-cornerstone/00-master-plan/DECISION_LOG.md` | Add DEC-030 |
| Modify | `project-cornerstone/01-architecture/architecture_context.md` | Update audit references |

---

## Chunk 1: EventEmitter class + tests

### Task 1: Create `simulation/event_emitter.py`

**Files:**
- Create: `simulation/event_emitter.py`

- [ ] **Step 1: Write `simulation/event_emitter.py`**

```python
"""
Canonical event emitter: writes an always-on JSONL event stream per run.

Output: data/runs/<run_id>/
  meta.json     — run config, model, seed, timestamp (written at init)
  events.jsonl  — one JSON object per line, the authoritative data source
"""

import datetime
import json
from pathlib import Path
from typing import Optional

from simulation.config import BASE_ACTIONS
from simulation.day_cycle import DayCycle

_BASE_ACTIONS_SET: frozenset[str] = frozenset(BASE_ACTIONS)


class EventEmitter:
    """Writes a canonical JSONL event stream and meta.json for each run.

    Creates data/runs/<run_id>/ on init and keeps events.jsonl open
    (line-buffered) until close() is called.
    """

    def __init__(
        self,
        run_id: str,
        seed: Optional[int],
        world_width: int,
        world_height: int,
        max_ticks: int,
        agent_count: int,
        agent_names: list[str],
        model_id: str,
        day_cycle: DayCycle,
    ):
        self.run_id = run_id
        self.seed = seed
        self._day_cycle = day_cycle

        run_dir = Path("data") / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Write meta.json immediately so it's available even if the run crashes
        meta = {
            "run_id": run_id,
            "seed": seed,
            "width": world_width,
            "height": world_height,
            "max_ticks": max_ticks,
            "agent_count": agent_count,
            "agent_names": agent_names,
            "model_id": model_id,
            "created_at": datetime.datetime.now().isoformat() + "Z",
        }
        (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        # Open events.jsonl with line-buffering so each write flushes automatically
        self._fh = (run_dir / "events.jsonl").open("w", encoding="utf-8", buffering=1)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _sim_time(self, tick: int) -> Optional[dict]:
        """Return {"day": N, "hour": H} for tick > 0, None for tick == 0."""
        if tick == 0:
            return None
        return {"day": self._day_cycle.get_day(tick), "hour": self._day_cycle.get_hour(tick)}

    def _emit(self, event_type: str, tick: int, payload: dict, agent_id: Optional[str] = None):
        event = {
            "run_id": self.run_id,
            "seed": self.seed,
            "tick": tick,
            "sim_time": self._sim_time(tick),
            "event_type": event_type,
            "agent_id": agent_id,
            "payload": payload,
        }
        self._fh.write(json.dumps(event) + "\n")

    @staticmethod
    def _action_origin(action_name: str) -> str:
        return "base" if action_name in _BASE_ACTIONS_SET else "innovation"

    # ------------------------------------------------------------------ #
    # Public emit methods (called from engine.py)
    # ------------------------------------------------------------------ #

    def emit_run_start(
        self,
        agent_names: list[str],
        model_id: str,
        world_seed: Optional[int],
        width: int,
        height: int,
        max_ticks: int,
    ):
        """Emit run_start as the first event (tick=0, sim_time=None)."""
        self._emit("run_start", 0, {
            "config": {
                "width": width,
                "height": height,
                "max_ticks": max_ticks,
                "agent_count": len(agent_names),
                "agent_names": agent_names,
            },
            "model_id": model_id,
            "world_seed": world_seed,
        })

    def emit_agent_decision(
        self,
        tick: int,
        agent_name: str,
        action: dict,
        parse_ok: bool,
    ):
        """Emit after agent.decide_action(). action must have _llm_trace stripped."""
        action_name = action.get("action", "none")
        self._emit("agent_decision", tick, {
            "parsed_action": action,
            "parse_ok": parse_ok,
            "action_origin": self._action_origin(action_name),
        }, agent_id=agent_name)

    def emit_oracle_resolution(self, tick: int, agent_name: str, result: dict):
        """Emit after oracle.resolve_action(). Normalises missing effect keys to 0."""
        effects = result.get("effects", {})
        self._emit("oracle_resolution", tick, {
            "success": result["success"],
            "effects": {
                "hunger": effects.get("hunger", 0),
                "energy": effects.get("energy", 0),
                "life": effects.get("life", 0),
            },
        }, agent_id=agent_name)

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

    def emit_run_end(self, tick: int, survivors: list[str], total_ticks: int):
        """Emit run_end as the last event before close()."""
        self._emit("run_end", tick, {
            "survivors": survivors,
            "total_ticks": total_ticks,
        })

    def close(self):
        """Flush and close the events.jsonl file handle. Safe to call twice."""
        if self._fh and not self._fh.closed:
            self._fh.close()
```

---

### Task 2: Write tests for EventEmitter

**Files:**
- Create: `tests/test_event_emitter.py`

- [ ] **Step 1: Write `tests/test_event_emitter.py`**

```python
"""Tests for simulation/event_emitter.py."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from simulation.config import BASE_ACTIONS
from simulation.day_cycle import DayCycle
from simulation.event_emitter import EventEmitter


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _make_emitter(tmp_path, monkeypatch, run_id="test-run-1234", seed=42):
    monkeypatch.chdir(tmp_path)
    day_cycle = DayCycle(start_hour=6)
    em = EventEmitter(
        run_id=run_id,
        seed=seed,
        world_width=15,
        world_height=15,
        max_ticks=72,
        agent_count=3,
        agent_names=["Ada", "Bruno", "Clara"],
        model_id="test-model",
        day_cycle=day_cycle,
    )
    return em


def _mock_agent(name="Ada", life=100.0, hunger=5.0, energy=90.0, x=3, y=4, alive=True, inventory=None):
    agent = MagicMock()
    agent.name = name
    agent.life = life
    agent.hunger = hunger
    agent.energy = energy
    agent.x = x
    agent.y = y
    agent.alive = alive
    agent.inventory.items = inventory or {}
    return agent


def _read_events(tmp_path, run_id="test-run-1234") -> list[dict]:
    path = tmp_path / "data" / "runs" / run_id / "events.jsonl"
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line]


# ------------------------------------------------------------------ #
# meta.json
# ------------------------------------------------------------------ #

class TestMeta:
    def test_meta_json_created(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.close()
        meta_path = tmp_path / "data" / "runs" / "test-run-1234" / "meta.json"
        assert meta_path.exists()

    def test_meta_json_fields(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch, seed=99)
        em.close()
        meta = json.loads((tmp_path / "data" / "runs" / "test-run-1234" / "meta.json").read_text())
        assert meta["run_id"] == "test-run-1234"
        assert meta["seed"] == 99
        assert meta["width"] == 15
        assert meta["height"] == 15
        assert meta["max_ticks"] == 72
        assert meta["agent_count"] == 3
        assert meta["agent_names"] == ["Ada", "Bruno", "Clara"]
        assert meta["model_id"] == "test-model"
        assert "created_at" in meta

    def test_events_jsonl_created(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.close()
        assert (tmp_path / "data" / "runs" / "test-run-1234" / "events.jsonl").exists()

    def test_meta_created_before_events(self, tmp_path, monkeypatch):
        """meta.json must exist even if the process crashes before any events."""
        em = _make_emitter(tmp_path, monkeypatch)
        # Don't emit anything — meta should still be there
        meta_path = tmp_path / "data" / "runs" / "test-run-1234" / "meta.json"
        assert meta_path.exists()
        em.close()


# ------------------------------------------------------------------ #
# run_start
# ------------------------------------------------------------------ #

class TestRunStart:
    def test_emits_one_line(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_start(["Ada", "Bruno"], "m", 42, 15, 15, 72)
        em.close()
        events = _read_events(tmp_path)
        assert len(events) == 1

    def test_event_type(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_start(["Ada"], "m", None, 10, 10, 50)
        em.close()
        assert _read_events(tmp_path)[0]["event_type"] == "run_start"

    def test_tick_zero_sim_time_null(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_start(["Ada"], "m", None, 10, 10, 50)
        em.close()
        ev = _read_events(tmp_path)[0]
        assert ev["tick"] == 0
        assert ev["sim_time"] is None

    def test_agent_id_null(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_start(["Ada"], "m", None, 10, 10, 50)
        em.close()
        assert _read_events(tmp_path)[0]["agent_id"] is None

    def test_payload_fields(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_start(["Ada", "Bruno"], "my-model", 7, 20, 20, 100)
        em.close()
        p = _read_events(tmp_path)[0]["payload"]
        assert p["config"]["width"] == 20
        assert p["config"]["agent_count"] == 2
        assert p["model_id"] == "my-model"
        assert p["world_seed"] == 7


# ------------------------------------------------------------------ #
# agent_decision
# ------------------------------------------------------------------ #

class TestAgentDecision:
    @pytest.mark.parametrize("base_action", BASE_ACTIONS)
    def test_base_action_origin(self, tmp_path, monkeypatch, base_action):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_agent_decision(1, "Ada", {"action": base_action}, parse_ok=True)
        em.close()
        ev = _read_events(tmp_path)[0]
        assert ev["payload"]["action_origin"] == "base"

    def test_innovation_action_origin(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_agent_decision(1, "Ada", {"action": "dance_with_wolves"}, parse_ok=True)
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["action_origin"] == "innovation"

    def test_parse_ok_true(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_agent_decision(1, "Ada", {"action": "move"}, parse_ok=True)
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["parse_ok"] is True

    def test_parse_ok_false(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_agent_decision(1, "Ada", {"action": "eat"}, parse_ok=False)
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["parse_ok"] is False

    def test_parsed_action_in_payload(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        action = {"action": "move", "direction": "north", "reason": "explore"}
        em.emit_agent_decision(2, "Bruno", action, parse_ok=True)
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["parsed_action"]["direction"] == "north"

    def test_agent_id_set(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_agent_decision(1, "Bruno", {"action": "eat"}, parse_ok=True)
        em.close()
        assert _read_events(tmp_path)[0]["agent_id"] == "Bruno"

    def test_sim_time_computed(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_agent_decision(1, "Ada", {"action": "move"}, parse_ok=True)
        em.close()
        # DayCycle(start_hour=6): tick=1 → hour=6, day=1
        st = _read_events(tmp_path)[0]["sim_time"]
        assert st == {"day": 1, "hour": 6}


# ------------------------------------------------------------------ #
# oracle_resolution
# ------------------------------------------------------------------ #

class TestOracleResolution:
    def test_success_true(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_oracle_resolution(1, "Ada", {"success": True, "effects": {"energy": -3}})
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["success"] is True

    def test_effects_normalized(self, tmp_path, monkeypatch):
        """Missing effect keys should default to 0."""
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_oracle_resolution(1, "Ada", {"success": True, "effects": {"energy": -3}})
        em.close()
        effects = _read_events(tmp_path)[0]["payload"]["effects"]
        assert effects["energy"] == -3
        assert effects["hunger"] == 0
        assert effects["life"] == 0

    def test_success_false(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_oracle_resolution(1, "Ada", {"success": False, "effects": {}})
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["success"] is False


# ------------------------------------------------------------------ #
# agent_state
# ------------------------------------------------------------------ #

class TestAgentState:
    def test_state_fields(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        agent = _mock_agent(life=95.0, hunger=20.0, energy=60.0, x=5, y=7, alive=True,
                             inventory={"fruit": 2})
        em.emit_agent_state(1, agent)
        em.close()
        p = _read_events(tmp_path)[0]["payload"]
        assert p["life"] == 95.0
        assert p["hunger"] == 20.0
        assert p["energy"] == 60.0
        assert p["pos"] == [5, 7]
        assert p["alive"] is True
        assert p["inventory"] == {"fruit": 2}

    def test_empty_inventory(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        agent = _mock_agent()
        em.emit_agent_state(1, agent)
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["inventory"] == {}

    def test_dead_agent(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        agent = _mock_agent(life=0, alive=False)
        em.emit_agent_state(5, agent)
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["alive"] is False


# ------------------------------------------------------------------ #
# run_end
# ------------------------------------------------------------------ #

class TestRunEnd:
    def test_event_type(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_end(10, ["Ada"], 10)
        em.close()
        assert _read_events(tmp_path)[0]["event_type"] == "run_end"

    def test_survivors(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_end(50, ["Ada", "Clara"], 50)
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["survivors"] == ["Ada", "Clara"]

    def test_total_ticks(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_end(72, [], 72)
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["total_ticks"] == 72


# ------------------------------------------------------------------ #
# Integration / ordering
# ------------------------------------------------------------------ #

class TestIntegration:
    def test_full_sequence_ordering(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_start(["Ada"], "m", 1, 10, 10, 5)
        em.emit_agent_decision(1, "Ada", {"action": "move"}, parse_ok=True)
        em.emit_oracle_resolution(1, "Ada", {"success": True, "effects": {}})
        em.emit_agent_state(1, _mock_agent())
        em.emit_run_end(1, ["Ada"], 1)
        em.close()
        types = [e["event_type"] for e in _read_events(tmp_path)]
        assert types == ["run_start", "agent_decision", "oracle_resolution", "agent_state", "run_end"]

    def test_run_id_consistent(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch, run_id="my-run-abc")
        em.emit_run_start(["Ada"], "m", None, 10, 10, 5)
        em.emit_agent_decision(1, "Ada", {"action": "eat"}, parse_ok=True)
        em.emit_run_end(1, ["Ada"], 1)
        em.close()
        for ev in _read_events(tmp_path, run_id="my-run-abc"):
            assert ev["run_id"] == "my-run-abc"

    def test_close_idempotent(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.close()
        em.close()  # must not raise

    def test_sim_time_night(self, tmp_path, monkeypatch):
        """tick=16 with start_hour=6 → hour=21 (night)."""
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_agent_decision(16, "Ada", {"action": "rest"}, parse_ok=True)
        em.close()
        st = _read_events(tmp_path)[0]["sim_time"]
        assert st["hour"] == 21
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd /home/gusy/emerge
uv run pytest tests/test_event_emitter.py -v
```

Expected: all tests pass. If `simulation/event_emitter.py` is correctly written, this should be fully green.

- [ ] **Step 3: Commit**

```bash
git add simulation/event_emitter.py tests/test_event_emitter.py
git commit -m "feat: add EventEmitter for canonical JSONL event stream"
```

---

## Chunk 2: Wire EventEmitter into engine + clean up

### Task 3: Update `simulation/engine.py`

**Files:**
- Modify: `simulation/engine.py`

The engine has three areas to change: imports/init, `run()`, and `_run_tick()`.

- [ ] **Step 1: Update imports in `engine.py` (top of file, ~line 22)**

Replace:
```python
from simulation.audit_recorder import AuditRecorder
```
With:
```python
import uuid
from simulation.event_emitter import EventEmitter
```

- [ ] **Step 2: Update `__init__` signature — remove `audit` parameter (~line 40)**

Remove `audit: bool = False,` from the parameter list.

- [ ] **Step 3: Replace the `self.recorder` block in `__init__` (~lines 102–112)**

Remove:
```python
        # Audit recorder
        self.recorder: Optional[AuditRecorder] = None
        if audit:
            audit_config = {
                "max_ticks": max_ticks,
                "num_agents": num_agents,
                "use_llm": self.use_llm,
                "world_seed": world_seed,
                "world_size": f"{world_width}x{world_height}",
            }
            self.recorder = AuditRecorder(self.sim_logger.run_dir, audit_config)
```

Replace with:
```python
        # Always-on canonical event emitter (data/runs/<run_id>/)
        self.run_id = str(uuid.uuid4())
        _model_id = self.llm.model if self.llm else "none"
        self.event_emitter = EventEmitter(
            run_id=self.run_id,
            seed=world_seed,
            world_width=world_width,
            world_height=world_height,
            max_ticks=max_ticks,
            agent_count=len(self.agents),
            agent_names=[a.name for a in self.agents],
            model_id=_model_id,
            day_cycle=self.day_cycle,
        )
```

- [ ] **Step 4: Update `run()` — emit run_start and run_end (~lines 119–147)**

After `self._log_overview_start()` (around line 122), add:
```python
        self.event_emitter.emit_run_start(
            agent_names=[a.name for a in self.agents],
            model_id=self.llm.model if self.llm else "none",
            world_seed=self._world_seed,
            width=self.world.width,
            height=self.world.height,
            max_ticks=self.max_ticks,
        )
```

In the `finally` block (after `self.lineage.save(...)`), add:
```python
            survivors = [a.name for a in self.agents if a.alive]
            self.event_emitter.emit_run_end(self.current_tick, survivors, self.current_tick)
            self.event_emitter.close()
```

- [ ] **Step 5: Update `_run_tick()` — remove recorder snapshot, add 3 emit calls**

**5a.** Remove the audit snapshot block (~lines 185–188):
```python
            # Audit: snapshot stats before action
            if self.recorder:
                stats_before = {"life": agent.life, "hunger": agent.hunger, "energy": agent.energy}
                position_before = (agent.x, agent.y)
```

**5b.** After `action.pop("_llm_trace", None)` and the `action_source` assignment (~line 205), add:
```python
            self.event_emitter.emit_agent_decision(
                tick, agent.name, action, parse_ok=(action_source == "llm")
            )
```

**5c.** After `result = self.oracle.resolve_action(agent, action, tick)` (~line 220), add:
```python
            self.event_emitter.emit_oracle_resolution(tick, agent.name, result)
```

**5d.** After `agent.apply_tick_effects()` (~line 273), replace the entire `if self.recorder:` block (~lines 293–308):
```python
            # Audit: record event after all effects applied
            if self.recorder:
                stats_after = {"life": agent.life, "hunger": agent.hunger, "energy": agent.energy}
                self.recorder.record_event(
                    ...
                )
```
With:
```python
            self.event_emitter.emit_agent_state(tick, agent)
```

- [ ] **Step 6: Check for any remaining `self.recorder` references in engine.py**

```bash
grep -n "recorder" /home/gusy/emerge/simulation/engine.py
```

Expected: zero matches. If any remain, remove them.

---

### Task 4: Update `main.py`

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Remove `--audit` argument (~line 42)**

Remove this line:
```python
    parser.add_argument("--audit", action="store_true", help="Record behavioral audit data for prompt A/B testing")
```

- [ ] **Step 2: Remove `audit=args.audit` from engine constructor (~line 100)**

Remove `audit=args.audit,` from the `SimulationEngine(...)` call.

---

### Task 5: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
cd /home/gusy/emerge
uv run pytest -m "not slow" -v
```

Expected: all tests pass. The existing tests in `test_visual_logging.py`, `test_day_cycle.py`, `test_memory.py`, `test_wandb_logger.py` should be unaffected.

- [ ] **Step 2: Smoke test — verify events.jsonl is created**

```bash
uv run main.py --no-llm --ticks 5 --agents 2
```

Then validate output:
```bash
python3 -c "
import json, glob
files = glob.glob('data/runs/*/events.jsonl')
assert files, 'No events.jsonl found!'
lines = open(files[0]).readlines()
events = [json.loads(l) for l in lines]
types = [e['event_type'] for e in events]
print('Event types:', types)
assert types[0] == 'run_start', f'First event not run_start: {types[0]}'
assert types[-1] == 'run_end', f'Last event not run_end: {types[-1]}'
print('OK — events.jsonl valid')
"
```

Expected output: `Event types: ['run_start', 'agent_decision', 'oracle_resolution', 'agent_state', ...]` ending with `run_end`.

- [ ] **Step 3: Commit**

```bash
git add simulation/engine.py main.py
git commit -m "feat: wire EventEmitter into engine, remove --audit flag"
```

---

### Task 6: Delete old audit files

- [ ] **Step 1: Delete the three old files**

```bash
rm /home/gusy/emerge/simulation/audit_recorder.py
rm /home/gusy/emerge/simulation/audit_compare.py
rm /home/gusy/emerge/tests/test_audit.py
```

- [ ] **Step 2: Run tests again to confirm clean**

```bash
uv run pytest -m "not slow" -v
```

Expected: all tests pass. No import errors from deleted files.

- [ ] **Step 3: Commit**

```bash
git add -u
git commit -m "chore: delete AuditRecorder, audit_compare, and test_audit (replaced by EventEmitter)"
```

---

## Chunk 3: Cornerstone docs update

### Task 7: Update DECISION_LOG.md

**Files:**
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`

- [ ] **Step 1: Add new decision entry**

Find the highest existing DEC number, then append:

```markdown
### DEC-030: Replace AuditRecorder with always-on canonical EventEmitter

**Date:** 2026-03-10
**Status:** Implemented

**Decision:** Replace the opt-in `AuditRecorder` (activated via `--audit`) with a new always-on `EventEmitter` that writes to `data/runs/<run_id>/events.jsonl` every run.

**Motivation:** The metrics plan (docs/plans/2026-03-10-metrics.md) requires a canonical, always-present event stream as the authoritative data source for all computed metrics. The old AuditRecorder had a narrow per-agent-per-tick schema and was buried in the `logs/` directory.

**Key changes:**
- `simulation/event_emitter.py` — new class, writes `meta.json` + `events.jsonl`
- Output directory: `data/runs/<run_id>/` (UUID-keyed, not timestamp-keyed)
- Event types (PR1): `run_start`, `agent_decision`, `oracle_resolution`, `agent_state`, `run_end`
- `action_origin` field: `"base"` for built-in actions, `"innovation"` for custom actions
- `simulation/audit_recorder.py` and `simulation/audit_compare.py` deleted

**Trade-offs:** Slight I/O overhead on every run (minimal; line-buffered). The A/B comparison CLI (`audit_compare.py`) is lost — a future metrics layer (PR3) will replace it by reading from `events.jsonl`.
```

---

### Task 8: Update architecture_context.md

**Files:**
- Modify: `project-cornerstone/01-architecture/architecture_context.md`

- [ ] **Step 1: Find and update AuditRecorder references**

```bash
grep -n "audit\|AuditRecorder" /home/gusy/emerge/project-cornerstone/01-architecture/architecture_context.md
```

Replace references to `AuditRecorder` / `--audit` / `audit/events.jsonl` with `EventEmitter` / always-on / `data/runs/<run_id>/events.jsonl`.

- [ ] **Step 2: Commit cornerstone updates**

```bash
git add project-cornerstone/
git commit -m "docs: update cornerstone for EventEmitter (DEC-030)"
```

---

## Final Verification

```bash
# Full test suite
uv run pytest -m "not slow" -v

# Smoke test
uv run main.py --no-llm --ticks 10 --agents 3

# Validate JSONL
python3 -c "
import json, glob, sys
files = sorted(glob.glob('data/runs/*/events.jsonl'))
f = files[-1]
print('Checking:', f)
events = [json.loads(l) for l in open(f)]
run_ids = {e['run_id'] for e in events}
assert len(run_ids) == 1, f'Multiple run_ids: {run_ids}'
assert events[0]['event_type'] == 'run_start'
assert events[-1]['event_type'] == 'run_end'
print(f'OK — {len(events)} events, run_id={run_ids.pop()}')
"

# Check meta.json
cat data/runs/*/meta.json | python3 -m json.tool
```

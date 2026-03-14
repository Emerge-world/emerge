# Infinite Ticks Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make simulation runs support infinite ticks everywhere, using the literal `infinite` and making unbounded runs the default.

**Architecture:** Introduce one small shared tick-limit utility so parsing, formatting, and bounded/unbounded iteration semantics live in one place. Then wire that contract through the CLI, web server, batch runner, engine, and event metadata, backed by focused parser/unit tests and engine/event integration tests. Keep the behavior change narrow: no new stop control, and runs still end when all agents die.

**Tech Stack:** Python, argparse, itertools, pytest, uv (`uv run pytest`)

---

## File Structure

- Create: `simulation/tick_limits.py`
  Responsibility: single source of truth for tick-limit parsing (`"infinite"` or positive integer), human-readable formatting, and bounded/unbounded tick iteration.
- Create: `tests/test_tick_limits.py`
  Responsibility: unit tests for tick-limit helper behavior plus parser tests for `main.py` and `server/run_server.py` after parser extraction.
- Create: `tests/test_engine_tick_limits.py`
  Responsibility: engine integration tests for finite vs infinite loop semantics and exact `run_end.total_ticks` accounting on extinction.
- Modify: `main.py`
  Responsibility: extract `build_parser()`, use shared tick-limit parsing, and expose infinite as the default in help text and runtime configuration.
- Modify: `server/run_server.py`
  Responsibility: same parser extraction and default/formatting behavior for web-server runs.
- Modify: `run_batch.py`
  Responsibility: validate `ticks` as positive integer or literal `infinite`, preserve omitted `ticks` as the new default, and pass through explicit `--ticks infinite` when configured.
- Modify: `simulation/config.py`
  Responsibility: change the default run-limit constant to unbounded.
- Modify: `simulation/engine.py`
  Responsibility: accept `Optional[int]`, iterate correctly in bounded and unbounded modes, format infinite for human-readable output, and keep `current_tick` / `run_end.total_ticks` accurate on extinction.
- Modify: `simulation/event_emitter.py`
  Responsibility: accept `Optional[int]` so machine-readable metadata naturally serializes infinite runs as JSON `null`.
- Modify: `tests/test_run_batch.py`
  Responsibility: cover infinite tick validation and command construction in batch mode.
- Modify: `tests/test_event_emitter.py`
  Responsibility: assert `max_ticks=None` serializes as JSON `null` in `meta.json` and `run_start`.
- Modify: `README.md`
  Responsibility: document infinite as the default and `infinite` as the explicit literal.
- Modify: `start.sh`
  Responsibility: update forwarded-argument comments if they still claim a finite default.
- Modify: `project-cornerstone/12-tooling/tooling_context.md`
  Responsibility: remove the obsolete “MAX_TICKS hard limit” mitigation claim and align examples with the new tick-limit semantics.
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
  Responsibility: record the behavior-level decision that runs are unbounded by default and use `None`/`null` internally for infinite mode.
- Inspect: `project-cornerstone/00-master-plan/MASTER_PLAN.md`
  Responsibility: verify it does not still describe a finite default or hard tick cap; update it only if it does.

## Chunk 1: Shared tick-limit contract + entrypoint parsing

### Task 1: Create the shared tick-limit utility with failing tests first

**Files:**
- Create: `simulation/tick_limits.py`
- Create: `tests/test_tick_limits.py`

- [ ] **Step 1: Write the failing helper tests**

```python
# tests/test_tick_limits.py
from argparse import ArgumentTypeError
from itertools import islice

import pytest

from simulation.tick_limits import (
    format_tick_limit,
    iter_tick_numbers,
    parse_tick_limit_arg,
    validate_tick_limit_value,
)


def test_parse_tick_limit_arg_accepts_infinite_literal():
    assert parse_tick_limit_arg("infinite") is None


def test_parse_tick_limit_arg_accepts_positive_integer():
    assert parse_tick_limit_arg("25") == 25


@pytest.mark.parametrize("raw", ["0", "-3", "forever"])
def test_parse_tick_limit_arg_rejects_invalid_values(raw):
    with pytest.raises(ArgumentTypeError):
        parse_tick_limit_arg(raw)


def test_validate_tick_limit_value_accepts_yaml_infinite_string():
    assert validate_tick_limit_value("infinite") is None


@pytest.mark.parametrize("raw", [0, -1, "forever"])
def test_validate_tick_limit_value_rejects_invalid_config_values(raw):
    with pytest.raises(ValueError):
        validate_tick_limit_value(raw)


def test_format_tick_limit_renders_none_as_infinite():
    assert format_tick_limit(None) == "infinite"


def test_iter_tick_numbers_is_unbounded_for_none():
    assert list(islice(iter_tick_numbers(None), 3)) == [1, 2, 3]


def test_iter_tick_numbers_is_bounded_for_positive_integer():
    assert list(iter_tick_numbers(3)) == [1, 2, 3]
```

- [ ] **Step 2: Run the new tests to confirm they fail**

Run: `uv run pytest tests/test_tick_limits.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'simulation.tick_limits'`.

- [ ] **Step 3: Implement the helper module**

```python
# simulation/tick_limits.py
from __future__ import annotations

from argparse import ArgumentTypeError
from itertools import count
from typing import Iterator, Optional

INFINITE_TICKS_LITERAL = "infinite"


def parse_tick_limit_arg(raw: str) -> Optional[int]:
    if raw == INFINITE_TICKS_LITERAL:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ArgumentTypeError(
            f"ticks must be a positive integer or '{INFINITE_TICKS_LITERAL}'"
        ) from exc
    if value <= 0:
        raise ArgumentTypeError(
            f"ticks must be a positive integer or '{INFINITE_TICKS_LITERAL}'"
        )
    return value


def validate_tick_limit_value(raw: object) -> Optional[int]:
    if raw == INFINITE_TICKS_LITERAL:
        return None
    if isinstance(raw, int) and raw > 0:
        return raw
    raise ValueError(
        f"ticks must be a positive integer or '{INFINITE_TICKS_LITERAL}'"
    )


def format_tick_limit(max_ticks: Optional[int]) -> str:
    return INFINITE_TICKS_LITERAL if max_ticks is None else str(max_ticks)


def iter_tick_numbers(max_ticks: Optional[int]) -> Iterator[int]:
    return count(1) if max_ticks is None else iter(range(1, max_ticks + 1))
```

Implementation notes:
- Keep this module narrow: parsing, validation, formatting, iteration only.
- Do not push batch-specific subprocess logic into this module.

- [ ] **Step 4: Run the helper tests again**

Run: `uv run pytest tests/test_tick_limits.py -v`
Expected: PASS for all helper tests.

- [ ] **Step 5: Commit the helper contract**

```bash
git add simulation/tick_limits.py tests/test_tick_limits.py
git commit -m "feat: add shared tick limit utilities"
```

---

### Task 2: Extract parsers and wire infinite defaults into CLI, server, and batch tooling

**Files:**
- Modify: `main.py`
- Modify: `server/run_server.py`
- Modify: `run_batch.py`
- Modify: `tests/test_tick_limits.py`
- Modify: `tests/test_run_batch.py`

- [ ] **Step 1: Add failing parser and batch tests**

Append these tests to `tests/test_tick_limits.py`:

```python
import main
import server.run_server as run_server


def test_main_parser_defaults_ticks_to_infinite():
    args = main.build_parser().parse_args([])
    assert args.ticks is None


def test_main_parser_accepts_infinite_literal():
    args = main.build_parser().parse_args(["--ticks", "infinite"])
    assert args.ticks is None


def test_main_parser_rejects_zero_ticks():
    with pytest.raises(SystemExit):
        main.build_parser().parse_args(["--ticks", "0"])


def test_server_parser_defaults_ticks_to_infinite():
    args = run_server.build_parser().parse_args([])
    assert args.ticks is None


def test_server_parser_accepts_integer_ticks():
    args = run_server.build_parser().parse_args(["--ticks", "12"])
    assert args.ticks == 12
```

Add these tests to `tests/test_run_batch.py`:

```python
def test_validate_accepts_infinite_ticks_literal():
    rb = _load()
    rb.validate_experiments([{"name": "test", "ticks": "infinite"}])


@pytest.mark.parametrize("ticks", [0, -2, "forever"])
def test_validate_rejects_invalid_ticks_values(ticks):
    rb = _load()
    with pytest.raises(SystemExit):
        rb.validate_experiments([{"name": "test", "ticks": ticks}])


def test_build_command_preserves_explicit_infinite_ticks():
    rb = _load()
    cmd = rb.build_command({"name": "foo", "ticks": "infinite"})
    assert "--ticks" in cmd
    assert "infinite" in cmd


def test_build_command_omits_ticks_when_not_configured():
    rb = _load()
    cmd = rb.build_command({"name": "foo"})
    assert "--ticks" not in cmd
```

- [ ] **Step 2: Run the parser and batch tests to confirm they fail**

Run: `uv run pytest tests/test_tick_limits.py tests/test_run_batch.py -v`
Expected:
- FAIL because `main.build_parser()` and `server.run_server.build_parser()` do not exist yet.
- FAIL because `run_batch.validate_experiments()` currently accepts invalid non-positive integers and arbitrary strings for `ticks`.

- [ ] **Step 3: Implement the parser extraction and batch validation**

In `main.py`, extract parser construction into a helper and use the shared tick-limit parser:

```python
from simulation.tick_limits import parse_tick_limit_arg


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autonomous agent life simulation (LLM)")
    parser.add_argument("--agents", type=int, default=3, help="Number of agents (max 5)")
    parser.add_argument(
        "--ticks",
        type=parse_tick_limit_arg,
        default=sim_config.MAX_TICKS,
        help="Maximum number of ticks (positive integer or 'infinite'; default: infinite)",
    )
    parser.add_argument("--seed", type=int, default=None, help="Seed for the world (reproducibility)")
    parser.add_argument("--no-llm", action="store_true", help="Run without LLM (rule-based fallback mode)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Detailed logging")
    parser.add_argument("--save-log", action="store_true", help="Save log on completion")
    parser.add_argument("--save-state", action="store_true", help="Save world state on completion")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
```

Keep the rest of the existing argument definitions unchanged when moving them into `build_parser()`.

In `server/run_server.py`, mirror that extraction:

```python
from simulation.tick_limits import format_tick_limit, parse_tick_limit_arg


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Emerge simulation web server")
    parser.add_argument("--agents", type=int, default=3, help="Number of agents")
    parser.add_argument(
        "--ticks",
        type=parse_tick_limit_arg,
        default=sim_config.MAX_TICKS,
        help="Max simulation ticks (positive integer or 'infinite'; default: infinite)",
    )
    parser.add_argument("--seed", type=int, default=None, help="World seed")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM, use fallback")
    parser.add_argument("--port", type=int, default=8001, help="HTTP port")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    print(f"  Max ticks: {format_tick_limit(args.ticks)}")
```

Keep the existing `--tick-delay` argument block unchanged inside `build_parser()`.

In `run_batch.py`, validate `ticks` only when the key is present:

```python
from simulation.tick_limits import validate_tick_limit_value


def validate_experiments(experiments: list[dict]) -> None:
    for i, exp in enumerate(experiments):
        if "name" not in exp:
            print(f"ERROR: experiment #{i + 1} is missing required field 'name'", file=sys.stderr)
            sys.exit(1)
        unknown = set(exp.keys()) - VALID_KEYS
        if unknown:
            print(
                f"ERROR: experiment '{exp.get('name', f'#{i+1}')}' has unknown keys: {sorted(unknown)}",
                file=sys.stderr,
            )
            sys.exit(1)
        if "ticks" in exp:
            try:
                validate_tick_limit_value(exp["ticks"])
            except ValueError as exc:
                print(
                    f"ERROR: experiment '{exp['name']}' has invalid ticks value: {exc}",
                    file=sys.stderr,
                )
                sys.exit(1)
```

Implementation notes:
- Do not normalize explicit `"infinite"` to `None` inside `run_batch.py`; command building needs to preserve the literal when the user wrote it in YAML.
- When `ticks` is omitted in batch config, keep omitting `--ticks` so `main.py` can apply the new infinite default.
- If `main.py` prints or logs ticks for humans, use `format_tick_limit(args.ticks)` instead of raw `args.ticks`.

- [ ] **Step 4: Run the parser and batch tests again**

Run: `uv run pytest tests/test_tick_limits.py tests/test_run_batch.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the entrypoint and batch changes**

```bash
git add main.py server/run_server.py run_batch.py tests/test_tick_limits.py tests/test_run_batch.py
git commit -m "feat: add infinite tick parsing across entrypoints"
```

## Chunk 2: Engine loop semantics + event metadata

### Task 3: Add failing event-emitter and engine integration tests

**Files:**
- Modify: `tests/test_event_emitter.py`
- Create: `tests/test_engine_tick_limits.py`

- [ ] **Step 1: Add the failing event-emitter tests**

In `tests/test_event_emitter.py`, make `_make_emitter()` accept an override:

```python
def _make_emitter(tmp_path, monkeypatch, run_id="test-run-1234", seed=42, max_ticks=72):
    monkeypatch.chdir(tmp_path)
    day_cycle = DayCycle(start_hour=6)
    em = EventEmitter(
        run_id=run_id,
        seed=seed,
        world_width=15,
        world_height=15,
        max_ticks=max_ticks,
        agent_count=3,
        agent_names=["Ada", "Bruno", "Clara"],
        agent_model_id="test-agent-model",
        oracle_model_id="test-oracle-model",
        day_cycle=day_cycle,
        precedents_file="data/precedents_42.json",
    )
    return em
```

Then add:

```python
class TestMeta:
    def test_meta_json_uses_null_for_infinite_ticks(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch, max_ticks=None)
        em.close()
        meta = json.loads((tmp_path / "data" / "runs" / "test-run-1234" / "meta.json").read_text())
        assert meta["max_ticks"] is None


class TestRunStart:
    def test_run_start_payload_uses_null_for_infinite_ticks(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch, max_ticks=None)
        em.emit_run_start(["Ada"], "m", None, 10, 10, None)
        em.close()
        payload = _read_events(tmp_path)[0]["payload"]
        assert payload["config"]["max_ticks"] is None
```

- [ ] **Step 2: Create the failing engine integration tests**

```python
# tests/test_engine_tick_limits.py
import json

from simulation.engine import SimulationEngine


def _read_events(run_dir):
    path = run_dir / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_finite_engine_stops_at_requested_tick(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("simulation.engine.TICK_DELAY_SECONDS", 0)
    engine = SimulationEngine(num_agents=1, use_llm=False, max_ticks=2, world_seed=42, run_digest=False)

    engine.run()

    assert engine.current_tick == 2


def test_infinite_engine_runs_until_extinction_and_counts_exact_ticks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("simulation.engine.TICK_DELAY_SECONDS", 0)
    monkeypatch.setattr("simulation.engine.MetricsBuilder.build", lambda self: None)
    monkeypatch.setattr("simulation.engine.EBSBuilder.build", lambda self: None)

    engine = SimulationEngine(num_agents=1, use_llm=False, max_ticks=None, world_seed=42, run_digest=False)
    seen_ticks = []

    def fake_run_tick(tick, alive_agents):
        seen_ticks.append(tick)
        if tick == 73:
            alive_agents[0].alive = False

    monkeypatch.setattr(engine, "_run_tick", fake_run_tick)

    engine.run()

    assert seen_ticks[:3] == [1, 2, 3]
    assert seen_ticks[-1] == 73
    assert engine.current_tick == 73

    run_end = [ev for ev in _read_events(engine.event_emitter.run_dir) if ev["event_type"] == "run_end"][0]
    assert run_end["payload"]["total_ticks"] == 73
```

Why tick `73`: it proves unbounded mode continues beyond the old `MAX_TICKS = 72` default instead of just stopping at the former ceiling.

- [ ] **Step 3: Run the new integration tests to confirm they fail**

Run: `uv run pytest tests/test_event_emitter.py tests/test_engine_tick_limits.py -v`
Expected:
- FAIL because `SimulationEngine.run()` currently uses `range(1, self.max_ticks + 1)` and cannot handle `None`.
- The new `tests/test_event_emitter.py` assertions may already pass before implementation because JSON serialization already renders Python `None` as `null`; if so, keep them as characterization coverage and proceed.
- If the engine test reports `current_tick == 74` on extinction, that confirms the existing off-by-one tick-accounting bug and the implementation must fix it.

- [ ] **Step 4: Implement engine and event-emitter support**

Update `simulation/config.py`:

```python
# --- Simulation ---
MAX_TICKS = None  # None = infinite/unbounded run by default
TICK_DELAY_SECONDS = 0.5
```

Update `simulation/event_emitter.py` signatures only; JSON serialization already does the right thing:

```python
from typing import Optional

class EventEmitter:
    def __init__(
        self,
        run_id: str,
        seed: Optional[int],
        world_width: int,
        world_height: int,
        max_ticks: Optional[int],
        agent_count: int,
        agent_names: list[str],
        agent_model_id: str,
        oracle_model_id: str,
        day_cycle: DayCycle,
        precedents_file: Optional[str] = None,
    ):
        # existing body unchanged; only the `max_ticks` type changes
        pass

    def emit_run_start(
        self,
        agent_names: list[str],
        model_id: str,
        world_seed: Optional[int],
        width: int,
        height: int,
        max_ticks: Optional[int],
    ):
        # existing body unchanged; only the `max_ticks` type changes
        pass
```

Update `simulation/engine.py` to use the shared tick-limit helpers:

```python
from simulation.tick_limits import format_tick_limit, iter_tick_numbers


class SimulationEngine:
    def __init__(
        self,
        num_agents: int = 3,
        world_seed: Optional[int] = None,
        use_llm: bool = True,
        max_ticks: Optional[int] = MAX_TICKS,
        start_hour: int = WORLD_START_HOUR,
        world_width: int = WORLD_WIDTH,
        world_height: int = WORLD_HEIGHT,
        wandb_logger: Optional["WandbLogger"] = None,
        ollama_model: Optional[str] = None,
        run_digest: bool = True,
    ):
        self.max_ticks = max_ticks

    def run(self):
        try:
            for tick in iter_tick_numbers(self.max_ticks):
                alive_agents = [a for a in self.agents if a.alive]
                if not alive_agents:
                    self._print_separator()
                    print("\n☠️  ALL AGENTS HAVE DIED. End of simulation.")
                    break

                self.current_tick = tick
                self._run_tick(tick, alive_agents)
                if TICK_DELAY_SECONDS > 0:
                    time.sleep(TICK_DELAY_SECONDS)
        finally:
            self.oracle.save_precedents(
                self._precedents_path, self.current_tick, self._world_seed
            )
```

Mirror the same change in `run_with_callback()`:

```python
for tick in iter_tick_numbers(self.max_ticks):
    if pause_flag is not None:
        while pause_flag.is_set():
            time.sleep(0.05)

    alive_agents = [a for a in self.agents if a.alive]
    if not alive_agents:
        logger.info("All agents have died — simulation complete")
        break

    self.current_tick = tick
    self._tick_events = []
    self._run_tick(tick, alive_agents)
    on_tick({
        "type": "tick",
        "tick": tick,
        "agents": [self._serialize_agent(a) for a in self.agents],
        "events": list(self._tick_events),
        "world_resources": {
            f"{x},{y}": res
            for (x, y), res in self.world.resources.items()
        },
    })
```

Also replace raw `self.max_ticks` human output with `format_tick_limit(self.max_ticks)` in:
- `_print_header()`
- `_log_overview_start()` if you want log-friendly strings there
- any other console/server-facing summary output touched by this feature

Implementation notes:
- Setting `self.current_tick` only after the alive-agent check fixes the extinction off-by-one bug and keeps `run_end.total_ticks` equal to actual completed ticks.
- Keep machine-readable metadata raw (`None` -> JSON `null`); only human output should use `format_tick_limit()`.

- [ ] **Step 5: Run the event-emitter and engine tests again**

Run: `uv run pytest tests/test_event_emitter.py tests/test_engine_tick_limits.py -v`
Expected: PASS.

- [ ] **Step 6: Commit the runtime semantics**

```bash
git add simulation/config.py simulation/engine.py simulation/event_emitter.py tests/test_event_emitter.py tests/test_engine_tick_limits.py
git commit -m "feat: support unbounded simulation runs"
```

## Chunk 3: Documentation + full verification

### Task 4: Update docs and cornerstone records, then run the full verification suite

**Files:**
- Modify: `README.md`
- Modify: `start.sh`
- Modify: `project-cornerstone/12-tooling/tooling_context.md`
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Inspect: `project-cornerstone/00-master-plan/MASTER_PLAN.md`

- [ ] **Step 1: Update README and startup comments**

In `README.md`, change the web-server options row from:

```markdown
| `--ticks N` | 500 | Max simulation ticks |
```

to:

```markdown
| `--ticks VALUE` | infinite | Max simulation ticks (`VALUE` = positive integer or `infinite`) |
```

Update the CLI examples so the default run example no longer implies a 30-tick ceiling, and add one explicit infinite example:

```bash
# Basic run (3 agents, infinite ticks until extinction or interruption)
uv run main.py

# Explicit infinite run
uv run main.py --ticks infinite --agents 5 --seed 42

# Finite run
uv run main.py --ticks 100 --agents 5 --seed 42
```

In `start.sh`, update the forwarded-argument comment block:

```bash
#   --ticks N|infinite  Max ticks (default: infinite)
```

- [ ] **Step 2: Update cornerstone docs**

In `project-cornerstone/12-tooling/tooling_context.md`, replace the obsolete risk row:

```markdown
| Infinite tick loop              | MAX_TICKS hard limit                                |
```

with:

```markdown
| Infinite tick loop              | Explicit `infinite` support; runs still stop on extinction or user interruption |
```

Add a new decision entry at the end of `project-cornerstone/00-master-plan/DECISION_LOG.md` using the next sequential decision number. Use this shape:

```markdown
### DEC-036: Infinite ticks as the default run mode
- **Date**: 2026-03-13
- **Context**: Reproduction, evolution, and long-running experiments are constrained by finite tick defaults scattered across CLI/server entrypoints and engine assumptions.
- **Decision**: Represent `max_ticks` as `Optional[int]` across runtime boundaries. `None` means unbounded. Public interfaces accept the literal `infinite`, and omitted `ticks` now default to infinite. Machine-readable metadata stores infinite mode as JSON `null`. Runs still end automatically when all agents die.
- **Rejected alternatives**: Huge integer sentinel (misleading and brittle), separate `run_forever` boolean (redundant state and invalid combinations).
- **Consequences**: Long-running runs no longer require choosing an arbitrary ceiling. Consumers that display `max_ticks` must render `None`/`null` as `infinite` for humans. Engine loop logic must avoid finite-range assumptions.
```

Also run:

```bash
rg -n "tick cap|max ticks|default: 500|default: 100|MAX_TICKS" project-cornerstone/00-master-plan/MASTER_PLAN.md
```

If `MASTER_PLAN.md` contains user-facing claims about a finite default or hard cap, update that file in the same docs pass. If it does not, leave it untouched and note that explicitly in the implementation handoff.

- [ ] **Step 3: Run focused regression tests first**

Run: `uv run pytest tests/test_tick_limits.py tests/test_run_batch.py tests/test_event_emitter.py tests/test_engine_tick_limits.py -v`
Expected: PASS.

- [ ] **Step 4: Run the required non-slow suite**

Run: `uv run pytest -m "not slow"`
Expected: PASS.

- [ ] **Step 5: Inspect the worktree before the final commit**

Run: `git status --short`
Expected: only the intentional feature files are modified.

- [ ] **Step 6: Commit the docs and verification-complete state**

```bash
git add README.md start.sh project-cornerstone/12-tooling/tooling_context.md project-cornerstone/00-master-plan/DECISION_LOG.md
git commit -m "docs: document infinite tick runs"
```

- [ ] **Step 7: Summarize verification evidence in the handoff**

Include:
- the focused test command result
- the `pytest -m "not slow"` result
- whether any unrelated worktree changes remained untouched

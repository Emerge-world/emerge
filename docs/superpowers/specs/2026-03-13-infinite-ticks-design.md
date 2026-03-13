# Infinite Ticks Design

**Date:** 2026-03-13
**Status:** Approved

## Problem

Runs currently require a finite numeric `ticks` value throughout the CLI, web server, engine, event metadata, and batch tooling. That blocks long-running experiments and creates mismatched expectations with features like reproduction and evolution that benefit from very long or open-ended runs.

## Goal

Allow simulations to run without a fixed tick cap.

## Non-Goals

- Adding a new explicit stop control to the web server or CLI
- Changing extinction behavior: runs must still stop automatically when all agents are dead
- Adding checkpointing, artifact retention limits, or other long-run operational controls
- Changing per-tick gameplay, Oracle behavior, or agent decision semantics

## Decision

Represent the run limit internally as `Optional[int]`.

- Finite runs use a positive integer tick limit
- Infinite runs use `None`
- Public interfaces accept the literal `infinite` and parse it into `None`
- Infinite becomes the default when `ticks` is omitted

This replaces the current assumption that `ticks` is always a finite integer while keeping a single source of truth for run boundedness.

## Design

### 1. Execution Model

`SimulationEngine` in `simulation/engine.py` treats `max_ticks` as `Optional[int]`.

- If `max_ticks` is an integer, the engine runs until that tick count is reached or all agents die first
- If `max_ticks` is `None`, the engine runs until all agents die or the run is externally interrupted
- Both `run()` and `run_with_callback()` share the same stop semantics

Implementation should avoid fake sentinel values like `999999999` or `sys.maxsize`. Unbounded mode must be represented explicitly and handled in the loop condition.

Human-facing output should render infinite mode as `infinite`, not `None`.

### 2. Public Interface Contract

The `ticks` input contract becomes:

- Positive integer: bounded run
- Literal `infinite`: unbounded run
- Omitted value: default to unbounded run

Rejected values:

- `0`
- Negative integers
- Arbitrary strings other than `infinite`

This contract applies everywhere a run can be configured:

- `main.py`
- `server/run_server.py`
- `run_batch.py`
- `simulation/config.py` default tick setting
- Batch YAML files such as `experiments.yaml`

For batch YAML, both of these must be valid:

```yaml
experiments:
  - name: finite
    ticks: 200

  - name: infinite-explicit
    ticks: infinite

  - name: infinite-default
```

The last entry inherits the new infinite default.

### 3. Event Metadata and Reporting

Run metadata must preserve the distinction between bounded and unbounded runs without encoding infinite as a giant integer.

In `simulation/event_emitter.py`:

- `meta.json` stores `"max_ticks": null` for infinite runs
- `run_start` event payload stores `"max_ticks": null` for infinite runs
- Finite runs continue storing the numeric limit

Downstream consumers should treat `null` as unbounded.

Human-readable output in the CLI or server startup should say:

- `Max ticks: 200` for bounded runs
- `Max ticks: infinite` for unbounded runs

`run_end.total_ticks` remains the actual number of ticks completed in both modes.

### 4. Compatibility Boundaries

This feature changes run configuration semantics, not simulation semantics.

What stays the same:

- All agents dying ends the run
- `KeyboardInterrupt` and equivalent external shutdown still trigger the existing shutdown path
- Post-run artifact generation still runs from the existing `finally` blocks
- Finite runs still behave exactly as before when given a positive integer

What must change:

- Type hints and internal loop logic that currently assume `max_ticks` is always an `int`
- Parsers and validators that currently accept only numeric tick values
- Docs and usage text that currently claim finite numeric defaults
- Any tests that hard-code the old finite defaults

### 5. Error Handling

Parsing should fail fast and clearly for invalid `ticks` values.

Examples:

- `--ticks infinite` is valid
- `--ticks 100` is valid
- `--ticks 0` is invalid
- `--ticks -5` is invalid
- `--ticks forever` is invalid

Batch validation should reject invalid `ticks` values before launching subprocesses.

No special new runtime error handling is needed inside the engine beyond the existing shutdown path. Infinite mode is only a different stop condition.

### 6. Testing

Tests should separate configuration parsing from engine behavior.

Parser and interface coverage:

- CLI parser defaults to infinite when `--ticks` is omitted
- CLI parser accepts `--ticks infinite`
- CLI parser accepts positive integers
- CLI parser rejects `0`, negative numbers, and invalid strings
- Server parser/defaults match the CLI contract
- Batch config accepts `ticks: infinite`
- Batch config omission inherits infinite default
- Batch config rejects invalid `ticks` values

Engine and event coverage:

- Finite engine run stops at the requested tick
- Infinite engine run continues past a previous default boundary when agents remain alive
- Infinite engine run still stops on extinction
- `meta.json` stores `null` for infinite runs and an integer for finite runs
- `run_start` config stores `null` for infinite runs and an integer for finite runs
- `run_end.total_ticks` equals the actual completed ticks in both modes

Infinite-run tests must still be bounded in wall-clock time. The test strategy should use a deterministic escape hatch such as monkeypatching the tick body, sleep delay, or callback flow so the test can prove unbounded loop semantics without relying on a truly endless process.

Testing does not need to simulate an actual manual stop control because that is out of scope for this feature.

### 7. Documentation Updates

Implementation should update the docs that describe tick defaults or hard run caps:

- `README.md`
- `main.py` usage/help text
- `server/run_server.py` usage/help text
- `start.sh` usage comments if they are still intended to reflect current defaults
- `project-cornerstone/12-tooling/tooling_context.md`
- `project-cornerstone/00-master-plan/DECISION_LOG.md`

The docs should state:

- Infinite is now the default when `ticks` is omitted
- The explicit literal is `infinite`
- Runs still end automatically when all agents die

### 8. Scope Guardrails

This spec intentionally excludes adjacent improvements that may become relevant later:

- No stop endpoint
- No automatic checkpoint cadence changes
- No log pruning or disk guardrails
- No progress-percentage UI, because unbounded runs do not have a meaningful completion ratio

Those are separate features and should not be folded into this change.

## Touch Points

| File | Change |
|---|---|
| `simulation/engine.py` | Treat `max_ticks` as `Optional[int]`, update loop conditions and display text |
| `simulation/config.py` | Change the default run-limit representation to unbounded |
| `simulation/event_emitter.py` | Persist `null` for infinite `max_ticks` in machine-readable metadata |
| `main.py` | Parse `ticks` as positive integer or `infinite`, default to infinite |
| `server/run_server.py` | Parse `ticks` as positive integer or `infinite`, default to infinite |
| `run_batch.py` | Accept string `infinite` and omitted `ticks`, validate accordingly |
| `README.md` | Update examples and defaults |
| `start.sh` | Update server usage comments if still maintained |
| `project-cornerstone/12-tooling/tooling_context.md` | Remove the hard-limit claim for run configuration |
| `project-cornerstone/00-master-plan/DECISION_LOG.md` | Record the behavior-level design decision |

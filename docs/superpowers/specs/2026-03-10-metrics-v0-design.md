# PR3 — Metrics v0 Design

**Date:** 2026-03-10
**Branch:** feat/event-emitter
**Depends on:** PR1 (EventEmitter), PR2 (meta.json + blobs) — both merged

---

## Scope

Implement metrics computation for simulation runs:

1. Add missing innovation events to the event stream
2. Build a `MetricsBuilder` that reads `events.jsonl` and writes `metrics/summary.json` + `metrics/timeseries.jsonl`
3. Integrate into engine (always runs at end-of-run)
4. Expose as standalone CLI for recomputing past runs

**Out of scope:** EBS scoring (PR4), contradiction detection (PR5), LLM digests (PR6).

---

## 1. New Innovation Events

Three new event types emitted from existing engine/oracle code paths.

### `innovation_attempt`

Emitted when an agent submits an `innovate` action, before oracle validation.

```json
{
  "event_type": "innovation_attempt",
  "run_id": "...",
  "seed": null,
  "tick": 5,
  "sim_time": {"day": 1, "hour": 12},
  "agent_id": "Ada",
  "payload": {
    "name": "gather_wood",
    "description": "Collect wood from trees",
    "requires": {"tile": "forest"},
    "produces": {"wood": 1}
  }
}
```

### `innovation_validated`

Emitted after oracle approves or rejects the innovation.

```json
{
  "event_type": "innovation_validated",
  "run_id": "...",
  "tick": 5,
  "sim_time": {"day": 1, "hour": 12},
  "agent_id": "Ada",
  "payload": {
    "name": "gather_wood",
    "approved": true,
    "category": "CRAFTING",
    "reason_code": "INNOVATION_APPROVED"
  }
}
```

`category` and `reason_code` come from data the oracle already produces — no new oracle logic needed.

### `custom_action_executed`

Emitted when an agent uses a previously approved innovation.

```json
{
  "event_type": "custom_action_executed",
  "run_id": "...",
  "tick": 8,
  "sim_time": {"day": 1, "hour": 18},
  "agent_id": "Ada",
  "payload": {
    "name": "gather_wood",
    "success": true,
    "effects": {"hunger": 0, "energy": -5, "life": 0}
  }
}
```

---

## 2. MetricsBuilder

### Location

`simulation/metrics_builder.py`

### Interface

```python
class MetricsBuilder:
    def __init__(self, run_dir: Path): ...
    def build(self) -> None: ...
```

Single public method. Reads `events.jsonl`, writes `metrics/` directory.

### Algorithm

One sequential pass through `events.jsonl`, accumulating:
- A per-tick rolling dict (for timeseries)
- Running totals across the full run (for summary)

Writes both files at end of pass.

### Output: `metrics/summary.json`

```json
{
  "run_id": "...",
  "total_ticks": 30,
  "agents": {
    "initial_count": 3,
    "final_survivors": ["Ada"],
    "deaths": 2,
    "survival_rate": 0.33
  },
  "actions": {
    "total": 87,
    "by_type": {"move": 50, "eat": 20, "rest": 10, "innovate": 7},
    "oracle_success_rate": 0.82,
    "parse_fail_rate": 0.04
  },
  "innovations": {
    "attempts": 7,
    "approved": 4,
    "rejected": 3,
    "used": 2,
    "approval_rate": 0.57,
    "realization_rate": 0.50
  }
}
```

### Output: `metrics/timeseries.jsonl`

One JSON object per line, one per tick:

```json
{"tick": 1, "sim_time": {"day": 1, "hour": 6}, "alive": 3, "mean_life": 98.3, "mean_hunger": 1.2, "mean_energy": 96.1, "deaths": 0, "actions": 3, "oracle_success_rate": 1.0, "innovations_attempted": 0, "innovations_approved": 0}
```

Fields per row:

| Field | Source event |
|-------|-------------|
| `tick` | all events |
| `sim_time` | all events |
| `alive` | `agent_state` (count where `alive=true`) |
| `mean_life` / `mean_hunger` / `mean_energy` | `agent_state` |
| `deaths` | `agent_state` transitions (`alive` false, previous true) |
| `actions` | `oracle_resolution` count |
| `oracle_success_rate` | `oracle_resolution.success` |
| `innovations_attempted` | `innovation_attempt` count |
| `innovations_approved` | `innovation_validated` where `approved=true` |

---

## 3. Engine Integration

One line added at the end of the run, after `emit_run_end()`:

```python
MetricsBuilder(self.event_emitter.run_dir).build()
```

No structural changes to the engine.

---

## 4. Standalone CLI

```bash
# Recompute metrics for a specific run
uv run python -m simulation.metrics_builder data/runs/<run_id>

# Recompute metrics for all runs
uv run python -m simulation.metrics_builder
```

The module's `if __name__ == "__main__"` block handles both cases.

---

## 5. Testing

### Innovation event emission

Extend `tests/test_event_emitter.py`: assert `innovation_attempt`, `innovation_validated`, and `custom_action_executed` appear in `events.jsonl` when an agent runs an innovate action end-to-end with `--no-llm`.

### MetricsBuilder unit tests

New file `tests/test_metrics_builder.py`: construct a synthetic `events.jsonl` with known values (2 agents, 3 ticks, 1 innovation attempt/approval, 1 death), run `MetricsBuilder.build()`, assert exact values in `summary.json` and `timeseries.jsonl`.

### Smoke test

`uv run main.py --no-llm --ticks 5 --agents 1` produces `metrics/summary.json` and `metrics/timeseries.jsonl` in the run directory.

No new test infrastructure — same `tmp_path` pytest fixtures as `test_event_emitter.py`.

---

## Run Directory After PR3

```
data/runs/<run_id>/
  meta.json
  events.jsonl
  blobs/
    prompts/
    llm_raw/
  metrics/
    summary.json
    timeseries.jsonl
```

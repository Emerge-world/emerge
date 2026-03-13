# Personality-Survival Correlation Metric Design

**Date:** 2026-03-13
**Branch:** main
**Depends on:** canonical event stream, `simulation/personality.py`, `simulation/metrics_builder.py`, born-agent support in `agent_birth`

---

## Scope

Add a per-run metric that answers:

> Across all agents that existed during this run, which personality trait correlates best with survival length?

The metric should be computed automatically at end-of-run and written into `metrics/summary.json`.

## Goals

1. Keep `events.jsonl` as the authoritative source for recomputing the metric.
2. Include agents born mid-run, not just the initial population.
3. Use raw numeric trait values, not prompt labels or buckets.
4. Produce a compact summary that batch tooling can aggregate later.

## Non-goals

1. Cross-run aggregation or experiment reporting.
2. Statistical significance testing or p-values.
3. Per-tick personality tracking.
4. UI or W&B visualization changes in this slice.

---

## Design Summary

The metric is implemented as a small extension of the existing event-sourced metrics pipeline:

1. Persist one personality snapshot for every initial agent in `run_start`.
2. Persist one personality snapshot for every born agent in `agent_birth`.
3. Derive each agent's lifespan in ticks from entry tick to death tick or run end.
4. Compute Pearson correlation between each trait and lifespan.
5. Write an additive `personality_survival` block into `metrics/summary.json`.

This keeps the runtime change small and preserves the current rule that post-run metrics can be rebuilt from canonical run artifacts.

---

## Event Contract Changes

### `run_start`

Extend `payload.config` with `agent_profiles`.

```json
{
  "config": {
    "width": 15,
    "height": 15,
    "max_ticks": 30,
    "agent_count": 2,
    "agent_names": ["Ada", "Bruno"],
    "agent_profiles": [
      {
        "name": "Ada",
        "personality": {
          "courage": 0.80,
          "curiosity": 0.20,
          "patience": 0.60,
          "sociability": 0.40
        }
      },
      {
        "name": "Bruno",
        "personality": {
          "courage": 0.30,
          "curiosity": 0.90,
          "patience": 0.50,
          "sociability": 0.10
        }
      }
    ]
  }
}
```

Notes:
- `agent_names` stays unchanged for backward compatibility.
- `agent_profiles` is additive and mirrors the existing initial population.

### `agent_birth`

Extend the birth payload with the child personality snapshot.

```json
{
  "event_type": "agent_birth",
  "tick": 12,
  "agent_id": "Kira",
  "payload": {
    "child_name": "Kira",
    "generation": 2,
    "born_tick": 12,
    "parent_ids": ["Ada", "Bruno"],
    "pos": [4, 7],
    "personality": {
      "courage": 0.56,
      "curiosity": 0.41,
      "patience": 0.73,
      "sociability": 0.28
    }
  }
}
```

Notes:
- Personality is captured once at birth because traits are effectively static afterward.
- No new event type is needed.

---

## Metrics Definition

### Lifespan

For each agent:

- `entry_tick = 1` for agents present at `run_start`
- `entry_tick = born_tick` for agents introduced by `agent_birth`
- `terminal_tick = first tick where an `agent_state` event records `alive=false``
- if the agent never dies during the run, `terminal_tick = run_end.total_ticks`

Then:

`lifespan_ticks = terminal_tick - entry_tick + 1`

Examples:
- initial agent alive through tick 30 -> lifespan `30`
- initial agent dies at tick 7 -> lifespan `7`
- child born at tick 12 and alive through tick 30 -> lifespan `19`
- child born at tick 12 and dies at tick 14 -> lifespan `3`

### Correlation Method

Use Pearson correlation between:

- `x`: trait values for one trait across the usable population
- `y`: `lifespan_ticks` for the same agents

Traits:
- `courage`
- `curiosity`
- `patience`
- `sociability`

Implementation detail:
- Use the Python 3.12 stdlib `statistics.correlation`.
- Round stored coefficients to 4 decimals for consistency with existing metric rates.

### Best Trait

- `best_trait` is the trait with the highest non-null correlation coefficient.
- `best_correlation` is the value of that coefficient.
- If every coefficient is `null`, both fields are `null`.
- If every coefficient is negative, the least negative value still wins. The full map remains the source of truth.

---

## `summary.json` Schema Change

Add one new top-level block:

```json
{
  "run_id": "abc123",
  "total_ticks": 30,
  "agents": {
    "initial_count": 2,
    "final_survivors": ["Ada", "Kira"],
    "deaths": 1,
    "survival_rate": 0.6667
  },
  "actions": {
    "total": 87,
    "by_type": {
      "move": 31,
      "eat": 18
    },
    "oracle_success_rate": 0.8046,
    "parse_fail_rate": 0.0115
  },
  "innovations": {
    "attempts": 4,
    "approved": 2,
    "rejected": 2,
    "used": 1,
    "approval_rate": 0.5,
    "realization_rate": 0.5
  },
  "personality_survival": {
    "method": "pearson_correlation",
    "lifespan_unit": "ticks_alive_since_entry",
    "sample_size": 3,
    "trait_correlations": {
      "courage": 0.8214,
      "curiosity": -0.1442,
      "patience": 0.4021,
      "sociability": 0.0918
    },
    "best_trait": "courage",
    "best_correlation": 0.8214
  }
}
```

Compatibility rules:
- Existing keys under `agents`, `actions`, and `innovations` remain unchanged.
- Downstream readers that ignore unknown top-level keys continue to work.

---

## MetricsBuilder Changes

`simulation/metrics_builder.py` remains the single builder for `summary.json` and `timeseries.jsonl`.

Add these accumulators:

- `agent_traits: dict[str, dict[str, float]]`
- `agent_entry_tick: dict[str, int]`
- `agent_terminal_tick: dict[str, int]`
- `prev_alive: dict[str, bool]`

Single-pass event handling:

1. On `run_start`
- read `payload.config.agent_profiles`
- store each initial agent's personality in `agent_traits`
- set each initial agent's `entry_tick` to `1`

2. On `agent_birth`
- store the child personality from `payload.personality`
- set `entry_tick[child_name]` from `payload.born_tick`

3. On `agent_state`
- when an agent transitions from alive to dead, store the first death tick in `agent_terminal_tick`
- ignore later dead-state repeats for that agent

4. On `run_end`
- use `total_ticks` as the terminal tick for every tracked agent without a death tick

5. At summary build time
- collect usable samples only for agents that have both a personality snapshot and a resolved lifespan
- compute one coefficient per trait

This remains a sequential pass over `events.jsonl` with no new artifact reads.

---

## Error Handling and Edge Cases

The metric must never break run completion or summary generation.

Rules:

1. Missing `agent_profiles` in older runs
- produce a valid summary with:
  - `sample_size = 0`
  - all trait coefficients `null`
  - `best_trait = null`
  - `best_correlation = null`

2. Missing personality for one specific agent
- exclude that agent from the sample instead of failing the run

3. Fewer than 2 usable agents
- return `null` for all coefficients

4. Zero variance in lifespan or in a trait
- return `null` for that trait's coefficient
- catch `statistics.StatisticsError` and convert it to `null`

5. Child birth without later `agent_state`
- use `run_end.total_ticks` as terminal tick if the child never records a death

6. Recomputed historical runs
- `MetricsBuilder` should degrade cleanly on old `events.jsonl` files that predate the event schema change

---

## Test Plan

### `tests/test_event_emitter.py`

Add event contract coverage for:

1. `run_start` writes `payload.config.agent_profiles`
2. each profile contains all four raw trait values
3. `agent_birth` writes `payload.personality`

### `tests/test_metrics_builder.py`

Add deterministic fixtures covering:

1. Positive winner
- synthetic run where one trait clearly increases with lifespan
- assert `best_trait` and exact coefficients

2. Born-agent inclusion
- include a child with birth tick and personality
- assert the child contributes to `sample_size` and lifespan math

3. Surviving agents
- verify agents alive at `run_end` use `total_ticks` as terminal tick

4. Low-sample handling
- one usable agent only -> all coefficients `null`

5. Zero-variance handling
- same lifespan for all agents or same value for one trait -> that trait coefficient `null`

6. Backward compatibility
- old-style `run_start` without `agent_profiles` still builds `summary.json`

### Verification

Implementation should be validated with:

```bash
uv run pytest tests/test_event_emitter.py tests/test_metrics_builder.py -v
uv run pytest -m "not slow"
```

---

## Documentation Impact

Implementation should update these cornerstone docs once the code lands:

- `project-cornerstone/00-master-plan/MASTER_PLAN.md`
- `project-cornerstone/00-master-plan/DECISION_LOG.md`
- `project-cornerstone/01-architecture/architecture_context.md`

Reason:
- the project standard requires metrics additions and material telemetry design changes to be reflected in cornerstone docs after implementation.

---

## Rationale

This design is intentionally narrow:

- no new builder
- no dependency additions
- no UI work
- no experiment-layer reporting

It extends the existing event stream just enough to make personality-to-survival analysis deterministic, recomputable, and compatible with born agents.

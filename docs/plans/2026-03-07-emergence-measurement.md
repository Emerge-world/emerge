# Emergence Measurement System

## Context

The Emerge simulation produces emergent behaviors (innovations, cooperation, teaching, specialization) but has no way to quantify them. The existing audit system tracks per-agent behavioral metrics, but nothing measures *emergence* — the collective phenomena that arise from agent interactions. We need a system that:
1. **Scientifically validates** that emergence is real (not coincidental LLM behavior)
2. **Monitors emergence live** during simulation runs (console dashboard + JSONL stream)

## Design Summary

New module `simulation/emergence_tracker.py` that hooks into the tick lifecycle and measures four dimensions of emergence, each scored 0-1:

| Dimension | What it measures | Key signals |
|-----------|-----------------|-------------|
| **Innovation Diffusion** | Knowledge spreading through population | Teaching events, innovation coverage, inventor→learner chains |
| **Social Structure** | Meaningful relationships forming | Trust levels, bonded pairs, cooperation/conflict counts |
| **Behavioral Specialization** | Agents developing distinct roles | Action distribution divergence (Jensen-Shannon) across agents |
| **Collective Adaptation** | Group adapting to environmental pressures | Night-rest behavior, survival trends |

**Composite Emergence Index** = equal-weight average of all four dimensions (0-1).

## Files to Create/Modify

### New files:
- `simulation/emergence_tracker.py` — Core tracker module (~300 lines)

### Modified files:
- `simulation/engine.py` — Hook tracker into tick loop (after audit, before memory compression ~line 241)
- `simulation/config.py` — Add emergence config constants (report interval, weight defaults)
- `main.py` — Add `--emergence` CLI flag
- `pyproject.toml` — Add `rich` dependency

## Implementation Plan

### Step 1: Add `rich` dependency
- Add `rich>=13.0` to `pyproject.toml` dependencies
- Run `uv sync`

### Step 2: Create `simulation/emergence_tracker.py`

```python
class EmergenceTracker:
    def __init__(self, agents, config=None):
        # Running state per dimension
        self.innovations_created: dict[str, dict]  # name -> {creator, tick, learners: []}
        self.teaching_events: list[dict]           # {tick, teacher, learner, action}
        self.cooperation_events: list[dict]        # {tick, agent, target, action}
        self.action_counts: dict[str, Counter]     # agent_name -> action Counter
        self.night_actions: dict[str, list]        # "rest" vs other during night hours
        self.survival_snapshots: list[dict]        # {tick, avg_life, alive_count}
        self.relationship_snapshots: list[dict]    # periodic trust/bond state

    def record_tick(self, tick, agents, oracle, day_cycle):
        """Called each tick. Lightweight data collection."""
        # Record actions taken this tick
        # Detect teaching/cooperation from oracle results
        # Snapshot relationships periodically
        # Every N ticks: compute scores and display/log

    def _compute_innovation_diffusion(self) -> float:
        # diffusion_ratio = innovations known by ≥2 agents / total innovations
        # coverage_mean = mean(agents_knowing / total_agents) per innovation
        # return 0.5 * diffusion_ratio + 0.5 * coverage_mean

    def _compute_social_structure(self, agents) -> float:
        # bond_ratio = bonded pairs / possible pairs
        # coop_rate = cooperation events per tick (normalized)
        # trust_variance = variance of all trust values
        # return 0.3 * bond_ratio + 0.4 * coop_rate + 0.3 * trust_variance

    def _compute_specialization(self) -> float:
        # Build action distribution vector per agent
        # Compute pairwise Jensen-Shannon divergence
        # Return mean JSD (already 0-1 for JSD)

    def _compute_collective_adaptation(self) -> float:
        # night_rest_rate = rest during night / total night actions
        # survival_trend = slope of avg life over time (clamped 0-1)
        # return 0.5 * night_rest_rate + 0.5 * survival_trend

    def get_scores(self) -> dict:
        """Return current dimension scores + composite index."""

    def _display_console(self, tick):
        """Rich console panel with bar charts and notable events."""

    def _write_jsonl(self, tick, scores):
        """Append one line to emergence/events.jsonl."""

    def finalize(self, output_dir) -> dict:
        """End-of-run: write summary.json with full breakdown."""
```

### Step 3: Hook into engine tick loop

In `engine.py._run_tick()`, after the agent loop and audit recording, before memory compression:

```python
# Emergence tracking
if self.emergence_tracker:
    self.emergence_tracker.record_tick(tick, alive_agents, self.oracle, self.day_cycle)
```

The tracker needs to access:
- `oracle.world_log` or oracle resolution results for this tick
- Agent action history (what action each agent took this tick)
- Agent relationships (trust, bonds)
- Day cycle (to know if it's night)

To feed per-agent action data, the engine will collect actions during the agent loop and pass them to the tracker. Simplest approach: tracker maintains a `current_tick_actions: dict[str, str]` that gets populated during the loop and consumed at end of tick.

### Step 4: Add `--emergence` CLI flag

In `main.py`, add argument `--emergence` that creates the tracker and passes it to the engine.

### Step 5: Config constants

In `config.py`:
```python
EMERGENCE_REPORT_INTERVAL = 10      # compute/display scores every N ticks
EMERGENCE_DIMENSION_WEIGHTS = {
    "innovation_diffusion": 0.25,
    "social_structure": 0.25,
    "specialization": 0.25,
    "collective_adaptation": 0.25,
}
```

### Step 6: Console dashboard with rich

Display a panel every `EMERGENCE_REPORT_INTERVAL` ticks showing:
- Bar chart per dimension (colored by score: red < 0.3, yellow < 0.6, green ≥ 0.6)
- Composite Emergence Index
- Notable events since last report (first innovation, first teaching, first bond, etc.)

### Step 7: JSONL + Summary output

- `emergence/events.jsonl`: one line per report interval with all scores
- `emergence/summary.json`: full end-of-run breakdown including:
  - Time series of all dimension scores
  - Innovation genealogy (who invented what, who learned from whom)
  - Final relationship network (trust matrix)
  - Per-agent specialization profiles

### Step 8: Tests

- Unit tests for each `_compute_*` method with known inputs/outputs
- Integration test: run 20-tick `--no-llm --emergence` and verify JSONL output exists and is valid JSON
- Test that tracker is only created when `--emergence` flag is passed

## Verification

1. `pytest -m "not slow"` — all existing tests pass
2. `uv run main.py --no-llm --ticks 20 --agents 3 --emergence` — smoke test, verify console dashboard appears and JSONL file is written
3. `uv run main.py --agents 3 --ticks 50 --emergence` — full run with LLM, verify meaningful scores emerge
4. Check `logs/sim_<timestamp>/emergence/events.jsonl` contains valid JSON lines
5. Check `logs/sim_<timestamp>/emergence/summary.json` has all four dimension breakdowns

## Key Reusable Code

- `simulation/audit_recorder.py` — Pattern for JSONL writing and end-of-run summary generation
- `simulation/relationship.py` — `Relationship` dataclass with trust, cooperations, conflicts, bonded
- `simulation/config.py` — Constants pattern (bounds, thresholds)
- `simulation/day_cycle.py` — `get_period()` to detect night hours
- `simulation/oracle.py` — `self.precedents` dict for innovation data (keys like `innovation:<name>`)

## Decision: No baselines in v1

Statistical baselines (random/solo-agent comparison) deferred to a future iteration. v1 focuses on computing and displaying the raw emergence scores.

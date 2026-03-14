# Experiment Decision Toolkit Design

- **Date:** 2026-03-12
- **Status:** Approved
- **Audience:** Emerge maintainers building automated experiment gating, prioritization, and later human-readable experiment reports
- **Primary goal:** Add an automation-first experiment toolkit that decides whether a change is better than baseline and which experiments to run next
- **Focus:** Build on the existing event stream, metrics artifacts, batch runner, and optional W&B observer rather than introducing a parallel analytics stack

## 1. Problem Statement

The repository already has the core ingredients for experimentation:

- persisted run artifacts in `data/runs/<run_id>/`
- canonical event logs in `events.jsonl`
- per-run metrics from `simulation/metrics_builder.py`
- optional EBS scoring and W&B export
- sequential batch execution via `run_batch.py`

What it does not have is a decision layer.

Today, the system can produce runs and metrics, but it cannot answer two operational questions in a reproducible way:

1. Is a candidate change better than baseline, worse, or inconclusive?
2. Given the current evidence, which experiment should run next?

The project needs an automation-first toolkit that turns run artifacts into cohort comparisons, policy-driven decisions, and prioritized next-step recommendations. Human-readable report plugins can come afterward, but they should render the same decision artifacts rather than own the decision logic.

## 2. Design Goals

The toolkit should:

1. reuse the existing `run_batch.py`, event stream, and metrics artifacts
2. support two first-class workflows: `change gating` and `experiment prioritization`
3. favor balanced rigor with explicit `better`, `worse`, `inconclusive`, and `needs_more_runs` outcomes
4. keep decisions deterministic and inspectable from artifacts and policy configuration
5. degrade gracefully when some runs or artifacts are missing
6. support later human-readable plugins without changing the core decision model

The toolkit should not:

- move experiment logic into the simulation engine tick loop
- replace `metrics_builder` as the canonical source of per-run metrics
- depend on W&B as the authoritative decision layer
- require heavyweight statistical infrastructure for the first version

## 3. Approaches Considered

### Option A: Scorecard + Policy Engine

Define a standard KPI schema, aggregate run artifacts into cohorts, compare candidate cohorts to baseline, and apply explicit policy rules to produce decisions and experiment priorities.

**Pros**

- fits the current artifact model directly
- easy to debug because every rule is explicit
- fast to ship while preserving rigor
- easy to extend later with stronger statistical modules

**Cons**

- not as statistically expressive as a full inference-first framework
- requires careful KPI and threshold design

### Option B: Statistics-First Experiment Harness

Model every change as a hypothesis test with stronger replication rules, confidence intervals, and power-aware stopping conditions.

**Pros**

- stronger methodological discipline
- better long-term research rigor

**Cons**

- heavier implementation and tuning burden
- easier to stall on underpowered or noisy suites
- less aligned with current lightweight tooling

### Option C: Planner-Agent Over Metrics

Use a higher-level recommender to read summaries and propose decisions or next experiments.

**Pros**

- flexible and adaptive
- potentially useful later for research guidance

**Cons**

- opaque for first-version gating
- harder to keep deterministic and reproducible

### Chosen Direction

**Option A** is the chosen design.

It matches the current repository state, gives reproducible machine decisions quickly, and leaves room for both stronger statistical modules and human-readable report plugins later.

## 4. Architecture

The decision toolkit should sit above the existing run artifact pipeline instead of inside the simulation loop.

The proposed stack is:

- `suite spec`: declares a baseline cohort, one or more candidate cohorts, seed budget, metrics, and policy mode
- `cohort runner`: expands suites into concrete runs and delegates execution to existing batch-running machinery
- `run analyzer`: loads `summary.json`, `timeseries.jsonl`, and later `ebs.json`
- `comparison engine`: aggregates cohort outcomes across seeds and computes deltas, stability, and evidence quality
- `policy engine`: emits machine decisions such as `promote`, `reject`, `rerun`, or `inconclusive`
- `prioritizer`: ranks next experiments by uncertainty, expected learning value, and strategic value

The critical boundary is:

- per-run metric generation remains canonical and deterministic
- experiment decisions are produced by a separate, replaceable layer that consumes those artifacts

That separation keeps the system inspectable and makes later report plugins straightforward.

## 5. Experiment Model And Data Flow

The toolkit should model experiments around explicit `cohorts`, not only individual runs.

A cohort is a set of runs that share the same config under different seeds. An experiment suite compares one baseline cohort to one or more candidate cohorts.

### Suite model

Each suite should declare:

- `name`
- `purpose`
- `mode`: `gating`, `prioritization`, or `both`
- `baseline`
- `candidates`
- `seed_set`
- `metrics`
- `policy`
- `budget`

### Data flow

1. Expand a suite into concrete runs.
2. Execute baseline and candidate cohorts with matched seeds where possible.
3. Build or refresh per-run metrics from existing artifacts.
4. Aggregate each cohort into a cohort summary.
5. Compare candidate cohorts to baseline.
6. Apply policy rules.
7. Emit machine-readable decision and prioritization artifacts.

The core chain is:

`run -> cohort -> decision`

This separates raw observations from aggregated evidence and final judgment.

## 6. KPI Scorecard

The first version should use a compact, explicit KPI scorecard rather than a generic scoring engine.

### KPI classes

#### Primary gates

These must not regress beyond threshold.

Examples:

- survival rate
- oracle success rate
- parse fail rate
- invalid-run rate

#### Secondary value metrics

These capture useful gains when primary gates remain safe.

Examples:

- innovation approval rate
- innovation realization rate
- EBS, when available
- action diversity

#### Stability metrics

These determine whether the evidence is trustworthy enough to act on.

Examples:

- variance across seeds
- fraction of runs ending in collapse
- artifact completeness rate
- number of invalid runs

## 7. Policy Engine

The policy engine should work in two passes.

### 7.1 Safety and regression pass

- reject if any primary gate regresses beyond allowed tolerance
- reject if run failures or artifact failures exceed threshold
- mark inconclusive if variability is high enough that the sign of improvement is unstable

### 7.2 Value pass

- promote if primary gates are safe and weighted secondary gains exceed a minimum effect threshold
- rank candidates by composite gain when more than one clears the gates
- request more runs when a candidate looks promising but evidence is too noisy

The first version should favor explicit thresholds and rule firing over opaque composite scoring.

## 8. Prioritization Model

The same scorecard should also support choosing what to run next.

The prioritizer should rank next experiments using:

- uncertainty
- possible impact
- strategic coverage gaps
- evidence already collected

Priority should be highest for experiments that combine high uncertainty with high upside, and lowest for candidates that are already clearly better or clearly worse.

## 9. Validation Guide And Initial Experiment Portfolio

The toolkit should ship with a fixed initial experiment portfolio so it can validate the overall approach without pretending one suite covers every subsystem.

### 9.1 Core gate suite

Default suite for merge or promotion decisions.

Primary metrics:

- survival rate
- oracle success rate
- parse fail rate
- invalid-run rate

Secondary metrics:

- innovation approval rate
- innovation realization rate
- EBS, when available
- action diversity

### 9.2 Determinism and artifact integrity suite

Re-run the same config on fixed seeds and verify artifact completeness plus low drift in deterministic or near-deterministic signals.

Purpose:

- catch broken instrumentation
- catch missing artifacts
- catch unstable policy behavior

### 9.3 Stress and robustness suite

Run a small matrix of agent counts, tick budgets, and optional model or `--no-llm` variants.

Purpose:

- detect changes that only succeed in the happy path
- measure whether improvements survive under pressure

### 9.4 Subsystem probe suites

Focused suites for:

- cognition
- oracle behavior
- survival balance
- social behavior
- lineage and evolution

Purpose:

- diagnose where a candidate regressed
- schedule narrower follow-up experiments instead of another broad suite

### 9.5 Frontier prioritization suite

A lightweight sweep over uncertain or high-upside hypotheses.

Purpose:

- rank what to test next
- guide experimentation budget toward the highest expected learning value

All suites should reuse the same `run -> cohort -> decision` pipeline while supplying different KPI weights and policies.

## 10. Error Handling

The toolkit must degrade gracefully.

- if `summary.json` is missing, attempt to rebuild from `events.jsonl`
- if required artifacts still cannot be produced, mark the run `invalid`
- never silently drop failed runs from cohort analysis
- if too many runs are invalid, default to `inconclusive`

Every decision artifact should include:

- input runs used
- missing or rebuilt artifacts
- thresholds applied
- metrics considered
- rule that produced the final decision

## 11. Verification Strategy

Verification should happen at three levels.

### Unit tests

Cover:

- KPI aggregation
- delta calculations
- policy evaluation
- prioritization ranking

### Integration tests

Cover:

- `suite -> runs -> metrics -> decision artifact`
- rebuild paths when metrics are missing
- matched-seed baseline/candidate comparison

### Regression tests

Cover:

- golden suite fixtures whose decisions should remain stable unless the policy intentionally changes

Key invariant:

The same suite spec and same run artifacts must always produce the same decision artifact.

## 12. Rollout Plan

### Phase 1

Add:

- machine-readable suite specs
- cohort summaries
- decision artifacts
- prioritization artifacts

### Phase 2

Add:

- stronger variance handling
- richer KPIs such as EBS-derived signals
- better experiment budget heuristics

### Phase 3

Add:

- human-readable plugins
- comparison tables
- narrative report renderers

These later plugins should sit on top of the same artifacts and must not become the source of truth for experiment decisions.

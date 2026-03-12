# Scarcity Adaptation Benchmark Design

**Date:** 2026-03-12

## Goal

Define an internal engineering benchmark that validates whether newer Emerge revisions adapt better to fixed resource-scarcity scenarios than older revisions do.

## Problem Statement

The project already has event-stream telemetry, per-run metrics, EBS scoring, and batch execution. What it does not have is a stable validation loop for the claim that the system is improving at emergence under pressure. For the first benchmark, "emergence" is narrowed to one operational claim:

- Under fixed scarcity conditions, later project revisions should survive longer and manage scarce food better than earlier revisions.

This is a benchmark-and-regression problem, not a general research evaluation.

## Scope

In scope:

- Fixed, versioned scarcity benchmark suites
- Repeatable benchmark batches across code revisions
- Scenario-level and aggregate comparison reports
- Scarcity-specific scoring focused on adaptation under limited food
- Diagnostic outputs that explain why a revision improved or regressed

Out of scope for v1:

- Research-grade statistical analysis
- General-purpose emergence scoring beyond scarcity adaptation
- Silent reuse of ad hoc experiment configs as benchmarks
- Social, evolutionary, or weather-focused benchmark suites

## Existing Project Fit

The design should build on the current repository shape:

- `run_batch.py` already supports repeated YAML-defined experiment execution
- `simulation/event_emitter.py` already writes immutable per-run artifacts under `data/runs/<run_id>/`
- `simulation/metrics_builder.py` already derives summary and timeseries outputs from `events.jsonl`
- `simulation/ebs_builder.py` already computes a broader emergence score that can be kept as a secondary diagnostic
- `meta.json` already records `git_commit`, prompts, model IDs, and core run metadata

The benchmark layer should not replace the event-first architecture. It should consume the same run artifacts and add a reproducible comparison layer above them.

## Alternatives Considered

### 1. Fixed Scarcity Benchmark Suite

Freeze a small set of scarcity scenarios and compare whole revision batches against the same suite.

Pros:

- Best fit for internal engineering iteration
- Cheap to rerun
- Easy to interpret as regression or improvement

Cons:

- Needs extra diagnostics to explain score movement

### 2. Scarcity Frontier Benchmark

Sweep scarcity severity until the system collapses, then compare failure thresholds.

Pros:

- Strong robustness signal

Cons:

- Slower to run
- Harder to use as a routine regression benchmark

### 3. Benchmark Plus Ablation Matrix

Run the fixed suite plus systematic capability-removal variants.

Pros:

- Better attribution of causal factors

Cons:

- More runtime and maintenance burden than needed for v1

## Decision

Adopt **Fixed Scarcity Benchmark Suite** for v1.

Use raw scarcity-adaptation metrics as the primary evidence. Keep EBS and innovation-related metrics in the report only as supporting diagnostics.

## Benchmark Contract

The benchmark comparison unit is a **benchmark batch**:

- One candidate code revision
- One frozen benchmark suite version
- One fixed set of seeds
- One fixed model configuration
- One fixed world size, agent count, and tick budget

The batch should be comparable across revisions only when all of the above match exactly.

The primary benchmark hypothesis is:

- A candidate revision improves population-level adaptation under resource scarcity relative to a baseline revision on the same benchmark suite.

The suite itself must be immutable and versioned. Any change to scenarios, seeds, scoring rules, or run budgets creates a new benchmark version rather than mutating the old one.

## Benchmark Architecture

### 1. Versioned benchmark suite definitions

Add a dedicated suite file such as:

- `benchmarks/scarcity_v1.yaml`

The suite defines:

- benchmark version and description
- scenario IDs and labels
- seed list
- world dimensions
- agent count
- tick budget
- model and LLM mode settings
- scarcity parameters for each scenario

### 2. Explicit scarcity controls

Scarcity must become a per-run input instead of remaining implicit in global config values. The benchmark needs direct control over:

- initial resource spawn scale
- regeneration chance scale
- regeneration amount scale
- optional scenario-specific resource overrides if needed later

This requires moving resource availability from static global assumptions into benchmark-configurable simulation inputs.

### 3. Dedicated benchmark runner

Add a benchmark runner separate from `run_batch.py`.

`run_batch.py` is useful for generic experiment execution, but a benchmark batch needs:

- suite-version awareness
- candidate and baseline labels
- predictable artifact layout
- validation against mismatched scenarios
- aggregate comparison output

### 4. Metadata propagation

Each run in a benchmark batch should record:

- `benchmark_id`
- `benchmark_version`
- `scenario_id`
- `candidate_label`
- optional `baseline_label`
- scarcity parameters applied to the run

This metadata should live alongside the existing run metadata so individual runs stay self-describing.

### 5. Aggregate comparison artifacts

The benchmark layer should read the authoritative run outputs:

- `events.jsonl`
- `metrics/summary.json`
- `metrics/timeseries.jsonl`
- `metrics/ebs.json`

It should then write one comparison artifact for the candidate batch and one delta report versus the chosen baseline batch.

## Scoring And Evidence

The benchmark should optimize for clear engineering evidence, not for a single abstract emergence score.

### Primary metrics

Each run should compute these scarcity-adaptation metrics:

- `survival_auc`: normalized area under the alive-agent curve across ticks
- `starvation_pressure`: hunger burden across the run, plus starvation/death signals
- `food_conversion_efficiency`: food gathered or consumed relative to survival outcome

These metrics should be shown raw in every report.

### Secondary score

Optionally combine the primary metrics into a single **Scarcity Adaptation Score** for ranking and regression gates. This score should be fixed and versioned with the benchmark suite.

The score is useful for summaries, but the benchmark should still show the underlying metrics because they are easier to debug and harder to game.

### Supporting diagnostics

Include these as supporting columns only:

- `ebs`
- innovation attempt/approval/use counts
- action success and parse-failure rates

These signals may help explain movement, but they should not determine pass/fail for the scarcity benchmark.

### Batch-level evidence

At the comparison level, the report should show:

- per-scenario medians and spread across seeds
- aggregate deltas across all matched runs
- matched-seed win/loss counts
- a simple verdict per scenario and overall: `improved`, `flat`, or `regressed`

## Diagnostics

The benchmark must explain score movement, not just present it.

Each scenario report should include:

- resource availability over time
- regeneration totals over time
- action mix over time
- first-food latency
- starvation onset timing
- optional EBS and innovation summaries

This keeps the benchmark actionable for engineers working on survival and adaptation.

## Error Handling

Benchmark execution and comparison should fail safely and explicitly.

Requirements:

- failed runs are preserved and marked, not hidden
- incomplete batches still produce a partial report with failures called out
- comparisons reject mismatched suite versions or scenario definitions
- reports include concrete revision identifiers and timestamps

Example comparison wording:

- baseline commit `abc123` on 2026-03-12 vs candidate commit `def456` on 2026-03-12

## Testing Strategy

The benchmark system should be tested at four levels:

### 1. Unit tests

- scarcity parameter application
- benchmark metric calculations
- comparison verdict logic

### 2. Integration tests

- tiny benchmark suite execution
- metadata propagation into run artifacts
- aggregate report generation from completed runs

### 3. Regression tests

- synthetic baseline/candidate batches with known expected deltas
- mismatch handling for incompatible suite versions or scenarios

### 4. Smoke tests

- small end-to-end scarcity benchmark in `--no-llm` mode

## Proposed Outputs

Suggested benchmark artifact layout:

```text
data/benchmarks/<benchmark_id>/
  suite.json
  manifest.json
  runs/
    <run_id> -> ../../runs/<run_id>
  reports/
    candidate_summary.json
    baseline_comparison.json
    scenario_table.json
    summary.md
```

Individual simulation runs should continue to live under `data/runs/<run_id>/` and remain the source of truth.

## Success Criteria

The benchmark design succeeds when the team can:

- freeze a scarcity suite and rerun it unchanged across revisions
- compare a candidate revision to a baseline revision using the same scenarios and seeds
- detect whether the candidate improved or regressed on scarcity adaptation
- inspect diagnostics that explain metric movement without reading raw logs first

## Recommendation

Implement the benchmark as a thin, versioned comparison layer on top of the current event-stream system. Keep the first claim narrow: improved adaptation to food scarcity across project revisions. Expand later only after the benchmark proves useful in routine engineering work.

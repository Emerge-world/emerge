# Experiment Toolkit Guide

This guide covers the current `experiment_toolkit.py` workflow on branch `feat/experiment-decision-toolkit`.

## What The Toolkit Does

The toolkit runs one or more experiment suites, executes the baseline and candidate cohorts for each suite, reads the resulting run metrics, and writes machine-readable artifacts for:

- cohort summaries
- baseline-vs-candidate decisions
- next-experiment prioritization

It builds on top of the existing simulation run flow:

1. `main.py` creates a run under `data/runs/<run_id>/`
2. `simulation/metrics_builder.py` writes `metrics/summary.json`
3. `experiment_toolkit.py` aggregates those per-run summaries into cohort artifacts and decisions

## When To Use It

Use the toolkit when you want to answer either of these questions:

- Is a candidate config or code change better than baseline?
- Which candidate looks most worth testing next?

Use `run_batch.py` instead when you only want to launch a flat set of runs without decision artifacts.

## Command

Run a suite file:

```bash
uv run experiment_toolkit.py path/to/suite.yaml
```

Choose a custom artifact directory:

```bash
uv run experiment_toolkit.py path/to/suite.yaml --output-dir /tmp/emerge-experiments
```

Example using the committed sample suite:

```bash
uv run experiment_toolkit.py tests/fixtures/experiments/gate_inventory_suite.yaml --output-dir /tmp/emerge-experiments
```

## Suite File Format

The current CLI accepts either:

- one top-level suite object
- a file with `suite: {...}`
- a file with `suites: [...]`

Minimal single-suite example:

```yaml
name: gate_inventory
purpose: Baseline vs candidate gate
mode: both
seed_set: [11, 12]
baseline:
  name: baseline
  config:
    agents: 1
    ticks: 5
    no_llm: true
    wandb: false
candidates:
  - name: candidate
    config:
      agents: 1
      ticks: 5
      no_llm: true
      wandb: false
metrics:
  primary: [survival_rate]
  secondary: [oracle_success_rate]
policy:
  max_invalid_run_rate: 0.25
  min_effect_size: 0.02
budget:
  max_runs: 4
```

### Field meanings

- `name`: suite identifier and output folder name
- `purpose`: human description of the suite
- `mode`: stored in artifacts for intent; current implementation does not branch behavior on it
- `seed_set`: seeds reused across baseline and all candidates
- `baseline`: the control cohort
- `candidates`: one or more cohorts compared to the baseline
- `config`: the same fields accepted by `run_batch.build_command()`, such as `agents`, `ticks`, `seed`, `model`, `no_llm`, `wandb`, `width`, and `height`
- `metrics.primary`: metrics treated as regression gates
- `metrics.secondary`: stored in the suite artifact; current implementation does not weight these separately yet
- `policy.max_invalid_run_rate`: if exceeded, the decision becomes `inconclusive`
- `policy.min_effect_size`: minimum positive delta required for promotion
- `budget.max_runs`: stored in the suite artifact; current implementation does not enforce this yet

## What Happens During Execution

For each suite, the toolkit:

1. writes the suite spec to `suite.json`
2. runs every baseline seed
3. runs every candidate seed
4. loads or rebuilds `metrics/summary.json` for each run
5. aggregates baseline and candidate cohorts
6. compares candidate metrics against baseline
7. applies the current policy engine
8. ranks candidate follow-up priority heuristically

Run artifacts from the simulation still live under `data/runs/<run_id>/`.

The toolkit writes its own outputs separately under the chosen output directory.

## Output Layout

Example output tree:

```text
<output-dir>/
└── gate_inventory/
    ├── suite.json
    ├── cohorts/
    │   ├── baseline.json
    │   └── candidate.json
    ├── decisions/
    │   └── candidate.json
    └── priorities.json
```

### `suite.json`

The normalized suite configuration used by the run.

### `cohorts/<name>.json`

One file per cohort. Each file includes:

- `run_count`
- `invalid_run_rate`
- aggregated metric means

Current aggregated metrics:

- `survival_rate`
- `oracle_success_rate`
- `parse_fail_rate`
- `innovation_approval_rate`
- `innovation_realization_rate`

### `decisions/<candidate>.json`

The gating result for a single candidate. Includes:

- `decision`
- `reason`
- `rules_fired`
- `comparison`
- embedded `baseline` and `candidate` cohort summaries

Current decisions are:

- `promote`
- `reject`
- `inconclusive`

### `priorities.json`

A ranked list of candidates for follow-up work. Each entry currently includes:

- `name`
- `decision`
- `uncertainty`
- `upside`
- `strategic_value`
- `priority_score`

## Current Decision Rules

The current implementation is intentionally simple.

### Gating

For each candidate:

1. If `invalid_run_rate > max_invalid_run_rate`, result is `inconclusive`.
2. If any primary metric delta is below its tolerance, result is `reject`.
3. If any metric delta is greater than or equal to `min_effect_size`, result is `promote`.
4. Otherwise, result is `inconclusive`.

Current tolerance behavior:

- primary metric tolerances are hardcoded to `-0.05` inside the CLI path

### Prioritization

Priority is currently heuristic:

- `upside` = largest positive metric delta
- `uncertainty` = `invalid_run_rate + 1 / run_count`
- `strategic_value` = `1.0` for `inconclusive`, otherwise `0.5`
- `priority_score` = `uncertainty + upside + strategic_value`

This is good enough for a first machine-readable ranking pass, but it is not a full research scheduler.

## Interpreting Results

### Promote

The candidate cleared the primary gates and produced at least one improvement above the minimum effect size.

### Reject

At least one primary metric regressed beyond tolerance.

### Inconclusive

Use this when:

- too many runs were invalid
- the observed changes were too small
- the candidate needs more seeds or a more targeted suite

For `inconclusive` outputs, inspect both:

- `decisions/<candidate>.json`
- `priorities.json`

Those two files tell you why the gate did not promote and whether the toolkit thinks the candidate is still worth additional runs.

## Relationship To `run_batch.py`

`run_batch.py` now supports `suites:` in dry-run or execution configs by expanding them into ordinary runs, but it does not write cohort summaries or decision artifacts.

Use:

- `run_batch.py` for raw batch launching
- `experiment_toolkit.py` for experiment gating and prioritization

## Practical Workflow

1. Start with a small no-LLM suite to verify the pipeline:

```bash
uv run experiment_toolkit.py tests/fixtures/experiments/gate_inventory_suite.yaml --output-dir /tmp/emerge-experiments
```

2. Inspect the generated files:

```bash
find /tmp/emerge-experiments/gate_inventory -maxdepth 3 -type f | sort
```

3. Open the decision artifact and check:

- which rules fired
- whether the candidate was promoted or marked inconclusive
- whether the comparison deltas match what you expected

4. Expand the suite:

- add more seeds
- add more candidates
- switch to LLM-enabled runs when the batch is worth the cost

## Current Limitations

This guide describes the code as it exists now. The following fields are present in the schema but not fully enforced yet:

- `mode` is descriptive only
- `metrics.secondary` and `metrics.stability` are stored but not weighted separately
- `budget.max_runs` is stored but not enforced
- primary tolerances are not configurable per suite yet in the execution path

There are also a few implementation details to keep in mind:

- run discovery is based on new directories appearing under `data/runs/`
- the toolkit executes runs sequentially
- prioritization is heuristic, not statistical
- human-readable reports are not part of this version

## Recommended First Use

Use the committed sample suite first:

```bash
uv run experiment_toolkit.py tests/fixtures/experiments/gate_inventory_suite.yaml --output-dir /tmp/emerge-experiments
```

If that completes and produces:

- `suite.json`
- at least one file under `cohorts/`
- at least one file under `decisions/`
- `priorities.json`

then the toolkit is wired correctly in your environment and you can start authoring larger suites.

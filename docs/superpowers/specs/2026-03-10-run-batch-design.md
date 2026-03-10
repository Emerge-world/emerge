# Design: run_batch — Batch Experiment Runner

Date: 2026-03-10

## Summary

A `run_batch.py` script at the project root that reads a YAML config file and
runs multiple `main.py` experiments sequentially, each tracked as an individual
W&B run. Failed experiments are skipped with a warning; a summary table is
printed at the end.

## Config file format (`experiments.yaml`)

```yaml
experiments:
  - name: baseline_seed42        # required; used as W&B run name prefix
    seed: 42
    agents: 3
    ticks: 100
    model: qwen2.5:3b
    runs: 3                      # optional (default: 1); repeats this config N times
    wandb: true                  # optional (default: true)

  - name: large_agents
    seed: 7
    agents: 5
    ticks: 200
    model: qwen2.5:3b

  - name: no_llm_smoke
    seed: 1
    agents: 2
    ticks: 50
    no_llm: true
    wandb: false
```

Supported keys (all optional except `name`):

| Key          | Type    | Maps to flag            | Default              |
|--------------|---------|-------------------------|----------------------|
| `name`       | str     | `--wandb-run-name`      | — (required)         |
| `seed`       | int     | `--seed`                | omitted              |
| `agents`     | int     | `--agents`              | omitted              |
| `ticks`      | int     | `--ticks`               | omitted              |
| `model`      | str     | `--model`               | omitted              |
| `no_llm`     | bool    | `--no-llm`              | false                |
| `wandb`      | bool    | `--wandb`               | true                 |
| `runs`       | int     | (repetition count)      | 1                    |

Unknown keys raise a clear error before any run starts.

## Script: `run_batch.py`

### CLI

```
uv run run_batch.py [config.yaml] [--dry-run]
```

- `config.yaml` — path to config file, defaults to `experiments.yaml`
- `--dry-run` — print the commands that would be run without executing them

### Execution flow

1. Load and validate YAML — fail fast on missing `name` or unknown keys.
2. Expand repetitions: `runs: 3` → three entries named `<name>_run1`, `<name>_run2`, `<name>_run3`. A config with `runs: 1` (or omitted) uses the name as-is (no suffix).
3. For each expanded run:
   - Print header: `[N/total] <run_name>`
   - Build command: `["uv", "run", "main.py", ...]`
   - Call `subprocess.run()` — output streams live to the terminal (no capturing).
   - Record result: OK (exit 0) or FAILED (non-zero exit).
4. Print summary table: run name | status | exit code.

### W&B run naming

When `wandb: true` (default), the script passes `--wandb-run-name <run_name>`.
The `--wandb` flag is also passed automatically so the user doesn't need to
repeat it in every experiment.

## Changes to existing files

### `simulation/wandb_logger.py`

- Add `run_name: Optional[str] = None` parameter to `__init__`.
- Pass `name=run_name` to `wandb.init()`.

### `main.py`

- Add `--wandb-run-name` argument (str, default None).
- Pass it to `WandbLogger.__init__()`.

## New files

- `run_batch.py` — the batch runner script
- `experiments.yaml` — committed template with 2–3 example experiments

## Out of scope

- Parallel execution
- Retry logic
- Capturing per-run output to separate log files

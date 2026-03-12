# 01 — Architecture (Codebase-Aligned)

## Runtime Topology

- `main.py` runs headless simulations (CLI mode).
- `server/run_server.py` + `server/server.py` run FastAPI + WebSocket mode.
- `simulation/engine.py` is the orchestration core in both modes.

```
Agents -> Oracle -> World
   |        |        |
   v        v        v
Memory   Precedents Resources
   \        |        /
    \---- EventEmitter ----> data/runs/<run_id>/events.jsonl
                          \-> blobs/prompts + llm_raw
                          \-> metrics/summary.json + timeseries.jsonl + ebs.json + scarcity.json

BenchmarkSuite YAML -> run_benchmark.py -> repeated main.py runs
                                           \-> data/benchmarks/<benchmark_id>/manifest.json
                                           \-> reports/summary.md + baseline_comparison.json
```

## Core Contracts

### Engine (`simulation/engine.py`)
- Owns world, agents, oracle, day cycle, lineage tracker, event emitter.
- Runs per-tick lifecycle and emits callback messages for web clients.
- Persists precedents/lineage/world state on shutdown paths.
- Emits resource consumption and regeneration events by diffing world resources before/after actions and dawn updates.
- Builds `MetricsBuilder`, `EBSBuilder`, and `ScarcityMetricsBuilder` outputs on shutdown.

### Agent (`simulation/agent.py`)
- Maintains stats, memory, personality, inventory, relationships.
- Decides action via structured LLM response or deterministic fallback.
- Starts with `INITIAL_ACTIONS`; `reproduce` unlocks by age.

### Oracle (`simulation/oracle.py`)
- Sole authority applying action outcomes and world mutations.
- Uses precedents for deterministic reuse.
- Handles base actions, innovated actions, crafting, social actions, reproduction checks.

### Event Layer (`simulation/event_emitter.py`)
- Always-on canonical telemetry per run.
- Stores prompt and raw LLM blobs deduplicated by hash.
- `meta.json` now records per-run scarcity settings and optional benchmark metadata.
- Event stream includes resource economy events (`resource_consumed`, `resource_regenerated`) in addition to action/state events.

### Benchmark Layer (`simulation/benchmark_suite.py`, `simulation/benchmark_report.py`, `run_benchmark.py`)
- `benchmark_suite.py` validates frozen YAML suites (`benchmarks/scarcity_v1.yaml`).
- `run_benchmark.py` expands scenario x seed runs, writes `data/benchmarks/<benchmark_id>/manifest.json`, and preserves failed runs.
- `benchmark_report.py` compares matched baseline/candidate pairs by scenario and writes aggregate reports.

## Invariants

1. Dead agents are never allowed to act.
2. Stats stay within clamped bounds.
3. Oracle remains the single mutation gateway for agent/world consequences.
4. Precedent lookups are deterministic for equivalent keys.
5. Event stream is append-only and machine-readable JSONL.

## Notable Supporting Modules

- `simulation/day_cycle.py`: day/sunset/night logic.
- `simulation/metrics_builder.py`: derives summary + timeseries from event streams.
- `simulation/scarcity.py`: per-run scarcity and benchmark metadata models.
- `simulation/scarcity_metrics.py`: derives scarcity adaptation metrics from resource/state events.
- `simulation/wandb_logger.py`: optional observer metrics to W&B.
- `run_batch.py`: YAML-configured subprocess sweep runner.
- `run_benchmark.py`: frozen scarcity benchmark runner across scenarios and seeds.
- `server/event_bus.py`: async fan-out from simulation thread to WebSocket clients.

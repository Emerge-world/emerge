# Scarcity Adaptation Benchmark Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a versioned scarcity benchmark pipeline that runs frozen food-scarcity scenarios across revisions and reports whether a candidate revision adapts better than a baseline revision.

**Architecture:** Add benchmark and scarcity configuration plumbing to the existing simulation event pipeline, emit explicit resource events, compute per-run scarcity metrics in `metrics/scarcity.json`, then add a suite loader, batch runner, and comparison reporter that operate on the existing immutable run directories under `data/runs/`.

**Tech Stack:** Python, pytest, PyYAML, existing `main.py`/`SimulationEngine`, existing JSONL event artifacts, existing metrics and EBS builders.

---

### Task 1: Add The Benchmark Suite Schema And Loader

**Files:**
- Create: `benchmarks/scarcity_v1.yaml`
- Create: `simulation/benchmark_suite.py`
- Test: `tests/test_benchmark_suite.py`

**Step 1: Write the failing test**

```python
from simulation.benchmark_suite import load_benchmark_suite


def test_load_benchmark_suite_reads_scenarios(tmp_path):
    path = tmp_path / "suite.yaml"
    path.write_text(
        """
benchmark_version: scarcity_v1
defaults:
  agents: 3
  ticks: 40
  width: 15
  height: 15
  no_llm: true
  seeds: [11, 22]
scenarios:
  - id: mild
    scarcity:
      initial_resource_scale: 0.6
      regen_chance_scale: 0.8
      regen_amount_scale: 0.8
""",
        encoding="utf-8",
    )

    suite = load_benchmark_suite(path)

    assert suite.benchmark_version == "scarcity_v1"
    assert suite.scenarios[0].id == "mild"
    assert suite.defaults.seeds == [11, 22]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_benchmark_suite.py -v`
Expected: FAIL with `ModuleNotFoundError` or missing `load_benchmark_suite`

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class BenchmarkDefaults:
    agents: int
    ticks: int
    width: int
    height: int
    no_llm: bool
    seeds: list[int]


@dataclass(frozen=True)
class ScarcityScenario:
    id: str
    label: str
    initial_resource_scale: float
    regen_chance_scale: float
    regen_amount_scale: float


def load_benchmark_suite(path: Path) -> BenchmarkSuite:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    ...
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_benchmark_suite.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add benchmarks/scarcity_v1.yaml simulation/benchmark_suite.py tests/test_benchmark_suite.py
git commit -m "feat: add scarcity benchmark suite loader"
```

### Task 2: Plumb Scarcity And Benchmark Metadata Through The Simulation

**Files:**
- Create: `simulation/scarcity.py`
- Modify: `simulation/world.py`
- Modify: `simulation/engine.py`
- Modify: `simulation/event_emitter.py`
- Modify: `main.py`
- Test: `tests/test_world.py`
- Test: `tests/test_event_emitter.py`
- Test: `tests/test_scarcity.py`

**Step 1: Write the failing tests**

```python
from simulation.scarcity import ScarcityConfig
from simulation.world import World


def test_initial_resource_scale_reduces_spawn_quantity():
    normal = World(width=10, height=10, seed=42)
    scarce = World(width=10, height=10, seed=42, scarcity=ScarcityConfig(initial_resource_scale=0.25))

    normal_total = sum(res["quantity"] for res in normal.resources.values() if res["type"] in {"fruit", "mushroom"})
    scarce_total = sum(res["quantity"] for res in scarce.resources.values() if res["type"] in {"fruit", "mushroom"})

    assert scarce_total < normal_total
```

```python
def test_meta_json_includes_benchmark_and_scarcity(tmp_path, monkeypatch):
    em = EventEmitter(
        ...,
        run_id="scarcity-v1__mild__seed11",
        benchmark_metadata={"benchmark_version": "scarcity_v1", "scenario_id": "mild", "candidate_label": "local"},
        scarcity_config={"initial_resource_scale": 0.6, "regen_chance_scale": 0.8, "regen_amount_scale": 0.8},
    )
    ...
    assert meta["benchmark"]["scenario_id"] == "mild"
    assert meta["scarcity"]["initial_resource_scale"] == 0.6
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_world.py tests/test_event_emitter.py tests/test_scarcity.py -v`
Expected: FAIL because `ScarcityConfig` and the new metadata plumbing do not exist yet

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class ScarcityConfig:
    initial_resource_scale: float = 1.0
    regen_chance_scale: float = 1.0
    regen_amount_scale: float = 1.0


@dataclass(frozen=True)
class BenchmarkMetadata:
    benchmark_id: str
    benchmark_version: str
    scenario_id: str
    candidate_label: str
    baseline_label: str | None = None
```

```python
class World:
    def __init__(..., scarcity: ScarcityConfig | None = None):
        self.scarcity = scarcity or ScarcityConfig()
```

```python
engine = SimulationEngine(
    ...,
    run_id=args.run_id,
    scarcity_config=ScarcityConfig(...),
    benchmark_metadata=BenchmarkMetadata(...),
)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_world.py tests/test_event_emitter.py tests/test_scarcity.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add simulation/scarcity.py simulation/world.py simulation/engine.py simulation/event_emitter.py main.py tests/test_world.py tests/test_event_emitter.py tests/test_scarcity.py
git commit -m "feat: add scarcity config and benchmark metadata plumbing"
```

### Task 3: Emit Resource Events And Build Per-Run Scarcity Metrics

**Files:**
- Create: `simulation/scarcity_metrics.py`
- Modify: `simulation/event_emitter.py`
- Modify: `simulation/engine.py`
- Test: `tests/test_scarcity_metrics.py`
- Test: `tests/test_event_emitter.py`

**Step 1: Write the failing tests**

```python
from simulation.scarcity_metrics import ScarcityMetricsBuilder


def test_build_writes_scarcity_json(tmp_path):
    run_dir = tmp_path / "run"
    _write_events(
        run_dir,
        [
            {"run_id": "r1", "tick": 1, "event_type": "agent_state", "agent_id": "Ada", "payload": {"alive": True, "hunger": 30, "life": 90, "energy": 70}},
            {"run_id": "r1", "tick": 1, "event_type": "resource_consumed", "agent_id": "Ada", "payload": {"resource_type": "fruit", "quantity": 1}},
            {"run_id": "r1", "tick": 2, "event_type": "run_end", "agent_id": None, "payload": {"survivors": ["Ada"], "total_ticks": 2}},
        ],
    )

    ScarcityMetricsBuilder(run_dir).build()

    data = json.loads((run_dir / "metrics" / "scarcity.json").read_text())
    assert "survival_auc" in data
    assert data["food_consumed"]["fruit"] == 1
```

```python
def test_emit_resource_regenerated_writes_event(tmp_path, monkeypatch):
    em = _make_emitter(tmp_path, monkeypatch)
    em.emit_resource_regenerated(24, resource_type="fruit", position=(3, 4), quantity=2)
    em.close()
    assert _read_events(tmp_path)[0]["event_type"] == "resource_regenerated"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scarcity_metrics.py tests/test_event_emitter.py -v`
Expected: FAIL because the new builder and event types do not exist

**Step 3: Write minimal implementation**

```python
class ScarcityMetricsBuilder:
    def build(self) -> None:
        summary = self._compute()
        (self._metrics_dir / "scarcity.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
```

```python
def emit_resource_consumed(self, tick: int, *, agent_name: str | None, resource_type: str, position: tuple[int, int], quantity: int):
    self._emit("resource_consumed", tick, {...}, agent_id=agent_name)
```

```python
resources_after_actions = {pos: dict(res) for pos, res in self.world.resources.items()}
for change in _diff_resources(resources_before, resources_after_actions):
    self.event_emitter.emit_resource_consumed(...)
```

Also update `SimulationEngine.run()` to call `ScarcityMetricsBuilder(self.event_emitter.run_dir).build()` after `MetricsBuilder` and `EBSBuilder`.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scarcity_metrics.py tests/test_event_emitter.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add simulation/scarcity_metrics.py simulation/event_emitter.py simulation/engine.py tests/test_scarcity_metrics.py tests/test_event_emitter.py
git commit -m "feat: add scarcity metrics from resource events"
```

### Task 4: Add Benchmark Comparison And Report Generation

**Files:**
- Create: `simulation/benchmark_report.py`
- Test: `tests/test_benchmark_report.py`

**Step 1: Write the failing tests**

```python
from simulation.benchmark_report import build_benchmark_report


def test_build_benchmark_report_marks_candidate_as_improved(tmp_path):
    benchmark_dir = tmp_path / "benchmarks" / "scarcity_v1_demo"
    benchmark_dir.mkdir(parents=True)
    (benchmark_dir / "manifest.json").write_text(json.dumps({
        "benchmark_version": "scarcity_v1",
        "candidate_label": "candidate",
        "baseline_label": "baseline",
        "runs": [
            {"scenario_id": "mild", "seed": 11, "role": "baseline", "scarcity_metrics": {"survival_auc": 0.40, "starvation_pressure": 0.80, "food_conversion_efficiency": 0.30}},
            {"scenario_id": "mild", "seed": 11, "role": "candidate", "scarcity_metrics": {"survival_auc": 0.65, "starvation_pressure": 0.45, "food_conversion_efficiency": 0.55}},
        ],
    }), encoding="utf-8")

    report = build_benchmark_report(benchmark_dir)

    assert report["overall_verdict"] == "improved"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_benchmark_report.py -v`
Expected: FAIL because `build_benchmark_report` does not exist

**Step 3: Write minimal implementation**

```python
def build_benchmark_report(benchmark_dir: Path) -> dict:
    manifest = json.loads((benchmark_dir / "manifest.json").read_text(encoding="utf-8"))
    ...
    return {
        "overall_verdict": overall_verdict,
        "scenarios": scenario_rows,
    }
```

Make sure the module:

- compares only matched `scenario_id` + `seed` pairs
- rejects mismatched `benchmark_version`
- writes `reports/candidate_summary.json`, `reports/baseline_comparison.json`, and `reports/summary.md`

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_benchmark_report.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add simulation/benchmark_report.py tests/test_benchmark_report.py
git commit -m "feat: add scarcity benchmark reporting"
```

### Task 5: Add The Benchmark Runner CLI

**Files:**
- Create: `run_benchmark.py`
- Modify: `benchmarks/scarcity_v1.yaml`
- Test: `tests/test_benchmark_runner.py`

**Step 1: Write the failing tests**

```python
from run_benchmark import build_run_command


def test_build_run_command_includes_scarcity_and_benchmark_flags():
    cmd = build_run_command(
        benchmark_id="scarcity_v1_demo",
        candidate_label="candidate",
        scenario_id="mild",
        seed=11,
        agents=3,
        ticks=40,
        width=15,
        height=15,
        no_llm=True,
        scarcity={"initial_resource_scale": 0.6, "regen_chance_scale": 0.8, "regen_amount_scale": 0.8},
    )

    assert cmd[:3] == ["uv", "run", "main.py"]
    assert "--benchmark-version" in cmd
    assert "--scenario-id" in cmd
    assert "--initial-resource-scale" in cmd
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_benchmark_runner.py -v`
Expected: FAIL because `run_benchmark.py` does not exist

**Step 3: Write minimal implementation**

```python
def build_run_command(...):
    return [
        "uv", "run", "main.py",
        "--run-id", run_id,
        "--seed", str(seed),
        "--agents", str(agents),
        "--ticks", str(ticks),
        "--benchmark-id", benchmark_id,
        "--benchmark-version", benchmark_version,
        "--scenario-id", scenario_id,
        "--candidate-label", candidate_label,
        "--initial-resource-scale", str(scarcity["initial_resource_scale"]),
        "--regen-chance-scale", str(scarcity["regen_chance_scale"]),
        "--regen-amount-scale", str(scarcity["regen_amount_scale"]),
        "--no-llm",
    ]
```

Implement `run_benchmark.py` so it:

- loads a frozen suite via `load_benchmark_suite()`
- expands every `scenario x seed` pair
- writes `data/benchmarks/<benchmark_id>/manifest.json`
- executes runs sequentially
- records failures instead of aborting the whole batch
- invokes `build_benchmark_report()` after the batch completes

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_benchmark_runner.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add run_benchmark.py benchmarks/scarcity_v1.yaml tests/test_benchmark_runner.py
git commit -m "feat: add scarcity benchmark runner"
```

### Task 6: Update Cornerstone Docs And Verify End-To-End

**Files:**
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Modify: `project-cornerstone/10-testing/testing_context.md`
- Modify: `project-cornerstone/01-architecture/architecture_context.md`

**Step 1: Write the failing doc/test checklist**

```text
- DECISION_LOG describes the benchmark architecture and why scarcity metrics are separate from EBS
- architecture_context documents the benchmark runner + scarcity metrics outputs
- testing_context documents the new suite loader, benchmark, and comparison tests
```

**Step 2: Run the targeted verification commands before the broad suite**

Run: `pytest tests/test_benchmark_suite.py tests/test_scarcity.py tests/test_scarcity_metrics.py tests/test_benchmark_report.py tests/test_benchmark_runner.py -v`
Expected: PASS

Run: `uv run main.py --no-llm --ticks 10 --agents 2 --run-id scarcity-smoke --initial-resource-scale 0.5 --regen-chance-scale 0.5 --regen-amount-scale 0.5`
Expected: PASS and create `data/runs/scarcity-smoke/metrics/scarcity.json`

**Step 3: Run the full benchmark smoke**

Run: `uv run run_benchmark.py benchmarks/scarcity_v1.yaml --candidate-label local-smoke --max-runs 2`
Expected: PASS and create `data/benchmarks/<benchmark_id>/reports/summary.md`

**Step 4: Run the fast suite**

Run: `pytest -m "not slow"`
Expected: PASS

**Step 5: Commit**

```bash
git add project-cornerstone/00-master-plan/DECISION_LOG.md project-cornerstone/10-testing/testing_context.md project-cornerstone/01-architecture/architecture_context.md
git commit -m "docs: record scarcity benchmark architecture"
```

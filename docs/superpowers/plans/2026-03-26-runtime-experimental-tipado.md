# Typed Experimental Runtime Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a typed per-run experimental runtime contract (`RuntimeSettings` + `ExperimentProfile`), wire `main.py` through it, and make the effective profile observable in run artifacts without coupling to the old benchmark runner.

**Architecture:** Add two focused modules: one pure dataclass contract module and one builder/serialization module that owns defaults, CLI mapping, legacy-engine normalization, and profile serialization. `main.py` becomes a profile builder + launcher, `SimulationEngine` becomes the compatibility boundary that normalizes to one effective profile, and `EventEmitter` records that effective profile in run metadata.

**Tech Stack:** Python 3.12 stdlib (`argparse`, `dataclasses`, `typing`, `json`), pytest, uv, markdown docs in `project-cornerstone/`

**Spec:** `docs/superpowers/specs/2026-03-26-runtime-experimental-tipado-design.md`

---

## File Structure

| File | Change | Responsibility |
|------|--------|----------------|
| `simulation/runtime_settings.py` | Create | Pure typed runtime dataclasses and mode aliases; no config or CLI knowledge |
| `simulation/runtime_profiles.py` | Create | Build default/CLI/legacy-engine profiles, serialize nested profile dicts, flatten profile keys for W&B |
| `main.py` | Modify | Build `ExperimentProfile` from CLI args, pass it to the engine, and derive W&B run config from `engine.profile` |
| `simulation/engine.py` | Modify | Accept `profile`, normalize legacy kwargs into an effective profile, preserve legacy direct-constructor semantics, and hand serialized profile to the emitter |
| `simulation/event_emitter.py` | Modify | Persist serialized `experiment_profile` in `meta.json` and `run_start` |
| `tests/test_runtime_profiles.py` | Create | Unit tests for default profile contract, CLI mapping, serialization, and flattened W&B config |
| `tests/test_main_runtime_profile.py` | Create | Entry-point tests for `main.py` profile wiring and W&B config derivation from `engine.profile` |
| `tests/test_engine_runtime_profile.py` | Create | Engine tests for profile precedence, legacy persistence defaults, agent clamping, and LLM fallback normalization |
| `tests/test_event_emitter.py` | Modify | Contract tests for persisted `experiment_profile` payloads |
| `tests/test_persistence_flag.py` | Modify | Keep CLI persistence expectations aligned with the new profile path and legacy engine compatibility |
| `project-cornerstone/00-master-plan/MASTER_PLAN.md` | Modify | Keep the canonical phase/status docs aligned with the new runtime boundary |
| `project-cornerstone/00-master-plan/DECISION_LOG.md` | Modify | Record the typed runtime/profile boundary decision |
| `project-cornerstone/01-architecture/architecture_context.md` | Modify | Document the new runtime boundary and run-artifact observability contract |

---

## Chunk 1: Typed Contract And Entry Point Wiring

### Task 1: Create the typed profile contract and builder helpers

**Files:**
- Create: `simulation/runtime_settings.py`
- Create: `simulation/runtime_profiles.py`
- Create: `tests/test_runtime_profiles.py`

- [ ] **Step 1: Write the failing unit tests for the profile layer**

Create `tests/test_runtime_profiles.py` with these tests:

```python
from dataclasses import replace

from main import build_parser
from simulation import config as sim_config
from simulation.runtime_profiles import (
    build_default_profile,
    build_profile_from_cli,
    build_profile_from_engine_kwargs,
    flatten_profile_for_wandb,
    serialize_experiment_profile,
)


def test_build_default_profile_matches_spec_defaults():
    profile = build_default_profile()

    assert profile.runtime.use_llm is True
    assert profile.runtime.model == sim_config.VLLM_MODEL
    assert profile.runtime.agents == 3
    assert profile.runtime.ticks == sim_config.MAX_TICKS
    assert profile.runtime.seed is None
    assert profile.runtime.width == sim_config.WORLD_WIDTH
    assert profile.runtime.height == sim_config.WORLD_HEIGHT
    assert profile.runtime.start_hour == sim_config.WORLD_START_HOUR

    assert profile.capabilities.explicit_planning is sim_config.ENABLE_EXPLICIT_PLANNING
    assert profile.capabilities.semantic_memory is True
    assert profile.capabilities.innovation is True
    assert profile.capabilities.item_reflection is True
    assert profile.capabilities.social is True
    assert profile.capabilities.teach is True
    assert profile.capabilities.reproduction is True

    assert profile.persistence.mode == "none"
    assert profile.persistence.clean_before_run is False
    assert profile.oracle.mode == "live"
    assert profile.oracle.freeze_precedents_path is None

    assert profile.benchmark.benchmark_id == "adhoc"
    assert profile.benchmark.benchmark_version == "adhoc"
    assert profile.benchmark.scenario_id == "default"
    assert profile.benchmark.arm_id == "default"
    assert profile.benchmark.seed_set is None
    assert profile.benchmark.session_id is None
    assert profile.benchmark.tags == []

    assert profile.world_overrides.initial_resource_scale is None
    assert profile.world_overrides.regen_chance_scale is None
    assert profile.world_overrides.regen_amount_scale is None
    assert profile.world_overrides.world_fixture is None


def test_default_list_fields_are_independent():
    first = build_default_profile()
    second = build_default_profile()

    first.benchmark.tags.append("smoke")

    assert second.benchmark.tags == []


def test_build_profile_from_cli_applies_runtime_overrides_only():
    parser = build_parser()
    args = parser.parse_args(
        [
            "--agents", "5",
            "--ticks", "12",
            "--seed", "77",
            "--no-llm",
            "--model", "test-model",
            "--width", "21",
            "--height", "13",
            "--start-hour", "20",
            "--persistence", "oracle",
        ]
    )

    profile = build_profile_from_cli(args)

    assert profile.runtime.agents == 5
    assert profile.runtime.ticks == 12
    assert profile.runtime.seed == 77
    assert profile.runtime.use_llm is False
    assert profile.runtime.model == "test-model"
    assert profile.runtime.width == 21
    assert profile.runtime.height == 13
    assert profile.runtime.start_hour == 20
    assert profile.persistence.mode == "oracle"

    assert profile.benchmark.benchmark_id == "adhoc"
    assert profile.oracle.mode == "live"


def test_build_profile_from_engine_kwargs_preserves_legacy_persistence_default():
    profile = build_profile_from_engine_kwargs(
        num_agents=1,
        world_seed=5,
        use_llm=False,
        max_ticks=2,
        start_hour=6,
        world_width=15,
        world_height=15,
        ollama_model=None,
        persistence="full",
    )

    assert profile.persistence.mode == "full"
    assert profile.runtime.agents == 1
    assert profile.runtime.seed == 5
    assert profile.runtime.use_llm is False


def test_build_profile_from_engine_kwargs_handles_none_inputs_like_legacy_constructor():
    profile = build_profile_from_engine_kwargs(
        num_agents=3,
        world_seed=None,
        use_llm=True,
        max_ticks=None,
        start_hour=sim_config.WORLD_START_HOUR,
        world_width=sim_config.WORLD_WIDTH,
        world_height=sim_config.WORLD_HEIGHT,
        ollama_model=None,
        persistence="full",
    )

    assert profile.runtime.seed is None
    assert profile.runtime.ticks is None
    assert profile.runtime.model == sim_config.VLLM_MODEL
    assert profile.persistence.mode == "full"


def test_profile_serialization_and_wandb_flattening_are_stable():
    profile = build_default_profile()
    profile = replace(
        profile,
        benchmark=replace(profile.benchmark, benchmark_id="runtime-pr1", tags=["typed"]),
    )

    payload = serialize_experiment_profile(profile)
    flattened = flatten_profile_for_wandb(profile)

    assert payload["runtime"]["agents"] == 3
    assert payload["benchmark"]["benchmark_id"] == "runtime-pr1"
    assert payload["benchmark"]["tags"] == ["typed"]

    assert flattened["profile/runtime/agents"] == 3
    assert flattened["profile/runtime/use_llm"] is True
    assert flattened["profile/oracle/mode"] == "live"
    assert flattened["profile/benchmark/benchmark_id"] == "runtime-pr1"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```bash
uv run pytest tests/test_runtime_profiles.py -v
```

Expected:
- `ModuleNotFoundError` for `simulation.runtime_profiles`
- or import failures because the typed profile helpers do not exist yet

- [ ] **Step 3: Implement the dataclasses and builder/serialization helpers**

Create `simulation/runtime_settings.py` with pure typed dataclasses and aliases:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

OracleMode = Literal["live", "frozen", "symbolic"]
PersistenceMode = Literal["none", "oracle", "lineage", "full"]


@dataclass(slots=True)
class RuntimeSettings:
    use_llm: bool
    model: str | None
    agents: int
    ticks: int | None
    seed: int | None
    width: int
    height: int
    start_hour: int


@dataclass(slots=True)
class CapabilitySettings:
    explicit_planning: bool
    semantic_memory: bool
    innovation: bool
    item_reflection: bool
    social: bool
    teach: bool
    reproduction: bool


@dataclass(slots=True)
class PersistenceSettings:
    mode: PersistenceMode
    clean_before_run: bool


@dataclass(slots=True)
class OracleSettings:
    mode: OracleMode
    freeze_precedents_path: str | None


@dataclass(slots=True)
class BenchmarkMetadata:
    benchmark_id: str
    benchmark_version: str
    scenario_id: str
    arm_id: str
    seed_set: str | None = None
    session_id: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WorldOverrides:
    initial_resource_scale: float | None = None
    regen_chance_scale: float | None = None
    regen_amount_scale: float | None = None
    world_fixture: str | None = None


@dataclass(slots=True)
class ExperimentProfile:
    runtime: RuntimeSettings
    capabilities: CapabilitySettings
    persistence: PersistenceSettings
    oracle: OracleSettings
    benchmark: BenchmarkMetadata
    world_overrides: WorldOverrides
```

Create `simulation/runtime_profiles.py` with the construction and serialization helpers:

```python
from __future__ import annotations

from dataclasses import asdict

from simulation import config as sim_config
from simulation.runtime_settings import (
    BenchmarkMetadata,
    CapabilitySettings,
    ExperimentProfile,
    OracleSettings,
    PersistenceSettings,
    RuntimeSettings,
    WorldOverrides,
)


def build_default_profile() -> ExperimentProfile:
    return ExperimentProfile(
        runtime=RuntimeSettings(
            use_llm=True,
            model=sim_config.VLLM_MODEL,
            agents=3,
            ticks=sim_config.MAX_TICKS,
            seed=None,
            width=sim_config.WORLD_WIDTH,
            height=sim_config.WORLD_HEIGHT,
            start_hour=sim_config.WORLD_START_HOUR,
        ),
        capabilities=CapabilitySettings(
            explicit_planning=sim_config.ENABLE_EXPLICIT_PLANNING,
            semantic_memory=True,
            innovation=True,
            item_reflection=True,
            social=True,
            teach=True,
            reproduction=True,
        ),
        persistence=PersistenceSettings(mode="none", clean_before_run=False),
        oracle=OracleSettings(mode="live", freeze_precedents_path=None),
        benchmark=BenchmarkMetadata(
            benchmark_id="adhoc",
            benchmark_version="adhoc",
            scenario_id="default",
            arm_id="default",
        ),
        world_overrides=WorldOverrides(),
    )


def build_profile_from_cli(args) -> ExperimentProfile:
    profile = build_default_profile()
    profile.runtime.agents = args.agents
    profile.runtime.ticks = args.ticks
    profile.runtime.seed = args.seed
    profile.runtime.use_llm = not args.no_llm
    profile.runtime.model = args.model or profile.runtime.model
    profile.runtime.width = args.width
    profile.runtime.height = args.height
    profile.runtime.start_hour = args.start_hour
    profile.persistence.mode = args.persistence
    return profile


def build_profile_from_engine_kwargs(
    *,
    num_agents: int,
    world_seed: int | None,
    use_llm: bool,
    max_ticks: int | None,
    start_hour: int,
    world_width: int,
    world_height: int,
    ollama_model: str | None,
    persistence: str,
) -> ExperimentProfile:
    profile = build_default_profile()
    profile.runtime.agents = num_agents
    profile.runtime.seed = world_seed
    profile.runtime.use_llm = use_llm
    profile.runtime.ticks = max_ticks
    profile.runtime.start_hour = start_hour
    profile.runtime.width = world_width
    profile.runtime.height = world_height
    profile.runtime.model = ollama_model or profile.runtime.model
    profile.persistence.mode = persistence
    return profile


def serialize_experiment_profile(profile: ExperimentProfile) -> dict:
    return asdict(profile)


def flatten_profile_for_wandb(profile: ExperimentProfile) -> dict:
    flattened: dict[str, object] = {}

    def _visit(prefix: str, value):
        if isinstance(value, dict):
            for key, child in value.items():
                _visit(f"{prefix}/{key}", child)
        else:
            flattened[prefix] = value

    _visit("profile", serialize_experiment_profile(profile))
    return flattened
```

Keep this module focused. Do not add YAML loading, benchmark manifests, or benchmark-specific conditionals here.

- [ ] **Step 4: Run the profile-layer tests and verify they pass**

Run:

```bash
uv run pytest tests/test_runtime_profiles.py -v
```

Expected: PASS for the new profile defaults, CLI mapping, legacy-engine helper, and serialization/flattening tests.

- [ ] **Step 5: Commit**

```bash
git add simulation/runtime_settings.py simulation/runtime_profiles.py tests/test_runtime_profiles.py
git commit -m "feat: add typed experimental runtime profiles"
```

---

## Chunk 2: Engine Compatibility, Entry Point Wiring, Observability, And Docs

### Task 3: Make `SimulationEngine` normalize to one effective profile

**Files:**
- Modify: `simulation/engine.py`
- Create: `tests/test_engine_runtime_profile.py`
- Modify: `tests/test_persistence_flag.py`

- [ ] **Step 1: Write the failing engine compatibility tests**

Create `tests/test_engine_runtime_profile.py`:

```python
from dataclasses import replace

from simulation.engine import SimulationEngine
from simulation.runtime_profiles import build_default_profile


def _patch_runtime_side_effects(monkeypatch):
    monkeypatch.setattr("simulation.engine.TICK_DELAY_SECONDS", 0)
    monkeypatch.setattr("simulation.engine.MetricsBuilder.build", lambda self: None)
    monkeypatch.setattr("simulation.engine.EBSBuilder.build", lambda self: None)


def test_profile_argument_has_precedence_over_legacy_kwargs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)
    profile = build_default_profile()
    profile = replace(
        profile,
        runtime=replace(
            profile.runtime,
            agents=2,
            ticks=1,
            seed=7,
            use_llm=False,
            width=18,
            height=12,
            start_hour=20,
        ),
        persistence=replace(profile.persistence, mode="none"),
    )

    engine = SimulationEngine(
        profile=profile,
        num_agents=99,
        world_seed=999,
        use_llm=True,
        max_ticks=123,
        start_hour=6,
        world_width=5,
        world_height=5,
        persistence="full",
        run_digest=False,
    )

    assert engine.profile.runtime.agents == 2
    assert engine.profile.runtime.seed == 7
    assert engine.profile.runtime.use_llm is False
    assert engine.profile.runtime.width == 18
    assert engine.profile.persistence.mode == "none"
    assert engine.max_ticks == 1
    assert engine._world_seed == 7
    assert engine._precedents_path.endswith("precedents_7.json")
    assert engine._lineage_path.endswith("lineage_7.json")


def test_legacy_engine_without_profile_keeps_full_persistence_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)

    engine = SimulationEngine(
        num_agents=1,
        use_llm=False,
        max_ticks=0,
        world_seed=3,
        run_digest=False,
    )

    assert engine.profile.persistence.mode == "full"


def test_agent_count_is_reflected_after_legacy_clamping(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)

    engine = SimulationEngine(
        num_agents=999,
        use_llm=False,
        max_ticks=0,
        world_seed=3,
        run_digest=False,
    )

    assert engine.profile.runtime.agents == len(engine.agents)


def test_unavailable_llm_updates_effective_profile(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)

    class FakeLLMClient:
        def __init__(self, *args, **kwargs):
            self.model = kwargs.get("model") or "fake-model"

        def is_available(self):
            return False

    monkeypatch.setattr("simulation.engine.LLMClient", FakeLLMClient)

    profile = build_default_profile()
    profile = replace(
        profile,
        runtime=replace(profile.runtime, use_llm=True, model="forced-model", ticks=0),
    )

    engine = SimulationEngine(profile=profile, run_digest=False)

    assert engine.use_llm is False
    assert engine.profile.runtime.use_llm is False
    assert engine.profile.runtime.model == "forced-model"


def test_explicit_wandb_logger_stays_outside_profile(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)
    sentinel = object()

    engine = SimulationEngine(
        profile=build_default_profile(),
        wandb_logger=sentinel,
        run_digest=False,
    )

    assert engine.wandb_logger is sentinel


def test_run_digest_stays_outside_profile(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)

    engine = SimulationEngine(
        profile=build_default_profile(),
        run_digest=False,
    )

    assert engine.run_digest is False
```

Update `tests/test_persistence_flag.py` so the CLI expectation matches the profile builder path:

```python
def test_persistence_defaults_to_none():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.persistence == "none"
```

- [ ] **Step 2: Run the engine compatibility tests and verify they fail**

Run:

```bash
uv run pytest tests/test_engine_runtime_profile.py tests/test_persistence_flag.py -v
```

Expected:
- `TypeError` because `SimulationEngine` does not accept `profile`
- or assertion failures because no effective profile is exposed and legacy defaults are not normalized into one typed object

- [ ] **Step 3: Update `simulation/engine.py` to own effective-profile normalization**

Modify `simulation/engine.py`:

1. Import the profile builder and serializer helpers:

```python
from simulation.runtime_profiles import (
    build_profile_from_engine_kwargs,
    serialize_experiment_profile,
)
from simulation.runtime_settings import ExperimentProfile
```

2. Extend `__init__` with `profile: ExperimentProfile | None = None`:

```python
def __init__(
    self,
    num_agents: int = 3,
    world_seed: Optional[int] = None,
    use_llm: bool = True,
    max_ticks: int | None = MAX_TICKS,
    start_hour: int = WORLD_START_HOUR,
    world_width: int = WORLD_WIDTH,
    world_height: int = WORLD_HEIGHT,
    wandb_logger: Optional["WandbLogger"] = None,
    ollama_model: Optional[str] = None,
    run_digest: bool = True,
    persistence: str = "full",
    profile: ExperimentProfile | None = None,
):
```

3. Normalize one profile up front:

```python
if profile is None:
    profile = build_profile_from_engine_kwargs(
        num_agents=num_agents,
        world_seed=world_seed,
        use_llm=use_llm,
        max_ticks=max_ticks,
        start_hour=start_hour,
        world_width=world_width,
        world_height=world_height,
        ollama_model=ollama_model,
        persistence=persistence,
    )

self.profile = profile
```

4. Use `self.profile.runtime` instead of loose kwargs for runtime construction, then write back startup normalization:

```python
runtime = self.profile.runtime
self.use_llm = runtime.use_llm
num_agents = min(runtime.agents, MAX_AGENTS)
runtime.agents = num_agents
world_seed = runtime.seed
max_ticks = runtime.ticks
start_hour = runtime.start_hour
world_width = runtime.width
world_height = runtime.height
use_llm = runtime.use_llm
ollama_model = runtime.model
persistence = self.profile.persistence.mode

self.max_ticks = max_ticks
self._world_seed = world_seed
seed_str = str(world_seed) if world_seed is not None else "unseeded"
self._precedents_path = f"data/precedents_{seed_str}.json"
self._lineage_path = f"data/lineage_{seed_str}.json"
```

5. After LLM availability check, persist effective fallback into the profile:

```python
if use_llm:
    kwargs = {"model": ollama_model} if ollama_model else {}
    self.llm = LLMClient(**kwargs)
    if not self.llm.is_available():
        logger.warning("⚠️  Ollama is not available. Running in fallback mode (no LLM).")
        self.llm = None
        self.use_llm = False
        self.profile.runtime.use_llm = False
```

6. Pass the serialized effective profile into `EventEmitter` at construction time:

```python
self._serialized_profile = serialize_experiment_profile(self.profile)

self.event_emitter = EventEmitter(
    run_id=self.run_id,
    seed=world_seed,
    world_width=world_width,
    world_height=world_height,
    max_ticks=max_ticks,
    agent_count=len(self.agents),
    agent_names=[a.name for a in self.agents],
    agent_model_id=_agent_model_id,
    oracle_model_id=_oracle_model_id,
    day_cycle=self.day_cycle,
    precedents_file=self._precedents_path,
    experiment_profile=self._serialized_profile,
)
```

Use that serialized dict for both emitter construction and `emit_run_start()` calls in `run()` and `run_with_callback()`.

- [ ] **Step 4: Run the engine compatibility tests and verify they pass**

Run:

```bash
uv run pytest tests/test_engine_runtime_profile.py tests/test_persistence_flag.py -v
```

Expected: PASS, including profile precedence, legacy direct-constructor persistence semantics, startup normalization, and updated CLI persistence expectation.

- [ ] **Step 5: Commit**

```bash
git add simulation/engine.py tests/test_engine_runtime_profile.py tests/test_persistence_flag.py
git commit -m "feat: normalize simulation engine to an effective runtime profile"
```

### Task 4: Wire `main.py` through the new profile layer

**Files:**
- Modify: `main.py`
- Create: `tests/test_main_runtime_profile.py`

- [ ] **Step 1: Write the failing `main.py` wiring tests**

Create `tests/test_main_runtime_profile.py`:

```python
from dataclasses import replace

import main as main_module
from simulation.runtime_profiles import build_default_profile


def test_main_builds_profile_and_passes_it_to_engine(monkeypatch):
    captured = {}

    class FakeEngine:
        def __init__(self, *, profile, run_digest, **kwargs):
            captured["profile"] = profile
            captured["run_digest"] = run_digest
            self.profile = profile
            self.run_id = "run-123"
            self.wandb_logger = None

        def run(self):
            captured["ran"] = True

    monkeypatch.setattr(main_module, "SimulationEngine", FakeEngine)
    monkeypatch.setattr(main_module, "setup_logging", lambda verbose: None)
    monkeypatch.setattr(
        "sys.argv",
        ["main.py", "--agents", "2", "--ticks", "5", "--seed", "9", "--no-llm"],
    )

    main_module.main()

    assert captured["profile"].runtime.agents == 2
    assert captured["profile"].runtime.ticks == 5
    assert captured["profile"].runtime.seed == 9
    assert captured["profile"].runtime.use_llm is False
    assert captured["run_digest"] is True
    assert captured["ran"] is True


def test_main_derives_wandb_run_config_from_engine_profile(monkeypatch, tmp_path):
    captured = {}
    requested = build_default_profile()
    normalized = replace(
        requested,
        runtime=replace(requested.runtime, agents=11, use_llm=False),
    )

    class FakeEngine:
        def __init__(self, *, profile, **kwargs):
            self.profile = normalized
            self.run_id = "run-456"
            self.wandb_logger = None

        def run(self):
            captured["ran"] = True

    class FakeWandbLogger:
        def __init__(self, *, run_config, run_name, **kwargs):
            captured["run_config"] = run_config
            captured["run_name"] = run_name

    monkeypatch.setattr(main_module, "SimulationEngine", FakeEngine)
    monkeypatch.setattr(main_module, "WandbLogger", FakeWandbLogger)
    monkeypatch.setattr(main_module, "setup_logging", lambda verbose: None)
    monkeypatch.setattr(
        "sys.argv",
        ["main.py", "--wandb", "--wandb-run-name", "cli-name", "--ticks", "1"],
    )

    main_module.main()

    assert captured["run_config"]["profile/runtime/agents"] == 11
    assert captured["run_config"]["profile/runtime/use_llm"] is False
    assert captured["run_config"]["LLM_TEMPERATURE"] == main_module.sim_config.LLM_TEMPERATURE
    assert "agents" not in captured["run_config"]
    assert captured["run_name"] == "cli-name"
```

- [ ] **Step 2: Run the `main.py` wiring tests and verify they fail**

Run:

```bash
uv run pytest tests/test_main_runtime_profile.py -v
```

Expected:
- assertions failing because `main.py` still calls `SimulationEngine` without `profile=`
- or W&B config still being built from raw CLI args instead of `engine.profile`

- [ ] **Step 3: Modify `main.py` to build and use the typed profile**

Update `main.py`:

1. Import the new helpers:

```python
from simulation.runtime_profiles import build_profile_from_cli, flatten_profile_for_wandb
```

2. Build the profile immediately after parsing args:

```python
profile = build_profile_from_cli(args)
```

3. Preserve the current CLI persistence default of `none` explicitly in `build_parser()` and make the help text match it, so the parser and profile-builder stay aligned:

```python
parser.add_argument(
    "--persistence",
    choices=["none", "oracle", "lineage", "full"],
    default="none",
    help="What to persist across runs: oracle precedents, lineage, both (full), or nothing (none). Default: none",
)
```

4. Pass `profile=profile` into `SimulationEngine` and keep `run_digest` as an explicit non-profile argument:

```python
engine = SimulationEngine(
    profile=profile,
    run_digest=not args.no_digest,
)
```

5. Build W&B config from `engine.profile`, not from raw CLI args:

```python
run_config = {
    **flatten_profile_for_wandb(engine.profile),
    "LLM_TEMPERATURE": sim_config.LLM_TEMPERATURE,
    "MOVE_ENERGY_COST": sim_config.ENERGY_COST_MOVE,
    "REST_ENERGY_GAIN": sim_config.ENERGY_RECOVERY_REST,
    "INNOVATE_ENERGY_COST": sim_config.ENERGY_COST_INNOVATE,
    "MAX_HUNGER": sim_config.AGENT_MAX_HUNGER,
    "HUNGER_DAMAGE": sim_config.HUNGER_DAMAGE_PER_TICK,
    "LIFE_MAX": sim_config.AGENT_MAX_LIFE,
    "ENERGY_MAX": sim_config.AGENT_MAX_ENERGY,
    "MEMORY_EPISODIC_MAX": sim_config.MEMORY_EPISODIC_MAX,
    "MEMORY_SEMANTIC_MAX": sim_config.MEMORY_SEMANTIC_MAX,
    "MEMORY_COMPRESSION_INTERVAL": sim_config.MEMORY_COMPRESSION_INTERVAL,
}
```

6. Keep W&B-specific CLI flags outside the profile path.

- [ ] **Step 4: Run the `main.py` wiring tests and verify they pass**

Run:

```bash
uv run pytest tests/test_main_runtime_profile.py -v
```

Expected: PASS, with `main.py` passing a typed profile into the engine and building W&B config from `engine.profile`.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main_runtime_profile.py
git commit -m "feat: wire main entrypoint through experiment profiles"
```

### Task 5: Persist the effective profile in run metadata and run-start events

**Files:**
- Modify: `simulation/event_emitter.py`
- Modify: `tests/test_event_emitter.py`

- [ ] **Step 1: Write the failing EventEmitter contract tests**

Add this helper near the top of `tests/test_event_emitter.py`:

```python
def _experiment_profile_dict() -> dict:
    return {
        "runtime": {
            "use_llm": False,
            "model": None,
            "agents": 3,
            "ticks": 72,
            "seed": 42,
            "width": 15,
            "height": 15,
            "start_hour": 6,
        },
        "capabilities": {
            "explicit_planning": True,
            "semantic_memory": True,
            "innovation": True,
            "item_reflection": True,
            "social": True,
            "teach": True,
            "reproduction": True,
        },
        "persistence": {"mode": "none", "clean_before_run": False},
        "oracle": {"mode": "live", "freeze_precedents_path": None},
        "benchmark": {
            "benchmark_id": "adhoc",
            "benchmark_version": "adhoc",
            "scenario_id": "default",
            "arm_id": "default",
            "seed_set": None,
            "session_id": None,
            "tags": [],
        },
        "world_overrides": {
            "initial_resource_scale": None,
            "regen_chance_scale": None,
            "regen_amount_scale": None,
            "world_fixture": None,
        },
    }
```

Update `_make_emitter()` to accept `experiment_profile=None` and pass it through to `EventEmitter(...)`.

Add these tests:

```python
class TestExperimentProfileMetadata:
    def test_meta_json_includes_experiment_profile(self, tmp_path, monkeypatch):
        profile = _experiment_profile_dict()
        em = _make_emitter(tmp_path, monkeypatch, experiment_profile=profile)
        em.close()

        meta = json.loads(
            (tmp_path / "data" / "runs" / "test-run-1234" / "meta.json").read_text()
        )
        assert meta["experiment_profile"] == profile

    def test_run_start_payload_includes_experiment_profile(self, tmp_path, monkeypatch):
        profile = _experiment_profile_dict()
        em = _make_emitter(tmp_path, monkeypatch, experiment_profile=profile)
        em.emit_run_start(
            ["Ada"],
            "my-model",
            42,
            15,
            15,
            72,
            experiment_profile=profile,
        )
        em.close()

        payload = _read_events(tmp_path)[0]["payload"]
        assert payload["config"]["experiment_profile"] == profile
```

- [ ] **Step 2: Run the EventEmitter tests and verify they fail**

Run:

```bash
uv run pytest tests/test_event_emitter.py -k "experiment_profile or meta_json_fields or run_start" -v
```

Expected:
- `TypeError` because `EventEmitter` and `emit_run_start()` do not accept `experiment_profile`
- or assertion failures because the serialized profile is missing from `meta.json` and `run_start`

- [ ] **Step 3: Extend `EventEmitter` to persist the serialized profile**

Modify `simulation/event_emitter.py`:

1. Extend the constructor:

```python
def __init__(
    self,
    run_id: str,
    seed: Optional[int],
    world_width: int,
    world_height: int,
    max_ticks: int | None,
    agent_count: int,
    agent_names: list[str],
    agent_model_id: str,
    oracle_model_id: str,
    day_cycle: DayCycle,
    precedents_file: Optional[str] = None,
    experiment_profile: Optional[dict] = None,
):
    self._experiment_profile = experiment_profile
```

2. Include it in `meta.json` when present:

```python
if experiment_profile is not None:
    meta["experiment_profile"] = experiment_profile
```

3. Extend `emit_run_start()`:

```python
def emit_run_start(
    self,
    agent_names: list[str],
    model_id: str,
    world_seed: Optional[int],
    width: int,
    height: int,
    max_ticks: int | None,
    agent_profiles: Optional[list[dict]] = None,
    experiment_profile: Optional[dict] = None,
):
    config = {
        "width": width,
        "height": height,
        "max_ticks": max_ticks,
        "agent_count": len(agent_names),
        "agent_names": agent_names,
    }
    profile_payload = experiment_profile or self._experiment_profile
    if profile_payload is not None:
        config["experiment_profile"] = profile_payload
```

Keep `EventEmitter` dataclass-agnostic: it should only ever receive plain nested dicts.

- [ ] **Step 4: Run the EventEmitter tests and verify they pass**

Run:

```bash
uv run pytest tests/test_event_emitter.py -v
```

Expected: PASS for the new `experiment_profile` metadata contract and the existing event-emitter tests.

- [ ] **Step 5: Commit**

```bash
git add simulation/event_emitter.py tests/test_event_emitter.py
git commit -m "feat: persist effective experiment profile in run artifacts"
```

### Task 6: Update cornerstone docs and run full verification

**Files:**
- Modify: `project-cornerstone/00-master-plan/MASTER_PLAN.md`
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Modify: `project-cornerstone/01-architecture/architecture_context.md`

- [ ] **Step 1: Update cornerstone docs for the new runtime boundary**

Add a decision-log entry to `project-cornerstone/00-master-plan/DECISION_LOG.md` that records:

- `ExperimentProfile` is now the canonical per-run contract
- `config.py` remains defaults-only
- `SimulationEngine.profile` is the effective post-normalization profile
- run artifacts serialize the effective profile under `experiment_profile`

Update `project-cornerstone/01-architecture/architecture_context.md` to describe:

- the new `runtime_settings.py` / `runtime_profiles.py` split
- `main.py -> ExperimentProfile -> SimulationEngine` flow
- `meta.json` and `run_start.config.experiment_profile` as the observability contract

Update `project-cornerstone/00-master-plan/MASTER_PLAN.md` with a short note in current product reality or priority/constraints so the canonical master plan reflects that the runtime now has a typed per-run profile boundary for experimental runs.

- [ ] **Step 2: Run the focused regression suite**

Run:

```bash
uv run pytest \
  tests/test_runtime_profiles.py \
  tests/test_main_runtime_profile.py \
  tests/test_engine_runtime_profile.py \
  tests/test_event_emitter.py \
  tests/test_persistence_flag.py -v
```

Expected: PASS for all new and updated runtime-profile tests.

- [ ] **Step 3: Run the standard non-slow suite**

Run:

```bash
uv run pytest -m "not slow"
```

Expected: PASS for the existing repo test suite.

- [ ] **Step 4: Run a smoke simulation through the CLI**

Run:

```bash
uv run main.py --no-llm --ticks 1 --agents 1
```

Expected:
- simulation starts and exits cleanly
- a new `data/runs/<run_id>/meta.json` is written
- `meta.json` includes `experiment_profile`

- [ ] **Step 5: Commit**

```bash
git add \
  project-cornerstone/00-master-plan/MASTER_PLAN.md \
  project-cornerstone/00-master-plan/DECISION_LOG.md \
  project-cornerstone/01-architecture/architecture_context.md
git commit -m "docs: record typed runtime profile boundary"
```

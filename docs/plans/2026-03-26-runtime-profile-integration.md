# Runtime Profile Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the real simulation runtime obey `ExperimentProfile` for backend capabilities and world overrides, with minimal integration tests that prove disabled capabilities are blocked in backend paths.

**Architecture:** Keep `ExperimentProfile` as the external run boundary, but derive subsystem-oriented runtime settings inside `SimulationEngine` and inject them into `World`, `Agent`, `Oracle`, and `Memory`. Backend enforcement must fail closed while preserving current behavior when all capabilities are enabled, and prompt-surface changes remain out of scope for this plan.

**Tech Stack:** Python 3, dataclasses, pytest, monkeypatch-based doubles, existing simulation runtime modules

---

### Task 1: Add Runtime Policy Derivation Layer

**Files:**
- Create: `simulation/runtime_policy.py`
- Test: `tests/test_runtime_policy.py`

**Step 1: Write the failing test**

Add unit tests that derive subsystem settings from `build_default_profile()` and a modified profile.

```python
from dataclasses import replace

from simulation.runtime_policy import derive_runtime_policy
from simulation.runtime_profiles import build_default_profile


def test_derive_runtime_policy_maps_capabilities_and_world_overrides():
    profile = build_default_profile()
    profile = replace(
        profile,
        world_overrides=replace(
            profile.world_overrides,
            initial_resource_scale=0.5,
            regen_chance_scale=0.25,
            regen_amount_scale=2.0,
        ),
    )
    profile.capabilities.explicit_planning = False
    profile.capabilities.semantic_memory = False

    policy = derive_runtime_policy(profile)

    assert policy.agent.explicit_planning is False
    assert policy.memory.semantic_memory is False
    assert policy.world.initial_resource_scale == 0.5
    assert policy.oracle.innovation is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runtime_policy.py -q`

Expected: FAIL with `ModuleNotFoundError` or missing `derive_runtime_policy`

**Step 3: Write minimal implementation**

Create `simulation/runtime_policy.py` with small internal dataclasses and a single derivation entrypoint.

```python
from dataclasses import dataclass


@dataclass(slots=True)
class AgentRuntimeSettings:
    explicit_planning: bool
    innovation: bool
    item_reflection: bool
    social: bool
    teach: bool
    reproduction: bool


@dataclass(slots=True)
class MemoryRuntimeSettings:
    semantic_memory: bool


@dataclass(slots=True)
class OracleRuntimeSettings:
    innovation: bool
    item_reflection: bool
    social: bool
    teach: bool
    reproduction: bool


@dataclass(slots=True)
class WorldRuntimeSettings:
    initial_resource_scale: float | None
    regen_chance_scale: float | None
    regen_amount_scale: float | None


@dataclass(slots=True)
class RuntimePolicy:
    agent: AgentRuntimeSettings
    memory: MemoryRuntimeSettings
    oracle: OracleRuntimeSettings
    world: WorldRuntimeSettings


def derive_runtime_policy(profile):
    caps = profile.capabilities
    return RuntimePolicy(
        agent=AgentRuntimeSettings(
            explicit_planning=caps.explicit_planning,
            innovation=caps.innovation,
            item_reflection=caps.item_reflection,
            social=caps.social,
            teach=caps.teach,
            reproduction=caps.reproduction,
        ),
        memory=MemoryRuntimeSettings(semantic_memory=caps.semantic_memory),
        oracle=OracleRuntimeSettings(
            innovation=caps.innovation,
            item_reflection=caps.item_reflection,
            social=caps.social,
            teach=caps.teach,
            reproduction=caps.reproduction,
        ),
        world=WorldRuntimeSettings(
            initial_resource_scale=profile.world_overrides.initial_resource_scale,
            regen_chance_scale=profile.world_overrides.regen_chance_scale,
            regen_amount_scale=profile.world_overrides.regen_amount_scale,
        ),
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_runtime_policy.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add simulation/runtime_policy.py tests/test_runtime_policy.py
git commit -m "feat: derive runtime policy from experiment profile"
```

### Task 2: Make World Obey Profile Resource Overrides

**Files:**
- Modify: `simulation/world.py`
- Modify or Test: `tests/test_world.py`

**Step 1: Write the failing test**

Add deterministic tests for initial spawn scaling and regeneration scaling.

```python
from simulation.runtime_policy import WorldRuntimeSettings
from simulation.world import World


def test_initial_resource_scale_reduces_spawned_resource_quantity():
    baseline = World(width=15, height=15, seed=7)
    scaled = World(
        width=15,
        height=15,
        seed=7,
        runtime_settings=WorldRuntimeSettings(
            initial_resource_scale=0.5,
            regen_chance_scale=None,
            regen_amount_scale=None,
        ),
    )

    baseline_total = sum(res["quantity"] for res in baseline.resources.values())
    scaled_total = sum(res["quantity"] for res in scaled.resources.values())

    assert scaled_total < baseline_total
```

Add a second test that forces regeneration and asserts scaled chance/amount changes the result.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_world.py -q`

Expected: FAIL because `World` does not accept `runtime_settings` yet

**Step 3: Write minimal implementation**

Update `World.__init__()` and resource helper paths to use injected settings.

```python
def _scale_quantity(self, qty: int) -> int:
    scale = self.runtime_settings.initial_resource_scale
    if scale is None:
        return qty
    return max(0, round(qty * scale))


def _regen_chance(self) -> float:
    scale = self.runtime_settings.regen_chance_scale
    base = RESOURCE_REGEN_CHANCE
    if scale is None:
        return base
    return max(0.0, min(1.0, base * scale))
```

Apply the same pattern for regeneration amount.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_world.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add simulation/world.py tests/test_world.py
git commit -m "feat: apply runtime world overrides"
```

### Task 3: Make Memory Obey Semantic-Memory Settings

**Files:**
- Modify: `simulation/memory.py`
- Modify: `tests/test_memory.py`

**Step 1: Write the failing test**

Add tests that prove semantic memory can be disabled while episodic memory stays active.

```python
from simulation.memory import Memory
from simulation.runtime_policy import MemoryRuntimeSettings


def test_semantic_memory_disabled_omits_knowledge_and_skips_compression():
    mem = Memory(runtime_settings=MemoryRuntimeSettings(semantic_memory=False))
    mem.add_episode("I saw fruit.")
    mem.add_knowledge("Fruit grows on trees.")

    assert "KNOWLEDGE" not in mem.to_prompt()
    assert mem.semantic == []
    assert mem.should_compress(10) is False
```

Add a second test for `inherit_from()` with semantic memory disabled.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_memory.py -q`

Expected: FAIL because `Memory` does not accept runtime settings and still stores semantic knowledge

**Step 3: Write minimal implementation**

Inject `MemoryRuntimeSettings` into `Memory` and gate semantic-only methods.

```python
class Memory:
    def __init__(self, runtime_settings=None):
        self.runtime_settings = runtime_settings or MemoryRuntimeSettings(
            semantic_memory=True
        )

    def add_knowledge(self, entry: str):
        if not self.runtime_settings.semantic_memory:
            return
        ...
```

Make the same gating change in `should_compress()`, `compress()`, `to_prompt()`, and `inherit_from()`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_memory.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add simulation/memory.py tests/test_memory.py
git commit -m "feat: gate semantic memory by runtime settings"
```

### Task 4: Make Agent Actions And Planning Capability-Aware

**Files:**
- Modify: `simulation/agent.py`
- Modify: `tests/test_agent_planning.py`
- Modify: `tests/test_reproduction.py`
- Create or Test: `tests/test_agent_runtime_capabilities.py`

**Step 1: Write the failing test**

Add tests for:

- `explicit_planning=false` skips planner invocation
- `social=false` removes `communicate`, `give_item`, and `teach`
- `teach=false` removes only `teach`
- `item_reflection=false` removes `reflect_item_uses`
- `innovation=false` removes `innovate`
- `reproduction=false` never unlocks `reproduce`

```python
from simulation.agent import Agent
from simulation.runtime_policy import AgentRuntimeSettings, MemoryRuntimeSettings


def test_reproduction_disabled_never_unlocks_action():
    agent = Agent(
        runtime_settings=AgentRuntimeSettings(
            explicit_planning=True,
            innovation=True,
            item_reflection=True,
            social=True,
            teach=True,
            reproduction=False,
        ),
        memory_settings=MemoryRuntimeSettings(semantic_memory=True),
    )

    agent.unlock_actions_for_tick(10_000)

    assert "reproduce" not in agent.actions
```

Use a planner double in the planning test and assert it is never called.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agent_planning.py tests/test_reproduction.py tests/test_agent_runtime_capabilities.py -q`

Expected: FAIL because `Agent` still reads global planning and action defaults

**Step 3: Write minimal implementation**

Inject `AgentRuntimeSettings` and `MemoryRuntimeSettings` into `Agent`, build the default action list from capability helpers, and gate the planner branch.

```python
def _build_initial_actions(self) -> list[str]:
    actions = ["move", "eat", "rest", "pickup", "drop_item"]
    if self.runtime_settings.innovation:
        actions.append("innovate")
    if self.runtime_settings.social:
        actions.extend(["communicate", "give_item"])
        if self.runtime_settings.teach:
            actions.append("teach")
    if self.runtime_settings.item_reflection:
        actions.append("reflect_item_uses")
    return actions
```

Then:

- instantiate `Memory(runtime_settings=memory_settings)`
- gate planning with `self.runtime_settings.explicit_planning`
- gate reproduction unlock with `self.runtime_settings.reproduction`

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agent_planning.py tests/test_reproduction.py tests/test_agent_runtime_capabilities.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add simulation/agent.py tests/test_agent_planning.py tests/test_reproduction.py tests/test_agent_runtime_capabilities.py
git commit -m "feat: make agent capabilities runtime-aware"
```

### Task 5: Make Oracle Enforce Capability Gates

**Files:**
- Modify: `simulation/oracle.py`
- Create or Test: `tests/test_oracle_runtime_capabilities.py`
- Modify: `tests/test_innovation.py`
- Modify: `tests/test_teach.py`
- Modify: `tests/test_communication.py`
- Modify: `tests/test_give_item.py`

**Step 1: Write the failing test**

Add focused tests that force disabled actions through `Oracle.resolve_action()`.

```python
from simulation.agent import Agent
from simulation.oracle import Oracle
from simulation.runtime_policy import OracleRuntimeSettings
from simulation.world import World


def test_oracle_treats_disabled_innovate_as_unavailable():
    world = World(seed=7)
    oracle = Oracle(
        world,
        runtime_settings=OracleRuntimeSettings(
            innovation=False,
            item_reflection=True,
            social=True,
            teach=True,
            reproduction=True,
        ),
    )
    agent = Agent()
    result = oracle.resolve_action(
        agent,
        {"action": "innovate", "new_action_name": "fish", "description": "catch fish"},
        tick=1,
    )

    assert result["success"] is False
    assert "Unknown action" in result["message"]
```

Add similar tests for:

- `reflect_item_uses` when item reflection is disabled
- `communicate` and `give_item` when social is disabled
- `teach` when either `social=false` or `teach=false`
- `reproduce` when reproduction is disabled
- post-craft affordance discovery blocked when `innovation=false`

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_oracle_runtime_capabilities.py -q`

Expected: FAIL because Oracle still accepts these actions

**Step 3: Write minimal implementation**

Add a small helper near `resolve_action()` and use it before dispatch.

```python
def _action_allowed(self, action_type: str) -> bool:
    if action_type == "innovate":
        return self.runtime_settings.innovation
    if action_type == "reflect_item_uses":
        return self.runtime_settings.item_reflection
    if action_type in {"communicate", "give_item"}:
        return self.runtime_settings.social
    if action_type == "teach":
        return self.runtime_settings.social and self.runtime_settings.teach
    if action_type == "reproduce":
        return self.runtime_settings.reproduction
    return True
```

When not allowed, return the same fallback shape as an unavailable action.

Also add a guard in `_trigger_post_craft_affordances()` and `_discover_item_affordances()` so `innovation=false` prevents side-entry action creation.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_oracle_runtime_capabilities.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add simulation/oracle.py tests/test_oracle_runtime_capabilities.py tests/test_innovation.py tests/test_teach.py tests/test_communication.py tests/test_give_item.py
git commit -m "feat: enforce runtime capability gates in oracle"
```

### Task 6: Wire Runtime Policy Through SimulationEngine

**Files:**
- Modify: `simulation/engine.py`
- Modify: `tests/test_engine_runtime_profile.py`
- Create or Test: `tests/test_engine_runtime_capabilities.py`

**Step 1: Write the failing test**

Add integration tests that construct `SimulationEngine(profile=...)` and prove settings reach real subsystems.

```python
from dataclasses import replace

from simulation.engine import SimulationEngine
from simulation.runtime_profiles import build_default_profile


def test_engine_injects_runtime_policy_into_agent_memory_oracle_and_world(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("simulation.engine.TICK_DELAY_SECONDS", 0)
    monkeypatch.setattr("simulation.engine.MetricsBuilder.build", lambda self: None)
    monkeypatch.setattr("simulation.engine.EBSBuilder.build", lambda self: None)

    profile = build_default_profile()
    profile.capabilities.explicit_planning = False
    profile.capabilities.semantic_memory = False
    profile.capabilities.innovation = False
    profile.world_overrides.initial_resource_scale = 0.5

    engine = SimulationEngine(profile=profile, run_digest=False)

    assert engine.agents[0].runtime_settings.explicit_planning is False
    assert engine.agents[0].memory_system.runtime_settings.semantic_memory is False
    assert engine.oracle.runtime_settings.innovation is False
    assert engine.world.runtime_settings.initial_resource_scale == 0.5
```

Add a second test for child spawning that asserts spawned children receive the same runtime settings object or equivalent settings values.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_engine_runtime_profile.py tests/test_engine_runtime_capabilities.py -q`

Expected: FAIL because engine does not derive or inject runtime policy

**Step 3: Write minimal implementation**

Update `SimulationEngine.__init__()` to derive runtime policy once and inject it into every subsystem, including `_spawn_child()`.

```python
from simulation.runtime_policy import derive_runtime_policy

...
self.runtime_policy = derive_runtime_policy(self.profile)
self.world = World(..., runtime_settings=self.runtime_policy.world)
self.oracle = Oracle(..., runtime_settings=self.runtime_policy.oracle)
agent = Agent(..., runtime_settings=self.runtime_policy.agent, memory_settings=self.runtime_policy.memory)
```

Preserve legacy behavior when no profile is passed by keeping `build_profile_from_engine_kwargs()`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_engine_runtime_profile.py tests/test_engine_runtime_capabilities.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add simulation/engine.py tests/test_engine_runtime_profile.py tests/test_engine_runtime_capabilities.py
git commit -m "feat: inject runtime policy into simulation subsystems"
```

### Task 7: Add End-To-End Capability Regression Coverage

**Files:**
- Create or Modify: `tests/test_runtime_profile_capabilities.py`

**Step 1: Write the failing test**

Add a compact integration file that covers the user-facing minimum matrix with doubles:

- planning off: planner not called, no planning events
- semantic memory off: no semantic learnings, no `KNOWLEDGE`
- innovation off: forced innovation blocked
- item reflection off: forced manual reflection blocked
- social off: forced social actions blocked
- teach off: only teach blocked
- reproduction off: no reproduce action and no child spawn

```python
def test_teach_off_preserves_other_social_actions():
    ...
    assert "communicate" in engine.agents[0].actions
    assert "give_item" in engine.agents[0].actions
    assert "teach" not in engine.agents[0].actions
```

Keep doubles local to the test file. There is no shared `MockLLM` in the repo today.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runtime_profile_capabilities.py -q`

Expected: FAIL until all previous tasks are integrated correctly

**Step 3: Write minimal implementation**

Do not add new production code in this task unless the failing integration tests expose a missing gap. If they do, patch the smallest missing runtime gate and rerun.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_runtime_profile_capabilities.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_runtime_profile_capabilities.py simulation/agent.py simulation/oracle.py simulation/engine.py simulation/memory.py simulation/world.py
git commit -m "test: add runtime profile capability regressions"
```

### Task 8: Update Cornerstone Docs And Run Full Verification

**Files:**
- Modify: `project-cornerstone/00-master-plan/MASTER_PLAN.md`
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Modify: `project-cornerstone/01-architecture/architecture_context.md`
- Modify: `project-cornerstone/02-world/world_context.md`
- Modify: `project-cornerstone/03-agents/agents_context.md`
- Modify: `project-cornerstone/04-oracle/oracle_context.md`
- Modify: `project-cornerstone/10-testing/testing_context.md`

**Step 1: Write the failing doc/test checks**

Write a short checklist in your working notes before editing docs:

- architecture docs must state that runtime behavior is derived from `ExperimentProfile`
- world docs must mention profile-driven resource scaling
- agent docs must mention capability-aware action repertoire and planning gate
- oracle docs must mention runtime capability enforcement
- testing docs must mention new capability regression coverage
- decision log must record the boundary between backend enforcement now and prompt-surface changes later

**Step 2: Run targeted verification before final doc edits**

Run:

- `uv run pytest tests/test_runtime_policy.py -q`
- `uv run pytest tests/test_world.py tests/test_memory.py -q`
- `uv run pytest tests/test_agent_runtime_capabilities.py tests/test_oracle_runtime_capabilities.py -q`
- `uv run pytest tests/test_engine_runtime_profile.py tests/test_engine_runtime_capabilities.py tests/test_runtime_profile_capabilities.py -q`

Expected: PASS

**Step 3: Write minimal documentation updates**

Update the cornerstone files to match the implemented architecture. Keep entries short and concrete.

Example DECISION_LOG entry shape:

```markdown
### DEC-0XX: Backend runtime capabilities are enforced from ExperimentProfile

- `SimulationEngine` derives subsystem runtime policy from `ExperimentProfile`
- `Agent`, `Memory`, `Oracle`, and `World` consume explicit runtime settings
- backend enforcement lands before prompt-surface fidelity
```

**Step 4: Run the full fast suite**

Run: `uv run pytest -m "not slow"`

Expected: PASS

**Step 5: Commit**

```bash
git add project-cornerstone/00-master-plan/MASTER_PLAN.md project-cornerstone/00-master-plan/DECISION_LOG.md project-cornerstone/01-architecture/architecture_context.md project-cornerstone/02-world/world_context.md project-cornerstone/03-agents/agents_context.md project-cornerstone/04-oracle/oracle_context.md project-cornerstone/10-testing/testing_context.md
git commit -m "docs: record runtime profile integration"
```

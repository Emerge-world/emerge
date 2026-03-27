# Capability-Aware Prompt Surface Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a shared `PromptSurfaceBuilder` that makes executor and planner prompts obey runtime capability ablations without duplicating full prompt templates, and lock that behavior in with golden prompt tests.

**Architecture:** Add `simulation/prompt_surface.py` as the single composition layer for agent-facing prompts. Keep the existing `prompts/agent/*.txt` files as base templates, replace capability-sensitive prose with optional placeholders, and route both `Agent` and `Planner` through the same builder so backend runtime policy and prompt surface cannot drift apart. Golden tests under `tests/golden/prompts/` will verify the fully rendered prompts, while existing runtime tests continue to verify backend gating.

**Tech Stack:** Python 3.12, `string.Template`, pytest, pathlib, existing `simulation.runtime_policy` dataclasses, prompt files under `prompts/agent`

---

**Spec Reference:** `docs/superpowers/specs/2026-03-27-capability-aware-prompt-surface-design.md`

## File Structure

- `simulation/prompt_surface.py`
  Purpose: new shared prompt composition layer. Owns optional block assembly, capability checks, and final whitespace normalization.
- `simulation/agent.py`
  Purpose: instantiate one `PromptSurfaceBuilder`, route executor prompt rendering through it, and move planner observation text assembly behind the same capability-aware layer.
- `simulation/planner.py`
  Purpose: consume the shared `PromptSurfaceBuilder` for planner system/user prompts instead of calling `prompt_loader.render()` directly.
- `simulation/prompt_loader.py`
  Purpose: low-level prompt loader/renderer. Reference only unless the implementation finds a real bug; do not turn it into the capability layer.
- `prompts/agent/system.txt`
  Purpose: base executor system prompt. Replace capability-sensitive sections with placeholders.
- `prompts/agent/decision.txt`
  Purpose: base executor decision prompt. Replace planning/social/reproduction/reflection sections with placeholders.
- `prompts/agent/planner_system.txt`
  Purpose: base planner system prompt. Replace capability-sensitive guidance with placeholders.
- `prompts/agent/planner.txt`
  Purpose: base planner user prompt. Replace current-plan and reflection-question sections with placeholders.
- `tests/test_prompt_surface.py`
  Purpose: new golden-test harness for full rendered executor/planner prompts.
- `tests/golden/prompts/*.txt`
  Purpose: canonical rendered prompt fixtures for full and ablated surfaces.
- `tests/test_agent_prompts.py`
  Purpose: integration regressions that prove `Agent._build_system_prompt()` and `Agent._build_decision_prompt()` expose or hide sections correctly.
- `tests/test_planner.py`
  Purpose: planner prompt regressions and direct `Planner.plan()` compatibility after constructor wiring changes.
- `tests/test_agent_planning.py`
  Purpose: preserve existing “planning off skips planner invocation” behavior while `Planner` now receives a prompt-surface dependency.
- `project-cornerstone/00-master-plan/DECISION_LOG.md`
  Purpose: record the architectural decision that prompt surfaces are capability-aware and composed from reusable blocks.
- `project-cornerstone/01-architecture/architecture_context.md`
  Purpose: document the shared prompt-surface layer between `Agent`, `Planner`, and `prompt_loader`.
- `project-cornerstone/05-llm-integration/llm-integration_context.md`
  Purpose: describe the new prompt composition boundary and its alignment with action-schema examples.
- `project-cornerstone/10-testing/testing_context.md`
  Purpose: document prompt-surface golden coverage and where prompt regressions now live.

## Chunk 1: Shared Builder Scaffold And Executor System Surface

### Task 1: Add failing golden tests for executor system prompts and implement the shared builder entrypoint

**Files:**
- Create: `tests/test_prompt_surface.py`
- Create: `tests/golden/prompts/executor_system_full.txt`
- Create: `tests/golden/prompts/executor_system_innovation_off.txt`
- Create: `tests/golden/prompts/executor_system_social_off.txt`
- Create: `simulation/prompt_surface.py`
- Modify: `prompts/agent/system.txt`
- Modify: `simulation/agent.py`
- Reference only: `simulation/prompt_loader.py`
- Reference only: `simulation/runtime_policy.py`

- [ ] **Step 1: Write the failing golden harness and executor-system tests**

Add a focused new test module `tests/test_prompt_surface.py` with:

```python
from pathlib import Path

from simulation.prompt_surface import PromptSurfaceBuilder
from simulation.runtime_policy import AgentRuntimeSettings, MemoryRuntimeSettings


GOLDEN_DIR = Path(__file__).parent / "golden" / "prompts"


def _builder(**caps: bool) -> PromptSurfaceBuilder:
    return PromptSurfaceBuilder(
        agent_settings=AgentRuntimeSettings(
            explicit_planning=caps.get("explicit_planning", True),
            innovation=caps.get("innovation", True),
            item_reflection=caps.get("item_reflection", True),
            social=caps.get("social", True),
            teach=caps.get("teach", True),
            reproduction=caps.get("reproduction", True),
        ),
        memory_settings=MemoryRuntimeSettings(
            semantic_memory=caps.get("semantic_memory", True)
        ),
    )


def _assert_matches_golden(name: str, text: str) -> None:
    assert text == (GOLDEN_DIR / name).read_text()


def test_executor_system_full_matches_golden():
    prompt = _builder().build_executor_system(
        name="Ada",
        actions=["move", "eat", "rest", "pickup", "drop_item", "innovate", "communicate", "give_item", "teach", "reflect_item_uses"],
        personality_description="You are curious but patient.",
        action_descriptions={},
    )
    _assert_matches_golden("executor_system_full.txt", prompt)


def test_executor_system_innovation_off_matches_golden():
    prompt = _builder(innovation=False).build_executor_system(
        name="Ada",
        actions=["move", "eat", "rest", "pickup", "drop_item", "communicate", "give_item", "teach", "reflect_item_uses"],
        personality_description="You are curious but patient.",
        action_descriptions={"cut_branches": "cut branches with a sharp tool"},
    )
    _assert_matches_golden("executor_system_innovation_off.txt", prompt)


def test_executor_system_social_off_matches_golden():
    prompt = _builder(social=False, teach=False).build_executor_system(
        name="Ada",
        actions=["move", "eat", "rest", "pickup", "drop_item", "innovate", "reflect_item_uses"],
        personality_description="You are curious but patient.",
        action_descriptions={},
    )
    _assert_matches_golden("executor_system_social_off.txt", prompt)
```

Notes:
- Keep this file builder-first. The new prompt composition unit should be testable without constructing a full `Agent`.
- Use stable small inputs so the goldens stay readable.

- [ ] **Step 2: Run the targeted prompt-surface tests to confirm failure**

Run:

```bash
uv run pytest tests/test_prompt_surface.py -k "executor_system" -q
```

Expected: FAIL with `ModuleNotFoundError` for `simulation.prompt_surface`, `AttributeError` for missing methods, or missing golden files.

- [ ] **Step 3: Implement the minimal `PromptSurfaceBuilder` scaffold and executor-system rendering**

Create `simulation/prompt_surface.py` with:

```python
from __future__ import annotations

import re

from simulation import prompt_loader
from simulation.runtime_policy import AgentRuntimeSettings, MemoryRuntimeSettings


class PromptSurfaceBuilder:
    def __init__(
        self,
        *,
        agent_settings: AgentRuntimeSettings,
        memory_settings: MemoryRuntimeSettings,
    ) -> None:
        self.agent_settings = agent_settings
        self.memory_settings = memory_settings

    def build_executor_system(
        self,
        *,
        name: str,
        actions: list[str],
        personality_description: str,
        action_descriptions: dict[str, str],
    ) -> str:
        return self._normalize(
            prompt_loader.render(
                "agent/system",
                name=name,
                actions=", ".join(actions),
                personality_description=personality_description,
                strategic_capability_reminders=self._strategic_capability_reminders(),
                builtin_action_examples=self._executor_builtin_action_examples(),
                reproduction_action_note=self._reproduction_action_note(actions),
                custom_actions_section=self._custom_actions_section(action_descriptions),
            )
        )

    def _normalize(self, text: str) -> str:
        lines = [line.rstrip() for line in text.splitlines()]
        normalized = "\n".join(lines).strip()
        return re.sub(r"\n{3,}", "\n\n", normalized)
```

Also add private helpers for:
- capability-aware strategic reminders
- capability-aware built-in action examples
- optional reproduction action note
- custom-actions section

Implementation rules:
- `innovation=False` removes the `innovate` example and innovation reminder lines
- `social=False` removes `communicate`, `give_item`, and `teach` examples and social reminder lines
- `teach=False` removes `teach` only
- `item_reflection=False` removes `reflect_item_uses`
- do not remove already-known custom actions when `innovation=False`

- [ ] **Step 4: Replace executor-system static prose in `prompts/agent/system.txt` with placeholders**

Refactor `prompts/agent/system.txt` so capability-sensitive regions are injected through:

```text
Strategic reminders:
$strategic_capability_reminders

GRID LEGEND:
  @=you  .=land  S=sand  ~=river  W=water
  F=fruit-tree  t=empty-tree  f=forest  M=mountain  C=cave  #=bounds

Action format - respond with a JSON object:
$builtin_action_examples
$reproduction_action_note
- For approved innovations: {"action": "<action_name>", "reason": "...", ...extra_params}
```

Keep the current prompt voice and all non-capability wording intact. Do not create variant templates.

- [ ] **Step 5: Wire `Agent._build_system_prompt()` through the new builder**

In `simulation/agent.py`:

```python
self.prompt_surface = PromptSurfaceBuilder(
    agent_settings=self.runtime_settings,
    memory_settings=self.memory_system.runtime_settings,
)
```

Then replace `_build_system_prompt()` with:

```python
def _build_system_prompt(self) -> str:
    return self.prompt_surface.build_executor_system(
        name=self.name,
        actions=self.actions,
        personality_description=self.personality.to_prompt(),
        action_descriptions=self.action_descriptions,
    )
```

Do not change action unlock logic in this task. The builder should consume `self.actions` exactly as the runtime already provides them.

- [ ] **Step 6: Author the three executor-system goldens**

Create these files with the exact normalized rendered output from the passing builder calls in Step 1:

- `tests/golden/prompts/executor_system_full.txt`
- `tests/golden/prompts/executor_system_innovation_off.txt`
- `tests/golden/prompts/executor_system_social_off.txt`

Golden-writing rules:
- keep the full rendered prompt, not excerpts
- do not hand-edit wording beyond what the builder already rendered
- verify `innovation_off` still shows `YOUR CUSTOM ACTIONS` when `action_descriptions` is non-empty
- verify `social_off` removes `communicate`, `give_item`, and `teach`

- [ ] **Step 7: Run executor-system regressions**

Run:

```bash
uv run pytest tests/test_prompt_surface.py -k "executor_system" -q
uv run pytest tests/test_agent_prompts.py -k "system_prompt" -q
```

Expected: PASS. The new goldens should pass, and the existing agent-level system-prompt tests should still pass after the integration change.

- [ ] **Step 8: Commit Chunk 1**

Run:

```bash
git add simulation/prompt_surface.py simulation/agent.py prompts/agent/system.txt tests/test_prompt_surface.py tests/golden/prompts/executor_system_full.txt tests/golden/prompts/executor_system_innovation_off.txt tests/golden/prompts/executor_system_social_off.txt tests/test_agent_prompts.py
git commit -m "feat: add capability-aware executor system prompt builder"
```

Expected: one commit containing the builder scaffold, executor system placeholders, and executor-system goldens.

## Chunk 2: Executor Decision Surface And Agent-Level Prompt Integration

### Task 2: Add failing decision-prompt goldens, implement capability-aware decision blocks, and route `Agent._build_decision_prompt()` through the builder

**Files:**
- Modify: `simulation/prompt_surface.py`
- Modify: `simulation/agent.py`
- Modify: `prompts/agent/decision.txt`
- Modify: `tests/test_prompt_surface.py`
- Create: `tests/golden/prompts/executor_decision_full.txt`
- Create: `tests/golden/prompts/executor_decision_planning_off.txt`
- Create: `tests/golden/prompts/executor_decision_social_off.txt`
- Create: `tests/golden/prompts/executor_decision_reproduction_off.txt`
- Modify: `tests/test_agent_prompts.py`
- Reference only: `simulation/memory.py`

- [ ] **Step 1: Extend `tests/test_prompt_surface.py` with failing decision goldens**

Add helper inputs and these new tests:

```python
def test_executor_decision_full_matches_golden():
    prompt = _builder().build_executor_decision(
        tick=7,
        time_info="Daylight.",
        current_tile_info="[Tile: land]",
        life=90,
        max_life=100,
        hunger=20,
        max_hunger=100,
        hunger_threshold=80,
        energy=70,
        max_energy=100,
        status_effects="",
        inventory_info="INVENTORY: fruit x1",
        ascii_grid=". . .",
        pickup_ready_resources="- fruit HERE (qty: 1)",
        nearby_resource_hints="- mushroom 1 tile EAST (qty: 1)",
        social_context={
            "nearby_agents": "NEARBY AGENTS:\n- Bruno 1 tile EAST",
            "incoming_messages": "INCOMING MESSAGES:\n- Bruno: fruit east",
            "relationships": "RELATIONSHIPS:\n- Bruno trust=0.60",
        },
        planning_context={
            "current_goal": "stabilize food",
            "active_subgoal": "move toward fruit",
            "plan_status": "status=active, confidence=0.80, horizon=short",
        },
        family_info="No known family ties.",
        memory_text="KNOWLEDGE (things I've learned):\n- [KNOW] Fruit reduces hunger.\n\nRECENT EVENTS:\n- [RECENT] I moved east.",
        reproduction_hint='To reproduce: {"action": "reproduce", "target": "<name>", "reason": "..."}',
    )
    _assert_matches_golden("executor_decision_full.txt", prompt)


def test_executor_decision_planning_off_matches_golden():
    prompt = _builder(explicit_planning=False).build_executor_decision(...)
    _assert_matches_golden("executor_decision_planning_off.txt", prompt)


def test_executor_decision_social_off_matches_golden():
    prompt = _builder(social=False, teach=False).build_executor_decision(...)
    _assert_matches_golden("executor_decision_social_off.txt", prompt)


def test_executor_decision_reproduction_off_matches_golden():
    prompt = _builder(reproduction=False).build_executor_decision(...)
    _assert_matches_golden("executor_decision_reproduction_off.txt", prompt)
```

Use the same deterministic fixture payload across the four tests and change only the capability flags.

- [ ] **Step 2: Add focused agent-level prompt regressions**

In `tests/test_agent_prompts.py`, add direct assertions for the key hard rules that are easier to read than golden diffs:

```python
def test_decision_prompt_hides_planning_sections_when_explicit_planning_disabled():
    ...
    assert "CURRENT GOAL" not in prompt
    assert "ACTIVE SUBGOAL" not in prompt
    assert "PLAN STATUS" not in prompt


def test_decision_prompt_hides_social_sections_when_social_disabled():
    ...
    assert "NEARBY AGENTS" not in prompt
    assert "INCOMING MESSAGES" not in prompt
    assert "RELATIONSHIPS" not in prompt


def test_decision_prompt_hides_reproduction_sections_when_reproduction_disabled():
    ...
    assert "FAMILY:" not in prompt
    assert '"action": "reproduce"' not in prompt


def test_decision_prompt_semantic_memory_off_keeps_recent_events():
    ...
    assert "KNOWLEDGE" not in prompt
    assert "RECENT EVENTS" in prompt


def test_decision_prompt_item_reflection_off_removes_reflection_hint():
    ...
    assert "reflect_item_uses" not in prompt
```

Use `AgentRuntimeSettings` and `MemoryRuntimeSettings` instead of monkeypatching globals.

- [ ] **Step 3: Run the targeted tests to confirm failure**

Run:

```bash
uv run pytest tests/test_prompt_surface.py -k "executor_decision" -q
uv run pytest tests/test_agent_prompts.py -k "decision_prompt" -q
```

Expected: FAIL because `build_executor_decision()` does not exist yet, new placeholders are missing, or the decision prompt still contains forbidden sections.

- [ ] **Step 4: Implement `build_executor_decision()` and its reusable blocks in `simulation/prompt_surface.py`**

Add a public method with this shape:

```python
def build_executor_decision(
    self,
    *,
    tick: int,
    time_info: str,
    current_tile_info: str,
    life: int,
    max_life: int,
    hunger: int,
    max_hunger: int,
    hunger_threshold: int,
    energy: int,
    max_energy: int,
    status_effects: str,
    inventory_info: str,
    ascii_grid: str,
    pickup_ready_resources: str,
    nearby_resource_hints: str,
    social_context: dict[str, str],
    planning_context: dict[str, str],
    family_info: str,
    memory_text: str,
    reproduction_hint: str,
) -> str:
    ...
```

Build the placeholders from small helpers:
- `_social_context_block(...)`
- `_planning_status_block(...)`
- `_family_block(...)`
- `_reproduction_hint_block(...)`
- `_decision_reflection_questions()`

Hard rules to enforce in code:
- `explicit_planning=False` removes the full planning block
- `social=False` removes nearby agents, messages, and relationships
- `teach=False` removes teaching references from reflection questions but keeps other social wording when `social=True`
- `item_reflection=False` removes the item-reflection reflection line
- `reproduction=False` removes family and reproduction hint
- `innovation=False` removes the “blocked opportunity suggests innovation” reflection line

- [ ] **Step 5: Refactor `prompts/agent/decision.txt` to use optional placeholders**

Replace the static sections with placeholder-driven layout like:

```text
$social_context_block
$planning_status_block
$family_block

YOUR MEMORY:
$memory_text

$reproduction_hint_block

Before choosing, briefly reflect:
$decision_reflection_questions
```

Keep the rest of the prompt structure unchanged. The builder, not the template, owns which blocks are empty.

- [ ] **Step 6: Route `Agent._build_decision_prompt()` through the builder**

In `simulation/agent.py`, keep the existing data gathering helpers for now, but replace direct `prompt_loader.render("agent/decision", ...)` with:

```python
return self.prompt_surface.build_executor_decision(
    tick=tick,
    time_info=time_description,
    current_tile_info=current_tile_info,
    life=self.life,
    max_life=AGENT_MAX_LIFE,
    hunger=self.hunger,
    max_hunger=AGENT_MAX_HUNGER,
    hunger_threshold=HUNGER_DAMAGE_THRESHOLD,
    energy=self.energy,
    max_energy=AGENT_MAX_ENERGY,
    status_effects=status_effects,
    inventory_info=inventory_info,
    ascii_grid=ascii_grid,
    pickup_ready_resources=pickup_ready_resources,
    nearby_resource_hints=nearby_resource_hints,
    social_context={
        "nearby_agents": nearby_agents_text,
        "incoming_messages": incoming_messages_text,
        "relationships": relationships_text,
    },
    planning_context={
        "current_goal": current_goal,
        "active_subgoal": active_subgoal,
        "plan_status": plan_status,
    },
    family_info=family_info,
    memory_text=memory_text,
    reproduction_hint=reproduction_hint,
)
```

Do not move planner observation text into the builder yet; that belongs to the next chunk.

- [ ] **Step 7: Author the executor-decision goldens**

Create:

- `tests/golden/prompts/executor_decision_full.txt`
- `tests/golden/prompts/executor_decision_planning_off.txt`
- `tests/golden/prompts/executor_decision_social_off.txt`
- `tests/golden/prompts/executor_decision_reproduction_off.txt`

Golden expectations:
- `planning_off` removes `CURRENT GOAL`, `ACTIVE SUBGOAL`, `PLAN STATUS`
- `social_off` removes `NEARBY AGENTS`, `INCOMING MESSAGES`, `RELATIONSHIPS`
- `reproduction_off` removes `FAMILY` and the reproduction hint
- `full` still includes both `KNOWLEDGE` and `RECENT EVENTS`

- [ ] **Step 8: Run executor decision regressions**

Run:

```bash
uv run pytest tests/test_prompt_surface.py -k "executor_decision" -q
uv run pytest tests/test_agent_prompts.py -q
```

Expected: PASS. Existing prompt tests and the new capability-aware prompt tests should pass together.

- [ ] **Step 9: Commit Chunk 2**

Run:

```bash
git add simulation/prompt_surface.py simulation/agent.py prompts/agent/decision.txt tests/test_prompt_surface.py tests/golden/prompts/executor_decision_full.txt tests/golden/prompts/executor_decision_planning_off.txt tests/golden/prompts/executor_decision_social_off.txt tests/golden/prompts/executor_decision_reproduction_off.txt tests/test_agent_prompts.py
git commit -m "feat: make executor decision prompt capability-aware"
```

Expected: one commit covering executor decision composition and regressions.

## Chunk 3: Planner Surface, Observation Text, And Planner Wiring

### Task 3: Add failing planner goldens, implement planner prompt composition, and share the builder between `Agent` and `Planner`

**Files:**
- Modify: `simulation/prompt_surface.py`
- Modify: `simulation/agent.py`
- Modify: `simulation/planner.py`
- Modify: `prompts/agent/planner_system.txt`
- Modify: `prompts/agent/planner.txt`
- Modify: `tests/test_prompt_surface.py`
- Create: `tests/golden/prompts/planner_system_full.txt`
- Create: `tests/golden/prompts/planner_system_innovation_off.txt`
- Create: `tests/golden/prompts/planner_system_reproduction_off.txt`
- Create: `tests/golden/prompts/planner_prompt_full.txt`
- Create: `tests/golden/prompts/planner_prompt_social_off.txt`
- Create: `tests/golden/prompts/planner_prompt_innovation_off.txt`
- Modify: `tests/test_planner.py`
- Modify: `tests/test_agent_planning.py`

- [ ] **Step 1: Add failing planner golden tests**

Extend `tests/test_prompt_surface.py` with:

```python
def test_planner_system_full_matches_golden():
    prompt = _builder().build_planner_system(agent_name="Ada")
    _assert_matches_golden("planner_system_full.txt", prompt)


def test_planner_system_innovation_off_matches_golden():
    prompt = _builder(innovation=False).build_planner_system(agent_name="Ada")
    _assert_matches_golden("planner_system_innovation_off.txt", prompt)


def test_planner_prompt_social_off_matches_golden():
    builder = _builder(social=False, teach=False)
    observation = builder.build_planner_observation_text(
        life=90,
        hunger=20,
        energy=70,
        inventory_info="INVENTORY: fruit x1",
        current_tile_resources="fruit",
        nearby_resources="mushroom",
        nearby_agent_names=["Bruno"],
        custom_actions=["cut_branches"],
        time_description="Daylight.",
    )
    prompt = builder.build_planner_prompt(
        tick=5,
        observation_text=observation,
        planner_context=["fruit helps"],
        current_plan="stabilize food",
    )
    _assert_matches_golden("planner_prompt_social_off.txt", prompt)
```

Also add full and innovation-off planner prompt goldens with the same fixture inputs.

- [ ] **Step 2: Add focused planner regressions to `tests/test_planner.py`**

Refactor direct `Planner` construction in `tests/test_planner.py` to pass a builder helper:

```python
def _builder(**caps):
    return PromptSurfaceBuilder(
        agent_settings=AgentRuntimeSettings(
            explicit_planning=caps.get("explicit_planning", True),
            innovation=caps.get("innovation", True),
            item_reflection=caps.get("item_reflection", True),
            social=caps.get("social", True),
            teach=caps.get("teach", True),
            reproduction=caps.get("reproduction", True),
        ),
        memory_settings=MemoryRuntimeSettings(semantic_memory=True),
    )
```

Add direct string-assertion tests that are easier to debug than goldens:

```python
def test_planner_prompt_omits_innovation_question_when_innovation_disabled():
    ...
    assert "suggests innovation" not in prompt


def test_planner_prompt_omits_social_progress_question_when_social_disabled():
    ...
    assert "relationship" not in prompt
    assert "cooperation" not in prompt


def test_planner_system_omits_reproduction_guidance_when_reproduction_disabled():
    ...
    assert "future reproduction" not in prompt
```

Keep the existing planner-behavior tests; only update construction as needed.

- [ ] **Step 3: Run planner-focused tests to confirm failure**

Run:

```bash
uv run pytest tests/test_prompt_surface.py -k "planner" -q
uv run pytest tests/test_planner.py -q
```

Expected: FAIL because planner builder methods do not exist yet and planner templates are still static.

- [ ] **Step 4: Implement planner-facing builder methods and capability-aware observation text**

Add to `simulation/prompt_surface.py`:

```python
def build_planner_system(self, *, agent_name: str) -> str:
    return self._normalize(
        prompt_loader.render(
            "agent/planner_system",
            agent_name=agent_name,
            planner_capability_guidance=self._planner_capability_guidance(),
        )
    )


def build_planner_prompt(
    self,
    *,
    tick: int,
    observation_text: str,
    planner_context: list[str],
    current_plan: str,
) -> str:
    return self._normalize(
        prompt_loader.render(
            "agent/planner",
            tick=tick,
            observation_text=observation_text,
            current_plan_block=self._current_plan_block(current_plan),
            planner_context="\n".join(f"- {entry}" for entry in planner_context) or "- none",
            planner_reflection_questions=self._planner_reflection_questions(),
        )
    )


def build_planner_observation_text(...):
    ...
```

Observation-text rules:
- omit nearby-agent line completely when `social=False`
- keep custom-actions line if custom actions exist, even when `innovation=False`
- keep time description if provided
- do not mention family or reproduction in observation text unless a later requirement explicitly adds it

- [ ] **Step 5: Refactor planner templates to use placeholders**

In `prompts/agent/planner_system.txt`, replace capability-sensitive rule bullets with:

```text
Rules:
$planner_capability_guidance
```

In `prompts/agent/planner.txt`, replace the static current-plan and reflection block with:

```text
$current_plan_block

RELEVANT MEMORY:
$planner_context

PLANNING QUESTIONS:
$planner_reflection_questions
```

Keep the existing planner prompt voice. The change should be structural, not a rewrite.

- [ ] **Step 6: Share the builder instance with `Planner`**

Update `simulation/planner.py`:

```python
class Planner:
    def __init__(self, llm, prompt_surface: PromptSurfaceBuilder):
        self.llm = llm
        self.prompt_surface = prompt_surface
```

Replace direct `prompt_loader.render()` calls with builder calls.

Update `simulation/agent.py`:

```python
self.planner = Planner(llm, prompt_surface=self.prompt_surface) if llm else None
```

Also replace `_build_observation_text()` usage inside `decide_action()` with `self.prompt_surface.build_planner_observation_text(...)`.

- [ ] **Step 7: Author the planner goldens**

Create:

- `tests/golden/prompts/planner_system_full.txt`
- `tests/golden/prompts/planner_system_innovation_off.txt`
- `tests/golden/prompts/planner_system_reproduction_off.txt`
- `tests/golden/prompts/planner_prompt_full.txt`
- `tests/golden/prompts/planner_prompt_social_off.txt`
- `tests/golden/prompts/planner_prompt_innovation_off.txt`

Golden expectations:
- innovation-off planner prompts remove innovation guidance and questions
- social-off planner prompts remove nearby-agent observation lines and social-progress questions
- reproduction-off planner system prompt removes reproduction guidance

- [ ] **Step 8: Run planner and planning regressions**

Run:

```bash
uv run pytest tests/test_prompt_surface.py -k "planner" -q
uv run pytest tests/test_planner.py tests/test_agent_planning.py -q
```

Expected: PASS. Direct planner tests should pass, and `test_explicit_planning_disabled_skips_planner_invocation` should still prove the runtime skips planner calls entirely.

- [ ] **Step 9: Commit Chunk 3**

Run:

```bash
git add simulation/prompt_surface.py simulation/agent.py simulation/planner.py prompts/agent/planner_system.txt prompts/agent/planner.txt tests/test_prompt_surface.py tests/golden/prompts/planner_system_full.txt tests/golden/prompts/planner_system_innovation_off.txt tests/golden/prompts/planner_system_reproduction_off.txt tests/golden/prompts/planner_prompt_full.txt tests/golden/prompts/planner_prompt_social_off.txt tests/golden/prompts/planner_prompt_innovation_off.txt tests/test_planner.py tests/test_agent_planning.py
git commit -m "feat: make planner prompt surface capability-aware"
```

Expected: one commit covering planner composition, observation-text gating, and planner goldens.

## Chunk 4: Cornerstone Updates And Final Verification

### Task 4: Document the new prompt-surface architecture, run the required regressions, and close the feature cleanly

**Files:**
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Modify: `project-cornerstone/01-architecture/architecture_context.md`
- Modify: `project-cornerstone/05-llm-integration/llm-integration_context.md`
- Modify: `project-cornerstone/10-testing/testing_context.md`
- Reference only: `docs/superpowers/specs/2026-03-27-capability-aware-prompt-surface-design.md`

- [ ] **Step 1: Add a decision-log entry for the capability-aware prompt surface**

Append the next decision entry in `project-cornerstone/00-master-plan/DECISION_LOG.md` (currently expected to be `DEC-046` if no other local change lands first).

The entry should state:
- context: runtime capability gates existed but prompts drifted
- decision: add `PromptSurfaceBuilder` with optional blocks/placeholders and shared Agent/Planner usage
- rejected alternatives: full template duplication, pure-Python prompt rewrite
- consequences: prompt surface now changes with capabilities; golden tests protect it

- [ ] **Step 2: Update architecture and LLM/testing context files**

Make these focused updates:

- `project-cornerstone/01-architecture/architecture_context.md`
  Add that `Agent` owns a shared `PromptSurfaceBuilder`, and `Planner` renders through it rather than directly through `prompt_loader`.
- `project-cornerstone/05-llm-integration/llm-integration_context.md`
  Add that file-based agent prompts are still the source of wording, but capability-aware composition now happens in `simulation/prompt_surface.py`.
- `project-cornerstone/10-testing/testing_context.md`
  Add a short section saying prompt regressions now live in `tests/test_prompt_surface.py` with full-text goldens in `tests/golden/prompts/`.

Keep the doc edits narrow and factual.

- [ ] **Step 3: Run the prompt-focused regression suite**

Run:

```bash
uv run pytest tests/test_prompt_surface.py tests/test_agent_prompts.py tests/test_planner.py tests/test_agent_planning.py tests/test_runtime_profile_capabilities.py -q
```

Expected: PASS. This proves prompt surfaces and the existing runtime capability gates stay aligned.

- [ ] **Step 4: Run the required fast suite**

Run:

```bash
uv run pytest -m "not slow"
```

Expected: PASS. This is required by `AGENTS.md` before claiming the change is complete.

- [ ] **Step 5: Run the no-LLM smoke command**

Run:

```bash
uv run main.py --no-llm --ticks 5 --agents 1
```

Expected: simulation completes successfully without prompt-related crashes. The actual agent choices may vary, but the run should exit cleanly.

- [ ] **Step 6: Commit docs and final verification result**

Run:

```bash
git add project-cornerstone/00-master-plan/DECISION_LOG.md project-cornerstone/01-architecture/architecture_context.md project-cornerstone/05-llm-integration/llm-integration_context.md project-cornerstone/10-testing/testing_context.md
git commit -m "docs: record capability-aware prompt surface"
```

If the implementation chunk and docs chunk are intentionally being squashed later, keep this commit separate until the review is complete.

## Execution Notes

- Keep `simulation/prompt_loader.py` as a dumb renderer. Do not move capability logic into it.
- Preserve current prompt voice. This plan is about structural composition and fidelity, not prompt rewriting.
- Favor builder-private helpers over giant methods. `simulation/prompt_surface.py` should be easy to reason about in isolation.
- When goldens and targeted assertions overlap, keep both: goldens catch formatting drift; string assertions communicate intent.
- Do not remove existing backend capability tests. Prompt-surface tests are additive to runtime-policy coverage.
- If a test becomes brittle because of harmless whitespace, fix the builder normalization once rather than weakening the golden expectations.
